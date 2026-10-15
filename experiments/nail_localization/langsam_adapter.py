from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module as _import_module
from pathlib import Path
from typing import Any, Protocol

from .config import FrozenConfig
from .contracts import (
    ContractError,
    Detection,
    LocalizationResult,
    MaskData,
    normalize_result,
)

_BOX_BOUNDARY_TOLERANCE_PX = 1.0


class LangSAMClient(Protocol):
    """Injected upstream boundary; the real ML client is not imported in stage C."""

    def predict(
        self,
        image: object,
        *,
        text_prompt: str,
        box_threshold: float,
        text_threshold: float,
    ) -> object: ...


class LazyLangSAMClient:
    """Stage E scaffold for the opt-in, local-only LangSAM binding."""

    GDINO_SNAPSHOT_PATH = Path(
        "/Users/v.pribylovskiy/Documents/Codex/outputs/nail-localization-v1/model-cache/"
        "grounding-dino-base--12bdfa3120f3e7ec7b434d90674b3396eccf88eb"
    )
    SAM_CHECKPOINT_PATH = Path(
        "/Users/v.pribylovskiy/Documents/Codex/outputs/nail-localization-v1/model-cache/"
        "sam2.1-hiera-small/sam2.1_hiera_small.pt"
    )

    def __init__(
        self,
        *,
        device: str = "mps",
        gdino_snapshot_path: Path | None = None,
        sam_checkpoint_path: Path | None = None,
        gdino_allowed_files: frozenset[str] | None = None,
        initialize_runtime: Callable[[], None] | None = None,
        import_module: Callable[[str], object] = _import_module,
    ) -> None:
        if device not in {"mps", "cpu"}:
            raise ValueError("device must be mps or cpu")
        self._import_module = import_module
        self._model: object | None = None
        self._device = device
        self._initialize_runtime = initialize_runtime
        self._gdino_snapshot_path = (
            self.GDINO_SNAPSHOT_PATH if gdino_snapshot_path is None else gdino_snapshot_path
        )
        self._sam_checkpoint_path = (
            self.SAM_CHECKPOINT_PATH if sam_checkpoint_path is None else sam_checkpoint_path
        )
        self._gdino_allowed_files = gdino_allowed_files or frozenset(
            {
                "config.json",
                "model.safetensors",
                "preprocessor_config.json",
                "special_tokens_map.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "vocab.txt",
            }
        )
        if not self._gdino_snapshot_path.is_absolute() or not self._sam_checkpoint_path.is_absolute():
            raise ValueError("model paths must be absolute")

    def predict(
        self,
        image: object,
        *,
        text_prompt: str,
        box_threshold: float,
        text_threshold: float,
    ) -> object:
        model = self._model
        if model is None:
            self._validate_local_allowlist()
            if self._initialize_runtime is not None:
                self._initialize_runtime()
            module = self._import_module("lang_sam")
            constructor = getattr(module, "LangSAM", None)
            if not callable(constructor):
                raise ValueError("LangSAM constructor is unavailable")
            model = constructor(
                sam_type="sam2.1_hiera_small",
                sam_ckpt_path=str(self._sam_checkpoint_path),
                gdino_model_ckpt_path=str(self._gdino_snapshot_path),
                gdino_processor_ckpt_path=str(self._gdino_snapshot_path),
                device=self._device,
            )
            self._model = model
        predict = getattr(model, "predict", None)
        if not callable(predict):
            raise TypeError("LangSAM predict is unavailable")
        batch = predict(
            images_pil=[image],
            texts_prompt=[text_prompt],
            box_threshold=box_threshold,
            text_threshold=text_threshold,
        )
        if (
            not isinstance(batch, Sequence)
            or isinstance(batch, (str, bytes, bytearray))
            or len(batch) != 1
            or not isinstance(batch[0], Mapping)
        ):
            raise ValueError("LangSAM must return exactly one mapping result")
        return batch[0]

    def _validate_local_allowlist(self) -> None:
        if not self._gdino_snapshot_path.is_dir() or not self._sam_checkpoint_path.is_file():
            raise ValueError("allowlisted local model paths are unavailable")
        if {path.name for path in self._gdino_snapshot_path.iterdir()} != self._gdino_allowed_files:
            raise ValueError("Grounding DINO local snapshot violates the allowlist")


