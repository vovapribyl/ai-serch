import os
from uuid import uuid4

import psycopg
import pytest

from product_search.infrastructure.nail_repository import PostgresNailCatalog
from product_search.search.nail_contracts import (
    BinaryMask,
    BuildIdentity,
    BuildPhoto,
    BuildPhotoResult,
    ModelIdentity,
    NailProcessingError,
    PhotoEmbeddings,
    PhotoInput,
    ProcessedPhoto,
    RegionArtifacts,
    RegionCrop,
    RgbImage,
)
from tests.support.nail_db import disposable_database, migrate


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    if os.environ.get("CANDIDATE_I_SYNTHETIC_DB_TESTS") != "yes":
        pytest.skip("Owned synthetic DB opt-in required")
    with disposable_database(tmp_path_factory.mktemp("nail-repo-db")) as (config, marker):
        result = migrate(config, marker, "upgrade", "head")
        assert result.returncode == 0, result.stderr
        yield config


@pytest.fixture
def case(database):
    factory = lambda: psycopg.connect(**database)
    with factory() as conn:
        corpus = conn.execute(
            "INSERT INTO corpus_versions(snapshot_name,is_active,operation_id) VALUES ('repo-fake',false,%s) RETURNING id",
            (uuid4().hex,),
        ).fetchone()[0]
        product = conn.execute(
            "INSERT INTO product_records(corpus_version_id,product_id,source_row,category,image_path,image_sha256,image_format) VALUES (%s,%s,1,'fake','private/fake',%s,'PNG') RETURNING id",
            (corpus, uuid4().hex, "0" * 64),
        ).fetchone()[0]
    models = tuple(
        ModelIdentity(key, "r" + str(i), "a" * 64, dim)
        for i, (key, dim) in enumerate(
            [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)], 1
        )
    )
    identity = BuildIdentity(
        str(uuid4()),
        corpus,
        uuid4().hex * 2,
        "b" * 64,
        (("crop_profile", "mask_bbox_white_v1"),),
        models,
    )
    photo = PhotoInput(1, uuid4().hex, "c" * 64)
    item = BuildPhoto(str(uuid4()), product, photo)
    yield PostgresNailCatalog(factory), identity, (item,), factory


def ok_outcome(identity, item):
    mask = BinaryMask(1, 1, b"\xff")
    crop = RegionCrop(1, (0.0, 0.0, 1.0, 1.0), (0, 0, 1, 1), mask, RgbImage(1, 1, b"abc"))
    processed = ProcessedPhoto(1, item.photo.input_sha256, "OK", (crop,))
    vectors = tuple(
        (model.model_key, ((1.0,) + (0.0,) * (model.dimension - 1),)) for model in identity.models
    )
    embeddings = PhotoEmbeddings(1, item.photo.input_sha256, (1,), vectors)
    return BuildPhotoResult(
        identity.representation_id,
        item.catalog_photo_id,
        processed,
        embeddings,
        (RegionArtifacts(1, "d" * 32, "e" * 32, "f" * 64),),
    )


def test_build_photo_publish_and_streamed_read_identity(case):
    repo, identity, items, _ = case
    repo.begin_build(identity, items)
    summary = repo.read_build_summary(identity.representation_id)
    assert summary is not None
    assert summary.pending_photos == 1 and not summary.complete
    repo.write_photo_outcome(ok_outcome(identity, items[0]))
    summary = repo.read_build_summary(identity.representation_id)
    assert summary.complete and summary.ok_photos == 1
    assert repo.publish(identity.representation_id, None) is True
    ready = repo.read_ready(identity.representation_id)
    assert ready.representation_fingerprint == identity.fingerprint
    assert ready.embedding_profile.revisions == tuple(
        (m.model_key, m.revision) for m in identity.models
    )
    groups = tuple(repo.iter_photo_groups(identity.representation_id))
    assert groups[0].product_record_id == items[0].product_record_id
    assert (
        groups[0].photos[0].embeddings.vectors == ok_outcome(identity, items[0]).embeddings.vectors
    )
    with pytest.raises(NailProcessingError):
        repo.write_photo_outcome(ok_outcome(identity, items[0]))


