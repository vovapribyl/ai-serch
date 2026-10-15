import pytest

from product_search.search.nail_contracts import (
    BinaryMask,
    DecodeProfile,
    LocalizationProfile,
    LocalizedRegion,
    NailLocalization,
    NailProcessingError,
    PhotoInput,
    RgbImage,
)
from product_search.search.nail_image_processor import NailImageProcessor


class Images:
    def read_rgb(self, photo, profile):
        assert isinstance(profile, DecodeProfile)
        return RgbImage(3, 2, bytes(range(18)))


class Localization:
    def __init__(self, result):
        self.result = result

    def localize(self, image, profile):
        assert (image.width, image.height) == (3, 2)
        assert profile.extractor_fingerprint == "a" * 64
        return self.result


def processor(result, max_regions=10):
    return NailImageProcessor(
        Images(),
        Localization(result),
        DecodeProfile(100, 100),
        LocalizationProfile("a" * 64),
        max_regions,
    )


def test_mask_bbox_white_pixels_and_source_mask():
    mask = BinaryMask(3, 2, bytes([0, 255, 0, 0, 0, 255]))
    result = NailLocalization("OK", (LocalizedRegion(1, "nail", 0.1, (0.0, 0.0, 3.0, 2.0), mask),))
    p = processor(result)
    query = p.process(PhotoInput(1, "a" * 32, "b" * 64))
    assert query is not None
    assert query == p.process(PhotoInput(1, "a" * 32, "b" * 64))
    crop = query.regions[0]
    assert crop.crop_box_xyxy == (1, 0, 3, 2)
    assert crop.detector_box_xyxy == (0.0, 0.0, 3.0, 2.0)
    assert crop.rgb_crop == RgbImage(
        2, 2, bytes([3, 4, 5, 255, 255, 255, 255, 255, 255, 15, 16, 17])
    )
    assert crop.mask == mask


def test_no_nails_is_not_a_failure_or_fallback():
    result = processor(NailLocalization("NO_NAILS", ())).process(PhotoInput(1, "a" * 32, "b" * 64))
    assert result is not None
    assert result.status == "NO_NAILS" and result.regions == ()


def test_invalid_frame_and_region_budget_reject_entire_photo():
    wrong = LocalizedRegion(1, "nail", 0.1, (0.0, 0.0, 1.0, 1.0), BinaryMask(1, 1, b"\xff"))
    with pytest.raises(NailProcessingError):
        processor(NailLocalization("OK", (wrong,))).process(PhotoInput(1, "a" * 32, "b" * 64))
    good = LocalizedRegion(1, "nail", 0.1, (0.0, 0.0, 3.0, 2.0), BinaryMask(3, 2, b"\xff" * 6))
    second = LocalizedRegion(2, "nail", 0.05, (0.0, 0.0, 3.0, 2.0), good.mask)
    with pytest.raises(NailProcessingError, match="RESOURCE_LIMIT"):
        processor(NailLocalization("OK", (good, second)), 1).process(
            PhotoInput(1, "a" * 32, "b" * 64)
        )


def test_low_confidence_regions_keep_order():
    mask = BinaryMask(3, 2, b"\xff" * 6)
    regions = tuple(
        LocalizedRegion(i, "nail", confidence, (0.0, 0.0, 3.0, 2.0), mask)
        for i, confidence in [(1, 0.2), (2, 0.0)]
    )
    result = processor(NailLocalization("OK", regions)).process(PhotoInput(1, "a" * 32, "b" * 64))
    assert result is not None
    assert tuple(c.ordinal for c in result.regions) == (1, 2)
