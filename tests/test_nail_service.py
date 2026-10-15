import pytest

from product_search.search.nail_contracts import (
    BinaryMask,
    CatalogPhoto,
    CatalogProduct,
    EmbeddingProfile,
    NailProcessingError,
    PhotoEmbeddings,
    PhotoInput,
    ProcessedPhoto,
    ReadyCatalog,
    RegionCrop,
    RgbImage,
    SearchProfile,
    SearchRequest,
)
from product_search.search.nail_service import NailSearchService

PROFILE = EmbeddingProfile(
    (("openclip_b32", "r1"), ("dinov2_b14", "r2"), ("siglip2_b16_224", "r3"))
)
RUNTIME = SearchProfile("f" * 64, PROFILE, 10000)
PHOTOS = (PhotoInput(1, "a" * 32, "b" * 64),)


def embedding(ordinal, direction=(1.0, 0.0)):
    vectors = tuple(
        (key, (tuple(direction) + (0.0,) * (dim - 2),))
        for key, dim in [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)]
    )
    return PhotoEmbeddings(ordinal, "d" * 64, (1,), vectors)


def product(key, directions=((1.0, 0.0),)):
    record_id = (
        int(key[1:]) + 1 if isinstance(key, str) and key[1:].isdigit() else 1 if key == "p" else key
    )
    return CatalogProduct(
        record_id,
        tuple(CatalogPhoto(f"{key}-{i}", embedding(i, d)) for i, d in enumerate(directions, 1)),
    )


class Catalog:
    def __init__(self, products, fp="f" * 64, ok=True):
        self.products = products
        self.fp = fp
        self.ok = ok

    def read_ready(self, representation_id):
        assert representation_id == "rep"
        return ReadyCatalog("rep", self.fp, PROFILE, self.ok)

    def iter_photo_groups(self, representation_id):
        assert representation_id == "rep"
        yield from self.products


class Processor:
    def __init__(self, no_nails=False, fail=False):
        self.no_nails = no_nails
        self.fail = fail

    def process(self, photo):
        if self.fail:
            raise AssertionError("ML must not start")
        if self.no_nails:
            return ProcessedPhoto(photo.photo_ordinal, photo.input_sha256, "NO_NAILS", ())
        crop = RegionCrop(
            1, (0.0, 0.0, 1.0, 1.0), (0, 0, 1, 1), BinaryMask(1, 1, b"\xff"), RgbImage(1, 1, b"abc")
        )
        return ProcessedPhoto(photo.photo_ordinal, photo.input_sha256, "OK", (crop,))


class Embedding:
    def __init__(self, fail_key=None):
        self.fail_key = fail_key

    def encode(self, key, crops, profile):
        assert profile == PROFILE
        if key == self.fail_key:
            raise NailProcessingError("MODEL_ERROR")
        dim = {"openclip_b32": 512, "dinov2_b14": 768, "siglip2_b16_224": 768}[key]
        return tuple((1.0,) + (0.0,) * (dim - 1) for _ in crops)


def service(products, processor=None, embedding=None, **kwargs):
    return NailSearchService(
        Catalog(products, **kwargs), processor or Processor(), embedding or Embedding()
    )


def test_best_photo_no_count_bonus_and_ten_unique_stable_products():
    products = tuple(product(f"p{i:02}", ((-1.0, 0.0), (1.0, 0.0), (1.0, 0.0))) for i in range(12))
    result = service(products).execute_many(SearchRequest(PHOTOS, "rep", RUNTIME))
    assert result is not None
    assert tuple(c.product_record_id for c in result.candidates) == tuple(range(1, 11))
    assert all(c.match.score == 1.0 for c in result.candidates)
    assert result.candidates[0].match.catalog_photo_id == "p00-2"
    assert result.representation_id == "rep"
    assert result.representation_fingerprint == "f" * 64
    assert result.score_kind == "nail_assignment_mean_v1"


@pytest.mark.parametrize(
    "products,kwargs,code",
    [
        ((), {}, "INDEX_EMPTY"),
        ((product("p"),), {"ok": False}, "INDEX_EMPTY"),
        ((product("p"),), {"fp": "e" * 64}, "PROFILE_MISMATCH"),
    ],
)
def test_pinned_identity_and_empty_index_before_ml(products, kwargs, code):
    with pytest.raises(NailProcessingError, match=code):
        service(products, Processor(fail=True), **kwargs).execute_many(
            SearchRequest(PHOTOS, "rep", RUNTIME)
        )


def test_no_nails_needs_more_photos_without_whole_image_fallback():
    result = service(
        (product("p"),), Processor(no_nails=True), Embedding(fail_key="openclip_b32")
    ).execute_many(SearchRequest(PHOTOS, "rep", RUNTIME))
    assert result is not None
    assert result.status == "NEED_MORE_PHOTOS"
    assert result.candidates == () and result.skipped_photo_ordinals == (1,)


def test_model_or_late_catalog_failure_cannot_return_partial_run():
    with pytest.raises(NailProcessingError, match="MODEL_ERROR"):
        service((product("p"),), embedding=Embedding(fail_key="dinov2_b14")).execute_many(
            SearchRequest(PHOTOS, "rep", RUNTIME)
        )

    class LateCatalog(Catalog):
        def iter_photo_groups(self, representation_id):
            yield product("p")
            raise NailProcessingError("INVALID_OUTPUT")

    with pytest.raises(NailProcessingError, match="INVALID_OUTPUT"):
        NailSearchService(LateCatalog(()), Processor(), Embedding()).execute_many(
            SearchRequest(PHOTOS, "rep", RUNTIME)
        )


