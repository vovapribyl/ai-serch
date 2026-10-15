from copy import deepcopy
from types import SimpleNamespace

import pytest

from product_search.infrastructure.nail_build_composition import (
    ObservationGate,
    RuntimeVerifier,
    compose_build,
)
from product_search.infrastructure.nail_build_runner import AdmissionBudget, BuildStop
from product_search.search.nail_contracts import (
    BinaryMask,
    DecodeProfile,
    LocalizationProfile,
    LocalizedRegion,
    NailLocalization,
    RgbImage,
)
from tests.test_nail_build_preparation import Lease
from tests.test_nail_catalog_build import IDENTITY, ITEMS, RUNTIME, Catalog, Images

LIMITS = {
    "i_rss_bytes": 10,
    "backend_rss_bytes": 10,
    "combined_rss_bytes": 15,
    "max_storage_bytes": 20,
    "min_free_bytes": 5,
    "freshness_s": 1,
}
SAMPLE = {
    "pressure": 1,
    "i_rss": 2,
    "backend_rss": 3,
    "artifact_bytes": 1,
    "db_bytes": 1,
    "host_free": 100,
    "vm_free": 100,
}
RUNTIME_OBS = {
    "mode": "fake",
    "extractor_fingerprint": "a" * 64,
    "backend_inventory_sha256": "b" * 64,
    "python": "3.12.14",
    "machine": "arm64",
    "device": "fake",
    "dtype": "float32",
    "operator_fallback": False,
    "models": [[m.model_key, m.revision, m.manifest_sha256, m.dimension] for m in IDENTITY.models],
}


@pytest.mark.parametrize(
    "field,value",
    [
        ("pressure", 4),
        ("pressure", 0),
        ("i_rss", 11),
        ("backend_rss", 11),
        ("i_rss", 13),
        ("host_free", 4),
        ("vm_free", 4),
        ("artifact_bytes", 20),
        ("db_bytes", 20),
        ("db_bytes", -1),
        ("pressure", True),
    ],
)
def test_terminal_bad_sample_never_recovers(field, value):
    gate = ObservationGate(LIMITS, lambda: 0)
    bad = {**SAMPLE, field: value}
    gate.update(bad, 0)
    assert not gate.allowed()
    gate.update(SAMPLE, 0)
    assert not gate.allowed()


def test_missing_sample_future_sample_and_stale_are_rejected():
    now = [0.0]
    gate = ObservationGate(LIMITS, lambda: now[0])
    assert not gate.allowed()
    gate.update(SAMPLE, 0)
    assert gate.allowed()
    now[0] = 1.1
    assert not gate.allowed()
    gate.update(SAMPLE, 1.1)
    assert not gate.allowed()
    other = ObservationGate(LIMITS, lambda: 0)
    other.update(SAMPLE, 1)
    assert not other.allowed()


def test_warning_and_immutable_limits_are_preserved():
    limits = dict(LIMITS)
    gate = ObservationGate(limits, lambda: 0)
    limits["min_free_bytes"] = 1000
    gate.update({**SAMPLE, "pressure": 2}, 0)
    assert gate.allowed()


def test_runtime_expectations_are_frozen_and_wrong_revision_is_not_ready():
    expected = deepcopy(RUNTIME_OBS)
    observed = deepcopy(RUNTIME_OBS)
    verifier = RuntimeVerifier(expected, lambda: observed)
    expected["models"][0][1] = "changed"
    assert verifier.verify()
    observed["models"][0][1] = "changed"
    assert not verifier.verify()


def test_existing_core_is_composed_with_all_three_providers_without_publish():
    catalog = Catalog()
    calls = []

    def localize(image, profile):
        calls.append("I")
        return NailLocalization(
            "OK",
            (LocalizedRegion(1, "nail", 0.9, (0.0, 0.0, 1.0, 1.0), BinaryMask(1, 1, b"\xff")),),
        )

    factories = {}
    for model in IDENTITY.models:

        def load(model=model):
            calls.append("load:" + model.model_key)
            return SimpleNamespace(
                model_key=model.model_key,
                revision=model.revision,
                embedding_dim=model.dimension,
                encode_image=lambda image, model=model: (
                    calls.append("encode:" + model.model_key)
                    or (1.0,) + (0.0,) * (model.dimension - 1)
                ),
            )

        factories[model.model_key] = load
    images = Images()
    images.read_rgb = lambda *args: RgbImage(1, 1, b"abc")
    gate = ObservationGate(LIMITS, lambda: 0)
    gate.update(SAMPLE, 0)
    budget = AdmissionBudget(7, 10, gate.allowed, lambda: 0)
    device, coordinator = Lease(), Lease()
    execute = compose_build(
        catalog=catalog,
        images=images,
        localization=SimpleNamespace(localize=localize),
        factories=factories,
        identity=IDENTITY,
        inventory=ITEMS,
        runtime=RUNTIME,
        localization_profile=LocalizationProfile("a" * 64),
        decode_profile=DecodeProfile(100, 1),
        max_regions=10,
        budget=budget,
        device=device,
        coordinator=coordinator,
        target_check=lambda: True,
        input_check=lambda: True,
        runtime_check=lambda: True,
    )
    result = execute()
    assert result.complete and result.status == "BUILDING" and result.ok_photos == 1
    assert len(calls) == 7 and budget.used == 7
    assert not catalog.published and not device.held and not coordinator.held


