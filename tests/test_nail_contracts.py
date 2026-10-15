from dataclasses import FrozenInstanceError

import pytest

from product_search.search.nail_contracts import (
    BinaryMask,
    LocalizationProfile,
    LocalizedRegion,
    NailLocalization,
    NailProcessingError,
    RgbImage,
)


def region(ordinal=1):
    return LocalizedRegion(ordinal, "nail", 0.9, (0.0, 0.0, 1.0, 1.0), BinaryMask(1, 1, b"\xff"))


@pytest.mark.parametrize(
    "args", [(0, 1, b""), (True, 1, b"abc"), (1, 1, b"ab"), (1, 1, bytearray(b"abc"))]
)
def test_rgb_rejects_invalid_shape_or_mutable_pixels(args):
    with pytest.raises(NailProcessingError) as caught:
        RgbImage(*args)
    assert caught.value.code == "INVALID_IMAGE"


@pytest.mark.parametrize(
    "args", [(1, 1, b"\x80"), (1, 1, b"\0"), (2, 1, b"\xff"), (1, False, b"\xff")]
)
def test_mask_rejects_invalid_pixels_or_empty_region(args):
    with pytest.raises(NailProcessingError) as caught:
        BinaryMask(*args)
    assert caught.value.code == "INVALID_OUTPUT"


@pytest.mark.parametrize(
    "box", [(0, 0, 2, 1), (0, 0, 0, 1), (0, 0, float("nan"), 1), (False, 0, 1, 1)]
)
def test_region_rejects_invalid_box(box):
    with pytest.raises(NailProcessingError):
        LocalizedRegion(1, "nail", 0.9, box, BinaryMask(1, 1, b"\xff"))


@pytest.mark.parametrize("confidence", [True, -0.1, 1.1, float("nan")])
def test_region_rejects_invalid_confidence(confidence):
    with pytest.raises(NailProcessingError):
        LocalizedRegion(1, "nail", confidence, (0, 0, 1, 1), BinaryMask(1, 1, b"\xff"))


@pytest.mark.parametrize(
    "status,regions",
    [
        ("OK", ()),
        ("NO_NAILS", (region(),)),
        ("WRONG", ()),
        ("OK", [region()]),
        ("OK", (region(2),)),
    ],
)
def test_localization_enforces_outcome_and_order(status, regions):
    with pytest.raises(NailProcessingError):
        NailLocalization(status, regions)


def test_values_are_immutable_and_valid_outcomes_work():
    image = RgbImage(1, 1, b"abc")
    with pytest.raises(FrozenInstanceError):
        image.width = 2
    assert NailLocalization("NO_NAILS", ()).regions == ()
    assert NailLocalization("OK", (region(),)).regions[0].mask.pixels == b"\xff"


def test_profile_rejects_noncanonical_fingerprint():
    with pytest.raises(NailProcessingError):
        LocalizationProfile("private/config/not-a-fingerprint")
    assert LocalizationProfile("a" * 64).extractor_fingerprint == "a" * 64


def test_extreme_numeric_output_is_a_typed_failure():
    with pytest.raises(NailProcessingError) as caught:
        LocalizedRegion(1, "nail", 10**1000, (0, 0, 1, 1), BinaryMask(1, 1, b"\xff"))
    assert caught.value.code == "INVALID_OUTPUT"


from product_search.search.nail_contracts import (
    CatalogPhoto,
    CatalogProduct,
    EmbeddingProfile,
    PairMatch,
    PhotoEmbeddings,
    ProcessedPhoto,
    ReadyCatalog,
    RegionCrop,
)


