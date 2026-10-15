"""Native B1 filesystem checks; no database receipt is manufactured here."""

import io
import json
import os
from dataclasses import replace

import pytest
from PIL import Image

from product_search.infrastructure.replenishment_artifacts import CheckpointFiles
from product_search.search.replenishment_contracts import ReplenishmentError, StageAttempt
from tests.test_replenishment_contracts import package


def attempt(stage="embedding", model="openclip_b32"):
    return StageAttempt("attempt-1", "photo-1", stage, model, "f" * 64, "revision-1", 1, 1, 1)


def vectors(values=None):
    return json.dumps(
        {
            "model_key": "openclip_b32",
            "vectors": [{"ordinal": 1, "values": [0.25] * 512 if values is None else values}],
        },
        separators=(",", ":"),
    ).encode()


def png(mode):
    image = Image.new(mode, (2, 2), 255 if mode == "L" else (255, 255, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def store(tmp_path):
    tmp_path.chmod(0o700)
    return CheckpointFiles(tmp_path)


def test_complete_vectors_are_verified_and_finalized_before_db_commit(store):
    work = attempt()
    output = store.write_staging(work, package(), 1, {"vectors.json": vectors()})
    store.verify(work, output, package())
    assert store.is_final(output)
    assert store.read_files(work, output, package()) == {"vectors.json": vectors()}
    # File readiness is not a DB COMPLETE receipt: adapter has no DB dependency.


def test_partial_or_corrupt_payload_cannot_be_finalized(store):
    work = attempt()
    output = store.write_staging(work, package(), 1, {"vectors.json": vectors()})
    store.staging_path(output).joinpath("vectors.json").write_bytes(b"partial")
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        store.verify(work, output, package())
    assert not store.is_final(output)


@pytest.mark.parametrize("values", [[0.0] * 511, [float("nan")] * 512, [True] * 512])
def test_vector_dimension_and_finite_numbers_are_checked(store, values):
    work = attempt()
    output = store.write_staging(work, package(), 1, {"vectors.json": vectors(values)})
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        store.verify(work, output, package())
    assert not store.is_final(output)


def test_manifest_cannot_be_reused_for_different_identity(store):
    work = attempt()
    output = store.write_staging(work, package(), 1, {"vectors.json": vectors()})
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        store.verify(replace(work, identity_sha="e" * 64), output, package())


def test_localization_requires_exact_crop_mask_pairs(store):
    work = attempt("localization", "")
    output = store.write_staging(work, package(), 1, {"crop-1.png": png("RGB")})
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        store.verify(work, output, package())


def test_valid_localization_and_no_nails_are_distinct(store):
    work = attempt("localization", "")
    output = store.write_staging(
        work, package(), 1, {"crop-1.png": png("RGB"), "mask-1.png": png("L")}
    )
    store.verify(work, output, package())
    assert store.is_final(output)
    empty = replace(work, attempt_ref="attempt-2")
    no_nails = store.write_staging(empty, package(), 0, {})
    store.verify(empty, no_nails, package())
    assert store.read_files(empty, no_nails, package()) == {}


def test_same_receipt_is_idempotent_and_other_bytes_cannot_overwrite_final(store):
    work = attempt()
    output = store.write_staging(work, package(), 1, {"vectors.json": vectors()})
    store.verify(work, output, package())
    store.verify(work, output, package())
    with pytest.raises(ReplenishmentError, match="ARTIFACT_CONFLICT"):
        store.write_staging(work, package(), 1, {"vectors.json": vectors([0.5] * 512)})
    assert store.read_files(work, output, package()) == {"vectors.json": vectors()}


def test_path_escape_and_symlinks_are_refused(store, tmp_path):
    with pytest.raises(ReplenishmentError):
        store.write_staging(attempt(), package(), 1, {"../escape": b"bad"})
    output = store.write_staging(attempt(), package(), 1, {"vectors.json": vectors()})
    payload = store.staging_path(output) / "vectors.json"
    payload.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(vectors())
    payload.symlink_to(outside)
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        store.verify(attempt(), output, package())


def test_sync_failure_cannot_be_reported_as_final(store, monkeypatch):
    output = store.write_staging(attempt(), package(), 1, {"vectors.json": vectors()})
    monkeypatch.setattr(
        os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("synthetic sync failure"))
    )
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        store.verify(attempt(), output, package())
    assert not store.is_final(output)


def test_huge_integer_vector_value_is_a_controlled_invalid_checkpoint(store):
    work = attempt()
    output = store.write_staging(
        work, package(), 1, {"vectors.json": vectors([10**400] + [0.0] * 511)}
    )
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        store.verify(work, output, package())


def test_rename_failure_leaves_uncommitted_staging(store, monkeypatch):
    output = store.write_staging(attempt(), package(), 1, {"vectors.json": vectors()})
    monkeypatch.setattr(
        os, "rename", lambda *args: (_ for _ in ()).throw(OSError("synthetic rename failure"))
    )
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        store.verify(attempt(), output, package())
    assert not store.is_final(output)
    assert store.staging_path(output).exists()


def test_parent_sync_failure_requires_successful_resync_before_file_verification(
    store, monkeypatch
):
    work = attempt()
    output = store.write_staging(work, package(), 1, {"vectors.json": vectors()})
    original = os.fsync
    parent_inode = (store.root / "final").stat().st_ino

    def failed_parent_sync(fd):
        if os.fstat(fd).st_ino == parent_inode:
            raise OSError("synthetic parent sync failure")
        original(fd)

    monkeypatch.setattr(os, "fsync", failed_parent_sync)
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        store.verify(work, output, package())
    assert store.is_final(output)  # Orphan files exist; no database COMPLETE has been committed.
    monkeypatch.setattr(os, "fsync", original)
    store.verify(work, output, package())
    assert store.read_files(work, output, package()) == {"vectors.json": vectors()}


def test_controller_commit_failure_leaves_orphan_files_without_photo_success(store):
    from product_search.search.corpus_replenishment import ReplenishmentController
    from product_search.search.replenishment_contracts import Ownership, PhotoOutcome
    from tests.test_replenishment_boundaries import Clock
    from tests.test_replenishment_controller import Progress, Workers
    from tests.test_replenishment_rules import photo

    queue = (photo(0),)
    events = []
    progress = Progress(queue, events)
    workers = Workers(events, progress)
    written = []

    def process(work, stage_attempt, owner, end_at):
        output = store.write_staging(
            stage_attempt, package(), 1, {"crop-1.png": png("RGB"), "mask-1.png": png("L")}
        )
        written.append(output)
        return output

    def unknown_commit(*args):
        raise ReplenishmentError("CHECKPOINT_UNKNOWN")

    workers.process = process
    progress.commit_checkpoint = unknown_commit
    controller = ReplenishmentController(progress, store, workers, Clock(10))
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_UNKNOWN"):
        controller.run(queue, package(), Ownership("run-1", "token-1", 1))
    assert store.is_final(written[0])
    assert progress.outcomes["photo-0"] == PhotoOutcome.PENDING
    assert progress.checkpoints == {}
    assert events[-1] == ("close", "localization", "")
