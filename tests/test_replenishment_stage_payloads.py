"""Checkpoint binding with fake SDK outputs and real private artifact files."""

import json
from dataclasses import replace

from product_search.infrastructure.replenishment_artifacts import CheckpointFiles
from product_search.search.nail_contracts import (
    BinaryMask,
    EmbeddingProfile,
    LocalizedRegion,
    NailLocalization,
    PhotoInput,
)
from product_search.search.replenishment_contracts import CheckpointReceipt, SavedCheckpoint
from tests.test_nail_image_processor import processor
from tests.test_replenishment_artifacts import attempt
from tests.test_replenishment_contracts import package


def test_crop_checkpoint_is_the_only_input_of_selected_encoder(tmp_path):
    from product_search.infrastructure.replenishment_workers import (
        encode_checkpoint,
        localization_files,
    )

    tmp_path.chmod(0o700)
    files = CheckpointFiles(tmp_path)
    pkg = package(max_vector_bytes=20000)
    mask = BinaryMask(3, 2, b"\xff" * 6)
    processed = processor(
        NailLocalization("OK", (LocalizedRegion(1, "nail", 1.0, (0.0, 0.0, 3.0, 2.0), mask),))
    ).process(PhotoInput(1, "a" * 32, "b" * 64))
    local = attempt("localization", "")
    output = files.write_staging(local, pkg, 1, localization_files(processed))
    files.verify(local, output, pkg)
    saved = SavedCheckpoint(
        local, output, CheckpointReceipt(local.attempt_ref, output.manifest_sha)
    )
    encoded = replace(attempt(), attempt_ref="encoder")
    calls = []

    class Embedding:
        def encode(self, key, crops, profile):
            calls.append((key, crops))
            return ((0.25,) * 512,)

    profile = EmbeddingProfile(
        (("openclip_b32", "pin"), ("dinov2_b14", "pin"), ("siglip2_b16_224", "pin"))
    )
    result = encode_checkpoint(saved, encoded, pkg, files, Embedding(), profile)
    files.verify(encoded, result, pkg)
    payload = json.loads(files.read_files(encoded, result, pkg)["vectors.json"])
    assert payload["model_key"] == "openclip_b32"
    assert payload["vectors"][0]["values"] == [0.25] * 512
    assert calls == [("openclip_b32", (processed.regions[0].rgb_crop,))]


def test_native_worker_control_rejects_unapproved_grant_before_import(tmp_path):
    import pytest

    from product_search.infrastructure.replenishment_worker_entry import validate_control
    from product_search.search.replenishment_contracts import ReplenishmentError

    tmp_path.chmod(0o700)
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        validate_control({"status": "PENDING_OWNER_APPROVAL"})


def test_native_driver_prepares_exact_private_child_control_without_starting_sdk(tmp_path):
    import hashlib
    import sys
    import time
    from dataclasses import asdict
    from pathlib import Path

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.replenishment_cli import private_json
    from product_search.infrastructure.replenishment_runtime_binding import FreshGrant, canonical
    from product_search.infrastructure.replenishment_supervisor import ModeLease
    from product_search.infrastructure.replenishment_workers import NativeStageDriver
    from product_search.search.replenishment_contracts import Ownership

    tmp_path.chmod(0o700)
    profile = {"schema_version": 1, "crop_version": "test", "models": []}
    binding = {
        "shared_runtime_root": str(tmp_path),
        "interpreters": {"encoder": sys.executable, "localization": sys.executable},
        "frozen_input_root": str(tmp_path),
    }
    code = {
        "src/product_search/infrastructure/replenishment_workers.py": hashlib.sha256(
            Path("src/product_search/infrastructure/replenishment_workers.py").read_bytes()
        ).hexdigest()
    }
    pkg = package(
        code_sha=hashlib.sha256(canonical(code)).hexdigest(),
        runtime_sha=hashlib.sha256(canonical(binding)).hexdigest(),
        semantic_profile_sha=hashlib.sha256(canonical(profile)).hexdigest(),
    )
    for name, value in [("profile.json", profile), ("binding.json", binding), ("code.json", code)]:
        publish_private_json(tmp_path / name, value)
    publish_private_json(
        tmp_path / "grant.json",
        {
            "schema_version": 1,
            "status": "APPROVED_BY_OWNER",
            "nonce": "a" * 64,
            "package_sha": FreshGrant.package_sha(pkg),
            "scope": pkg.scope,
            "expires_at": time.time() + 60,
            "search_authorized": False,
        },
    )
    grant = FreshGrant(tmp_path / "grant.json")
    owner = Ownership("run", "token", 1)
    grant.consume(owner, pkg)
    files = CheckpointFiles(tmp_path)
    driver = NativeStageDriver(
        tmp_path,
        grant,
        tmp_path / "binding.json",
        tmp_path / "code.json",
        tmp_path / "profile.json",
        files,
        object(),
    )
    import pytest

    from product_search.infrastructure.nail_runtime import FileLease
    from product_search.infrastructure.replenishment_worker_entry import validate_control
    from product_search.search.replenishment_contracts import ReplenishmentError

    coordinator = FileLease(tmp_path, "coordinator.lock")
    assert coordinator.try_acquire()
    driver.inherited_fds = (coordinator._fd,)
    with ModeLease(tmp_path) as lease:
        argv = driver.command(
            "embedding", "openclip_b32", owner, pkg, time.monotonic() + 10, lease.fd
        )
        assert argv[:3] == (sys.executable, "-I", "-B")
        assert argv[3].endswith("/scripts/run_replenishment_worker.py")
        control = private_json(argv[4])
        assert control["package"] == asdict(pkg)
        assert control["owner"] == asdict(owner)
        assert control["lease_fd"] == lease.fd
        assert control["model_key"] == "openclip_b32"
        assert not (Path(control["control_root"]) / "stage.claim").exists()
        expanded = {**control, "end_at": time.monotonic() + pkg.overall_seconds + 1}
        with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
            validate_control(expanded)
        assert not (Path(control["control_root"]) / "stage.claim").exists()
        validated, current_owner, current_binding = validate_control(control)
        assert (validated, current_owner, current_binding) == (pkg, owner, binding)
        with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
            validate_control(control)
    coordinator.release()


