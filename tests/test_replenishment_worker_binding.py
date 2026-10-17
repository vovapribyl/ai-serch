"""B1 native wiring: real owned processes, synthetic driver, no SDK imports."""

import sys
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from product_search.infrastructure.replenishment_supervisor import Supervisor
from product_search.search.replenishment_contracts import (
    Ownership,
    PhotoOutcome,
    PhotoWork,
    ReplenishmentError,
    ResourceObservation,
    StageAttempt,
    StageOutput,
)
from tests.test_replenishment_lifecycle import bounded_case  # noqa: F401
from tests.test_replenishment_runtime_binding import gate


class Driver:
    def __init__(self):
        self.events = []

    def command(self, stage, model, owner, p, end_at, lease_fd):
        self.events.append(("command", stage, model))
        return (sys.executable, "-c", "import time; time.sleep(10)")

    def ready(self, child, end_at):
        self.events.append(("ready", child.pid))

    def exchange(self, photo, attempt, end_at):
        self.events.append(("process", attempt.attempt_ref))
        return StageOutput("a" * 64, "b" * 64, 1)


@pytest.fixture
def runtime(tmp_path):
    root = tmp_path
    root.chmod(0o700)
    from product_search.infrastructure.replenishment_workers import ProcessStageWorkers

    guard, p = gate(root)
    state = SimpleNamespace(status="OK")
    observe = lambda: ResourceObservation(state.status, time.monotonic())
    supervisor = Supervisor(
        root,
        issue_owner=lambda *args: Ownership("run", "token", 2),
        observe=observe,
        quiesce=lambda *args: True,
    )
    end_at = time.monotonic() + 20
    supervisor.activate_search(
        lambda: Ownership("search", "query", 1), end_at=end_at, stop_grace=1, kill_wait=1
    )
    owner = supervisor.begin_build(p, end_at=end_at)
    guard.consume(owner, p)
    driver = Driver()
    workers = ProcessStageWorkers(supervisor, guard, driver, p, owner, end_at, poll_seconds=0.01)
    try:
        yield workers, driver, owner, p, state
    finally:
        workers.close_stage(owner, time.monotonic() + 3)
        supervisor.close(end_at=time.monotonic() + 3, stop_grace=1, kill_wait=1)


def photo_attempt(p):
    photo = PhotoWork("photo", "revision", p.semantic_profile_sha, 100, PhotoOutcome.PENDING, 1, 1)
    attempt = StageAttempt("attempt", "photo", "localization", "", "c" * 64, "revision", 1, 1, 1)
    return photo, attempt


def test_stage_has_one_owned_child_and_next_waits_for_physical_exit(runtime):
    workers, driver, owner, p, _ = runtime
    end = time.monotonic() + 10
    workers.open_stage("localization", "", owner, p, end)
    child = workers.child
    with pytest.raises(ReplenishmentError, match="BUSY"):
        workers.open_stage("embedding", "openclip_b32", owner, p, end)
    photo, attempt = photo_attempt(p)
    assert workers.process(photo, attempt, owner, end).region_count == 1
    assert child.poll() is None
    assert workers.close_stage(owner, time.monotonic() + 3)
    assert child.poll() is not None
    workers.open_stage("embedding", "openclip_b32", owner, p, end)
    assert workers.child.pid != child.pid
    assert [event[:3] for event in driver.events if event[0] == "command"] == [
        ("command", "localization", ""),
        ("command", "embedding", "openclip_b32"),
    ]


def test_foreign_attempt_is_refused_before_driver_invocation(runtime):
    workers, driver, owner, p, _ = runtime
    end = time.monotonic() + 10
    workers.open_stage("localization", "", owner, p, end)
    photo, attempt = photo_attempt(p)
    with pytest.raises(ReplenishmentError, match="ATTEMPT_MISMATCH"):
        workers.process(photo, replace(attempt, photo_ref="other"), owner, end)
    assert not any(event[0] == "process" for event in driver.events)


def test_critical_signal_stops_owned_child_and_never_accepts_late_result(runtime):
    workers, driver, owner, p, state = runtime
    end = time.monotonic() + 10
    workers.open_stage("localization", "", owner, p, end)
    child = workers.child
    state.status = "STOP"

    def late(*args):
        time.sleep(0.05)
        return StageOutput("a" * 64, "b" * 64, 1)

    driver.exchange = late
    photo, attempt = photo_attempt(p)
    with pytest.raises(ReplenishmentError, match="RESOURCE_STOP"):
        workers.process(photo, attempt, owner, end)
    assert workers.close_stage(owner, time.monotonic() + 3)
    assert child.poll() is not None


def test_driver_releases_resource_handle_only_after_confirmed_teardown(runtime):
    workers, driver, owner, p, _ = runtime
    released = []
    driver.closed = lambda: released.append(workers.child.poll())
    workers.open_stage("localization", "", owner, p, time.monotonic() + 10)
    assert released == []
    assert workers.close_stage(owner, time.monotonic() + 3)
    assert released and released[0] is not None