def test_runtime_mismatch_prevents_provider_load_and_building():
    catalog = Catalog()
    calls = []
    execute = compose_build(
        catalog=catalog,
        images=Images(),
        localization=None,
        factories={m.model_key: lambda: calls.append("load") for m in IDENTITY.models},
        identity=IDENTITY,
        inventory=ITEMS,
        runtime=RUNTIME,
        localization_profile=LocalizationProfile("a" * 64),
        decode_profile=DecodeProfile(100, 1),
        max_regions=10,
        budget=AdmissionBudget(7, 10, lambda: True, lambda: 0),
        device=Lease(),
        coordinator=Lease(),
        target_check=lambda: True,
        input_check=lambda: True,
        runtime_check=lambda: False,
    )
    with pytest.raises(BuildStop):
        execute()
    assert calls == [] and not catalog.created


def test_combined_rss_and_invalid_sample_are_terminal():
    gate = ObservationGate(LIMITS, lambda: 0)
    gate.update({**SAMPLE, "i_rss": 8, "backend_rss": 8}, 0)
    assert not gate.allowed()
    other = ObservationGate(LIMITS, lambda: 0)
    other.update({k: v for k, v in SAMPLE.items() if k != "vm_free"}, 0)
    assert not other.allowed()


@pytest.mark.parametrize("fault", ["critical", "storage", "exception", "blocked_observer", "wall"])
def test_external_supervisor_stops_owned_worker_and_is_independent_of_observer(tmp_path, fault):
    import sys
    import time

    from product_search.infrastructure.nail_build_composition import supervise_owned
    from tests.support.candidate_i_probe_watchdog import run_owned_probe

    tmp_path.chmod(0o700)
    script = "import os,json,pathlib,time,sys; p=pathlib.Path(sys.argv[1])/'worker-pid.json'; f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(f,json.dumps({'pid':os.getpid(),'parent':os.getppid()}).encode()); os.close(f); time.sleep(30)"

    def observe(pid):
        if fault == "exception":
            raise OSError("test-only observation error")
        if fault == "blocked_observer":
            time.sleep(2)
        return {
            **SAMPLE,
            "pressure": 4 if fault == "critical" else 1,
            "artifact_bytes": 20 if fault == "storage" else 1,
        }

    policy = {**LIMITS, "freshness_s": 0.2, "wall_s": 0.5}
    started = time.monotonic()
    result = supervise_owned(
        [sys.executable, "-B", "-c", script, str(tmp_path)],
        tmp_path,
        policy,
        observe=observe,
        watchdog=run_owned_probe,
    )
    assert result["exit_code"] < 0 and time.monotonic() - started < 1.5
    assert result["stop_reason"] is not None
    assert result["observation_stop"] == (
        "STORAGE_CEILING"
        if fault == "storage"
        else "RESOURCE_CEILING"
        if fault == "critical"
        else "RESOURCE_OBSERVATION_ERROR"
        if fault in ("exception", "blocked_observer")
        else None
    )


def test_owned_supervisor_returns_success_without_affecting_an_unrelated_process(tmp_path):
    import subprocess
    import sys

    from product_search.infrastructure.nail_build_composition import supervise_owned
    from tests.support.candidate_i_probe_watchdog import run_owned_probe

    tmp_path.chmod(0o700)
    script = "import os,json,pathlib,time,sys; r=pathlib.Path(sys.argv[1]); p=r/'worker-pid.json'; f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(f,json.dumps({'pid':os.getpid(),'parent':os.getppid()}).encode()); os.close(f); time.sleep(.2)"
    unrelated = subprocess.Popen([sys.executable, "-B", "-c", "import time;time.sleep(10)"])
    try:
        result = supervise_owned(
            [sys.executable, "-B", "-c", script, str(tmp_path)],
            tmp_path,
            {**LIMITS, "freshness_s": 1, "wall_s": 2},
            observe=lambda pid: SAMPLE,
            watchdog=run_owned_probe,
        )
        assert result["exit_code"] == 0 and result["stop_reason"] is None
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=3)