def test_multiquery_best_pair_tie_and_single_photo_entrypoint():
    second = PhotoInput(2, "c" * 32, "e" * 64)
    s = service((product("p"),))
    result = s.execute_many(SearchRequest(PHOTOS + (second,), "rep", RUNTIME))
    assert result is not None
    assert result.candidates[0].match.query_photo_ordinal == 1
    assert result == s.execute(PHOTOS[0], "rep", RUNTIME)


@pytest.mark.parametrize("photos", [(), PHOTOS * 2, PHOTOS * 5])
def test_invalid_request_rejected_before_ml(photos):
    with pytest.raises(NailProcessingError):
        service((product("p"),), Processor(fail=True)).execute_many(
            SearchRequest(photos, "rep", RUNTIME)
        )


def test_missing_runtime_budget_rejected():
    with pytest.raises(NailProcessingError):
        SearchProfile("f" * 64, PROFILE, 0)


def test_duplicate_catalog_product_rejected_instead_of_double_candidates():
    with pytest.raises(NailProcessingError):
        service((product("p"), product("p"))).execute_many(SearchRequest(PHOTOS, "rep", RUNTIME))


def test_real_file_crop_embedding_matcher_pipeline_with_fake_models(tmp_path):
    import hashlib

    from PIL import Image

    from product_search.infrastructure.nail_image_store import NailImageStore
    from product_search.infrastructure.nail_ml_adapters import NailEmbeddingAdapter
    from product_search.search.nail_contracts import (
        DecodeProfile,
        LocalizationProfile,
        LocalizedRegion,
        NailLocalization,
    )
    from product_search.search.nail_image_processor import NailImageProcessor

    tmp_path.chmod(0o700)
    image = Image.frombytes("RGB", (2, 1), bytes([1, 0, 0, 0, 1, 0]))
    path = tmp_path / ("a" * 32)
    image.save(path, format="PNG")
    path.chmod(0o600)
    photo = PhotoInput(1, path.name, hashlib.sha256(path.read_bytes()).hexdigest())

    class Localizer:
        def localize(self, image, profile):
            assert image.pixels == bytes([1, 0, 0, 0, 1, 0])
            return NailLocalization(
                "OK",
                (
                    LocalizedRegion(
                        1, "nail", 0.9, (0.0, 0.0, 1.0, 1.0), BinaryMask(2, 1, b"\xff\x00")
                    ),
                    LocalizedRegion(
                        2, "nail", 0.8, (1.0, 0.0, 2.0, 1.0), BinaryMask(2, 1, b"\x00\xff")
                    ),
                ),
            )

    class Provider:
        def __init__(self, key, revision, dim):
            self.model_key, self.revision, self.embedding_dim = key, revision, dim

        def encode_image(self, image):
            r, g, _ = image.getpixel((0, 0))
            return (float(r), float(g)) + (0.0,) * (self.embedding_dim - 2)

    factories = {
        key: (lambda key=key, rev=rev, dim=dim: Provider(key, rev, dim))
        for (key, rev), dim in zip(PROFILE.revisions, (512, 768, 768))
    }
    catalog_vectors = tuple(
        (key, ((0.0, 1.0) + (0.0,) * (dim - 2), (1.0, 0.0) + (0.0,) * (dim - 2)))
        for key, dim in [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)]
    )
    catalog_photo = CatalogPhoto("p-photo", PhotoEmbeddings(1, "d" * 64, (1, 2), catalog_vectors))
    processor = NailImageProcessor(
        NailImageStore(tmp_path),
        Localizer(),
        DecodeProfile(10000, 100),
        LocalizationProfile("a" * 64),
        10,
    )
    result = NailSearchService(
        Catalog((CatalogProduct(1, (catalog_photo,)),)),
        processor,
        NailEmbeddingAdapter(factories),
    ).execute(photo, "rep", RUNTIME)
    assert result.candidates[0].match.pairs == (2, 1)
    assert result.candidates[0].match.score == 1.0


def test_integer_product_record_ids_rank_numerically_on_equal_scores():
    photos = (CatalogPhoto("fake-photo", embedding(1)),)
    products = (CatalogProduct(2, photos), CatalogProduct(10, photos))
    result = service(products).execute_many(SearchRequest(PHOTOS, "rep", RUNTIME))
    assert tuple(c.product_record_id for c in result.candidates) == (2, 10)


@pytest.mark.parametrize("kind", ["changed", "response", "representation"])
def test_commit_guard_rejects_changed_inputs_or_representation(kind):
    from product_search.search.nail_service import validate_nail_commit

    expected = ("a" * 64,)
    current = ("b" * 64,) if kind == "changed" else expected
    response = ("b" * 64,) if kind == "response" else expected
    with pytest.raises(NailProcessingError, match="SESSION_CONFLICT"):
        validate_nail_commit(
            expected, current, response, "rep", "other" if kind == "representation" else "rep"
        )


@pytest.mark.parametrize(
    "current,served,status",
    [(("a" * 64, "b" * 64), ("a" * 64,), "OK"), (("a" * 64,), ("a" * 64,), "NEED_MORE_PHOTOS")],
)
def test_finalize_guard_disallows_stale_or_no_nails_result(current, served, status):
    from product_search.search.nail_service import validate_nail_finalization

    with pytest.raises(NailProcessingError, match="STALE_RESULT"):
        validate_nail_finalization(current, served, status)
