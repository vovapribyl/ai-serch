import math

import pytest

from product_search.infrastructure.nail_ml_adapters import NailEmbeddingAdapter
from product_search.search.nail_contracts import EmbeddingProfile, NailProcessingError, RgbImage

PROFILE = EmbeddingProfile(
    (("openclip_b32", "r1"), ("dinov2_b14", "r2"), ("siglip2_b16_224", "r3"))
)


class Provider:
    def __init__(self, key, revision, dim, invalid=None):
        self.model_key = key
        self.revision = revision
        self.embedding_dim = dim
        self.invalid = invalid

    def encode_image(self, image):
        if self.invalid is not None:
            return self.invalid
        return (float(image.getpixel((0, 0))[0] + 1),) + (0.0,) * (self.embedding_dim - 1)


def adapter(invalid=None, revision=None, dimension=None):
    factories = {}
    for (key, rev), dim in zip(PROFILE.revisions, (512, 768, 768)):
        factories[key] = lambda key=key, rev=rev, dim=dim: Provider(
            key, revision or rev, dimension or dim, invalid
        )
    return NailEmbeddingAdapter(factories)


def test_full_models_preserve_crop_order():
    crops = (RgbImage(1, 1, b"\x09\x00\x00"), RgbImage(1, 1, b"\x03\x00\x00"))
    for key, dim in [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)]:
        rows = adapter().encode(key, crops, PROFILE)
        assert rows is not None
        assert tuple(row[0] for row in rows) == (10.0, 4.0)
        assert all(len(row) == dim for row in rows)


@pytest.mark.parametrize(
    "invalid", [(0.0,) * 512, (math.nan,) + (0.0,) * 511, (1.0,), (math.inf,) + (0.0,) * 511]
)
def test_provider_invalid_output_is_failure(invalid):
    with pytest.raises(NailProcessingError):
        adapter(invalid).encode("openclip_b32", (RgbImage(1, 1, b"abc"),), PROFILE)


@pytest.mark.parametrize("kwargs", [{"revision": "other"}, {"dimension": 3}])
def test_identity_mismatch_before_encode(kwargs):
    with pytest.raises(NailProcessingError, match="PROFILE_MISMATCH"):
        adapter(**kwargs).encode("openclip_b32", (RgbImage(1, 1, b"abc"),), PROFILE)


def test_no_degraded_profile_or_missing_factory():
    with pytest.raises(NailProcessingError):
        EmbeddingProfile((("openclip_b32", "r1"),))
    with pytest.raises(NailProcessingError):
        NailEmbeddingAdapter({}).encode("openclip_b32", (RgbImage(1, 1, b"abc"),), PROFILE)