class LangSAMAdapter:
    """Normalize one injected LangSAM-like client into the experiment contract."""

    def __init__(self, client: LangSAMClient) -> None:
        self._client = client

    def localize(self, image: object, frozen_config: FrozenConfig) -> LocalizationResult:
        try:
            width, height = _image_size(image)
            response = self._client.predict(
                image,
                text_prompt=frozen_config.data["prompt"]["text"],
                box_threshold=frozen_config.data["thresholds"]["box"],
                text_threshold=frozen_config.data["thresholds"]["text"],
            )
        except Exception:  # noqa: BLE001 - upstream details must not cross the adapter boundary.
            return LocalizationResult("TECHNICAL_ERROR", (), "MODEL_ERROR")

        try:
            return _normalize_response(
                response,
                width=width,
                height=height,
                mask_threshold=frozen_config.data["thresholds"]["mask"],
            )
        except (ContractError, KeyError, TypeError, ValueError, OverflowError):
            return LocalizationResult("TECHNICAL_ERROR", (), "INVALID_MODEL_OUTPUT")


def _normalize_response(
    response: object,
    *,
    width: int,
    height: int,
    mask_threshold: float,
) -> LocalizationResult:
    if not isinstance(response, Mapping):
        raise ContractError("upstream response must be a mapping")
    allowed_fields = {
        "boxes",
        "masks",
        "scores",
        "labels",
        "mask_scores",
        "rendered_image",
    }
    required_fields = {"boxes", "masks", "scores", "labels"}
    if not required_fields.issubset(response) or not set(response).issubset(allowed_fields):
        raise ContractError("upstream response has unknown or missing fields")

    boxes = _sequence(response["boxes"])
    masks = _sequence(response["masks"])
    scores = _sequence(response["scores"])
    labels = _sequence(response["labels"])
    if not boxes:
        if masks or scores or labels:
            raise ContractError("empty boxes require every model output to be empty")
        return LocalizationResult("LOCALIZATION_FAILED", (), "DETECTOR_NO_MATCH")
    if not masks and len(scores) == len(boxes) == len(labels):
        return LocalizationResult("LOCALIZATION_FAILED", (), "SEGMENTER_EMPTY")
    if not (len(boxes) == len(masks) == len(scores) == len(labels)):
        raise ContractError("model output lengths do not match")

    detections: list[Detection] = []
    for box, mask, score, label in zip(boxes, masks, scores, labels, strict=True):
        box_values = _sequence(box)
        if len(box_values) != 4:
            raise ContractError("box must contain four coordinates")
        coordinates = _bounded_box(box_values, width=width, height=height)
        confidence = _finite_number(score)
        if not isinstance(label, str) or not label:
            raise ContractError("label must be a non-empty string")
        mask_data = MaskData(
            width=width,
            height=height,
            pixels=_mask_bytes(mask, width=width, height=height, threshold=mask_threshold),
        )
        detections.append(Detection(label, confidence, coordinates, mask_data))

    return normalize_result(
        LocalizationResult("SUCCESS", tuple(detections), None),
        width=width,
        height=height,
    )


def _image_size(image: object) -> tuple[int, int]:
    size = getattr(image, "size", None)
    if (
        not isinstance(size, tuple)
        or len(size) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in size)
    ):
        raise ContractError("image must expose positive integer dimensions")
    return size


def _bounded_box(
    box: Sequence[object], *, width: int, height: int
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (_finite_number(value) for value in box)
    if (
        x0 < -_BOX_BOUNDARY_TOLERANCE_PX
        or y0 < -_BOX_BOUNDARY_TOLERANCE_PX
        or x1 > width + _BOX_BOUNDARY_TOLERANCE_PX
        or y1 > height + _BOX_BOUNDARY_TOLERANCE_PX
    ):
        raise ContractError("box exceeds the image boundary tolerance")
    bounded = (
        min(max(x0, 0.0), float(width)),
        min(max(y0, 0.0), float(height)),
        min(max(x1, 0.0), float(width)),
        min(max(y1, 0.0), float(height)),
    )
    if not (bounded[0] < bounded[2] and bounded[1] < bounded[3]):
        raise ContractError("box must have positive area after boundary normalization")
    return bounded


def _mask_bytes(mask: object, *, width: int, height: int, threshold: float) -> bytes:
    rows = _sequence(mask)
    if len(rows) != height:
        raise ContractError("mask height does not match the image")
    pixels = bytearray()
    for row in rows:
        values = _sequence(row)
        if len(values) != width:
            raise ContractError("mask width does not match the image")
        for value in values:
            numeric = _finite_number(value)
            if numeric == 255:
                pixels.append(255)
            elif 0 <= numeric <= 1:
                pixels.append(255 if numeric >= threshold else 0)
            else:
                raise ContractError("mask values must be binary or normalized")
    return bytes(pixels)


def _sequence(value: object) -> Sequence[Any]:
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    raise ContractError("model output must be a sequence")


def _finite_number(value: object) -> float:
    item = getattr(value, "item", None)
    if callable(item):
        value = item()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("model output number has an invalid type")
    number = float(value)
    if not math.isfinite(number):
        raise ContractError("model output number must be finite")
    return number
