"""B1 snapshot read/binding and synthetic parity; no real runtime admission."""

from copy import deepcopy
from dataclasses import asdict, replace
from uuid import uuid4

import pytest

from product_search.infrastructure.nail_repository import PostgresNailCatalog
from product_search.infrastructure.replenishment_repository import digest
from product_search.search.nail_contracts import (
    EmbeddingProfile,
    PhotoInput,
    SearchProfile,
    SearchRequest,
)
from product_search.search.nail_service import NailSearchService
from product_search.search.replenishment_contracts import (
    ReplenishmentError,
    SnapshotDescriptor,
    SnapshotEmbeddingProfile,
    SnapshotQueryClaim,
    SnapshotRuntimeIdentity,
    SnapshotSearchRequest,
    VerifiedCatalogBinding,
)
from tests.test_nail_service import Embedding, Processor
from tests.test_replenishment_postgres_integration import (
    db as db,  # noqa: PLC0414 -- pytest fixture
)
from tests.test_replenishment_postgres_integration import profile_payload
from tests.test_replenishment_publication import complete, ready, setup

PHOTOS = (PhotoInput(1, "a" * 32, "b" * 64),)


def runtime_metadata(profile=None):
    payload = profile or profile_payload()
    return {
        "runtime": {
            "mode": "fake",
            "extractor_fingerprint": "e" * 64,
            "backend_inventory_sha256": "c" * 64,
            "python": "synthetic-3.12",
            "machine": "synthetic-arm64",
            "device": "fake",
            "dtype": "float32",
            "operator_fallback": False,
            "models": [
                [m["model_key"], m["revision"], "d" * 64, m["dimension"]] for m in payload["models"]
            ],
        },
        "embedding_profile": payload,
    }


def typed_profile():
    p = profile_payload()
    return SnapshotEmbeddingProfile(
        p["crop_version"],
        tuple(
            (m["model_key"], m["dimension"], m["revision"], m["preprocessing"], m["dtype"])
            for m in p["models"]
        ),
    )


def binding_values():
    desc = SnapshotDescriptor(str(uuid4()), "a" * 64, digest(profile_payload()))
    metadata = runtime_metadata()
    profile = typed_profile()
    runtime = SnapshotRuntimeIdentity(
        digest(metadata), "c" * 64, digest(metadata["runtime"]["models"]), "e" * 64, "fake", profile
    )
    claim = SnapshotQueryClaim(
        (desc.snapshot_ref,),
        ((1, "b" * 64),),
        runtime.runtime_sha,
        desc.semantic_profile_sha,
        "QUERY",
    )
    return desc, profile, runtime, claim


@pytest.mark.parametrize(
    "change",
    [{"snapshot_ref": "legacy-rep"}, {"content_sha": "bad"}, {"semantic_profile_sha": True}],
)
def test_descriptor_is_distinct_and_requires_valid_identity(change):
    descriptor, _, _, _ = binding_values()
    with pytest.raises(ReplenishmentError):
        replace(descriptor, **change)


@pytest.mark.parametrize(
    "change",
    [
        {"crop_version": ""},
        {"models": ()},
        {"models": (("openclip_b32", 768, "v", "p", "float32"),)},
    ],
)
def test_full_profile_cannot_drop_dimensions_revisions_or_preprocessing(change):
    with pytest.raises(ReplenishmentError):
        replace(typed_profile(), **change)


def test_binding_refuses_other_input_scope_runtime_profile_or_solver_budget():
    d, p, r, c = binding_values()
    for bad in (
        replace(c, snapshot_refs=(str(uuid4()),)),
        replace(c, runtime_sha="f" * 64),
        replace(c, semantic_profile_sha="f" * 64),
    ):
        with pytest.raises(ReplenishmentError):
            VerifiedCatalogBinding(d, p, r, bad, 10000)
    with pytest.raises(ReplenishmentError):
        VerifiedCatalogBinding(d, p, r, c, 0)
    good = VerifiedCatalogBinding(d, p, r, c, 10000)
    with pytest.raises(ReplenishmentError):
        SnapshotSearchRequest((PhotoInput(1, "a" * 32, "f" * 64),), good)
    with pytest.raises(ReplenishmentError):
        replace(c, scope="BUILD")


def published(db, tmp_path):
    repo, owner, products, revision, store = ready(db, tmp_path)
    receipt = repo.publish_revision(revision, None, owner)
    descriptor = repo.resolve_active("nail-search-v1")
    assert isinstance(descriptor, SnapshotDescriptor)
    assert descriptor.snapshot_ref == receipt.snapshot_ref
    return repo, owner, products, revision, store, descriptor


