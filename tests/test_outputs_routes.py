"""HTTP integration tests for /outputs endpoints (spec §8.2, §11).

No SDK interaction needed — these tests exercise the standalone outputs
registry + routes only. Mirrors the fixture pattern from
test_attachments_routes.py / test_kb_versions_routes.py.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from da_agent.config import Settings
from da_agent.server.app import create_app


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_AGENT_HOME", str(tmp_path))
    s = Settings()
    s.data_root = tmp_path
    s.ensure_dirs()
    return s


@pytest_asyncio.fixture
async def app(settings):
    a = create_app(settings)
    async with a.router.lifespan_context(a):
        yield a


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _register_output(
    app, *, session_id: str | None = None, content: bytes = b"PK fake xlsx"
):
    """Drop a file into outputs_dir/_tmp/, then register it via the registry.

    Phase C 2026-05-31: `session_id` is required by the registry layout
    (`outputs/<session_id>/<output_id>/<filename>`). We default to
    `sess_default` when the caller doesn't care which session owns the row.
    `source_session_id` is passed through unchanged so existing assertions
    on filterable provenance continue to work.
    """
    state = app.state.app_state
    tmp_dir = state.settings.outputs_dir / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_dir / f"src_{id(content):x}.xlsx"
    src.write_bytes(content)
    layout_sid = session_id or "sess_default"
    meta = await state.outputs.register_standalone(
        session_id=layout_sid,
        src_path=src,
        title="My report",
        filename="report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        source_session_id=session_id,
    )
    return meta


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
async def test_list_outputs_empty(client):
    r = await client.get("/outputs")
    assert r.status_code == 200
    assert r.json() == {"outputs": []}


async def test_list_outputs_returns_registered_entry(client, app):
    meta = await _register_output(app)
    r = await client.get("/outputs")
    assert r.status_code == 200
    items = r.json()["outputs"]
    assert len(items) == 1
    assert items[0]["output_id"] == meta.id
    assert items[0]["kind"] == "standalone"
    assert items[0]["title"] == "My report"
    assert items[0]["filename"] == "report.xlsx"


async def test_list_outputs_filters_by_session_id(client, app):
    a = await _register_output(app, session_id="sess_a")
    b = await _register_output(app, session_id="sess_b")

    r_all = await client.get("/outputs")
    assert {o["output_id"] for o in r_all.json()["outputs"]} == {a.id, b.id}

    r_a = await client.get("/outputs", params={"session_id": "sess_a"})
    ids_a = [o["output_id"] for o in r_a.json()["outputs"]]
    assert ids_a == [a.id]

    r_b = await client.get("/outputs", params={"session_id": "sess_b"})
    ids_b = [o["output_id"] for o in r_b.json()["outputs"]]
    assert ids_b == [b.id]


async def test_get_output_meta_returns_meta(client, app):
    meta = await _register_output(app, session_id="sess_x")
    r = await client.get(f"/outputs/{meta.id}/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["output_id"] == meta.id
    assert body["source_session_id"] == "sess_x"
    assert body["mime"].endswith("spreadsheetml.sheet")


async def test_download_output_returns_file_bytes(client, app):
    payload = b"PK\x03\x04 fake xlsx body"
    meta = await _register_output(app, content=payload)

    r = await client.get(f"/outputs/{meta.id}")
    assert r.status_code == 200
    assert r.content == payload
    # FileResponse uses meta.mime for content-type.
    assert "spreadsheetml" in r.headers["content-type"]


async def test_delete_output_removes_entry_and_dir(client, app):
    meta = await _register_output(app)
    # Phase C 2026-05-31: layout is `outputs/<session_id>/<output_id>/`.
    # `_register_output` defaults `session_id` to "sess_default" when the
    # caller doesn't pass one, and that's the layout key the registry uses.
    settings = app.state.app_state.settings
    out_dir = settings.outputs_dir / "sess_default" / meta.id
    assert out_dir.exists()

    r = await client.delete(f"/outputs/{meta.id}")
    assert r.status_code == 204

    # Subsequent fetches 404.
    miss = await client.get(f"/outputs/{meta.id}/meta")
    assert miss.status_code == 404

    # On-disk dir is gone.
    assert not out_dir.exists()


async def test_meta_unknown_id_returns_404(client):
    r = await client.get("/outputs/out_doesnotexist/meta")
    assert r.status_code == 404


async def test_download_unknown_id_returns_404(client):
    r = await client.get("/outputs/out_doesnotexist")
    assert r.status_code == 404


async def test_delete_unknown_id_returns_404(client):
    r = await client.delete("/outputs/out_doesnotexist")
    assert r.status_code == 404
