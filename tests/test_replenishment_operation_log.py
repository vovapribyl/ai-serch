"""Operational evidence is private, bounded and independent of model diagnostics."""

import json
import os
from types import SimpleNamespace

import pytest

from product_search.infrastructure.replenishment_operation_log import OperationLog


def rows(log):
    return [
        json.loads(line)
        for path in log.root.glob("events*.jsonl")
        for line in path.read_text().splitlines()
    ]


def test_wrapper_preserves_calls_and_hides_private_values(tmp_path):
    tmp_path.chmod(0o700)
    log = OperationLog(tmp_path)
    result = object()
    seen = []
    attempt = SimpleNamespace(
        photo_ref="private-photo",
        attempt_ref="private-attempt",
        revision_ref="private-revision",
        stage_key="localization",
        model_key="",
    )
    fn = log.wrap("checkpoint", lambda a, b, c: seen.append((a, b, c)) or result)
    assert fn(attempt, "private-vector", "private-owner") is result
    assert seen == [(attempt, "private-vector", "private-owner")]
    log.close()
    records = rows(log)
    assert [(r["event"], r["phase"]) for r in records] == [
        ("checkpoint", "before"),
        ("checkpoint", "after"),
        ("host", "closed"),
    ]
    assert records[0]["photo_ref"] == records[1]["photo_ref"]
    assert records[0]["photo_ref"] != attempt.photo_ref
    assert all("private-" not in p.read_text() for p in log.root.iterdir())
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in log.root.iterdir())


def test_error_is_durable_and_original_exception_survives(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    log = OperationLog(tmp_path)
    sync = []
    monkeypatch.setattr(os, "fsync", lambda fd: sync.append(fd))
    error = ValueError("secret credential")

    def fail():
        raise error

    with pytest.raises(ValueError) as caught:
        log.wrap("batch", fail)()
    assert caught.value is error
    assert len(sync) == 1
    assert rows(log)[-1]["error_type"] == "ValueError"
    assert "secret credential" not in (log.root / "events.jsonl").read_text()
    log.close()


def test_rotation_bounds_storage_and_keeps_latest_events(tmp_path):
    tmp_path.chmod(0o700)
    log = OperationLog(tmp_path, max_bytes=512, backups=2)
    for i in range(30):
        log.emit("worker", "exit", pid=i, returncode=-15, expected=True)
    log.close()
    files = list(log.root.glob("events*.jsonl"))
    assert len(files) <= 3
    assert all(p.stat().st_size <= 512 for p in files)
    assert any(r.get("pid") == 29 for r in rows(log))
    status = json.loads((log.root / "status.json").read_text())
    assert status["rotations"] > 0 and not status["incomplete"]


def test_write_failure_does_not_replace_processing_result(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    log = OperationLog(tmp_path)
    monkeypatch.setattr(os, "write", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    assert log.wrap("batch", lambda: 42)() == 42
    assert log.incomplete
    log.close()


def test_refuses_symlink_root(tmp_path):
    tmp_path.chmod(0o700)
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        OperationLog(link)


def test_known_stop_reason_and_os_errno_without_messages(tmp_path):
    from product_search.search.replenishment_contracts import ReplenishmentError

    tmp_path.chmod(0o700)
    log = OperationLog(tmp_path)
    for error in (ReplenishmentError("WAIT_TIMEOUT"), OSError(28, "secret path")):

        def fail(error=error):
            raise error

        with pytest.raises(type(error)):
            log.wrap("batch", fail)()
    errors = [row for row in rows(log) if row["phase"] == "error"]
    assert errors[0]["error_code"] == "WAIT_TIMEOUT"
    assert errors[1]["errno"] == 28
    log.close()


def test_exit_remembers_controller_stop_when_cleanup_check_raises(tmp_path):
    from product_search.infrastructure.replenishment_workers import ProcessStageWorkers

    tmp_path.chmod(0o700)
    log = OperationLog(tmp_path)
    owner = SimpleNamespace(run_ref="run")
    child = SimpleNamespace(pid=1234, returncode=None)
    child.poll = lambda: child.returncode
    failure = PermissionError(1, "private detail")
    calls = []

    def stop(*args):
        calls.append(True)
        child.returncode = -15
        if len(calls) == 1:
            raise failure
        return True

    workers = ProcessStageWorkers.__new__(ProcessStageWorkers)
    from threading import Event, Lock

    workers.owner = owner
    workers.operation_log = log
    workers.child = child
    workers._exit_recorded = False
    workers._termination_requested = False
    workers.stage = ("embedding", "openclip_b32")
    workers.reason = None
    workers.thread = None
    workers._stop = Event()
    workers._registry_lock = Lock()
    workers.registry = SimpleNamespace(stop=stop)
    workers.package = SimpleNamespace(
        observation_max_age_seconds=1, stop_grace_seconds=1, kill_wait_seconds=1
    )
    workers.end_at = 100
    workers.driver = SimpleNamespace()
    workers.supervisor = SimpleNamespace(require_recovery=lambda: None)
    with pytest.raises(PermissionError) as caught:
        workers.close_stage(owner, 90)
    assert caught.value is failure
    exits = [r for r in rows(log) if r["phase"] == "exit"]
    assert len(exits) == 1 and exits[0]["expected"] is True
    assert workers.close_stage(owner, 90)
    assert len([r for r in rows(log) if r["phase"] == "exit"]) == 1
    log.close()


def test_batch_records_safe_progress_and_final_summary(tmp_path):
    tmp_path.chmod(0o700)
    log = OperationLog(tmp_path)
    result = {
        "status": "FINISHED",
        "reason": "COMPLETED",
        "outcomes": [["secret-photo", "OK"], ["other", "NO_NAILS"]],
        "publications": [{"state": "SUCCEEDED", "revision_ref": "secret-revision"}],
    }
    inventory = [{"photos": [{"source_ref": "secret-path"}, {}]}]
    assert log.wrap("batch", lambda *a: result)({}, inventory) is result
    records = rows(log)
    assert records[0]["total_photos"] == 2
    assert records[1]["completed_photos"] == 2 and records[1]["ok_photos"] == 1
    assert records[1]["error_code"] == "COMPLETED" and records[1]["publications"] == 1
    assert "secret-" not in (log.root / "events.jsonl").read_text()
    photo = SimpleNamespace(photo_ref="private-photo")
    from product_search.search.replenishment_contracts import PhotoOutcome

    log.wrap("photo_outcome", lambda *a: None)(photo, PhotoOutcome.OK, None)
    assert rows(log)[-1]["outcome"] == "OK"
    log.close()