def test_native_entrypoint_is_closed_without_reading_job_or_loading_sdk(capsys):
    from scripts.run_nail_build import main

    assert main(["--mode", "native"]) == 4
    assert "NATIVE_EXECUTION_NOT_AUTHORIZED" in capsys.readouterr().out


@pytest.mark.parametrize("vm_failure", [False, True])
def test_host_and_vm_free_space_are_observed_separately(tmp_path, monkeypatch, vm_failure):
    import hashlib
    import json
    import os
    import shutil
    import subprocess
    from contextlib import contextmanager

    from product_search.infrastructure.nail_build_composition import HostStorageObserver

    path = tmp_path / "target.json"
    path.write_text(json.dumps({"container_id": "fake-container"}))
    path.chmod(0o600)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    (artifacts / "payload").write_bytes(b"ab")

    @contextmanager
    def connect():
        yield SimpleNamespace(execute=lambda sql: SimpleNamespace(fetchone=lambda: (30,)))

    target = SimpleNamespace(
        path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), connect=connect
    )

    def run(args, **kwargs):
        if args[0] == "ps":
            text = f"123 {os.getpid()} 123 10\n124 123 123 20\n999 1 999 1000\n"
        elif args[0] == "sysctl":
            text = "1\n"
        elif args[0] == "vm_stat":
            text = "Swapouts: 10.\n"
        else:
            return SimpleNamespace(
                returncode=1 if vm_failure else 0,
                stdout="Filesystem 1024-blocks Used Available Capacity Mounted\nx 1000 20 40 1% /data\n",
            )
        return SimpleNamespace(returncode=0, stdout=text)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(shutil, "disk_usage", lambda root: SimpleNamespace(free=999))
    observer = HostStorageObserver(artifacts, target)
    if vm_failure:
        with pytest.raises(BuildStop):
            observer.sample(123)
    else:
        sample = observer.sample(123)
        assert sample["host_free"] == 999 and sample["vm_free"] == 40960
        assert sample["backend_rss"] == 10240 and sample["i_rss"] == 20480
        assert sample["db_bytes"] == 30 and sample["artifact_bytes"] == 2


def test_reserved_admission_is_recorded_before_native_operation_and_record_failure_stops():
    from product_search.infrastructure.nail_build_composition import RecordingBudget
    from product_search.infrastructure.nail_build_runner import admitted_provider

    records = []
    base = AdmissionBudget(3, 10, lambda: True, lambda: 0)
    budget = RecordingBudget(base, lambda n: records.append(n))

    def operation():
        assert records == [1]
        raise SystemExit(17)

    with pytest.raises(SystemExit):
        admitted_provider(operation, budget, Lease())()
    assert records == [1] and budget.stopped
    other = RecordingBudget(
        AdmissionBudget(3, 10, lambda: True, lambda: 0),
        lambda n: (_ for _ in ()).throw(OSError("fake persistence failure")),
    )
    calls = []
    with pytest.raises(BuildStop):
        admitted_provider(lambda: calls.append("SDK"), other, Lease())()
    assert calls == [] and other.stopped


def test_late_mandatory_observer_failure_cannot_be_hidden_by_successful_worker_exit(tmp_path):
    import sys
    import threading
    import time

    from product_search.infrastructure.nail_build_composition import supervise_owned
    from tests.support.candidate_i_probe_watchdog import run_owned_probe

    tmp_path.chmod(0o700)
    release = threading.Event()
    code = "import os,json,pathlib,time,sys; p=pathlib.Path(sys.argv[1])/'worker-pid.json'; f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(f,json.dumps({'pid':os.getpid(),'parent':os.getppid()}).encode()); os.close(f); time.sleep(.1)"

    def observe(pid):
        release.wait(timeout=1)
        return {**SAMPLE, "pressure": 4}

    def guardian(*args):
        result = run_owned_probe(*args)
        assert result["exit_code"] == 0 and result["stop_reason"] is None
        release.set()
        time.sleep(0.05)
        return result

    result = supervise_owned(
        [sys.executable, "-B", "-c", code, str(tmp_path)],
        tmp_path,
        {**LIMITS, "freshness_s": 1, "wall_s": 2},
        observe=observe,
        watchdog=guardian,
    )
    assert result["exit_code"] == 0
    assert result["stop_reason"] is not None