def bind(repo, descriptor, **changes):
    metadata = runtime_metadata()
    claim = SnapshotQueryClaim(
        (descriptor.snapshot_ref,),
        tuple((p.photo_ordinal, p.input_sha256) for p in PHOTOS),
        digest(metadata),
        descriptor.semantic_profile_sha,
        "QUERY",
    )
    args = {
        "expected_claim_sha": digest(asdict(claim)),
        "expected_runtime": deepcopy(metadata["runtime"]),
        "observe_runtime": lambda: deepcopy(metadata),
        "expected_runtime_sha": digest(metadata),
        "expected_code_sha": "c" * 64,
        "expected_model_sha": digest(metadata["runtime"]["models"]),
        "max_solver_states": 10000,
    }
    args.update(changes)
    return repo.bind_snapshot(descriptor, PHOTOS, claim, **args)


def test_descriptor_profile_and_ordered_complete_photos_are_read_from_db(db, tmp_path):
    repo, _, _, _, _, desc = published(db, tmp_path)
    assert repo.read_snapshot_profile(desc) == typed_profile()
    groups = tuple(repo.read_snapshot(desc))
    assert len(groups) == 1 and len(groups[0].photos) == 1
    vectors = groups[0].photos[0].embeddings
    assert tuple((key, len(rows[0])) for key, rows in vectors.vectors) == (
        ("openclip_b32", 512),
        ("dinov2_b14", 768),
        ("siglip2_b16_224", 768),
    )
    assert vectors.vectors[0][1][0] == (0.25,) * 512
    binding = bind(repo, desc)
    assert isinstance(binding, VerifiedCatalogBinding)


def test_content_and_profile_mismatch_are_rejected_before_reading_products(db, tmp_path):
    repo, _, _, _, _, desc = published(db, tmp_path)
    for bad in (replace(desc, content_sha="f" * 64), replace(desc, semantic_profile_sha="f" * 64)):
        with pytest.raises(ReplenishmentError):
            tuple(repo.read_snapshot(bad))


def test_runtime_and_claims_are_independently_checked_before_query(db, tmp_path):
    repo, _, _, _, _, desc = published(db, tmp_path)
    metadata = runtime_metadata()
    for change in ("revision", "preprocessing", "dtype"):
        bad = deepcopy(metadata)
        bad["embedding_profile"]["models"][0][change] = "mismatch"
        with pytest.raises(ReplenishmentError):
            bind(repo, desc, observe_runtime=lambda bad=bad: bad)
    bad = deepcopy(metadata)
    bad["runtime"]["models"][0][1] = "wrong-runtime-revision"
    with pytest.raises(ReplenishmentError):
        bind(repo, desc, observe_runtime=lambda bad=bad: bad)
    for arg in (
        "expected_claim_sha",
        "expected_runtime_sha",
        "expected_code_sha",
        "expected_model_sha",
    ):
        with pytest.raises(ReplenishmentError):
            bind(repo, desc, **{arg: "f" * 64})


def test_pinned_descriptor_survives_new_active_publication(db, tmp_path):
    repo, _, products, _, _, old = published(db, tmp_path)
    extra = replace(
        products[0],
        expected_head_version=1,
        photos=(replace(products[0].photos[0], input_sha="f" * 64),),
    )
    newer, next_owner, _, refs, store = setup(db, tmp_path, products=(extra,), epoch=1)
    complete(newer, next_owner, store, newer.read_queue(next_owner)[0])
    revision = newer.prepare_revision(refs[0], next_owner, store)
    newer.publish_revision(revision, old.snapshot_ref, next_owner)
    current = newer.resolve_active("nail-search-v1")
    assert current != old
    old_groups = tuple(repo.read_snapshot(old))
    new_groups = tuple(newer.read_snapshot(current))
    assert old_groups[0].photos[0].embeddings.input_sha256 == "a" * 64
    assert new_groups[0].photos[0].embeddings.input_sha256 == "f" * 64


