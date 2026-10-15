from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from PIL import Image

from experiments.nail_localization.config import FrozenConfig, freeze_config
from experiments.nail_localization.langsam_adapter import LangSAMAdapter, LazyLangSAMClient

LOCK_BYTES = b"synthetic-package==1.0.0\n"


def canonical_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def frozen_config() -> FrozenConfig:
    lock_fingerprint = f"sha256:{hashlib.sha256(LOCK_BYTES).hexdigest()}"
    body: dict[str, Any] = {
        "schema_version": "1",
        "adapter": {"repository": "example/langsam", "revision": "abc123"},
        "detector": {"repository": "example/detector", "revision": "def456"},
        "segmenter": {"repository": "example/segmenter", "revision": "789abc"},
        "prompt": {"id": "nails-v1", "text": "press-on nails"},
        "thresholds": {"box": 0.25, "text": 0.2, "mask": 0.5},
        "postprocessing": {"min_mask_area_px": 1, "merge_overlaps": False},
        "image_preparation": {
            "exif_transpose": True,
            "color_mode": "RGB",
            "max_side_px": 1024,
        },
        "device": "cpu",
        "mps_operator_fallback_enabled": False,
        "python_version": "3.12.11",
        "dependencies": {"synthetic-package": "1.0.0"},
        "dependency_lock_fingerprint": lock_fingerprint,
        "deterministic": {"seed": 0, "deterministic_algorithms": True},
    }
    payload = {**body, "config_fingerprint": canonical_fingerprint(body)}
    return freeze_config(payload, lock_bytes=LOCK_BYTES)


def valid_response() -> dict[str, Any]:
    return {
        "boxes": [[0.0, 0.0, 2.0, 2.0]],
        "masks": [[[1, 0], [0, 1]]],
        "scores": [0.9],
        "labels": ["press-on nails"],
    }


class FakeUpstreamClient:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = valid_response() if response is None else response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def predict(
        self,
        image: object,
        *,
        text_prompt: str,
        box_threshold: float,
        text_threshold: float,
    ) -> object:
        self.calls.append(
            {
                "image": image,
                "text_prompt": text_prompt,
                "box_threshold": box_threshold,
                "text_threshold": text_threshold,
            }
        )
        if self.error is not None:
            raise self.error
        return self.response


class FakeArrayLike:
    def __init__(self, value: object) -> None:
        self.value = value

    def tolist(self) -> object:
        return self.value


def test_c01_normalizes_one_box_and_mask_without_model_specific_objects() -> None:
    image = Image.new("RGB", (2, 2), color=(0, 0, 0))
    response = valid_response()
    response["boxes"] = FakeArrayLike(response["boxes"])
    response["masks"] = FakeArrayLike(response["masks"])
    response["scores"] = FakeArrayLike(response["scores"])
    client = FakeUpstreamClient(response)

    result = LangSAMAdapter(client).localize(image, frozen_config())

    assert result.status == "SUCCESS"
    assert result.error_code is None
    assert len(result.detections) == 1
    detection = result.detections[0]
    assert detection.box_xyxy == (0.0, 0.0, 2.0, 2.0)
    assert detection.mask.pixels == b"\xff\x00\x00\xff"
    assert client.calls == [
        {
            "image": image,
            "text_prompt": "press-on nails",
            "box_threshold": 0.25,
            "text_threshold": 0.2,
        }
    ]


def test_c02_normalizes_and_deterministically_sorts_multiple_objects() -> None:
    response = {
        "boxes": [[1.0, 0.0, 2.0, 2.0], [0.0, 0.0, 1.0, 2.0]],
        "masks": [[[0, 1], [0, 1]], [[1, 0], [1, 0]]],
        "scores": [0.7, 0.95],
        "labels": ["second", "first"],
    }

    result = LangSAMAdapter(FakeUpstreamClient(response)).localize(
        Image.new("RGB", (2, 2)), frozen_config()
    )

    assert result.status == "SUCCESS"
    assert [item.label for item in result.detections] == ["first", "second"]
    assert all(not hasattr(item.mask, "numpy") for item in result.detections)


def test_c03_empty_detector_result_is_explicit_localization_failure() -> None:
    response = {"boxes": [], "masks": [], "scores": [], "labels": []}

    result = LangSAMAdapter(FakeUpstreamClient(response)).localize(
        Image.new("RGB", (2, 2)), frozen_config()
    )

    assert result.status == "LOCALIZATION_FAILED"
    assert result.detections == ()
    assert result.error_code == "DETECTOR_NO_MATCH"


def test_c04_mismatched_output_lengths_are_invalid_model_output() -> None:
    response = valid_response()
    response["scores"] = []

    result = LangSAMAdapter(FakeUpstreamClient(response)).localize(
        Image.new("RGB", (2, 2)), frozen_config()
    )

    assert result.status == "TECHNICAL_ERROR"
    assert result.detections == ()
    assert result.error_code == "INVALID_MODEL_OUTPUT"


