from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RoiSelection:
    box_xyxy: tuple[int, int, int, int]
    parent_ordinal: int
    child_ordinals: tuple[int, ...]


def select_nested_roi(
    boxes: Sequence[tuple[float, float, float, float]],
    confidences: Sequence[float],
    *,
    width: int,
    height: int,
    min_parent_area_ratio: float = 0.1,
    max_parent_area_ratio: float = 0.5,
    padding_ratio: float = 0.1,
    min_roi_aspect_ratio: float = 0.9,
    max_roi_aspect_ratio: float = 1.25,
) -> RoiSelection | None:
    """Select a padded ROI from detections nested inside a coarse parent box.

    Candidate parents are ranked first by the confidence of their strongest
    contained detection, then by the number of contained detections. The ROI
    is the padded union of those contained boxes rather than the coarse parent.
    """
    _validate_inputs(
        boxes,
        confidences,
        width=width,
        height=height,
        min_parent_area_ratio=min_parent_area_ratio,
        max_parent_area_ratio=max_parent_area_ratio,
        padding_ratio=padding_ratio,
        min_roi_aspect_ratio=min_roi_aspect_ratio,
        max_roi_aspect_ratio=max_roi_aspect_ratio,
    )
    image_area = width * height
    candidates: list[
        tuple[
            tuple[float, int, float, float, int],
            int,
            tuple[int, ...],
            tuple[int, int, int, int],
        ]
    ] = []
    for parent_ordinal, parent in enumerate(boxes):
        parent_area = _area(parent)
        parent_area_ratio = parent_area / image_area
        if not min_parent_area_ratio <= parent_area_ratio <= max_parent_area_ratio:
            continue
        children = tuple(
            child_ordinal
            for child_ordinal, child in enumerate(boxes)
            if child_ordinal != parent_ordinal
            and _area(child) < parent_area
            and _contains(parent, child)
        )
        if not children:
            continue
        roi = _padded_union(
            boxes,
            children,
            width=width,
            height=height,
            padding_ratio=padding_ratio,
        )
        roi_aspect_ratio = (roi[2] - roi[0]) / (roi[3] - roi[1])
        if not min_roi_aspect_ratio <= roi_aspect_ratio <= max_roi_aspect_ratio:
            continue
        rank = (
            max(confidences[ordinal] for ordinal in children),
            len(children),
            confidences[parent_ordinal],
            -parent_area,
            -parent_ordinal,
        )
        candidates.append((rank, parent_ordinal, children, roi))
    if not candidates:
        return None

    _, parent_ordinal, children, roi = max(candidates, key=lambda item: item[0])
    return RoiSelection(roi, parent_ordinal, children)


def _padded_union(
    boxes: Sequence[tuple[float, float, float, float]],
    children: tuple[int, ...],
    *,
    width: int,
    height: int,
    padding_ratio: float,
) -> tuple[int, int, int, int]:
    x0 = min(boxes[ordinal][0] for ordinal in children)
    y0 = min(boxes[ordinal][1] for ordinal in children)
    x1 = max(boxes[ordinal][2] for ordinal in children)
    y1 = max(boxes[ordinal][3] for ordinal in children)
    padding_x = (x1 - x0) * padding_ratio
    padding_y = (y1 - y0) * padding_ratio
    return (
        max(0, math.floor(x0 - padding_x)),
        max(0, math.floor(y0 - padding_y)),
        min(width, math.ceil(x1 + padding_x)),
        min(height, math.ceil(y1 + padding_y)),
    )


def _validate_inputs(
    boxes: Sequence[tuple[float, float, float, float]],
    confidences: Sequence[float],
    *,
    width: int,
    height: int,
    min_parent_area_ratio: float,
    max_parent_area_ratio: float,
    padding_ratio: float,
    min_roi_aspect_ratio: float,
    max_roi_aspect_ratio: float,
) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    if len(boxes) != len(confidences):
        raise ValueError("boxes and confidences must have equal lengths")
    if not 0 < min_parent_area_ratio <= max_parent_area_ratio <= 1:
        raise ValueError("parent area ratios must define a range within (0, 1]")
    if not 0 <= padding_ratio <= 1:
        raise ValueError("padding ratio must be within [0, 1]")
    if not 0 < min_roi_aspect_ratio <= max_roi_aspect_ratio:
        raise ValueError("ROI aspect ratios must define a positive range")
    for box in boxes:
        if len(box) != 4 or not all(math.isfinite(value) for value in box):
            raise ValueError("box coordinates must be finite xyxy values")
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError("box must be within image bounds")
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in confidences):
        raise ValueError("confidences must be finite and within [0, 1]")


def _area(box: tuple[float, float, float, float]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _contains(
    parent: tuple[float, float, float, float],
    child: tuple[float, float, float, float],
) -> bool:
    return (
        parent[0] <= child[0]
        and parent[1] <= child[1]
        and child[2] <= parent[2]
        and child[3] <= parent[3]
    )