@pytest.mark.parametrize(
    "make",
    [
        lambda: PhotoEmbeddings(1, "a" * 64, (1,), [("openclip_b32", ((1.0,),))]),
        lambda: PhotoEmbeddings(1, "a" * 64, (1,), (("openclip_b32", ((1.0,),)),)),
        lambda: ProcessedPhoto(1, "a" * 64, "OK", ()),
        lambda: ProcessedPhoto(1, "a" * 64, "NO_NAILS", []),
        lambda: CatalogProduct("p", ()),
        lambda: CatalogPhoto("", None),
        lambda: ReadyCatalog(
            "rep",
            "a" * 64,
            EmbeddingProfile(
                (("openclip_b32", "r1"), ("dinov2_b14", "r2"), ("siglip2_b16_224", "r3"))
            ),
            "yes",
        ),
        lambda: PairMatch(1, "p", (1, 1), (), 1.1),
        lambda: RegionCrop(
            1, (0.0, 0.0, 1.0, 1.0), (0, 0, 2, 1), BinaryMask(1, 1, b"\xff"), RgbImage(1, 1, b"abc")
        ),
    ],
)
def test_us2_malformed_boundary_is_rejected(make):
    with pytest.raises(NailProcessingError):
        make()


@pytest.mark.parametrize(
    "first,second",
    [
        ((0.1, (0.0, 0.0, 2.0, 2.0), "nail"), (0.9, (0.0, 0.0, 2.0, 2.0), "nail")),
        ((0.5, (1.0, 0.0, 2.0, 2.0), "nail"), (0.5, (0.0, 0.0, 2.0, 2.0), "nail")),
        ((0.5, (0.0, 0.0, 2.0, 2.0), "z"), (0.5, (0.0, 0.0, 2.0, 2.0), "a")),
    ],
)
def test_localization_rejects_noncanonical_detection_order(first, second):
    mask = BinaryMask(2, 2, b"\xff" * 4)
    regions = tuple(
        LocalizedRegion(i, label, confidence, box, mask)
        for i, (confidence, box, label) in enumerate((first, second), 1)
    )
    with pytest.raises(NailProcessingError):
        NailLocalization("OK", regions)


def test_exact_duplicate_sort_keys_preserve_upstream_masks():
    first = LocalizedRegion(
        1, "nail", 0.5, (0.0, 0.0, 2.0, 2.0), BinaryMask(2, 2, b"\xff\x00\x00\x00")
    )
    second = LocalizedRegion(
        2, "nail", 0.5, (0.0, 0.0, 2.0, 2.0), BinaryMask(2, 2, b"\x00\x00\x00\xff")
    )
    assert NailLocalization("OK", (first, second)).regions == (first, second)


from product_search.search.nail_contracts import (
    BuildPhoto,
    BuildPhotoResult,
    BuildSummary,
    PhotoInput,
    RegionArtifacts,
    StoredPhotoState,
)

G3_UUID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.parametrize(
    "make",
    [
        lambda: BuildPhoto(G3_UUID, True, PhotoInput(1, "a" * 32, "b" * 64)),
        lambda: RegionArtifacts(1, "../escape", "a" * 32, "b" * 64),
        lambda: BuildPhotoResult(G3_UUID, G3_UUID, None, None, [], "MODEL_ERROR"),
        lambda: StoredPhotoState(
            BuildPhoto(G3_UUID, 1, PhotoInput(1, "a" * 32, "b" * 64)), "BROKEN", None, ()
        ),
        lambda: BuildSummary(G3_UUID, "BUILDING", 1, 0, 0, 0, 1, True, ()),
    ],
)
def test_g3_build_data_rejects_mutable_or_incoherent_boundaries(make):
    with pytest.raises(NailProcessingError):
        make()


from product_search.search.nail_contracts import (
    EvaluationAnnotation,
    EvaluationCandidate,
    EvaluationPhoto,
    EvaluationRun,
)


@pytest.mark.parametrize(
    "make",
    [
        lambda: EvaluationPhoto(True, "a" * 64),
        lambda: EvaluationCandidate(1, 1, float("nan")),
        lambda: EvaluationAnnotation(1, "BROKEN", None),
        lambda: EvaluationRun([("openclip_b32", "r")], b"{}"),
    ],
)
def test_final_evidence_scalar_and_immutable_contracts(make):
    with pytest.raises(NailProcessingError):
        make()
