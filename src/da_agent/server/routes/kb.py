"""KB CRUD: upload, list, get meta, get manifest, delete.

Upload is multipart -- the request streams the file to disk in an executor
thread, then schedules the preprocessing pipeline as a fire-and-forget
asyncio task and returns 202 immediately. Status transitions are surfaced
on subsequent GETs (FE polls; SSE for KB status is open question §14).
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from ...kb import read_manifest, run_pipeline
from ..schemas import (
    KbFileListResponse,
    KbFileResponse,
    KbVersionListResponse,
    KbVersionResponse,
)
from ..state import AppState

router = APIRouter(prefix="/kb", tags=["kb"])

# Defensive limits. Spec mentions `attachment_max_bytes` for short-term
# attachments (§5.3); KB uploads are persistent and can be larger, but
# rejecting absurd sizes early protects the executor pool.
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB
_FILENAME_CLEAN = re.compile(r"[^A-Za-z0-9._-]+")
_ALLOWED_EXTS = {".xlsx", ".xlsm"}


def get_state(request: Request) -> AppState:
    return request.app.state.app_state


def _sanitize_filename(raw: str | None) -> str:
    """Strip path components and collapse anything weird. Keeps `.xlsx`."""
    name = (raw or "uploaded.xlsx").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    cleaned = _FILENAME_CLEAN.sub("_", name).strip("._-") or "uploaded.xlsx"
    return cleaned[:200]  # keep filenames short for filesystem sanity


def _meta_to_response(meta) -> KbFileResponse:
    return KbFileResponse(
        id=meta.id,
        filename=meta.filename,
        size_bytes=meta.size_bytes,
        status=meta.status,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
        error=meta.error,
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post(
    "/files",
    response_model=KbFileResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_kb_file(
    file: UploadFile, state: AppState = Depends(get_state)
) -> KbFileResponse:
    filename = _sanitize_filename(file.filename)
    if Path(filename).suffix.lower() not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=400, detail="only .xlsx / .xlsm files are accepted"
        )

    # Stream to a tmp path while counting bytes; reject if it exceeds the cap.
    kb_root = state.settings.kb_dir
    kb_root.mkdir(parents=True, exist_ok=True)
    tmp_dir = kb_root / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"upload_{id(file):x}.bin"

    total = 0
    try:
        with tmp_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > _MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="file too large")
                out.write(chunk)
    except BaseException:
        # Always clean up the tmp file -- HTTP errors, disk-full OSError,
        # client-disconnect CancelledError, anything.
        tmp_path.unlink(missing_ok=True)
        raise

    if total == 0:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="file is empty")

    # Register first so we own a kb_id, then move the bytes into place. If
    # the move fails (disk full, permissions), roll back the registry row
    # so the user does not see a permanently-FAILED orphan.
    meta = await state.kb.create(filename=filename, size_bytes=total)
    kb_dir = kb_root / meta.id
    kb_dir.mkdir(parents=True, exist_ok=True)
    raw_path = kb_dir / "raw.xlsx"
    try:
        await asyncio.to_thread(shutil.move, str(tmp_path), str(raw_path))
    except BaseException:
        await state.kb.delete(meta.id)
        await asyncio.to_thread(shutil.rmtree, str(kb_dir), True)
        tmp_path.unlink(missing_ok=True)
        raise

    # Fire-and-forget pipeline. Tracked so shutdown can cancel cleanly.
    task = asyncio.create_task(
        run_pipeline(registry=state.kb, kb_root=kb_root, kb_id=meta.id)
    )
    state.track_kb_task(task)

    return _meta_to_response(meta)


@router.get("/files", response_model=KbFileListResponse)
async def list_kb_files(
    state: AppState = Depends(get_state),
) -> KbFileListResponse:
    metas = await state.kb.list()
    return KbFileListResponse(files=[_meta_to_response(m) for m in metas])


@router.get("/files/{kb_id}", response_model=KbFileResponse)
async def get_kb_file(
    kb_id: str, state: AppState = Depends(get_state)
) -> KbFileResponse:
    meta = await state.kb.get(kb_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="kb file not found")
    return _meta_to_response(meta)


@router.get("/files/{kb_id}/manifest")
async def get_kb_manifest(
    kb_id: str, state: AppState = Depends(get_state)
) -> JSONResponse:
    meta = await state.kb.get(kb_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="kb file not found")
    if meta.status != "READY":
        raise HTTPException(
            status_code=409,
            detail=f"manifest unavailable; status={meta.status}",
        )
    manifest_path = state.settings.kb_dir / kb_id / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest file missing on disk")
    payload = await asyncio.to_thread(read_manifest, manifest_path)
    return JSONResponse(content=payload)


@router.delete("/files/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb_file(kb_id: str, state: AppState = Depends(get_state)) -> None:
    meta = await state.kb.get(kb_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="kb file not found")
    await state.kb.delete(kb_id)
    kb_dir = state.settings.kb_dir / kb_id
    if kb_dir.exists():
        await asyncio.to_thread(shutil.rmtree, str(kb_dir), True)


# --------------------------------------------------------------------------- #
# KB version endpoints (spec §7, §8.2, §11) — READ-ONLY.
# Spec §8.2 — physical 2-version cap: only `v_curr` (latest) and optionally
# `v_prev` (one-step rollback) live on disk. Older revisions are deleted on
# rotation. The observer + permission resolver mint these files; we only
# scan and serve here.
# --------------------------------------------------------------------------- #
_VERSION_FILE_RE = re.compile(r"^v_(curr|prev)\.(xlsx|xlsm|xls|csv|tsv)$")
_VERSION_SLOT_RE = re.compile(r"^v_(curr|prev)$")
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _scan_versions(versions_dir: Path) -> list[KbVersionResponse]:
    """Scan kb/<id>/versions/ for v_curr.<ext> / v_prev.<ext> files.

    For each, read companion <slot>.meta.json sidecar if present (spec §8.2).
    Slots are ordered: v_curr first, v_prev second.
    """
    out: list[KbVersionResponse] = []
    if not versions_dir.exists():
        return out
    by_slot: dict[str, Path] = {}
    for entry in sorted(versions_dir.iterdir()):
        m = _VERSION_FILE_RE.match(entry.name)
        if m is None or not entry.is_file():
            continue
        by_slot[f"v_{m.group(1)}"] = entry
    for slot in ("v_curr", "v_prev"):
        entry = by_slot.get(slot)
        if entry is None:
            continue
        sidecar = versions_dir / f"{slot}.meta.json"
        meta: dict[str, Any] = {}
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                meta = {}
        parent_default = "v_prev" if slot == "v_curr" else "raw"
        out.append(
            KbVersionResponse(
                version=slot,
                parent_version=meta.get("parent_version", parent_default),
                operation=meta.get("operation"),
                sheet_affected=meta.get("sheet_affected"),
                source_session_id=meta.get("source_session_id"),
                created_at=float(meta.get("created_at", entry.stat().st_mtime)),
                size_bytes=int(meta.get("size_bytes", entry.stat().st_size)),
            )
        )
    return out


def _find_version_file(versions_dir: Path, slot: str) -> Path | None:
    """Locate `versions_dir/<slot>.<ext>` for any allowed extension."""
    if not versions_dir.exists():
        return None
    for entry in versions_dir.iterdir():
        m = _VERSION_FILE_RE.match(entry.name)
        if m is None:
            continue
        if f"v_{m.group(1)}" == slot:
            return entry
    return None


@router.get("/files/{kb_id}/versions", response_model=KbVersionListResponse)
async def list_kb_versions(
    kb_id: str, state: AppState = Depends(get_state)
) -> KbVersionListResponse:
    meta = await state.kb.get(kb_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="kb file not found")
    versions_dir = state.settings.kb_dir / kb_id / "versions"
    versions = await asyncio.to_thread(_scan_versions, versions_dir)
    return KbVersionListResponse(versions=versions)


@router.get("/files/{kb_id}/versions/{version}/download")
async def download_kb_version(
    kb_id: str, version: str, state: AppState = Depends(get_state)
) -> FileResponse:
    meta = await state.kb.get(kb_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="kb file not found")
    if not _VERSION_SLOT_RE.match(version):
        raise HTTPException(
            status_code=400,
            detail="invalid version slot; expected v_curr or v_prev",
        )
    versions_dir = state.settings.kb_dir / kb_id / "versions"
    file_path = _find_version_file(versions_dir, version)
    if file_path is None:
        raise HTTPException(status_code=404, detail="version not found on disk")
    return FileResponse(
        path=file_path,
        media_type=_XLSX_MIME,
        filename=f"{kb_id}_{version}{file_path.suffix}",
    )


# --- Google Sheets import stub (spec §11, §14 open question) --------- #
@router.post("/files/import-sheet", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def import_sheet_stub() -> JSONResponse:
    """Spec §14 open question — OAuth flow not yet defined.

    Returning 501 here lets the FE see a deliberate `not implemented` rather
    than a 404 for an endpoint that doesn't exist at all.
    """
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error": "Google Sheets import not implemented",
            "spec_reference": "technical-spec.md §14 open question (OAuth)",
        },
    )