def test_encoder_job_cannot_change_the_frozen_stage(tmp_path):
    import pytest

    from product_search.infrastructure.replenishment_worker_entry import handle_embedding_job
    from product_search.search.replenishment_contracts import ReplenishmentError

    control = {"model_key": "openclip_b32", "nonce": "current", "end_at": 100.0}
    job = {"nonce": "old", "attempt": {}, "saved": {}, "end_at": 99.0}
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        handle_embedding_job(control, job, package(), object(), object(), object())


def test_native_entry_never_imports_sdk_from_a_permission_proposal(tmp_path):
    import pytest

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.replenishment_worker_entry import run_native
    from product_search.search.replenishment_contracts import ReplenishmentError

    tmp_path.chmod(0o700)
    path = tmp_path / "control.json"
    publish_private_json(path, {"status": "PENDING_OWNER_APPROVAL"})
    imports = []
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        run_native(path, importer=lambda name: imports.append(name))
    assert imports == []


def test_known_localization_failure_is_photo_error_but_timeout_requires_recovery():
    import pytest

    from product_search.infrastructure.replenishment_workers import NativeStageDriver
    from product_search.search.nail_contracts import NailProcessingError
    from product_search.search.replenishment_contracts import (
        PhotoProcessingError,
        ReplenishmentError,
    )

    driver = NativeStageDriver.__new__(NativeStageDriver)

    def invalid(*args):
        raise NailProcessingError("INVALID_OUTPUT")

    driver._localize = invalid
    with pytest.raises(PhotoProcessingError, match="INVALID_OUTPUT"):
        driver.exchange(None, attempt("localization", ""), 100.0)

    def timeout(*args):
        raise NailProcessingError("MODEL_ERROR", reason="LOCALIZATION_TIMEOUT")

    driver._localize = timeout
    with pytest.raises(ReplenishmentError, match="RECOVERY_REQUIRED"):
        driver.exchange(None, attempt("localization", ""), 100.0)


def test_native_invalid_image_is_photo_error_but_legacy_reader_stays_terminal(tmp_path):
    import hashlib
    from types import SimpleNamespace

    import pytest

    from product_search.infrastructure.nail_build_runner import BuildStop, ManifestImageStore
    from product_search.infrastructure.replenishment_workers import NativeStageDriver
    from product_search.search.nail_contracts import DecodeProfile
    from product_search.search.replenishment_contracts import PhotoProcessingError

    tmp_path.chmod(0o700)
    path = tmp_path / "bad.jpg"
    path.write_bytes(b"not an encoded image")
    path.chmod(0o600)
    selected = PhotoInput(1, "a" * 32, hashlib.sha256(path.read_bytes()).hexdigest())
    store = ManifestImageStore(tmp_path, {selected.source_ref: path.name}, None)
    profile = DecodeProfile(1000, 10000)
    with pytest.raises(BuildStop, match="INVALID_SOURCE"):
        store.read_rgb(selected, profile)
    driver = NativeStageDriver.__new__(NativeStageDriver)
    driver._localize = lambda *args: store.read_rgb(selected, profile)
    with pytest.raises(PhotoProcessingError, match="INVALID_IMAGE"):
        driver.exchange(None, SimpleNamespace(stage_key="localization"), 10)


def test_native_source_integrity_error_still_stops_whole_run(tmp_path):
    from types import SimpleNamespace

    import pytest

    from product_search.infrastructure.nail_build_runner import BuildStop, ManifestImageStore
    from product_search.infrastructure.replenishment_workers import NativeStageDriver
    from product_search.search.nail_contracts import DecodeProfile

    tmp_path.chmod(0o700)
    path = tmp_path / "changed.jpg"
    path.write_bytes(b"not an encoded image")
    path.chmod(0o600)
    selected = PhotoInput(1, "a" * 32, "0" * 64)
    store = ManifestImageStore(tmp_path, {selected.source_ref: path.name}, None)
    driver = NativeStageDriver.__new__(NativeStageDriver)
    driver._localize = lambda *args: store.read_rgb(selected, DecodeProfile(1000, 10000))
    with pytest.raises(BuildStop, match="SOURCE_HASH_MISMATCH"):
        driver.exchange(None, SimpleNamespace(stage_key="localization"), 10)