def test_native_entry_reports_pre_sdk_memory_before_runtime_inventory(tmp_path, monkeypatch):
    import json
    import os
    import platform
    from pathlib import Path

    from product_search.infrastructure import replenishment_worker_entry as entry
    from product_search.infrastructure.nail_build_composition import publish_private_json
    from services.candidate_i import bootstrap

    tmp_path.chmod(0o700)
    control = {
        "stage_key": "localization",
        "control_root": str(tmp_path),
        "grant_path": str(tmp_path / "grant.json"),
        "nonce": "a" * 64,
    }
    publish_private_json(tmp_path / "control.json", control)
    binding = {
        "device": "mps",
        "dtype": "float32",
        "fallback": False,
        "installed_inventories": {
            "localization": {
                "python": platform.python_version(),
                "machine": platform.machine(),
                "packages": ["expected"],
            }
        },
    }
    owner = Ownership("run", "owner", 1)
    monkeypatch.setattr(entry, "validate_control", lambda _: (object(), owner, binding))

    class Grant:
        def __init__(self, path):
            self.path = Path(path)

        def _read(self, package):
            return {"nonce": "b" * 64}

        def check_owner(self, *args):
            return True

    monkeypatch.setattr(entry, "FreshGrant", Grant)

    def inventory():
        path = tmp_path / "telemetry.json"
        assert path.exists(), "validated entry must report pre-SDK memory before inventory scan"
        sample = json.loads(path.read_text())
        assert sample["pid"] == os.getpid() and sample["nonce"] == control["nonce"]
        assert sample["mps_bytes"] == 0
        return ["mismatch"]

    monkeypatch.setattr(bootstrap, "installed_inventory", inventory)
    with pytest.raises(ReplenishmentError, match="RUNTIME_MISMATCH"):
        entry.run_native(
            tmp_path / "control.json", importer=lambda _: pytest.fail("SDK must not import")
        )


def test_localization_assembly_accepts_manifest_path_records_without_sdk(tmp_path, monkeypatch):
    from pathlib import Path

    from product_search.infrastructure.replenishment_worker_entry import _serve_localization
    from services.candidate_i import bootstrap

    class AssemblyReached(Exception):
        pass

    paths = {
        "model/gdino/config.json": {
            "path": str(tmp_path / "gdino/config.json"),
            "sha256": "a" * 64,
        },
        "model/sam": str(tmp_path / "sam.pt"),
    }

    def assemble(manifest, files, **kwargs):
        assert files == {
            "model/gdino/config.json": tmp_path / "gdino/config.json",
            "model/sam": tmp_path / "sam.pt",
        }
        assert kwargs["gdino_snapshot_path"] == tmp_path / "gdino"
        assert kwargs["sam_checkpoint_path"] == tmp_path / "sam.pt"
        assert all(isinstance(value, Path) for value in files.values())
        raise AssemblyReached

    monkeypatch.setattr(bootstrap, "assemble_service", assemble)
    guard = SimpleNamespace(check_owner=lambda *args: True)
    with pytest.raises(AssemblyReached):
        _serve_localization(
            {"shared_runtime_root": str(tmp_path)},
            object(),
            {"i_files": paths, "i_manifest": {}},
            guard,
            object(),
        )


def test_intentional_stage_teardown_stops_monitor_before_worker_disappears(runtime):
    workers, _driver, owner, p, state = runtime
    workers.open_stage("localization", "", owner, p, time.monotonic() + 10)
    original_stop = workers.registry.stop

    def stop(*args):
        # The observer loses its mandatory live-worker sample during teardown.
        state.status = "STOP"
        time.sleep(0.05)
        return original_stop(*args)

    workers.registry.stop = stop
    assert workers.close_stage(owner, time.monotonic() + 3)
    assert workers.reason is None
    assert workers.supervisor.mode == "BUILD"


@pytest.mark.parametrize("unexpected", [False, True])
def test_controller_records_exit_even_without_worker_footer(runtime, tmp_path, unexpected):
    import json
    import signal

    from product_search.infrastructure.replenishment_operation_log import OperationLog

    workers, _, owner, package, _ = runtime
    log = OperationLog(tmp_path)
    workers.operation_log = log
    workers.open_stage("localization", "", owner, package, time.monotonic() + 10)
    pid = workers.child.pid
    if unexpected:
        workers.child.send_signal(signal.SIGKILL)
        workers.child.wait(timeout=2)
    assert workers.close_stage(owner, time.monotonic() + 3)
    log.close()
    events = [json.loads(line) for line in (log.root / "events.jsonl").read_text().splitlines()]
    exits = [e for e in events if e["event"] == "worker" and e["phase"] == "exit"]
    assert len(exits) == 1
    assert exits[0]["pid"] == pid and exits[0]["expected"] is not unexpected
    assert exits[0]["returncode"] == (-9 if unexpected else -15)
    assert exits[0]["signal"] == (9 if unexpected else 15)
    assert exits[0]["stage_key"] == "localization"


