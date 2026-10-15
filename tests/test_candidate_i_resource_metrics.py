import json
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from tests.support import candidate_i_runtime_probe as probe
from tests.support.candidate_i_resource_metrics import sample_mps


def test_admission_requires_successful_live_resource_sampler():
    event = threading.Event()
    live = SimpleNamespace(is_alive=lambda: True)
    with pytest.raises(AssertionError, match="not ready"):
        probe.require_resource_sample(event, live, [], timeout=0)
    event.set()
    probe.require_resource_sample(event, live, [], timeout=0)
    with pytest.raises(AssertionError, match="stopped"):
        probe.require_resource_sample(event, SimpleNamespace(is_alive=lambda: False), [], timeout=0)
    with pytest.raises(AssertionError, match="RESOURCE_CEILING"):
        probe.require_resource_sample(event, live, ["RESOURCE_CEILING"], timeout=0)


def test_telemetry_before_torch_import_does_not_initialize_it():
    assert sample_mps(None) == {"status": "not_imported"}


def test_telemetry_reports_active_driver_and_recommended_memory_separately():
    module = SimpleNamespace(
        mps=SimpleNamespace(
            current_allocated_memory=lambda: 11,
            driver_allocated_memory=lambda: 21,
            recommended_max_memory=lambda: 31,
        )
    )
    assert sample_mps(module) == {
        "status": "ok",
        "active_bytes": 11,
        "driver_bytes": 21,
        "recommended_bytes": 31,
    }


def test_partial_torch_import_is_explicitly_unavailable():
    assert sample_mps(SimpleNamespace()) == {
        "status": "unavailable",
        "error_type": "AttributeError",
    }


def test_old_mps_api_preserves_available_allocation_counters():
    module = SimpleNamespace(
        mps=SimpleNamespace(current_allocated_memory=lambda: 11, driver_allocated_memory=lambda: 21)
    )
    assert sample_mps(module) == {
        "status": "partial",
        "active_bytes": 11,
        "driver_bytes": 21,
        "errors": {"recommended_bytes": "AttributeError"},
    }


def test_existing_host_trace_blocks_before_server_launch(tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"max_model_calls": 8}))
    assembly = tmp_path / "assembly.json"
    assembly.write_text(
        json.dumps({"runtime_root": str(tmp_path), "files": {"runtime_profile": str(profile)}})
    )
    (tmp_path / "host-footprint-20261008.jsonl").write_text("preserved trace\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe",
            "--assembly",
            str(assembly),
            "--i-python",
            "unused",
            "--models",
            "unused",
            "--started-at",
            str(time.time()),
            "--initial-model-calls",
            "0",
            "--swapouts-baseline",
            "0",
            "--cold-only",
            "--mps-footprint",
        ],
    )

    def forbidden_launch(*args, **kwargs):
        raise AssertionError("server launched before trace startup validation")

    monkeypatch.setattr(probe.subprocess, "Popen", forbidden_launch)
    with pytest.raises(FileExistsError):
        probe.main()
    assert (tmp_path / "host-footprint-20261008.jsonl").read_text() == "preserved trace\n"
