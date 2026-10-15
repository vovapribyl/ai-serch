from dataclasses import replace
from uuid import uuid4

import pytest

from product_search.search.nail_catalog_build import NailCatalogBuildService
from product_search.search.nail_contracts import (
    BinaryMask,
    BuildIdentity,
    BuildPhoto,
    BuildSummary,
    EmbeddingProfile,
    ModelIdentity,
    NailProcessingError,
    PhotoInput,
    ProcessedPhoto,
    RegionArtifacts,
    RegionCrop,
    RgbImage,
    SearchProfile,
    StoredPhotoState,
)

MODELS = tuple(
    ModelIdentity(key, "r" + str(i), "a" * 64, dim)
    for i, (key, dim) in enumerate(
        [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)], 1
    )
)
IDENTITY = BuildIdentity(
    str(uuid4()), 1, "b" * 64, "c" * 64, (("crop_profile", "mask_bbox_white_v1"),), MODELS
)
RUNTIME = SearchProfile(
    "b" * 64, EmbeddingProfile(tuple((m.model_key, m.revision) for m in MODELS)), 10000
)
ITEMS = (BuildPhoto(str(uuid4()), 1, PhotoInput(1, "d" * 32, "e" * 64)),)


class Catalog:
    def __init__(self, states=None, uncovered=()):
        self.states = states
        self.outcomes = []
        self.uncovered = uncovered
        self.created = False
        self.published = False

    def begin_build(self, identity, inventory):
        self.created = True
        self.identity = identity
        self.states = tuple(StoredPhotoState(item, "PENDING", None, ()) for item in inventory)

    def read_build_identity(self, representation_id):
        return getattr(self, "identity", IDENTITY)

    def read_photo_states(self, representation_id):
        return self.states

    def write_photo_outcome(self, outcome):
        self.outcomes.append(outcome)

    def read_build_summary(self, representation_id):
        statuses = [("ERROR" if o.photo is None else o.photo.status) for o in self.outcomes]
        ok = statuses.count("OK") or sum(s.status == "OK" for s in self.states or ())
        errors = statuses.count("ERROR")
        pending = (
            len(self.states or ())
            - len(self.outcomes)
            - sum(s.status != "PENDING" for s in self.states or ())
        )
        return BuildSummary(
            representation_id,
            "BUILDING",
            len(self.states or ()),
            ok,
            statuses.count("NO_NAILS"),
            errors,
            pending,
            ok > 0 and errors == 0 and pending == 0,
            self.uncovered,
        )

    def publish(self, representation_id, expected_active_id):
        self.published = True
        return True


class Processor:
    decode_profile = object()

    def __init__(self, status="OK", fail=False):
        self.status, self.fail = status, fail

    def process(self, photo):
        if self.fail:
            raise NailProcessingError("MODEL_ERROR")
        regions = (
            ()
            if self.status == "NO_NAILS"
            else (
                RegionCrop(
                    1,
                    (0.0, 0.0, 1.0, 1.0),
                    (0, 0, 1, 1),
                    BinaryMask(1, 1, b"\xff"),
                    RgbImage(1, 1, b"abc"),
                ),
            )
        )
        return ProcessedPhoto(photo.photo_ordinal, photo.input_sha256, self.status, regions)


class Embedding:
    def encode(self, key, crops, profile):
        assert profile == RUNTIME.embedding_profile
        dimension = {m.model_key: m.dimension for m in MODELS}[key]
        return tuple((1.0,) + (0.0,) * (dimension - 1) for _ in crops)


class Images:
    def __init__(self):
        self.verified = False

    def write_region_artifacts(self, build_id, photo):
        return (RegionArtifacts(1, "a" * 32, "b" * 32, "c" * 64),)

    def verify_artifacts(self, build_id, artifacts, profile):
        self.verified = True

    def read_rgb(self, photo, profile):
        return RgbImage(1, 1, b"abc")

    def cleanup(self, refs):
        pass

    def cleanup_orphans(self, build_id, keep_refs):
        return 0


def test_terminal_outcomes_and_no_automatic_publish():
    catalog = Catalog()
    service = NailCatalogBuildService(catalog, Processor(), Embedding(), Images())
    summary = service.execute(IDENTITY, ITEMS, RUNTIME)
    assert summary is not None
    assert summary.ok_photos == 1 and summary.complete
    assert not catalog.published
    assert catalog.outcomes[0].embeddings.region_ordinals == (1,)


@pytest.mark.parametrize(
    "processor,status", [(Processor("NO_NAILS"), "NO_NAILS"), (Processor(fail=True), "ERROR")]
)
def test_no_nails_and_technical_error_are_different_terminal_records(processor, status):
    catalog = Catalog()
    summary = NailCatalogBuildService(catalog, processor, Embedding(), Images()).execute(
        IDENTITY, ITEMS, RUNTIME
    )
    assert summary is not None and not summary.complete
    outcome = catalog.outcomes[0]
    assert ("ERROR" if outcome.photo is None else outcome.photo.status) == status
    assert outcome.artifacts == () and outcome.embeddings is None