@pytest.mark.parametrize("enabled", [True, False])
def test_native_records_import_boundary_before_sdk_failure(tmp_path, monkeypatch, enabled):
    import json
    import os
    import platform
    import subprocess
    import time
    from pathlib import Path
    from types import SimpleNamespace

    from product_search.infrastructure import replenishment_load_diagnostics as diagnostic
    from product_search.infrastructure import replenishment_worker_entry as entry
    from product_search.infrastructure.nail_build_composition import publish_private_json
    from services.candidate_i import bootstrap

    tmp_path.chmod(0o700)
    control = {
        "stage_key": "localization",
        "control_root": str(tmp_path),
        "grant_path": str(tmp_path / "grant.json"),
        "nonce": "a" * 64,
        "lease_fd": 0,
        "coordinator_fd": 1,
        "end_at": time.monotonic() + 5,
    }
    publish_private_json(tmp_path / "control.json", control)
    binding = {
        "load_diagnostics": enabled,
        "device": "mps",
        "dtype": "float32",
        "fallback": False,
        "installed_inventories": {
            "localization": {
                "python": platform.python_version(),
                "machine": platform.machine(),
                "packages": [],
            }
        },
    }
    package = SimpleNamespace(max_wire_bytes=4096)
    owner = Ownership("run", "owner", 1)
    monkeypatch.setattr(entry, "validate_control", lambda _: (package, owner, binding))

    class Grant:
        def __init__(self, path):
            self.path = Path(path)

        def _read(self, package):
            return {"nonce": "b" * 64}

        def check_owner(self, *args):
            return True

    monkeypatch.setattr(entry, "FreshGrant", Grant)
    monkeypatch.setattr(bootstrap, "installed_inventory", list)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: object())
    monkeypatch.setattr(os, "getpgrp", os.getpid)
    monkeypatch.setattr(diagnostic, "worker_sample", lambda torch: {})
    original = RuntimeError("SDK import failure")

    def importer(name):
        assert name == "torch"
        path = tmp_path / "load-events.jsonl"
        if enabled:
            events = [json.loads(line) for line in path.read_text().splitlines()]
            assert [(r["step"], r["phase"]) for r in events] == [
                ("worker", "before"),
                ("torch.import", "before"),
            ]
        else:
            assert not path.exists()
        raise original

    with pytest.raises(RuntimeError) as caught:
        entry.run_native(tmp_path / "control.json", importer=importer)
    assert caught.value is original
    if enabled:
        assert (tmp_path / "load-events.status.json").exists()


def test_opt_in_region_capture_is_bound_to_owned_worker_directory(tmp_path, monkeypatch):
    from product_search.infrastructure.replenishment_worker_entry import _serve_localization
    from services.candidate_i import bootstrap

    tmp_path.chmod(0o700)
    control = {"shared_runtime_root": str(tmp_path), "control_root": str(tmp_path)}
    binding = {
        "i_files": {
            "model/gdino/config.json": str(tmp_path / "config.json"),
            "model/sam": str(tmp_path / "sam.pt"),
        },
        "i_manifest": {},
        "save_localization_diagnostics": True,
    }

    class AssemblyReached(Exception):
        pass

    def assemble(manifest, files, **kwargs):
        assert kwargs["diagnostic_root"] == tmp_path / "localized-regions"
        assert kwargs["diagnostic_root"].stat().st_mode & 0o777 == 0o700
        raise AssemblyReached

    monkeypatch.setattr(bootstrap, "assemble_service", assemble)
    with pytest.raises(AssemblyReached):
        _serve_localization(
            control, object(), binding, SimpleNamespace(check_owner=lambda *a: True), object()
        )


@pytest.mark.parametrize("flag", ["true", 1, None])
def test_invalid_region_capture_flag_is_refused_before_service_creation(
    tmp_path, monkeypatch, flag
):
    from product_search.infrastructure.replenishment_worker_entry import _serve_localization
    from services.candidate_i import bootstrap

    def must_not_assemble(*a, **kw):
        pytest.fail("Invalid flag must not assemble service")

    monkeypatch.setattr(bootstrap, "assemble_service", must_not_assemble)
    with pytest.raises(ReplenishmentError, match="RUNTIME_MISMATCH"):
        _serve_localization(
            {"shared_runtime_root": str(tmp_path)},
            object(),
            {"i_files": {}, "save_localization_diagnostics": flag},
            SimpleNamespace(check_owner=lambda *a: True),
            object(),
        )
