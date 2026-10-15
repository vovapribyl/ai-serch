import json

import pytest

from product_search.infrastructure.replenishment_monitor import render, snapshot


def fixture(tmp_path, events, resources=None):
    tmp_path.chmod(0o700)
    folder = tmp_path / "operation-logs" / "operations-test"
    folder.mkdir(parents=True, mode=0o700)
    folder.parent.chmod(0o700)
    for name, value in [("runtime-binding.json", {"operation_log_root": str(folder.parent)})]:
        p = tmp_path / name
        p.write_text(json.dumps(value))
        p.chmod(0o600)
    p = folder / "events.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in events))
    p.chmod(0o600)
    if resources:
        p = tmp_path / "resource-observations.jsonl"
        p.write_text(json.dumps(resources) + "\n")
        p.chmod(0o600)
    return tmp_path


def test_running_progress_uses_checkpoints_not_just_worker_response(tmp_path):
    events = [
        {"sequence": 1, "event": "batch", "phase": "before", "monotonic": 10, "total_photos": 2},
        {
            "sequence": 2,
            "event": "stage",
            "phase": "before",
            "monotonic": 11,
            "stage_key": "embedding",
            "model_key": "openclip_b32",
        },
        {
            "sequence": 3,
            "event": "photo",
            "phase": "after",
            "monotonic": 12,
            "photo_ref": "private-alias",
        },
        {
            "sequence": 4,
            "event": "checkpoint",
            "phase": "after",
            "monotonic": 13,
            "photo_ref": "private-alias",
            "stage_key": "localization",
            "model_key": "",
        },
    ]
    root = fixture(
        tmp_path,
        events,
        {
            "status": "OK",
            "observed_at": 14,
            "sample": {"rss_bytes": 1024, "mps_bytes": 2048, "pressure": 1},
        },
    )
    s = snapshot(root, now=15)
    assert s["checkpoints"] == 1 and s["total_photos"] == 2
    assert s["stage"] == "embedding" and s["model"] == "openclip_b32"
    assert s["heartbeat_age_seconds"] == 1 and s["resources_fresh"]
    assert s["elapsed_seconds"] == 5 and s["state"] == "RUNNING"
    assert "private-alias" not in render(s)


def test_final_outcome_is_explicit_and_stale_resource_sample_not_current(tmp_path):
    events = [
        {"sequence": 1, "event": "batch", "phase": "before", "monotonic": 10},
        {
            "sequence": 2,
            "event": "batch",
            "phase": "after",
            "monotonic": 20,
            "result_state": "FINISHED",
            "error_code": "COMPLETED",
            "total_photos": 5,
            "completed_photos": 5,
            "ok_photos": 5,
            "publications": 5,
        },
        {"sequence": 3, "event": "host", "phase": "closed", "monotonic": 21},
    ]
    s = snapshot(
        fixture(tmp_path, events, {"status": "OK", "observed_at": 19, "sample": {"rss_bytes": 1}}),
        now=100,
    )
    assert s["state"] == "COMPLETED" and s["elapsed_seconds"] == 10
    assert s["completed_photos"] == 5 and s["publications"] == 5
    assert not s["resources_fresh"]
    assert "устарели" in render(s)


def test_old_journal_does_not_invent_success_or_full_progress(tmp_path):
    events = [
        {"sequence": 21, "event": "batch", "phase": "after", "monotonic": 20},
        {"sequence": 22, "event": "host", "phase": "closed", "monotonic": 21},
    ]
    s = snapshot(fixture(tmp_path, events), now=30)
    assert s["state"] == "UNKNOWN" and not s["history_complete"]
    assert s["total_photos"] is None


def test_error_and_partial_last_record_are_handled(tmp_path):
    root = fixture(
        tmp_path,
        [
            {
                "sequence": 1,
                "event": "batch",
                "phase": "error",
                "monotonic": 20,
                "error_type": "PermissionError",
                "error_code": "UNKNOWN",
                "errno": 1,
            }
        ],
    )
    p = next((root / "operation-logs").glob("*/events.jsonl"))
    with p.open("a") as stream:
        stream.write('{"sequence":')
    s = snapshot(root, now=25)
    assert s["state"] == "ERROR" and s["error"] == "PermissionError"