def test_c05_invalid_box_geometry_or_mask_shape_is_invalid_model_output() -> None:
    invalid_box = valid_response()
    invalid_box["boxes"] = [[2.0, 0.0, 1.0, 2.0]]
    invalid_mask = deepcopy(valid_response())
    invalid_mask["masks"] = [[[1, 0]]]

    for response in (invalid_box, invalid_mask):
        result = LangSAMAdapter(FakeUpstreamClient(response)).localize(
            Image.new("RGB", (2, 2)), frozen_config()
        )
        assert result.status == "TECHNICAL_ERROR"
        assert result.detections == ()
        assert result.error_code == "INVALID_MODEL_OUTPUT"


def test_c05a_clamps_subpixel_box_boundary_overshoot() -> None:
    response = valid_response()
    response["boxes"] = [[-0.05, 0.04, 2.05, 1.96]]

    result = LangSAMAdapter(FakeUpstreamClient(response)).localize(
        Image.new("RGB", (2, 2)), frozen_config()
    )

    assert result.status == "SUCCESS"
    assert result.detections[0].box_xyxy == (0.0, 0.04, 2.0, 1.96)


def test_c05b_rejects_box_outside_boundary_tolerance() -> None:
    response = valid_response()
    response["boxes"] = [[-1.01, 0.0, 2.0, 2.0]]

    result = LangSAMAdapter(FakeUpstreamClient(response)).localize(
        Image.new("RGB", (2, 2)), frozen_config()
    )

    assert result.status == "TECHNICAL_ERROR"
    assert result.detections == ()
    assert result.error_code == "INVALID_MODEL_OUTPUT"


def test_c06_upstream_exception_becomes_model_error_without_leaking_exception() -> None:
    client = FakeUpstreamClient(error=RuntimeError("synthetic upstream details"))

    result = LangSAMAdapter(client).localize(Image.new("RGB", (2, 2)), frozen_config())

    assert result.status == "TECHNICAL_ERROR"
    assert result.detections == ()
    assert result.error_code == "MODEL_ERROR"


def test_c07_rendered_original_image_never_becomes_a_silent_mask_fallback() -> None:
    image = Image.new("RGB", (2, 2), color=(10, 20, 30))
    response = {
        "boxes": [[0.0, 0.0, 2.0, 2.0]],
        "masks": [],
        "scores": [0.9],
        "labels": ["press-on nails"],
        "rendered_image": image.copy(),
    }

    result = LangSAMAdapter(FakeUpstreamClient(response)).localize(image, frozen_config())

    assert result.status == "LOCALIZATION_FAILED"
    assert result.detections == ()
    assert result.error_code == "SEGMENTER_EMPTY"


def test_e01_lazy_client_does_not_import_ml_modules_before_first_prediction() -> None:
    imported: list[str] = []

    def forbidden_import(name: str) -> object:
        imported.append(name)
        raise AssertionError("ML import must be lazy")

    LazyLangSAMClient(import_module=forbidden_import)

    assert imported == []


def test_e02_lazy_client_uses_single_item_batch_and_local_allowlisted_paths() -> None:
    image = Image.new("RGB", (2, 2))
    calls: list[dict[str, object]] = []

    class FakeLangSAM:
        def __init__(self, **kwargs: object) -> None:
            calls.append({"init": kwargs})

        def predict(self, **kwargs: object) -> list[dict[str, object]]:
            calls.append({"predict": kwargs})
            return [valid_response()]

    def fake_import(name: str) -> object:
        assert name == "lang_sam"
        return type("Module", (), {"LangSAM": FakeLangSAM})

    client = LazyLangSAMClient(import_module=fake_import)
    result = client.predict(
        image,
        text_prompt="press-on nails",
        box_threshold=0.25,
        text_threshold=0.2,
    )

    assert result == valid_response()
    assert calls == [
        {
            "init": {
                "sam_type": "sam2.1_hiera_small",
                "sam_ckpt_path": str(LazyLangSAMClient.SAM_CHECKPOINT_PATH),
                "gdino_model_ckpt_path": str(LazyLangSAMClient.GDINO_SNAPSHOT_PATH),
                "gdino_processor_ckpt_path": str(LazyLangSAMClient.GDINO_SNAPSHOT_PATH),
                "device": "mps",
            }
        },
        {
            "predict": {
                "images_pil": [image],
                "texts_prompt": ["press-on nails"],
                "box_threshold": 0.25,
                "text_threshold": 0.2,
            }
        },
    ]


def test_e03_lazy_client_requires_exactly_one_mapping_result() -> None:
    class FakeLangSAM:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def predict(self, **kwargs: object) -> object:
            del kwargs
            return []

    def fake_import(name: str) -> object:
        assert name == "lang_sam"
        return type("Module", (), {"LangSAM": FakeLangSAM})

    client = LazyLangSAMClient(import_module=fake_import)

    try:
        client.predict(
            Image.new("RGB", (2, 2)),
            text_prompt="press-on nails",
            box_threshold=0.25,
            text_threshold=0.2,
        )
    except ValueError as exc:
        assert "exactly one mapping" in str(exc)
    else:
        raise AssertionError("multiple or empty batch result must be rejected")


def test_e04_adapter_ignores_upstream_mask_scores_metadata() -> None:
    response = valid_response()
    response["mask_scores"] = [0.99]

    result = LangSAMAdapter(FakeUpstreamClient(response)).localize(
        Image.new("RGB", (2, 2)), frozen_config()
    )

    assert result.status == "SUCCESS"
    assert result.error_code is None
