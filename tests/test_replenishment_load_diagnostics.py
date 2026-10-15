"""Load instrumentation preserves model calls and keeps bounded private evidence."""

import json
from collections import Counter
from threading import RLock

import pytest

from product_search.infrastructure.replenishment_load_diagnostics import LoadDiagnostics


def spy_recorder():
    recorder = LoadDiagnostics.__new__(LoadDiagnostics)
    recorder._calls = Counter()
    recorder._lock = RLock()
    events = []
    recorder.emit = lambda step, phase, call: events.append((step, phase, call))
    return recorder, events


def test_wrap_preserves_result_arguments_and_records_both_boundaries():
    recorder, events = spy_recorder()
    result = object()
    inputs = []

    def predict(*args, **kwargs):
        inputs.append((args, kwargs))
        return result

    wrapped = recorder.wrap("gdino.predict", predict)
    assert wrapped("private-photo", threshold=0.3) is result
    assert inputs == [(("private-photo",), {"threshold": 0.3})]
    assert events == [("gdino.predict", "before", 1), ("gdino.predict", "after", 1)]
    wrapped("another-photo")
    assert events[-2:] == [("gdino.predict", "before", 2), ("gdino.predict", "after", 2)]


def test_wrap_keeps_original_exception_and_marks_error_without_message():
    recorder, events = spy_recorder()
    original = ValueError("private secret")

    def fail():
        raise original

    with pytest.raises(ValueError) as caught:
        recorder.wrap("sam.predict", fail)()
    assert caught.value is original
    assert events == [("sam.predict", "before", 1), ("sam.predict", "error", 1)]