def test_real_legacy_and_snapshot_readers_have_matching_parity(db, tmp_path):
    repo, _, products, _, _, desc = published(db, tmp_path)
    rep = uuid4()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO search_representations VALUES (%s,%s,%s,'BUILDING','{}'::jsonb,%s,now(),now())",
            (rep, products[0].corpus_version_id, "e" * 64, "a" * 64),
        )
        for model, dim in [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)]:
            conn.execute(
                "INSERT INTO representation_models VALUES (%s,%s,%s,%s,%s)",
                (rep, model, "synthetic-v1", "d" * 64, dim),
            )
        conn.execute(
            "INSERT INTO catalog_photos SELECT p.id,%s,r.product_record_id,p.ordinal,p.input_sha,p.source_ref,'OK',NULL FROM revision_photos p JOIN product_revisions r ON r.id=p.revision_id WHERE p.outcome='OK'",
            (rep,),
        )
        conn.execute(
            "INSERT INTO nail_regions SELECT gen_random_uuid(),%s,g.revision_photo_id,g.region_ordinal,'[0,0,2,2]'::jsonb,'[0,0,2,2]'::jsonb,g.mask_ref,g.crop_ref,g.crop_sha FROM revision_regions g",
            (rep,),
        )
        conn.execute(
            "INSERT INTO nail_embeddings SELECT %s,r.id,v.model_key,vector_dims(v.vector),v.vector FROM nail_regions r JOIN revision_vectors v ON v.revision_photo_id=r.catalog_photo_id AND v.region_ordinal=r.ordinal",
            (rep,),
        )
        conn.execute("UPDATE search_representations SET status='READY' WHERE id=%s", (rep,))
    legacy = PostgresNailCatalog(db.connect)
    assert tuple(legacy.iter_photo_groups(str(rep))) == tuple(repo.read_snapshot(desc))
    profile = EmbeddingProfile(tuple((m[0], m[2]) for m in typed_profile().models))

    class Encoder(Embedding):
        def encode(self, key, crops, actual):
            assert actual == profile
            dim = {m[0]: m[1] for m in typed_profile().models}[key]
            return tuple((1.0,) + (0.0,) * (dim - 1) for _ in crops)

    old = NailSearchService(legacy, Processor(), Encoder()).execute_many(
        SearchRequest(PHOTOS, str(rep), SearchProfile("e" * 64, profile, 10000))
    )
    service = NailSearchService(repo, Processor(), Encoder(), catalog_backend="snapshot")
    new = service.execute_snapshot(SnapshotSearchRequest(PHOTOS, bind(repo, desc)))
    assert new.candidates == old.candidates and new.score_kind == old.score_kind
    assert new.descriptor == desc
    assert not hasattr(new, "representation_id")


@pytest.mark.parametrize(
    "field,value",
    [
        ("snapshot_refs", ([],)),
        ("inputs", ((1, []),)),
        ("inputs", ((True, "b" * 64),)),
        ("snapshot_refs", ()),
        ("runtime_sha", None),
    ],
)
def test_malformed_claim_is_a_controlled_error(field, value):
    _, _, _, claim = binding_values()
    with pytest.raises(ReplenishmentError):
        replace(claim, **{field: value})


def test_independent_observation_failure_does_not_admit_query(db, tmp_path):
    repo, _, _, _, _, desc = published(db, tmp_path)

    def failed():
        raise RuntimeError("SYNTHETIC_OBSERVATION_UNAVAILABLE")

    with pytest.raises(ReplenishmentError, match="RUNTIME_MISMATCH"):
        bind(repo, desc, observe_runtime=failed)


def test_reader_skips_no_nails_and_preserves_photo_ordinals(db, tmp_path):
    from product_search.search.replenishment_contracts import PhotoOutcome

    repo, owner, _, refs, store = setup(db, tmp_path, count=3)
    photos = repo.read_queue(owner)
    complete(repo, owner, store, photos[0])
    complete(repo, owner, store, photos[1], PhotoOutcome.NO_NAILS)
    complete(repo, owner, store, photos[2])
    ref = repo.prepare_revision(refs[0], owner, store)
    repo.publish_revision(ref, None, owner)
    desc = repo.resolve_active("nail-search-v1")
    products = tuple(repo.read_snapshot(desc))
    assert tuple(p.embeddings.photo_ordinal for p in products[0].photos) == (1, 3)


def test_empty_and_wrong_backend_are_rejected_before_models(db, tmp_path):
    from product_search.search.nail_contracts import NailProcessingError

    repo, _, _, _, _, desc = published(db, tmp_path)
    request = SnapshotSearchRequest(PHOTOS, bind(repo, desc))
    with pytest.raises(NailProcessingError, match="INVALID_REQUEST"):
        NailSearchService(repo, Processor(fail=True), Embedding()).execute_snapshot(request)
    with pytest.raises(NailProcessingError, match="INVALID_REQUEST"):
        NailSearchService(
            repo, Processor(fail=True), Embedding(), catalog_backend="snapshot"
        ).execute_many(
            SearchRequest(
                PHOTOS,
                "legacy",
                SearchProfile(
                    "e" * 64,
                    EmbeddingProfile(tuple((m[0], m[2]) for m in typed_profile().models)),
                    10000,
                ),
            )
        )
    with pytest.raises(NailProcessingError, match="INVALID_REQUEST"):
        NailSearchService(repo, Processor(fail=True), Embedding(), catalog_backend="automatic")


def test_stream_is_closed_when_query_has_no_nails(db, tmp_path, monkeypatch):
    repo, _, _, _, _, desc = published(db, tmp_path)
    request = SnapshotSearchRequest(PHOTOS, bind(repo, desc))
    closed = []
    original = repo.read_snapshot

    def groups(d):
        try:
            yield from original(d)
        finally:
            closed.append(d)

    monkeypatch.setattr(repo, "read_snapshot", groups)
    result = NailSearchService(
        repo,
        Processor(no_nails=True),
        Embedding(fail_key="openclip_b32"),
        catalog_backend="snapshot",
    ).execute_snapshot(request)
    assert result.status == "NEED_MORE_PHOTOS" and result.candidates == ()
    assert closed == [desc]
