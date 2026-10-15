import hashlib
import json
import platform
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from product_search.search.nail_contracts import NailProcessingError
from services.candidate_i.bootstrap import assemble_service
from tests.nail_localization.test_langsam_adapter_contract import LOCK_BYTES, frozen_config


def bootstrap_inputs(tmp_path):
    config = json.loads(json.dumps(frozen_config().data, default=dict))
    config.update(device="mps", python_version=platform.python_version())
    del config["config_fingerprint"]
    config["config_fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
    )
    gdino = tmp_path / "gdino"
    gdino.mkdir()
    sam = tmp_path / "sam.pt"
    sam.write_bytes(b"synthetic")
    files = {"model/sam": sam}
    for name in (
        "config.json",
        "model.safetensors",
        "preprocessor_config.json",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    ):
        path = gdino / name
        path.write_bytes(b"synthetic")
        files["model/gdino/" + name] = path
    data = {
        "config": json.dumps(config).encode(),
        "lock": LOCK_BYTES,
        "contract": b"synthetic contract",
        "runtime_profile": json.dumps(
            {
                "max_decoded_pixels": 10000,
                "max_region_count": 10,
                "max_response_bytes": 1000000,
                "dtype": "float32",
            }
        ).encode(),
    }
    for name, content in data.items():
        path = tmp_path / name
        path.write_bytes(content)
        files[name] = path
    code = Path(__file__).parents[1]
    for relative in (
        "services/candidate_i/app.py",
        "services/candidate_i/settings.py",
        "services/candidate_i/binding.py",
        "services/candidate_i/readiness.py",
        "services/candidate_i/bootstrap.py",
        "experiments/nail_localization/config.py",
        "experiments/nail_localization/contracts.py",
        "experiments/nail_localization/langsam_adapter.py",
        "experiments/nail_localization/roi.py",
        "experiments/nail_localization/roi_localizer.py",
        "src/product_search/search/nail_contracts.py",
        "src/product_search/infrastructure/nail_wire.py",
        "src/product_search/infrastructure/nail_runtime.py",
    ):
        files["code/" + relative] = code / relative
    manifest = {
        "files": {
            name: {
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in files.items()
        },
        "packages": ["lang-sam==0.2.1", "sam-2==1.0", "synthetic-package==1.0.0"],
        "vcs": {"lang-sam": "a" * 40, "sam-2": "b" * 40},
        "runtime": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "device": "mps",
            "dtype": "float32",
            "operator_fallback": None,
        },
    }
    return manifest, files, gdino, sam


def test_assembly_uses_verified_fingerprint_and_remains_model_free(tmp_path):
    manifest, files, gdino, sam = bootstrap_inputs(tmp_path)
    app = assemble_service(
        manifest,
        files,
        runtime_root=tmp_path,
        gdino_snapshot_path=gdino,
        sam_checkpoint_path=sam,
        observe_inventory=lambda: manifest["packages"],
        observe_vcs=lambda: manifest["vcs"],
    )
    expected = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    with TestClient(app) as client:
        assert client.get("/health/ready").json()["extractor_fingerprint"] == expected
        files["runtime_profile"].write_bytes(b"modified limits")
        assert client.get("/health/ready").status_code == 503


def test_assembly_rejects_changed_config_before_model_load(tmp_path):
    manifest, files, gdino, sam = bootstrap_inputs(tmp_path)
    files["config"].write_bytes(b"modified config")
    with pytest.raises(NailProcessingError, match="MODEL_NOT_READY"):
        assemble_service(
            manifest,
            files,
            runtime_root=tmp_path,
            gdino_snapshot_path=gdino,
            sam_checkpoint_path=sam,
            observe_inventory=lambda: manifest["packages"],
            observe_vcs=lambda: manifest["vcs"],
        )


def test_assembly_rejects_model_path_unrelated_to_manifest(tmp_path):
    manifest, files, gdino, sam = bootstrap_inputs(tmp_path)
    other = tmp_path / "other.pt"
    other.write_bytes(sam.read_bytes())
    with pytest.raises(NailProcessingError, match="MODEL_NOT_READY"):
        assemble_service(
            manifest,
            files,
            runtime_root=tmp_path,
            gdino_snapshot_path=gdino,
            sam_checkpoint_path=other,
            observe_inventory=lambda: manifest["packages"],
            observe_vcs=lambda: manifest["vcs"],
        )
