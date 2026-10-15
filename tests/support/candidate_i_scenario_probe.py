"""Test-only full-scenario helpers; never import model SDKs."""

import hashlib
import math
from types import SimpleNamespace

from product_search.search.nail_contracts import DecodeProfile, PhotoInput
from product_search.search.nail_image_processor import NailImageProcessor


def real_crops(image, result, localization_profile, profile):
    if result.status != "OK" or not result.regions:
        raise ValueError("full lifecycle not exercised")
    processor = NailImageProcessor(
        SimpleNamespace(read_rgb=lambda photo, decode: image),
        SimpleNamespace(localize=lambda rgb, pinned: result),
        DecodeProfile(profile["max_source_bytes"], profile["max_decoded_pixels"]),
        localization_profile,
        profile["max_region_count"],
    )
    photo = processor.process(PhotoInput(1, "a" * 32, hashlib.sha256(image.pixels).hexdigest()))
    return tuple(region.rgb_crop for region in photo.regions)


def counted_factory(factory, admit):
    def load():
        admit()
        provider = factory()

        def encode(image):
            admit()
            return provider.encode_image(image)

        return SimpleNamespace(
            model_key=provider.model_key,
            revision=provider.revision,
            embedding_dim=provider.embedding_dim,
            encode_image=encode,
        )

    return load


def encode_all_crops(adapter, crops, profile):
    summaries = []
    for key, dimension in (("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)):
        rows = adapter.encode(key, crops, profile)
        assert len(rows) == len(crops)
        for row in rows:
            assert len(row) == dimension and all(math.isfinite(value) for value in row)
            assert abs(math.sqrt(sum(value * value for value in row)) - 1) < 1e-5
        summaries.append({"model_key": key, "count": len(rows), "dimension": dimension})
    return summaries


def backend_embedding(model_root, admit):
    """Same pinned providers as G4; SDK imports occur only in an authorized controller."""
    from product_search.infrastructure.nail_ml_adapters import NailEmbeddingAdapter
    from product_search.search.model_manifest import read_manifest, verify_manifest
    from product_search.search.openclip_provider import OpenClipImageProvider
    from product_search.search.transformers_provider import TransformersImageProvider

    revisions = (
        ("openclip_b32", "1a25a446712ba5ee05982a381eed697ef9b435cf"),
        ("dinov2_b14", "f9e44c814b77203eaa57a6bdbbd535f21ede1415"),
        ("siglip2_b16_224", "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"),
    )
    hashes = (
        "7daa2142c71b4c9b0ec0555361845dc78fbb0dbce6bed64ca784ae853404d67d",
        "ecb704699963bfe8bb17f8defd3792daa26cf0da822032b796f6f5a40d606783",
        "45f047affe3c7c58e6789db142ae73b40096a0207f1417e3f976d3a9d15969e9",
    )
    for (key, _), expected in zip(revisions, hashes):
        manifest = read_manifest(model_root / key)
        assert verify_manifest(model_root / key, manifest).sha256 == expected
    factories = {
        "openclip_b32": lambda: OpenClipImageProvider(
            revisions[0][1], model_root / revisions[0][0], device="mps"
        ),
        "dinov2_b14": lambda: TransformersImageProvider(
            *revisions[1], model_root / revisions[1][0], 768, device="mps"
        ),
        "siglip2_b16_224": lambda: TransformersImageProvider(
            *revisions[2], model_root / revisions[2][0], 768, device="mps"
        ),
    }
    return NailEmbeddingAdapter(
        {key: counted_factory(factory, admit) for key, factory in factories.items()}
    ), revisions
