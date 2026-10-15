import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from product_search.infrastructure.nail_runtime import FileLease
from product_search.infrastructure.nail_wire import WireLimits
from product_search.search.nail_contracts import NailLocalization
from services.candidate_i.settings import ServiceSettings
from tests.test_candidate_i_http_service import FP, app, multipart, success


def test_device_lease_conflicts_and_coordinator_is_distinct(tmp_path):
    first, second = FileLease(tmp_path, "device.lock"), FileLease(tmp_path, "device.lock")
    coordinator = FileLease(tmp_path, "coordinator.lock")
    assert first.try_acquire()
    try:
        assert not second.try_acquire()
        assert coordinator.try_acquire()
    finally:
        first.release()
        second.release()
        coordinator.release()
    assert second.try_acquire()
    second.release()


def test_device_lease_is_shared_across_processes(tmp_path):
    lease = FileLease(tmp_path, "device.lock")
    assert lease.try_acquire()
    source = "from pathlib import Path; from product_search.infrastructure.nail_runtime import FileLease; import sys; x=FileLease(Path(sys.argv[1]), 'device.lock'); print('acquired' if x.try_acquire() else 'blocked'); x.release()"
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-c", source, str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        assert result.stdout.strip() == "blocked"
    finally:
        lease.release()


def test_lock_symlink_is_rejected_without_touching_target(tmp_path):
    target = tmp_path / "untouched"
    target.write_text("safe")
    (tmp_path / "device.lock").symlink_to(target)
    with pytest.raises(ValueError):
        FileLease(tmp_path, "device.lock").try_acquire()
    assert target.read_text() == "safe"


def test_public_runtime_root_is_rejected(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError):
        FileLease(tmp_path, "device.lock")
    with pytest.raises(ValueError):
        ServiceSettings(FP, WireLimits(100, 2, 1024), tmp_path)


@pytest.mark.parametrize("values", [(0, 1, 1024), (True, 1, 1024), (100, 0, 1024), (100, 1, -1)])
def test_missing_or_nonpositive_limits_are_not_ready_configuration(values):
    with pytest.raises(ValueError):
        WireLimits(*values)


def test_native_binding_does_not_block_health_and_second_admission(tmp_path):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def bind(image, profile):
        entered.set()
        release.wait(5)
        finished.set()
        return success(image, profile)

    with TestClient(app(tmp_path, bind)) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, "/v1/localizations", files=multipart())
        assert entered.wait(2)
        try:
            health = client.get("/health/ready")
            assert health.json()["busy"] is True
            assert not finished.is_set()
            second = client.post("/v1/localizations", files=multipart())
            assert second.status_code == 503
            assert second.json()["code"] == "BUSY"
        finally:
            release.set()
        assert first.result(timeout=2).status_code == 200


def test_service_respects_device_guard_but_does_not_reacquire_coordinator(tmp_path):
    device = FileLease(tmp_path, "device.lock")
    coordinator = FileLease(tmp_path, "coordinator.lock")
    calls = []

    def bind(image, profile):
        calls.append(image)
        return NailLocalization("NO_NAILS", ())

    with TestClient(app(tmp_path, bind)) as client:
        assert device.try_acquire()
        try:
            assert client.post("/v1/localizations", files=multipart()).status_code == 503
            assert not calls
        finally:
            device.release()
        assert coordinator.try_acquire()
        try:
            assert client.post("/v1/localizations", files=multipart()).status_code == 200
        finally:
            coordinator.release()