@pytest.mark.parametrize("fault", ["vanished_file", "permission", "root_removed"])
def test_storage_scan_handles_deleted_snapshot_entry_but_keeps_real_failure_stops(
    tmp_path, monkeypatch, fault
):
    import hashlib
    import json
    import os
    import subprocess
    from contextlib import contextmanager
    from pathlib import Path

    from product_search.infrastructure.nail_build_composition import HostStorageObserver

    path = tmp_path / "target.json"
    path.write_text(json.dumps({"container_id": "fake-container"}))
    path.chmod(0o600)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    (artifacts / "payload").write_bytes(b"ab")
    transient = artifacts / ".manifest-test.tmp"
    transient.write_bytes(b"temp")

    @contextmanager
    def connect():
        yield SimpleNamespace(execute=lambda sql: SimpleNamespace(fetchone=lambda: (30,)))

    target = SimpleNamespace(
        path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), connect=connect
    )

    def run(args, **kwargs):
        text = (
            f"123 {os.getpid()} 123 10\n"
            if args[0] == "ps"
            else "1\n"
            if args[0] == "sysctl"
            else "Swapouts: 10.\n"
            if args[0] == "vm_stat"
            else "Filesystem 1024-blocks Used Available Capacity Mounted\nx 1000 20 40 1% /data\n"
        )
        return SimpleNamespace(returncode=0, stdout=text)

    monkeypatch.setattr(subprocess, "run", run)
    actual = Path.lstat
    triggered = False

    def lstat(p, *args, **kwargs):
        nonlocal triggered
        if p == transient and not triggered:
            triggered = True
            if fault == "permission":
                raise PermissionError("private-path-must-not-be-published")
            if fault == "root_removed":
                transient.unlink()
                (artifacts / "payload").unlink()
                artifacts.rmdir()
            else:
                transient.unlink()
        return actual(p, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    if fault == "vanished_file":
        sample = HostStorageObserver(artifacts, target).sample(123)
        assert triggered and sample["artifact_bytes"] == 2 and sample["db_bytes"] == 30
    else:
        with pytest.raises((BuildStop, OSError)):
            HostStorageObserver(artifacts, target).sample(123)


def test_observer_failure_trace_keeps_exception_class_without_private_message(tmp_path):
    import json
    import sys

    from product_search.infrastructure.nail_build_composition import supervise_owned
    from tests.support.candidate_i_probe_watchdog import run_owned_probe

    tmp_path.chmod(0o700)
    script = "import os,json,pathlib,time,sys; p=pathlib.Path(sys.argv[1])/'worker-pid.json'; fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,json.dumps({'pid':os.getpid(),'parent':os.getppid()}).encode()); os.close(fd); time.sleep(30)"

    def observe(pid):
        raise PermissionError("private-path-must-not-be-published")

    result = supervise_owned(
        [sys.executable, "-B", "-c", script, str(tmp_path)],
        tmp_path,
        {**LIMITS, "freshness_s": 0.2, "wall_s": 1},
        observe=observe,
        watchdog=run_owned_probe,
    )
    assert result["stop_reason"] == "RESOURCE_OBSERVATION_ERROR"
    text = (tmp_path / "supervisor-trace.jsonl").read_text()
    event = json.loads(text.splitlines()[-1])
    assert (
        event.get("error_class") == "PermissionError"
        and "private-path-must-not-be-published" not in text
    )


@pytest.mark.parametrize(
    "reason",
    [
        "RESOURCE_CEILING",
        "STORAGE_CEILING",
        "PRESSURE_CRITICAL",
        "RSS_LIMIT",
        "MPS_LIMIT",
        "OBSERVATION_FAILED",
        "SECRET_REASON",
    ],
)
def test_watchdog_preserves_safe_terminal_cause(tmp_path, reason):
    import sys

    from tests.support.candidate_i_probe_watchdog import run_owned_probe

    trace = tmp_path / "trace.jsonl"
    code = (
        "import json,pathlib,sys,time; "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps("
        "{'event':'resource_observation_error','reason':sys.argv[2],"
        "'pressure':4,'i_rss':2,'controller_rss':3,'mps_driver_bytes':17,'swapouts_delta':0})+'\\n'); "
        "time.sleep(10)"
    )
    result = run_owned_probe(
        [sys.executable, "-B", "-c", code, str(trace), reason],
        tmp_path / "worker.log",
        trace,
        2,
        {
            "resource_policy": "scenario_suitability_v1",
            "i_rss_bytes": 10,
            "backend_rss_bytes": 10,
            "combined_rss_bytes": 15,
        },
    )
    assert result["stop_reason"] == (
        reason if reason != "SECRET_REASON" else "RESOURCE_OBSERVATION_ERROR"
    )
    assert result["exit_code"] == -9
    assert result["termination_action"] == "SIGKILL_OWNED_GROUP"
    assert result["stop_sample"]["mps_driver_bytes"] == 17
    assert "SECRET" not in (tmp_path / "worker.log").read_text()