def test_profile_mismatch_before_catalog_or_ml():
    catalog = Catalog()
    with pytest.raises(NailProcessingError, match="PROFILE_MISMATCH"):
        NailCatalogBuildService(catalog, Processor(fail=True), Embedding(), Images()).execute(
            IDENTITY, ITEMS, replace(RUNTIME, representation_fingerprint="f" * 64)
        )
    assert not catalog.created


def test_resume_validates_same_identity_and_existing_artifacts_without_ml():
    artifacts = (RegionArtifacts(1, "a" * 32, "b" * 32, "c" * 64),)
    catalog = Catalog((StoredPhotoState(ITEMS[0], "OK", None, artifacts),))
    images = Images()
    summary = NailCatalogBuildService(catalog, Processor(fail=True), Embedding(), images).execute(
        IDENTITY, ITEMS, RUNTIME, resume=True
    )
    assert summary is not None and summary.complete
    assert images.verified and catalog.outcomes == []


def test_resume_error_never_automatically_retries():
    catalog = Catalog((StoredPhotoState(ITEMS[0], "ERROR", "MODEL_ERROR", ()),))
    with pytest.raises(NailProcessingError):
        NailCatalogBuildService(catalog, Processor(), Embedding(), Images()).execute(
            IDENTITY, ITEMS, RUNTIME, resume=True
        )
    assert catalog.outcomes == []


def test_coverage_exception_must_be_accepted_before_publish():
    catalog = Catalog(uncovered=(2,))
    service = NailCatalogBuildService(catalog, Processor(), Embedding(), Images())
    service.execute(IDENTITY, ITEMS, RUNTIME)
    with pytest.raises(NailProcessingError, match="COVERAGE_NOT_ACCEPTED"):
        service.publish(IDENTITY.representation_id, None)
    assert not catalog.published
    assert service.publish(IDENTITY.representation_id, None, coverage_accepted=True) is True


def test_resume_profile_key_order_is_not_a_new_profile():
    identity = replace(IDENTITY, profile=(("z", "extra"), ("crop_profile", "mask_bbox_white_v1")))
    artifacts = (RegionArtifacts(1, "a" * 32, "b" * 32, "c" * 64),)
    catalog = Catalog((StoredPhotoState(ITEMS[0], "OK", None, artifacts),))
    catalog.identity = replace(identity, profile=tuple(sorted(identity.profile)))
    assert (
        NailCatalogBuildService(catalog, Processor(fail=True), Embedding(), Images())
        .execute(identity, ITEMS, RUNTIME, resume=True)
        .complete
    )


def test_noncanonical_inventory_is_rejected_before_creating_build():
    first = replace(ITEMS[0], product_record_id=2)
    second = replace(ITEMS[0], product_record_id=1, catalog_photo_id=str(uuid4()))

    class OrderedCatalog(Catalog):
        def read_photo_states(self, representation_id):
            return tuple(
                sorted(
                    self.states,
                    key=lambda state: (
                        state.item.product_record_id,
                        state.item.photo.photo_ordinal,
                    ),
                )
            )

    catalog = OrderedCatalog()
    with pytest.raises(NailProcessingError, match="INVALID_OUTPUT"):
        NailCatalogBuildService(catalog, Processor(), Embedding(), Images()).execute(
            IDENTITY, (first, second), RUNTIME
        )
    assert not catalog.created


@pytest.mark.parametrize("code", ["REGION_COUNT_LIMIT", "RESPONSE_SIZE_LIMIT"])
def test_guarded_photo_limit_records_error_then_processes_next_photo(code):
    from types import SimpleNamespace

    from product_search.infrastructure.nail_build_runner import AdmissionBudget, GuardedLocalization
    from product_search.search.nail_contracts import NailLocalization
    calls = []
    def localize(*args):
        calls.append(1)
        if len(calls) == 1:
            raise NailProcessingError(code)
        return NailLocalization("NO_NAILS", ())
    budget = AdmissionBudget(2, 10, lambda: True, lambda: 0)
    guard = GuardedLocalization(SimpleNamespace(localize=localize), budget)
    class GuardedProcessor(Processor):
        def process(self, photo):
            result = guard.localize(None, None)
            return ProcessedPhoto(photo.photo_ordinal, photo.input_sha256, result.status, ())
    items = ITEMS + (BuildPhoto(str(uuid4()), 2, PhotoInput(1, "f" * 32, "0" * 64)),)
    catalog = Catalog()
    summary = NailCatalogBuildService(catalog, GuardedProcessor(), Embedding(), Images()).execute(
        IDENTITY, items, RUNTIME
    )
    assert [o.error_code for o in catalog.outcomes] == [code, "DETECTOR_NO_MATCH"]
    assert summary.error_photos == 1 and summary.no_nails_photos == 1 and summary.pending_photos == 0
    assert not summary.complete and not catalog.published and not budget.stopped