def test_monitor_refuses_symlink_and_shared_files(tmp_path):
    root = fixture(tmp_path, [])
    p = root / "runtime-binding.json"
    p.chmod(0o644)
    with pytest.raises(ValueError):
        snapshot(root)


def test_outcomes_and_worker_exit_give_live_counts_and_stage_duration(tmp_path):
    events = [
        {"sequence": 1, "event": "batch", "phase": "before", "monotonic": 10, "total_photos": 2},
        {
            "sequence": 2,
            "event": "stage",
            "phase": "before",
            "monotonic": 11,
            "stage_key": "localization",
            "model_key": "",
        },
        {
            "sequence": 3,
            "event": "photo_outcome",
            "phase": "after",
            "monotonic": 12,
            "photo_ref": "a",
            "outcome": "NO_NAILS",
        },
        {
            "sequence": 4,
            "event": "worker",
            "phase": "exit",
            "monotonic": 14,
            "stage_key": "localization",
            "model_key": "",
        },
    ]
    s = snapshot(fixture(tmp_path, events), now=30)
    assert s["completed_photos"] == 1 and s["ok_photos"] == 0
    assert s["stage_seconds"] == 3


def test_cli_reads_once_and_fails_safely(tmp_path):
    import io

    from product_search.infrastructure.replenishment_monitor import main

    root = fixture(tmp_path, [])
    out, err = io.StringIO(), io.StringIO()
    assert main(["--runtime-root", str(root)], stdout=out, stderr=err) == 0
    assert "WAITING" in out.getvalue()
    assert main(["--runtime-root", str(root), "--interval", "0"], stdout=out, stderr=err) == 5
    assert str(root) not in err.getvalue()


