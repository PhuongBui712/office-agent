"""Pure-unit tests for OutputsObserver (spec §8.2)."""

from __future__ import annotations

import pytest

from da_agent.outputs import OutputDetection, OutputsObserver


@pytest.fixture
def dirs(tmp_path):
    outputs_dir = tmp_path / "outputs"
    kb_dir = tmp_path / "kb"
    outputs_dir.mkdir()
    kb_dir.mkdir()
    return outputs_dir, kb_dir


@pytest.fixture
def make_observer(dirs):
    outputs_dir, kb_dir = dirs

    def _make():
        events: list[OutputDetection] = []
        obs = OutputsObserver(outputs_dir, kb_dir, on_detect=events.append)
        return obs, events

    return _make


def test_write_under_outputs_dir_with_out_prefix_fires(dirs, make_observer):
    outputs_dir, _ = dirs
    obs, events = make_observer()

    file_path = outputs_dir / "out_abc" / "report.xlsx"
    obs.observe_tool_use(
        "u1", "Write", {"file_path": str(file_path)}
    )
    obs.observe_tool_result("u1", "ok", False)

    assert len(events) == 1
    det = events[0]
    assert det.kind == "standalone"
    assert det.output_id == "out_abc"
    assert det.filename == "report.xlsx"


def test_tool_result_with_is_error_does_not_fire(dirs, make_observer):
    outputs_dir, _ = dirs
    obs, events = make_observer()

    obs.observe_tool_use(
        "u1", "Write", {"file_path": str(outputs_dir / "out_abc" / "x.xlsx")}
    )
    obs.observe_tool_result("u1", "permission denied", True)

    assert events == []


def test_bash_redirect_outside_known_roots_does_not_fire(dirs, make_observer):
    obs, events = make_observer()

    obs.observe_tool_use("u1", "Bash", {"command": "echo hi > /tmp/x.txt"})
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_bash_output_flag_under_kb_versions_fires_kb_version(dirs, make_observer):
    _, kb_dir = dirs
    obs, events = make_observer()

    target = kb_dir / "kb_xyz" / "versions" / "v3.xlsx"
    obs.observe_tool_use(
        "u1",
        "Bash",
        {"command": f"python script.py --output {target}"},
    )
    obs.observe_tool_result("u1", "", False)

    assert len(events) == 1
    det = events[0]
    assert det.kind == "kb_version"
    assert det.kb_id == "kb_xyz"
    assert det.version == "v3"


def test_write_under_outputs_dir_without_out_prefix_does_not_fire(
    dirs, make_observer
):
    outputs_dir, _ = dirs
    obs, events = make_observer()

    file_path = outputs_dir / "some_random_dir" / "file.xlsx"
    obs.observe_tool_use("u1", "Write", {"file_path": str(file_path)})
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_duplicate_tool_result_fires_only_once(dirs, make_observer):
    outputs_dir, _ = dirs
    obs, events = make_observer()

    file_path = outputs_dir / "out_abc" / "report.xlsx"
    obs.observe_tool_use("u1", "Write", {"file_path": str(file_path)})
    obs.observe_tool_result("u1", "", False)
    obs.observe_tool_result("u1", "", False)  # second time -> no-op

    assert len(events) == 1


def test_invalid_kb_version_filename_does_not_fire(dirs, make_observer):
    _, kb_dir = dirs
    obs, events = make_observer()

    target = kb_dir / "kb_xyz" / "versions" / "v0.5.xlsx"
    obs.observe_tool_use("u1", "Write", {"file_path": str(target)})
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_reset_clears_pending_state(dirs, make_observer):
    outputs_dir, _ = dirs
    obs, events = make_observer()

    obs.observe_tool_use(
        "u1", "Write", {"file_path": str(outputs_dir / "out_abc" / "x.xlsx")}
    )
    obs.reset()
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_non_write_non_bash_tool_is_ignored(dirs, make_observer):
    outputs_dir, _ = dirs
    obs, events = make_observer()

    obs.observe_tool_use(
        "u1",
        "Read",
        {"file_path": str(outputs_dir / "out_abc" / "x.xlsx")},
    )
    obs.observe_tool_result("u1", "ok", False)

    assert events == []
