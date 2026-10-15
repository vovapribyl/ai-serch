from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


class ConfigError(ValueError):
    """Raised when configuration or its lock violates the frozen contract."""


@dataclass(frozen=True)
class FrozenConfig:
    data: Mapping[str, Any]
    config_fingerprint: str
    dependency_lock_fingerprint: str


def freeze_config(payload: Mapping[str, Any], *, lock_bytes: bytes) -> FrozenConfig:
    top_fields = {
        "schema_version",
        "adapter",
        "detector",
        "segmenter",
        "prompt",
        "thresholds",
        "postprocessing",
        "image_preparation",
        "device",
        "mps_operator_fallback_enabled",
        "python_version",
        "dependencies",
        "dependency_lock_fingerprint",
        "deterministic",
        "config_fingerprint",
    }
    if set(payload) != top_fields or payload.get("schema_version") != "1":
        raise ConfigError("config has unknown or missing top-level fields")
    for key in ("adapter", "detector", "segmenter"):
        value = payload[key]
        if not isinstance(value, Mapping) or set(value) != {"repository", "revision"} or not all(
            isinstance(item, str) and item.strip() for item in value.values()
        ):
            raise ConfigError(f"invalid {key} identity")
    prompt = payload["prompt"]
    if not isinstance(prompt, Mapping) or set(prompt) != {"id", "text"} or not all(
        isinstance(item, str) and item.strip() for item in prompt.values()
    ):
        raise ConfigError("invalid prompt")
    thresholds = payload["thresholds"]
    if not isinstance(thresholds, Mapping) or set(thresholds) != {"box", "text", "mask"}:
        raise ConfigError("invalid threshold fields")
    for value in thresholds.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError("thresholds must be numbers")
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ConfigError("thresholds must be finite and within [0, 1]")

    postprocessing = payload["postprocessing"]
    legacy_postprocessing_fields = {"min_mask_area_px", "merge_overlaps"}
    roi_postprocessing_fields = {
        *legacy_postprocessing_fields,
        "max_detection_box_area_ratio",
        "packaging_roi",
    }
    if not isinstance(postprocessing, Mapping) or frozenset(postprocessing) not in {
        frozenset(legacy_postprocessing_fields),
        frozenset(roi_postprocessing_fields),
    }:
        raise ConfigError("invalid postprocessing fields")
    if (
        isinstance(postprocessing["min_mask_area_px"], bool)
        or not isinstance(postprocessing["min_mask_area_px"], int)
        or postprocessing["min_mask_area_px"] < 0
        or postprocessing["merge_overlaps"] is not False
    ):
        raise ConfigError("invalid postprocessing values")
    if set(postprocessing) == roi_postprocessing_fields:
        max_box_ratio = postprocessing["max_detection_box_area_ratio"]
        if (
            isinstance(max_box_ratio, bool)
            or not isinstance(max_box_ratio, (int, float))
            or not math.isfinite(max_box_ratio)
            or not 0 < max_box_ratio <= 1
        ):
            raise ConfigError("invalid maximum detection box area ratio")
        _validate_packaging_roi(postprocessing["packaging_roi"])

    image_preparation = payload["image_preparation"]
    if not isinstance(image_preparation, Mapping) or set(image_preparation) != {
        "exif_transpose",
        "color_mode",
        "max_side_px",
    }:
        raise ConfigError("invalid image preparation fields")
    if (
        image_preparation["exif_transpose"] is not True
        or image_preparation["color_mode"] != "RGB"
        or isinstance(image_preparation["max_side_px"], bool)
        or not isinstance(image_preparation["max_side_px"], int)
        or image_preparation["max_side_px"] <= 0
    ):
        raise ConfigError("invalid image preparation values")
    if payload["device"] not in {"mps", "cpu"}:
        raise ConfigError("device must be mps or cpu")
    if not isinstance(payload["mps_operator_fallback_enabled"], bool) or (
        payload["device"] == "cpu" and payload["mps_operator_fallback_enabled"]
    ):
        raise ConfigError("invalid explicit MPS operator fallback setting")
    if not isinstance(payload["python_version"], str) or not payload["python_version"].strip():
        raise ConfigError("python_version must be an exact non-empty string")

    dependencies = payload["dependencies"]
    exact_version = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
    if not isinstance(dependencies, dict) or not dependencies:
        raise ConfigError("dependencies must be a non-empty object")
    if any(
        not isinstance(name, str)
        or not name
        or not isinstance(version, str)
        or not exact_version.fullmatch(version)
        for name, version in dependencies.items()
    ):
        raise ConfigError("dependency versions must be exact")
    deterministic = payload["deterministic"]
    if (
        not isinstance(deterministic, Mapping)
        or set(deterministic) != {"seed", "deterministic_algorithms"}
        or isinstance(deterministic["seed"], bool)
        or not isinstance(deterministic["seed"], int)
        or not isinstance(deterministic["deterministic_algorithms"], bool)
    ):
        raise ConfigError("invalid deterministic settings")

    lock_fingerprint = f"sha256:{hashlib.sha256(lock_bytes).hexdigest()}"
    if payload["dependency_lock_fingerprint"] != lock_fingerprint:
        raise ConfigError("dependency lock fingerprint mismatch")
    body = {key: value for key, value in payload.items() if key != "config_fingerprint"}
    fingerprint = _canonical_fingerprint(body)
    if payload["config_fingerprint"] != fingerprint:
        raise ConfigError("config fingerprint mismatch")
    frozen_data = _freeze(dict(payload))
    return FrozenConfig(frozen_data, fingerprint, lock_fingerprint)


def verify_lock(config: FrozenConfig, *, lock_bytes: bytes) -> None:
    fingerprint = f"sha256:{hashlib.sha256(lock_bytes).hexdigest()}"
    if fingerprint != config.dependency_lock_fingerprint:
        raise ConfigError("dependency lock fingerprint mismatch")


def _validate_packaging_roi(value: object) -> None:
    fields = {
        "mode",
        "min_parent_area_ratio",
        "max_parent_area_ratio",
        "padding_ratio",
        "min_aspect_ratio",
        "max_aspect_ratio",
        "fallback_to_full_image",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ConfigError("invalid packaging ROI fields")
    if value["mode"] != "nested_detection_v1" or value["fallback_to_full_image"] is not True:
        raise ConfigError("invalid packaging ROI mode or fallback")
    numeric = (
        "min_parent_area_ratio",
        "max_parent_area_ratio",
        "padding_ratio",
        "min_aspect_ratio",
        "max_aspect_ratio",
    )
    if any(
        isinstance(value[key], bool)
        or not isinstance(value[key], (int, float))
        or not math.isfinite(value[key])
        for key in numeric
    ):
        raise ConfigError("packaging ROI ratios must be finite numbers")
    if not 0 < value["min_parent_area_ratio"] <= value["max_parent_area_ratio"] <= 1:
        raise ConfigError("invalid packaging ROI parent area range")
    if not 0 <= value["padding_ratio"] <= 1:
        raise ConfigError("invalid packaging ROI padding")
    if not 0 < value["min_aspect_ratio"] <= value["max_aspect_ratio"]:
        raise ConfigError("invalid packaging ROI aspect range")


def _canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConfigError("config is not canonical JSON") from exc
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