def test_failed_historical_run_without_summary_keeps_counts_unknown(tmp_path):
    import hashlib

    root = fixture(
        tmp_path,
        [
            {
                "sequence": 1,
                "event": "batch",
                "phase": "error",
                "monotonic": 10,
                "error_type": "PermissionError",
            }
        ],
    )
    package = {"schema_version": 1}
    digest = hashlib.sha256(
        json.dumps(package, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    for name, value in [
        ("execution-package.proposed.json", package),
        (
            "probe050-result.json",
            {"package_sha": digest, "answer": {"status": "ERROR", "summary": None}},
        ),
    ]:
        p = root / name
        p.write_text(json.dumps(value))
        p.chmod(0o600)
    s = snapshot(root, now=20)
    assert s["state"] == "ERROR" and s["total_photos"] is None


def test_watch_refreshes_without_starting_processing(tmp_path, monkeypatch):
    import io

    from product_search.infrastructure import replenishment_monitor as monitor

    root = fixture(
        tmp_path,
        [{"sequence": 1, "event": "batch", "phase": "before", "monotonic": 10, "total_photos": 2}],
    )
    path = next((root / "operation-logs").glob("*/events.jsonl"))
    sleeps = []

    def tick(seconds):
        sleeps.append(seconds)
        with path.open("a") as stream:
            for e in [
                {
                    "sequence": 2,
                    "event": "batch",
                    "phase": "after",
                    "monotonic": 20,
                    "error_code": "COMPLETED",
                    "total_photos": 2,
                    "completed_photos": 2,
                    "ok_photos": 2,
                    "publications": 2,
                },
                {"sequence": 3, "event": "host", "phase": "closed", "monotonic": 21},
            ]:
                stream.write(json.dumps(e) + "\n")

    monkeypatch.setattr(monitor.time, "sleep", tick)
    out = io.StringIO()
    assert (
        monitor.main(["--runtime-root", str(root), "--watch"], stdout=out, stderr=io.StringIO())
        == 0
    )
    assert sleeps == [3] and "RUNNING" in out.getvalue() and "COMPLETED" in out.getvalue()


@pytest.mark.parametrize(
    "reason,check",
    [
        ("PRESSURE_CRITICAL", "RESOURCE_LIMITS"),
        ("RSS_LIMIT", "RESOURCE_LIMITS"),
        ("MPS_LIMIT", "RESOURCE_LIMITS"),
        ("OBSERVATION_FAILED", "TELEMETRY_FRESHNESS"),
        ("OBSERVATION_FAILED", "PROCESS_TABLE"),
        ("JOURNAL_WRITE_FAILED", "RESOURCE_JOURNAL"),
    ],
)
def test_stop_summary_uses_first_cause_and_does_not_refresh_old_sample(tmp_path, reason, check):
    root = fixture(
        tmp_path,
        [
            {"sequence": 1, "event": "batch", "phase": "before", "monotonic": 10},
            {
                "sequence": 2,
                "event": "stage",
                "phase": "before",
                "monotonic": 11,
                "stage_key": "localization",
                "model_key": "",
            },
            {
                "sequence": 3,
                "event": "worker",
                "phase": "exit",
                "monotonic": 14,
                "stage_key": "localization",
                "model_key": "",
                "returncode": -9,
                "signal": 9,
                "expected": True,
                "error_code": "RESOURCE_STOP",
            },
        ],
        {
            "status": "STOP",
            "observed_at": 29,
            "sample": {"rss_bytes": 999, "mps_bytes": 888, "pressure": 1},
            "diagnostic": {"reason": "OBSERVATION_FAILED", "sample_current": False},
        },
    )
    first = {
        "status": "STOP",
        "observed_at": 13,
        "sample_observed_at": 12,
        "sample": {"rss_bytes": 1024, "mps_bytes": 2048, "pressure": 4},
        "diagnostic": {
            "reason": reason,
            "check": check,
            "sample_current": False,
            "error_type": "PRIVATE_ERROR_TEXT",
        },
    }
    path = root / "resource-stop.json"
    path.write_text(json.dumps(first))
    path.chmod(0o600)
    view = snapshot(root, now=30)
    assert view["failure"]["reason"] == reason
    assert view["failure"]["check"] == check
    assert view["failure"]["sample_observed_at"] == 12
    assert view["failure"]["sample_age_seconds"] == 18
    assert view["failure"]["sample"]["rss_bytes"] == 1024
    assert view["failure"]["worker_exit"]["signal"] == 9
    assert view["failure"]["worker_exit"]["expected"] is True
    assert view["stage_seconds"] == 3
    assert reason in render(view)
    assert "PRIVATE" not in json.dumps(view)
    assert not view["resources_fresh"]


def test_unexpected_worker_exit_is_not_diagnosed_as_oom(tmp_path):
    root = fixture(
        tmp_path,
        [
            {
                "sequence": 1,
                "event": "worker",
                "phase": "exit",
                "monotonic": 14,
                "stage_key": "localization",
                "model_key": "",
                "returncode": -9,
                "signal": 9,
                "expected": False,
            },
        ],
    )
    view = snapshot(root, now=30)
    assert view["failure"]["reason"] == "UNEXPECTED_WORKER_EXIT"
    assert view["failure"]["worker_exit"]["returncode"] == -9
    assert "OOM" not in render(view)


def test_partial_record_marks_summary_history_incomplete(tmp_path):
    root = fixture(tmp_path, [{"sequence": 1, "event": "host", "phase": "closed", "monotonic": 10}])
    path = next((root / "operation-logs").glob("*/events.jsonl"))
    with path.open("a") as stream:
        stream.write('{"sequence":')
    assert snapshot(root, now=30)["history_complete"] is False


def test_json_report_includes_failure_and_still_reads_only(tmp_path):
    import io

    from product_search.infrastructure.replenishment_monitor import main

    root = fixture(
        tmp_path,
        [
            {
                "sequence": 1,
                "event": "worker",
                "phase": "exit",
                "monotonic": 10,
                "returncode": -9,
                "signal": 9,
                "expected": False,
            }
        ],
    )
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    out = io.StringIO()
    assert main(["--runtime-root", str(root), "--json"], stdout=out) == 0
    assert json.loads(out.getvalue())["failure"]["reason"] == "UNEXPECTED_WORKER_EXIT"
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_latched_stop_does_not_make_original_measurement_fresh(tmp_path):
    root = fixture(
        tmp_path,
        [],
        {
            "status": "STOP",
            "observed_at": 29,
            "sample_observed_at": 10,
            "sample": {"rss_bytes": 1024},
            "diagnostic": {
                "reason": "PRESSURE_CRITICAL",
                "check": "RESOURCE_LIMITS",
                "sample_current": True,
            },
        },
    )
    view = snapshot(root, now=30)
    assert view["resources_fresh"] is False
    assert view["failure"]["sample_age_seconds"] == 20
