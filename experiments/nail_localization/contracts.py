from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class MaskData:
    width: int
    height: int
    pixels: bytes


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box_xyxy: tuple[float, float, float, float]
    mask: MaskData


@dataclass(frozen=True)
class LocalizationResult:
    status: str
    detections: tuple[Detection, ...]
    error_code: str | None


class ContractError(ValueError):
    """Raised when a normalized localization result violates the contract."""


def normalize_result(result: LocalizationResult, *, width: int, height: int) -> LocalizationResult:
    if width <= 0 or height <= 0:
        raise ContractError("image dimensions must be positive")

    allowed_statuses = {"SUCCESS", "LOCALIZATION_FAILED", "TECHNICAL_ERROR"}
    allowed_errors = {
        "DETECTOR_NO_MATCH",
        "SEGMENTER_EMPTY",
        "INVALID_MODEL_OUTPUT",
        "MODEL_ERROR",
        "INVALID_IMAGE",
        "RESOURCE_ERROR",
        "ARTIFACT_WRITE_ERROR",
    }
    if result.status not in allowed_statuses:
        raise ContractError("unknown localization status")
    if result.status == "SUCCESS":
        if not result.detections or result.error_code is not None:
            raise ContractError("SUCCESS requires detections and no error code")
    elif result.detections or result.error_code not in allowed_errors:
        raise ContractError("failed results require no detections and an allowed error code")

    validated: list[Detection] = []
    for detection in result.detections:
        if not detection.label:
            raise ContractError("detection label must not be empty")
        if not math.isfinite(detection.confidence) or not 0 <= detection.confidence <= 1:
            raise ContractError("confidence must be finite and within [0, 1]")
        if len(detection.box_xyxy) != 4 or not all(
            math.isfinite(value) for value in detection.box_xyxy
        ):
            raise ContractError("box coordinates must be finite")
        x0, y0, x1, y1 = detection.box_xyxy
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ContractError("box must be a valid half-open image region")
        mask = detection.mask
        if mask.width != width or mask.height != height:
            raise ContractError("mask dimensions must match the decoded image")
        if len(mask.pixels) != width * height or any(value not in {0, 255} for value in mask.pixels):
            raise ContractError("mask pixels must contain width * height binary bytes")
        validated.append(detection)

    validated.sort(
        key=lambda item: (
            -item.confidence,
            *item.box_xyxy,
            item.label,
        )
    )
    return LocalizationResult(result.status, tuple(validated), result.error_code)
