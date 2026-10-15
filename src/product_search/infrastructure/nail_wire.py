"""Bounded wire codecs shared by the two HTTP edges, never imported by core."""

import base64
import binascii
import hashlib
import io
import json
import re
import zlib
from dataclasses import dataclass
from uuid import UUID

from PIL import Image

from product_search.search.nail_contracts import (
    BinaryMask,
    LocalizationProfile,
    LocalizedRegion,
    NailLocalization,
    NailProcessingError,
    RgbImage,
)

MAX_PNG_BYTES = 20 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024
MAX_BODY_BYTES = MAX_PNG_BYTES + 64 * 1024
PROBLEM_CODES = {
    400: {"INVALID_REQUEST"},
    413: {"PAYLOAD_TOO_LARGE"},
    415: {"UNSUPPORTED_MEDIA_TYPE"},
    422: {"INVALID_IMAGE", "INVALID_METADATA"},
    409: {"PROFILE_MISMATCH"},
    503: {"BUSY", "MODEL_NOT_READY", "RESOURCE_ERROR", "REGION_COUNT_LIMIT", "RESPONSE_SIZE_LIMIT"},
    500: {"MODEL_ERROR", "INVALID_MODEL_OUTPUT", "SEGMENTER_EMPTY"},
}


class WireValidationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WireLimits:
    max_decoded_pixels: int
    max_region_count: int
    max_response_bytes: int

    def __post_init__(self) -> None:
        if any(
            type(v) is not int or v <= 0
            for v in (self.max_decoded_pixels, self.max_region_count, self.max_response_bytes)
        ):
            raise ValueError("Finite positive wire limits are required")


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WireValidationError("INVALID_REQUEST")
        result[key] = value
    return result


def _constant(value):
    raise WireValidationError("INVALID_REQUEST")