def test_private_records_numeric_metrics_only_and_respects_cap(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "load.jsonl"
    recorder = LoadDiagnostics(
        path,
        sample=lambda: {"mps_live_bytes": 10, "mps_driver_bytes": 25, "secret": "/private/photo"},
        max_bytes=700,
    )
    assert recorder.emit("gdino.predict", "before", 1)
    first = path.read_bytes()
    assert b"secret" not in first and b"/private/photo" not in first
    record = json.loads(first)
    assert record["metrics"] == {"mps_live_bytes": 10, "mps_driver_bytes": 25}
    assert isinstance(record["monotonic"], float) and isinstance(record["wall_time"], float)
    assert path.stat().st_mode & 0o777 == 0o600
    for _ in range(20):
        recorder.emit("gdino.predict", "after", 1)
    assert recorder.incomplete and path.stat().st_size <= 700
    recorder.close()


def test_refuses_existing_file_and_symlink(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "load.jsonl"
    path.write_text("existing")
    with pytest.raises(FileExistsError):
        LoadDiagnostics(path, sample=dict, max_bytes=1000)
    path.unlink()
    target = tmp_path / "target"
    target.write_text("protected")
    path.symlink_to(target)
    with pytest.raises(OSError):
        LoadDiagnostics(path, sample=dict, max_bytes=1000)
    assert target.read_text() == "protected"


def test_sample_failure_is_recorded_as_incomplete_and_does_not_change_result(tmp_path):
    tmp_path.chmod(0o700)

    def unavailable():
        raise RuntimeError("private path")

    recorder = LoadDiagnostics(tmp_path / "load.jsonl", sample=unavailable, max_bytes=4000)
    assert recorder.wrap("sam.predict", lambda: 42)() == 42
    recorder.close()
    rows = [json.loads(line) for line in (tmp_path / "load.jsonl").read_text().splitlines()]
    assert recorder.incomplete and all(row["measurement_ok"] is False for row in rows)
    assert "private path" not in (tmp_path / "load.jsonl").read_text()


def test_metrics_include_only_owned_processes_and_parse_cpu_and_swap():
    from types import SimpleNamespace

    from product_search.infrastructure.replenishment_load_diagnostics import mac_process_sample

    replies = {
        "/bin/ps": "10 8 100 0:02.50\n20 20 200 1:02.00\n21 20 30 0:00.10\n99 99 9999 2:00.00\n",
        "/usr/bin/vm_stat": "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 10.\nPages inactive: 20.\nPageouts: 30.\n",
    }

    def command(argv, **kwargs):
        if argv[-1] == "vm.swapusage":
            return SimpleNamespace(stdout="total = 1024.00M used = 2.50M free = 1021.50M")
        return SimpleNamespace(stdout=replies.get(argv[0], "2"))

    sample = mac_process_sample(10, 20, command=command)
    assert sample["measurement_ok"]
    assert [p["pid"] for p in sample["processes"]] == [10, 20, 21]
    assert [p["role"] for p in sample["processes"]] == ["controller", "worker", "owned_child"]
    assert sample["processes"][1]["cpu_seconds"] == 62
    assert sample["swap_used_bytes"] == 2621440 and sample["free_bytes"] == 163840


def test_missing_process_measurement_is_unknown_not_zero():
    from types import SimpleNamespace

    from product_search.infrastructure.replenishment_load_diagnostics import mac_process_sample

    sample = mac_process_sample(10, command=lambda *a, **k: SimpleNamespace(stdout=""))
    assert sample == {"measurement_ok": False}


def test_instrumentation_restores_methods_even_after_failure():
    from product_search.infrastructure.replenishment_load_diagnostics import instrument_localizer

    class Fake:
        def build_model(self):
            return "loaded"

        def predict(self, **kwargs):
            return kwargs

        def predict_batch(self):
            return "masks"

        def __call__(self):
            return "photo"

    classes = [type(str(i), (Fake,), {}) for i in range(4)]
    before = [cls.predict for cls in classes]
    recorder, events = spy_recorder()
    with pytest.raises(ValueError), instrument_localizer(recorder, *classes):
        assert classes[0]().predict(threshold=0.3) == {"threshold": 0.3}
        assert classes[1]().predict_batch() == "masks"
        raise ValueError("same failure")
    assert [cls.predict for cls in classes] == before
    assert events == [
        ("gdino.predict", "before", 1),
        ("gdino.predict", "after", 1),
        ("sam.predict", "before", 1),
        ("sam.predict", "after", 1),
    ]


def test_resource_diagnostics_preserve_guard_and_throttle_extra_sampling():
    from types import SimpleNamespace

    from product_search.infrastructure.replenishment_load_diagnostics import ResourceDiagnostics

    now = [0.0]
    calls = []
    status = object()

    class Observe:
        def __call__(self):
            return status

        def close(self):
            calls.append("closed")

    recorder = SimpleNamespace(
        emit=lambda *a: calls.append(a), close=lambda: calls.append("sink_closed")
    )
    wrapped = ResourceDiagnostics(Observe(), recorder, clock=lambda: now[0])
    assert wrapped() is status and wrapped() is status
    now[0] = 1.0
    assert wrapped() is status
    wrapped.close()
    assert calls == [
        ("resources", "sample", 0),
        ("resources", "sample", 0),
        "closed",
        "sink_closed",
    ]


@pytest.mark.parametrize("empty_cache", [False, True])
def test_native_localizer_wires_measurements_without_sdk_or_socket(
    tmp_path, monkeypatch, empty_cache
):
    import socket
    import sys
    from types import ModuleType, SimpleNamespace

    import uvicorn

    from product_search.infrastructure.replenishment_worker_entry import _serve_localization
    from services.candidate_i import binding as binding_module
    from services.candidate_i import bootstrap

    class Gdino:
        def build_model(self):
            return None

        def predict(self):
            return "boxes"

    class Sam:
        def build_model(self):
            return None

        def predict_batch(self):
            return "masks"

    class Binding:
        def __call__(self):
            return Gdino().predict(), Sam().predict_batch()

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def bind(self, value):
            assert value == ("127.0.0.1", 0)

        def listen(self, value):
            return None

        def getsockname(self):
            return ("127.0.0.1", 12345)

    class Server:
        def __init__(self, config):
            pass

        def run(self, **kwargs):
            assert Binding()() == ("boxes", "masks")

    for name, attribute, cls in [
        ("lang_sam.models.gdino", "GDINO", Gdino),
        ("lang_sam.models.sam", "SAM", Sam),
    ]:
        module = ModuleType(name)
        setattr(module, attribute, cls)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(binding_module, "CandidateIBinding", Binding)
    monkeypatch.setattr(bootstrap, "assemble_service", lambda *a, **k: object())
    monkeypatch.setattr(socket, "socket", FakeSocket)
    monkeypatch.setattr(uvicorn, "Config", lambda *a, **k: object())
    monkeypatch.setattr(uvicorn, "Server", Server)
    recorder, events = spy_recorder()
    cache_calls = []
    tmp_path.chmod(0o700)
    _serve_localization(
        {"shared_runtime_root": str(tmp_path), "control_root": str(tmp_path), "nonce": "a" * 64},
        SimpleNamespace(stop_grace_seconds=1),
        {
            "i_manifest": {},
            "i_files": {
                "model/gdino/config.json": str(tmp_path / "gdino/config.json"),
                "model/sam": str(tmp_path / "sam.pt"),
            },
        },
        SimpleNamespace(check_owner=lambda *a: True),
        object(),
        diagnostics=recorder,
        cache_cleanup=(lambda: cache_calls.append("cache")) if empty_cache else None,
    )
    expected = [
        ("langsam.import", "before"),
        ("langsam.import", "after"),
        ("localizer.photo", "before"),
        ("gdino.predict", "before"),
        ("gdino.predict", "after"),
        ("sam.predict", "before"),
        ("sam.predict", "after"),
    ]
    if empty_cache:
        expected.extend([("mps.empty_cache", "before"), ("mps.empty_cache", "after")])
    expected.append(("localizer.photo", "after"))
    assert [e[:2] for e in events] == expected
    assert cache_calls == (["cache"] if empty_cache else [])
    assert Binding.__call__.__name__ == "__call__"
    assert "torch" not in sys.modules


def test_db_memory_sample_rejects_foreign_marker_and_reports_owned_container(tmp_path):
    from types import SimpleNamespace

    from product_search.infrastructure.replenishment_load_diagnostics import db_memory_sample

    tmp_path.chmod(0o700)
    target = tmp_path / "target.json"
    target.write_text(
        json.dumps({"container_id": "a" * 64, "marker": "owned", "config": {"password": "private"}})
    )
    target.chmod(0o600)
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout="owned\n" if "inspect" in argv else "12.5MiB / 512MiB\n")

    assert db_memory_sample(target, "owned", command=command) == 13107200
    assert len(calls) == 2 and all("private" not in str(a) for a in calls)
    calls.clear()
    assert db_memory_sample(target, "foreign", command=command) is None
    assert not calls


def test_after_photo_cleanup_runs_once_after_success_and_preserves_arguments_and_result():
    from product_search.infrastructure.replenishment_load_diagnostics import after_success

    events = []
    result = object()

    def photo(value, *, threshold):
        events.extend(["pass1", "pass2"])
        assert value == "private-photo" and threshold == 0.3
        return result

    wrapped = after_success(photo, lambda: events.append("empty_cache"))
    assert wrapped("private-photo", threshold=0.3) is result
    assert events == ["pass1", "pass2", "empty_cache"]


def test_after_photo_cleanup_does_not_run_on_model_failure():
    from product_search.infrastructure.replenishment_load_diagnostics import after_success

    error = ValueError("private model error")
    calls = []

    def fail():
        raise error

    with pytest.raises(ValueError) as caught:
        after_success(fail, lambda: calls.append("cache"))()
    assert caught.value is error and calls == []


def test_cache_failure_is_not_hidden_as_a_successful_experiment():
    from product_search.infrastructure.replenishment_load_diagnostics import after_success

    error = RuntimeError("private cache failure")

    def unavailable():
        raise error

    with pytest.raises(RuntimeError) as caught:
        after_success(lambda: 42, unavailable)()
    assert caught.value is error


def test_cache_cleanup_policy_is_opt_in_and_requires_diagnostics():
    from product_search.infrastructure.replenishment_load_diagnostics import cache_cleanup_enabled
    from product_search.search.replenishment_contracts import ReplenishmentError

    assert cache_cleanup_enabled({}) is False
    assert cache_cleanup_enabled({"empty_cache_after_photo": False}) is False
    assert (
        cache_cleanup_enabled({"empty_cache_after_photo": True, "load_diagnostics": True}) is True
    )
    for binding in [
        {"empty_cache_after_photo": True},
        {"empty_cache_after_photo": "true", "load_diagnostics": True},
    ]:
        with pytest.raises(ReplenishmentError, match="RUNTIME_MISMATCH"):
            cache_cleanup_enabled(binding)


def test_rotation_keeps_recent_records_with_bounded_private_files(tmp_path):
    tmp_path.chmod(0o700)
    recorder = LoadDiagnostics(tmp_path / "load.jsonl", sample=dict, max_bytes=512, backups=2)
    for number in range(20):
        assert recorder.emit("resources", "sample", number)
    recorder.close()
    logs = list(tmp_path.glob("*.jsonl"))
    assert len(logs) == 3
    assert all(p.stat().st_size <= 512 and p.stat().st_mode & 0o777 == 0o600 for p in logs)
    retained = [json.loads(line)["call"] for p in logs for line in p.read_text().splitlines()]
    assert max(retained) == 19 and 0 not in retained
    status = json.loads((tmp_path / "load.status.json").read_text())
    assert status["history_truncated"] and status["rotations"] > 2
    assert not status["incomplete"]


def test_periodic_sampling_captures_during_long_operation_and_stops(tmp_path):
    from threading import Event

    tmp_path.chmod(0o700)
    observed = Event()
    recorder = LoadDiagnostics(
        tmp_path / "load.jsonl", sample=lambda: observed.set() or {}, max_bytes=4096
    )
    with recorder.periodic(interval_seconds=0.01):
        assert observed.wait(2), "measurement must happen before the operation ends"
    before = (tmp_path / "load.jsonl").read_bytes()
    recorder.close()
    assert before
    assert all(json.loads(line)["step"] == "resources" for line in before.splitlines())
    assert not recorder.incomplete


def test_worker_sample_before_sdk_does_not_fabricate_mps_zero(monkeypatch):
    from product_search.infrastructure import replenishment_load_diagnostics as module

    monkeypatch.setattr(module, "mac_process_sample", lambda *a: {"pressure": 1})
    assert module.worker_sample(None) == {"pressure": 1}


def test_worker_diagnostics_records_import_failure_without_replacing_it(tmp_path):
    from product_search.infrastructure.replenishment_load_diagnostics import worker_diagnostics

    tmp_path.chmod(0o700)
    original = RuntimeError("private details")
    with (
        pytest.raises(RuntimeError) as caught,
        worker_diagnostics(
            {"load_diagnostics": True}, tmp_path / "load.jsonl", sample=dict, max_bytes=4096
        ) as recorder,
    ):
        assert recorder is not None
        recorder.wrap("torch.import", lambda: (_ for _ in ()).throw(original))()
    assert caught.value is original
    rows = [json.loads(line) for line in (tmp_path / "load.jsonl").read_text().splitlines()]
    assert [(r["step"], r["phase"]) for r in rows] == [
        ("worker", "before"),
        ("torch.import", "before"),
        ("torch.import", "error"),
        ("worker", "error"),
    ]
    assert "private details" not in (tmp_path / "load.jsonl").read_text()


@pytest.mark.parametrize("value", [True, 0, -1, "1", 2])
def test_worker_diagnostics_rejects_invalid_interval_before_measurement(tmp_path, value):
    from product_search.infrastructure.replenishment_load_diagnostics import worker_diagnostics
    from product_search.search.replenishment_contracts import ReplenishmentError

    with (
        pytest.raises(ReplenishmentError, match="RUNTIME_MISMATCH"),
        worker_diagnostics(
            {"load_diagnostics": True, "diagnostic_interval_seconds": value},
            tmp_path / "load.jsonl",
            sample=lambda: pytest.fail("must not sample"),
            max_bytes=4096,
        ),
    ):
        pytest.fail("invalid diagnostic interval admitted")


def test_logging_unavailable_does_not_prevent_worker_result(tmp_path, monkeypatch):
    from product_search.infrastructure import replenishment_load_diagnostics as module

    def unavailable(*args, **kwargs):
        raise OSError("disk full private details")

    monkeypatch.setattr(module, "LoadDiagnostics", unavailable)
    with module.worker_diagnostics(
        {"load_diagnostics": True}, tmp_path / "load.jsonl", sample=dict, max_bytes=4096
    ) as recorder:
        assert recorder is None
        result = "processed"
    assert result == "processed"


def test_disabled_worker_diagnostics_creates_no_files_or_samples(tmp_path):
    from product_search.infrastructure.replenishment_load_diagnostics import worker_diagnostics

    with worker_diagnostics(
        {"load_diagnostics": False},
        tmp_path / "load.jsonl",
        sample=lambda: pytest.fail("disabled sampler ran"),
        max_bytes=4096,
    ) as recorder:
        assert recorder is None
    assert list(tmp_path.iterdir()) == []


def test_unavailable_logging_preserves_cache_cleanup_precondition(tmp_path, monkeypatch):
    from product_search.infrastructure import replenishment_load_diagnostics as module

    original = OSError("unavailable private sink")

    def unavailable(*args, **kwargs):
        raise original

    monkeypatch.setattr(module, "LoadDiagnostics", unavailable)
    with (
        pytest.raises(OSError) as caught,
        module.worker_diagnostics(
            {"load_diagnostics": True, "empty_cache_after_photo": True},
            tmp_path / "load.jsonl",
            sample=dict,
            max_bytes=4096,
        ),
    ):
        pytest.fail("cache experiment requires its diagnostic sink")
    assert caught.value is original
