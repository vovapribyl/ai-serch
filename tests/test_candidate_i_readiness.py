import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from product_search.infrastructure.nail_wire import WireLimits
from services.candidate_i.app import create_app
from services.candidate_i.readiness import VerifiedReadiness
from services.candidate_i.settings import ServiceSettings


def fixture(tmp_path):
    paths = {}
    entries = {}
    for name in ("contract", "lock", "config", "runtime_profile", "code/binding", "model/sam"):
        path = tmp_path / name.replace("/", "-")
        data = name.encode()
        path.write_bytes(data)
        paths[name] = path
        entries[name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest = {
        "files": entries,
        "packages": ["lang-sam==0.2.1", "sam-2==1.0", "torch==2.13.0"],
        "vcs": {"lang-sam": "a" * 40, "sam-2": "b" * 40},
        "runtime": {
            "python": "3.12.14", "machine": "arm64", "device": "mps",
            "dtype": "float32", "operator_fallback": None,
        },
    }
    actual = json.loads(json.dumps(manifest))
    ready = VerifiedReadiness(
        manifest,
        paths,
        observe_inventory=lambda: actual["packages"],
        observe_vcs=lambda: actual["vcs"],
        observe_runtime=lambda: actual["runtime"],
    )
    return ready, manifest, actual, paths


def test_verified_identity_is_derived_and_does_not_contain_paths(tmp_path):
    ready, manifest, _, _ = fixture(tmp_path)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert ready.extractor_fingerprint == hashlib.sha256(canonical).hexdigest()
    assert ready() is True


@pytest.mark.parametrize("change", ["package", "extra", "vcs", "runtime", "file", "missing"])
def test_changed_runtime_cannot_attest_ready(tmp_path, change):
    ready, _, actual, paths = fixture(tmp_path)
    assert ready() is True
    if change == "package":
        actual["packages"][-1] = "torch==2.4.1"
    elif change == "extra":
        actual["packages"].append("unexpected==1.0")
    elif change == "vcs":
        actual["vcs"]["lang-sam"] = "c" * 40
    elif change == "runtime":
        actual["runtime"]["operator_fallback"] = "1"
    elif change == "file":
        paths["model/sam"].write_bytes(b"replacement")
    else:
        paths["config"].unlink()
    assert ready() is False


def test_expected_manifest_cannot_be_mutated_after_construction(tmp_path):
    ready, manifest, actual, _ = fixture(tmp_path)
    fingerprint = ready.extractor_fingerprint
    manifest["packages"].append("unexpected==1.0")
    actual["packages"].append("unexpected==1.0")
    assert ready.extractor_fingerprint == fingerprint
    assert ready() is False


def test_unverified_runtime_blocks_health_and_post_before_binding(tmp_path):
    ready, _, _, paths = fixture(tmp_path)
    paths["lock"].write_bytes(b"wrong lock")
    calls = []
    settings = ServiceSettings(ready.extractor_fingerprint, WireLimits(100, 10, 10000), tmp_path)
    with TestClient(create_app(settings, lambda *args: calls.append(args), ready_check=ready)) as client:
        assert client.get("/health/ready").json()["ready"] is False
        response = client.post("/v1/localizations", content=b"synthetic malformed body")
        assert response.status_code == 503
        assert response.json()["code"] == "MODEL_NOT_READY"
    assert calls == []


def test_service_cannot_advertise_fingerprint_unrelated_to_verified_manifest(tmp_path):
    ready, _, _, _ = fixture(tmp_path)
    settings = ServiceSettings("0" * 64, WireLimits(100, 10, 10000), tmp_path)
    with TestClient(create_app(settings, lambda *args: None, ready_check=ready)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["ready"] is False