def strict_object(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise WireValidationError("INVALID_REQUEST") from error
    if type(value) is not dict:
        raise WireValidationError("INVALID_REQUEST")
    return value


def _keys(value, required, optional=()):
    if (
        type(value) is not dict
        or not set(required) <= value.keys()
        or not value.keys() <= set(required) | set(optional)
    ):
        raise WireValidationError("INVALID_METADATA")


def canonical_uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def fingerprint(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _png(pixels: bytes, size: tuple[int, int], mode: str) -> bytes:
    stream = io.BytesIO()
    with Image.frombytes(mode, size, pixels) as image:
        image.save(stream, format="PNG")
    return stream.getvalue()


def encode_png(image: RgbImage) -> bytes:
    payload = _png(image.pixels, (image.width, image.height), "RGB")
    if len(payload) > MAX_PNG_BYTES:
        raise NailProcessingError("INVALID_IMAGE", reason="PAYLOAD_TOO_LARGE")
    return payload


def encode_metadata(
    image: RgbImage, payload: bytes, profile: LocalizationProfile, request_id: str
) -> str:
    return json_bytes(
        {
            "api_version": 1,
            "request_id": request_id,
            "expected_extractor_fingerprint": profile.extractor_fingerprint,
            "image_sha256": hashlib.sha256(payload).hexdigest(),
            "width": image.width,
            "height": image.height,
        }
    ).decode()


def decode_metadata(raw: bytes) -> dict:
    if len(raw) > MAX_METADATA_BYTES:
        raise WireValidationError("PAYLOAD_TOO_LARGE")
    value = strict_object(raw)
    _keys(
        value,
        (
            "api_version",
            "request_id",
            "expected_extractor_fingerprint",
            "image_sha256",
            "width",
            "height",
        ),
    )
    if (
        type(value["api_version"]) is not int
        or value["api_version"] != 1
        or not canonical_uuid(value["request_id"])
        or not fingerprint(value["expected_extractor_fingerprint"])
        or not fingerprint(value["image_sha256"])
        or any(type(value[k]) is not int or value[k] < 1 for k in ("width", "height"))
    ):
        raise WireValidationError("INVALID_METADATA")
    return value


def _png_end(payload: bytes) -> None:
    """Pillow verifies preceding chunks but not the final IEND CRC or trailing bytes."""
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise WireValidationError("INVALID_IMAGE")
    offset = 8
    while offset + 12 <= len(payload):
        length = int.from_bytes(payload[offset : offset + 4], "big")
        end = offset + length + 12
        if end > len(payload):
            break
        kind = payload[offset + 4 : offset + 8]
        if kind == b"IEND":
            if (
                length
                or end != len(payload)
                or int.from_bytes(payload[end - 4 : end], "big") != zlib.crc32(kind)
            ):
                break
            return
        offset = end
    raise WireValidationError("INVALID_IMAGE")


def _png_pixels(payload: bytes, width: int, height: int, mode: str, limits: WireLimits) -> bytes:
    if width * height > limits.max_decoded_pixels:
        raise WireValidationError("INVALID_IMAGE")
    try:
        _png_end(payload)
        with Image.open(io.BytesIO(payload)) as image:
            if (
                image.format != "PNG"
                or image.mode != mode
                or image.size != (width, height)
                or getattr(image, "n_frames", 1) != 1
                or "exif" in image.info
                or "transparency" in image.info
                or len(payload) < 25
                or payload[24] != 8
            ):
                raise WireValidationError("INVALID_IMAGE")
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            return image.tobytes()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, OverflowError) as error:
        raise WireValidationError("INVALID_IMAGE") from error


def decode_rgb_png(payload: bytes, metadata: dict, limits: WireLimits) -> RgbImage:
    if len(payload) > MAX_PNG_BYTES:
        raise WireValidationError("PAYLOAD_TOO_LARGE")
    if hashlib.sha256(payload).hexdigest() != metadata["image_sha256"]:
        raise WireValidationError("INVALID_IMAGE")
    width, height = metadata["width"], metadata["height"]
    return RgbImage(width, height, _png_pixels(payload, width, height, "RGB", limits))


def decode_result(body, image, profile, request_id, image_sha256, limits) -> NailLocalization:
    try:
        if len(body) > limits.max_response_bytes:
            raise WireValidationError("INVALID_METADATA")
        data = strict_object(body)
        _keys(
            data,
            (
                "api_version",
                "request_id",
                "image_sha256",
                "extractor_fingerprint",
                "image",
                "status",
                "regions",
            ),
        )
        _keys(data["image"], ("width", "height"))
        if (
            type(data["api_version"]) is not int
            or data["api_version"] != 1
            or data["request_id"] != request_id
            or data["image_sha256"] != image_sha256
            or type(data["image"]["width"]) is not int
            or type(data["image"]["height"]) is not int
            or data["image"] != {"width": image.width, "height": image.height}
            or not fingerprint(data["extractor_fingerprint"])
            or type(data["regions"]) is not list
            or len(data["regions"]) > limits.max_region_count
        ):
            raise WireValidationError("INVALID_METADATA")
        if data["extractor_fingerprint"] != profile.extractor_fingerprint:
            raise NailProcessingError("PROFILE_MISMATCH")
        regions = []
        for item in data["regions"]:
            _keys(item, ("ordinal", "label", "confidence", "detector_box_xyxy", "mask_png_base64"))
            if (
                type(item["mask_png_base64"]) is not str
                or type(item["detector_box_xyxy"]) is not list
            ):
                raise WireValidationError("INVALID_METADATA")
            encoded = item["mask_png_base64"]
            pixels_png = base64.b64decode(encoded, validate=True)
            if base64.b64encode(pixels_png).decode() != encoded:
                raise WireValidationError("INVALID_METADATA")
            mask = BinaryMask(
                image.width,
                image.height,
                _png_pixels(pixels_png, image.width, image.height, "L", limits),
            )
            regions.append(
                LocalizedRegion(
                    item["ordinal"],
                    item["label"],
                    item["confidence"],
                    tuple(item["detector_box_xyxy"]),
                    mask,
                )
            )
        return NailLocalization(data["status"], tuple(regions))
    except NailProcessingError:
        raise
    except (
        WireValidationError,
        ValueError,
        TypeError,
        KeyError,
        binascii.Error,
        OverflowError,
    ) as error:
        raise NailProcessingError("INVALID_OUTPUT") from error


def encode_result(
    result: NailLocalization, metadata: dict, extractor: str, limits: WireLimits
) -> dict:
    if not isinstance(result, NailLocalization):
        raise WireValidationError("INVALID_MODEL_OUTPUT")
    if len(result.regions) > limits.max_region_count:
        raise WireValidationError("REGION_COUNT_LIMIT")
    regions = []
    for region in result.regions:
        if (region.mask.width, region.mask.height) != (metadata["width"], metadata["height"]):
            raise WireValidationError("INVALID_MODEL_OUTPUT")
        regions.append(
            {
                "ordinal": region.ordinal,
                "label": region.label,
                "confidence": region.confidence,
                "detector_box_xyxy": list(region.detector_box_xyxy),
                "mask_png_base64": base64.b64encode(
                    _png(region.mask.pixels, (region.mask.width, region.mask.height), "L")
                ).decode(),
            }
        )
    data = {
        "api_version": 1,
        "request_id": metadata["request_id"],
        "image_sha256": metadata["image_sha256"],
        "extractor_fingerprint": extractor,
        "image": {"width": metadata["width"], "height": metadata["height"]},
        "status": result.status,
        "regions": regions,
    }
    if len(json_bytes(data)) > limits.max_response_bytes:
        raise WireValidationError("RESPONSE_SIZE_LIMIT")
    return data
