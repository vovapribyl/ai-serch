from __future__ import annotations

from typing import Protocol

from PIL import Image

from .config import FrozenConfig
from .contracts import Detection, LocalizationResult, MaskData
from .roi import select_nested_roi


class Localizer(Protocol):
    def localize(self, image: object, frozen_config: FrozenConfig) -> LocalizationResult: ...


class TwoPassRoiLocalizer:
    """Apply the frozen box filter and an optional second pass inside packaging ROI."""

    def __init__(self, base: Localizer) -> None:
        self._base = base

    def localize(self, image: object, frozen_config: FrozenConfig) -> LocalizationResult:
        if not isinstance(image, Image.Image):
            raise TypeError("PIL image required")
        first = self._base.localize(image, frozen_config)
        if first.status != "SUCCESS":
            return first
        postprocessing = frozen_config.data["postprocessing"]
        max_box_ratio = postprocessing["max_detection_box_area_ratio"]
        roi_config = postprocessing["packaging_roi"]
        selection = select_nested_roi(
            tuple(detection.box_xyxy for detection in first.detections),
            tuple(detection.confidence for detection in first.detections),
            width=image.width,
            height=image.height,
            min_parent_area_ratio=roi_config["min_parent_area_ratio"],
            max_parent_area_ratio=roi_config["max_parent_area_ratio"],
            padding_ratio=roi_config["padding_ratio"],
            min_roi_aspect_ratio=roi_config["min_aspect_ratio"],
            max_roi_aspect_ratio=roi_config["max_aspect_ratio"],
        )
        if selection is None:
            return _filter_large_boxes(first, width=image.width, height=image.height, limit=max_box_ratio)

        crop = image.crop(selection.box_xyxy)
        second = self._base.localize(crop, frozen_config)
        if second.status != "SUCCESS":
            return _filter_large_boxes(first, width=image.width, height=image.height, limit=max_box_ratio)
        filtered = _filter_large_boxes(second, width=crop.width, height=crop.height, limit=max_box_ratio)
        if filtered.status != "SUCCESS":
            return _filter_large_boxes(first, width=image.width, height=image.height, limit=max_box_ratio)
        return _restore_to_source(filtered, source_size=image.size, offset=selection.box_xyxy[:2])


def _filter_large_boxes(
    result: LocalizationResult,
    *,
    width: int,
    height: int,
    limit: float,
) -> LocalizationResult:
    image_area = width * height
    retained = tuple(
        detection
        for detection in result.detections
        if _box_area(detection.box_xyxy) / image_area <= limit
    )
    if not retained:
        return LocalizationResult("LOCALIZATION_FAILED", (), "DETECTOR_NO_MATCH")
    return LocalizationResult("SUCCESS", retained, None)


def _restore_to_source(
    result: LocalizationResult,
    *,
    source_size: tuple[int, int],
    offset: tuple[int, int],
) -> LocalizationResult:
    source_width, source_height = source_size
    offset_x, offset_y = offset
    restored: list[Detection] = []
    for detection in result.detections:
        pixels = bytearray(source_width * source_height)
        crop_width = detection.mask.width
        for row in range(detection.mask.height):
            source_start = (offset_y + row) * source_width + offset_x
            crop_start = row * crop_width
            pixels[source_start : source_start + crop_width] = detection.mask.pixels[
                crop_start : crop_start + crop_width
            ]
        x0, y0, x1, y1 = detection.box_xyxy
        restored.append(
            Detection(
                detection.label,
                detection.confidence,
                (x0 + offset_x, y0 + offset_y, x1 + offset_x, y1 + offset_y),
                MaskData(source_width, source_height, bytes(pixels)),
            )
        )
    return LocalizationResult("SUCCESS", tuple(restored), None)


def _box_area(box: tuple[float, float, float, float]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])