def test_no_nails_and_incomplete_representation_not_publish(case):
    repo, identity, items, _ = case
    repo.begin_build(identity, items)
    with pytest.raises(NailProcessingError):
        repo.publish(identity.representation_id, None)
    outcome = BuildPhotoResult(
        identity.representation_id,
        items[0].catalog_photo_id,
        ProcessedPhoto(1, items[0].photo.input_sha256, "NO_NAILS", ()),
        None,
        (),
        "DETECTOR_NO_MATCH",
    )
    repo.write_photo_outcome(outcome)
    summary = repo.read_build_summary(identity.representation_id)
    assert summary is not None
    assert summary.uncovered_product_ids == (items[0].product_record_id,)
    with pytest.raises(NailProcessingError):
        repo.publish(identity.representation_id, None)


def test_compare_and_set_active_pointer_rolls_back_new_ready_status(case):
    repo, identity, items, factory = case
    repo.begin_build(identity, items)
    repo.write_photo_outcome(ok_outcome(identity, items[0]))
    with factory() as conn:
        old = conn.execute("SELECT representation_id FROM search_active_representations").fetchone()
    expected = str(old[0]) if old else None
    with pytest.raises(NailProcessingError, match="ACTIVE_CONFLICT"):
        repo.publish(identity.representation_id, str(uuid4()))
    assert repo.read_build_summary(identity.representation_id).status == "BUILDING"
    assert repo.publish(identity.representation_id, expected) is True


def test_invalid_artifact_set_or_failed_vector_write_is_atomic(case):
    repo, identity, items, factory = case
    repo.begin_build(identity, items)
    good = ok_outcome(identity, items[0])
    bad = BuildPhotoResult(
        good.representation_id, good.catalog_photo_id, good.photo, good.embeddings, ()
    )
    with pytest.raises(NailProcessingError):
        repo.write_photo_outcome(bad)
    with factory() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM nail_regions WHERE representation_id=%s",
                (identity.representation_id,),
            ).fetchone()[0]
            == 0
        )
    assert repo.read_build_summary(identity.representation_id).pending_photos == 1


def test_read_not_ready_or_unknown_identity_rejected(case):
    repo, identity, items, _ = case
    repo.begin_build(identity, items)
    with pytest.raises(NailProcessingError):
        repo.read_ready(identity.representation_id)
    with pytest.raises(NailProcessingError):
        repo.read_ready(str(uuid4()))


def test_database_error_after_partial_vector_inserts_rolls_back_photo(case):
    repo, identity, items, factory = case
    repo.begin_build(identity, items)
    with factory() as conn:
        conn.execute(
            "DELETE FROM representation_models WHERE representation_id=%s AND model_key='siglip2_b16_224'",
            (identity.representation_id,),
        )
    with pytest.raises(NailProcessingError):
        repo.write_photo_outcome(ok_outcome(identity, items[0]))
    with factory() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM nail_regions WHERE representation_id=%s",
                (identity.representation_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM nail_embeddings WHERE representation_id=%s",
                (identity.representation_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT status FROM catalog_photos WHERE id=%s", (items[0].catalog_photo_id,)
            ).fetchone()[0]
            == "PENDING"
        )


def test_concurrent_publish_has_one_winner_and_one_atomic_conflict(case):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from threading import Barrier

    repo, identity, items, factory = case
    identities = (
        identity,
        replace(identity, representation_id=str(uuid4()), fingerprint=uuid4().hex * 2),
    )
    for current in identities:
        inventory = (replace(items[0], catalog_photo_id=str(uuid4())),)
        repo.begin_build(current, inventory)
        repo.write_photo_outcome(ok_outcome(current, inventory[0]))
    with factory() as conn:
        row = conn.execute("SELECT representation_id FROM search_active_representations").fetchone()
    expected = str(row[0]) if row else None
    barrier = Barrier(2)

    def publish(current):
        barrier.wait(timeout=5)
        try:
            repo.publish(current.representation_id, expected)
            return "READY"
        except NailProcessingError as error:
            assert error.code == "ACTIVE_CONFLICT"
            return "BUILDING"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(publish, current) for current in identities]
        assert sorted(f.result(timeout=10) for f in futures) == ["BUILDING", "READY"]
    assert sorted(
        repo.read_build_summary(current.representation_id).status for current in identities
    ) == ["BUILDING", "READY"]
