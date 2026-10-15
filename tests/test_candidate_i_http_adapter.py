import asyncio
import base64
import hashlib
import io
import json
from email.parser import BytesParser
from email.policy import default

import httpx
import pytest
from PIL import Image

from product_search.infrastructure.nail_ml_adapters import (
    ClientSettings,
    HttpNailLocalizationAdapter,
)
from product_search.infrastructure.nail_wire import (
    WireLimits,
    WireValidationError,
    decode_metadata,
    decode_result,
    encode_metadata,
    encode_png,
)
from product_search.search.nail_contracts import LocalizationProfile, NailProcessingError, RgbImage

UID = "11111111-1111-4111-8111-111111111111"
FP = "a" * 64
LIMITS = WireLimits(10000, 10, 1024 * 1024)
RGB = RgbImage(1, 1, b"\x12\x34\x56")


def png(mode="L", size=(1, 1), color=255):
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, format="PNG")
    return out.getvalue()


def response():
    return {
        "api_version": 1,
        "request_id": UID,
        "image_sha256": "b" * 64,
        "extractor_fingerprint": FP,
        "image": {"width": 1, "height": 1},
        "status": "OK",
        "regions": [
            {
                "ordinal": 1,
                "label": "nail",
                "confidence": 0.9,
                "detector_box_xyxy": [0.0, 0.0, 1.0, 1.0],
                "mask_png_base64": base64.b64encode(png()).decode(),
            }
        ],
    }


def parse(payload):
    return decode_result(
        json.dumps(payload).encode(), RGB, LocalizationProfile(FP), UID, "b" * 64, LIMITS
    )


def test_png_preserves_rgb_bytes_and_has_no_alpha_or_exif():
    with Image.open(io.BytesIO(encode_png(RGB))) as decoded:
        assert decoded.mode == "RGB"
        assert decoded.size == (1, 1)
        assert decoded.tobytes() == b"\x12\x34\x56"
        assert not decoded.getexif()


def test_metadata_contains_exact_wire_identity_not_source_paths():
    payload = png("RGB", color=(18, 52, 86))
    metadata = json.loads(encode_metadata(RGB, payload, LocalizationProfile(FP), UID))
    assert metadata == {
        "api_version": 1,
        "request_id": UID,
        "image_sha256": hashlib.sha256(payload).hexdigest(),
        "width": 1,
        "height": 1,
        "expected_extractor_fingerprint": FP,
    }
    assert decode_metadata(json.dumps(metadata).encode()) == metadata


@pytest.mark.parametrize(
    "raw", [b'{"api_version":1,"api_version":1}', b'{"x":NaN}', b"[]", b"not-json"]
)
def test_metadata_rejects_ambiguous_or_invalid_json(raw):
    with pytest.raises(WireValidationError):
        decode_metadata(raw)


def test_valid_result_is_plain_mask_data():
    result = parse(response())
    assert result.status == "OK"
    assert result.regions[0].mask.pixels == b"\xff"
    assert result.regions[0].detector_box_xyxy == (0.0, 0.0, 1.0, 1.0)


def test_no_nails_is_a_distinct_empty_success():
    payload = response()
    payload.update(status="NO_NAILS", regions=[])
    assert parse(payload).status == "NO_NAILS"


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", "22222222-2222-4222-8222-222222222222"),
        ("image_sha256", "c" * 64),
        ("extractor_fingerprint", "c" * 64),
        ("api_version", True),
        ("raw_path", "/private/raw"),
    ],
)
def test_response_rejects_wrong_identity_or_extra_fields(field, value):
    payload = response()
    payload[field] = value
    with pytest.raises(NailProcessingError):
        parse(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ordinal", 2),
        ("confidence", True),
        ("confidence", float("nan")),
        ("detector_box_xyxy", [0, 0, 2, 1]),
        ("mask_png_base64", "not-base64"),
        ("label", ""),
    ],
)
def test_invalid_region_rejects_whole_photo(field, value):
    payload = response()
    payload["regions"][0][field] = value
    with pytest.raises(NailProcessingError) as caught:
        parse(payload)
    assert caught.value.code == "INVALID_OUTPUT"


@pytest.mark.parametrize(
    "mask", [png(color=0), png(color=128), png(size=(2, 1)), png("RGB", color=(255, 255, 255))]
)
def test_mask_must_be_full_frame_binary_grayscale(mask):
    payload = response()
    payload["regions"][0]["mask_png_base64"] = base64.b64encode(mask).decode()
    with pytest.raises(NailProcessingError):
        parse(payload)


def test_mask_color_key_transparency_is_rejected():
    out = io.BytesIO()
    Image.new("L", (1, 1), 255).save(out, format="PNG", transparency=255)
    payload = response()
    payload["regions"][0]["mask_png_base64"] = base64.b64encode(out.getvalue()).decode()
    with pytest.raises(NailProcessingError) as caught:
        parse(payload)
    assert caught.value.code == "INVALID_OUTPUT"


@pytest.mark.parametrize("chunk", [b"IEND", b"IDAT"])
def test_corrupt_png_crc_is_a_typed_mask_failure(chunk):
    mask = bytearray(png())
    kind_offset = mask.index(chunk)
    length = int.from_bytes(mask[kind_offset - 4 : kind_offset], "big")
    crc_offset = kind_offset + 4 + length
    mask[crc_offset] ^= 255
    payload = response()
    payload["regions"][0]["mask_png_base64"] = base64.b64encode(mask).decode()
    with pytest.raises(NailProcessingError) as caught:
        parse(payload)
    assert caught.value.code == "INVALID_OUTPUT"


def test_no_partial_result_when_later_region_is_invalid():
    payload = response()
    payload["regions"].append({**payload["regions"][0], "ordinal": 2, "confidence": -1})
    with pytest.raises(NailProcessingError):
        parse(payload)


def test_bounded_response_and_region_count():
    body = json.dumps(response()).encode()
    with pytest.raises(NailProcessingError):
        decode_result(body, RGB, LocalizationProfile(FP), UID, "b" * 64, WireLimits(10000, 1, 10))


def client(handler, overall=1.0):
    return HttpNailLocalizationAdapter(
        ClientSettings("http://127.0.0.1:8001", 0.2, 0.2, 0.2, overall, LIMITS),
        transport=httpx.MockTransport(handler),
    )


def ready():
    return httpx.Response(
        200, json={"api_version": 1, "ready": True, "busy": False, "extractor_fingerprint": FP}
    )


@pytest.mark.parametrize("outcome", ["OK", "NO_NAILS"])
def test_client_sends_direct_png_and_returns_validated_outcome(outcome):
    received = []

    def handler(request):
        if request.method == "GET":
            return ready()
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: "
            + request.headers["content-type"].encode()
            + b"\r\n\r\n"
            + request.read()
        )
        parts = {
            part.get_param("name", header="content-disposition"): part
            for part in message.iter_parts()
        }
        assert set(parts) == {"metadata", "image"}
        meta = json.loads(parts["metadata"].get_payload(decode=True))
        image_payload = parts["image"].get_payload(decode=True)
        assert parts["image"].get_filename() == "image.png"
        assert meta["image_sha256"] == hashlib.sha256(image_payload).hexdigest()
        with Image.open(io.BytesIO(image_payload)) as decoded:
            assert decoded.tobytes() == b"\x12\x34\x56"
        received.append(meta)
        payload = response()
        payload.update(
            request_id=meta["request_id"], image_sha256=meta["image_sha256"], status=outcome
        )
        if outcome == "NO_NAILS":
            payload["regions"] = []
        return httpx.Response(200, json=payload)

    result = client(handler).localize(RGB, LocalizationProfile(FP))
    assert result.status == outcome
    assert len(received) == 1


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (503, "BUSY", "BUSY"),
        (503, "RESOURCE_ERROR", "RESOURCE_ERROR"),
        (503, "REGION_COUNT_LIMIT", "REGION_COUNT_LIMIT"),
        (503, "RESPONSE_SIZE_LIMIT", "RESPONSE_SIZE_LIMIT"),
        (503, "MODEL_NOT_READY", "MODEL_ERROR"),
        (409, "PROFILE_MISMATCH", "PROFILE_MISMATCH"),
        (500, "MODEL_ERROR", "MODEL_ERROR"),
        (500, "SEGMENTER_EMPTY", "SEGMENTER_EMPTY"),
        (500, "INVALID_MODEL_OUTPUT", "INVALID_OUTPUT"),
        (422, "INVALID_IMAGE", "INVALID_IMAGE"),
        (400, "INVALID_REQUEST", "INVALID_IMAGE"),
        (413, "PAYLOAD_TOO_LARGE", "INVALID_IMAGE"),
        (415, "UNSUPPORTED_MEDIA_TYPE", "INVALID_IMAGE"),
        (422, "INVALID_METADATA", "INVALID_IMAGE"),
    ],
)
def test_http_problem_mapping_and_no_retry(status, code, expected):
    posts = []

    def handler(request):
        if request.method == "GET":
            return ready()
        posts.append(request)
        return httpx.Response(
            status,
            headers={"Content-Type": "application/problem+json", "Retry-After": "1"},
            json={
                "type": "about:blank",
                "title": "Failure",
                "detail": "/private/must-not-leak",
                "status": status,
                "code": code,
                "request_id": UID,
            },
        )

    with pytest.raises(NailProcessingError) as caught:
        client(handler).localize(RGB, LocalizationProfile(FP))
    assert caught.value.code == expected
    assert "/private" not in str(caught.value)
    assert len(posts) == 1


def test_read_timeout_does_not_repeat_post():
    posts = []

    def handler(request):
        if request.method == "GET":
            return ready()
        posts.append(request)
        raise httpx.ReadTimeout("/private/url")

    with pytest.raises(NailProcessingError) as caught:
        client(handler).localize(RGB, LocalizationProfile(FP))
    assert caught.value.code == "MODEL_ERROR"
    assert caught.value.reason == "LOCALIZATION_TIMEOUT"
    assert len(posts) == 1


def test_overall_deadline_cancels_wait_not_retries():
    posts = []

    async def handler(request):
        if request.method == "GET":
            return ready()
        posts.append(request)
        await asyncio.Event().wait()

    with pytest.raises(NailProcessingError) as caught:
        client(handler, overall=0.02).localize(RGB, LocalizationProfile(FP))
    assert caught.value.reason == "LOCALIZATION_TIMEOUT"
    assert len(posts) == 1


def test_wrong_problem_status_is_not_trusted():
    def handler(request):
        if request.method == "GET":
            return ready()
        return httpx.Response(
            503,
            headers={"Content-Type": "application/problem+json"},
            json={
                "type": "about:blank",
                "title": "Failure",
                "detail": "safe",
                "status": 500,
                "code": "MODEL_ERROR",
                "request_id": UID,
            },
        )

    with pytest.raises(NailProcessingError) as caught:
        client(handler).localize(RGB, LocalizationProfile(FP))
    assert caught.value.code == "INVALID_OUTPUT"


def test_redirect_is_a_failure_not_a_second_request():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "http://example.invalid/private"})

    with pytest.raises(NailProcessingError) as caught:
        client(handler).localize(RGB, LocalizationProfile(FP))
    assert caught.value.code == "INVALID_OUTPUT"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid",
        "http://user:pass@127.0.0.1:8001",
        "http://127.0.0.1:8001/private",
        "http://127.0.0.1:8001?token=secret",
    ],
)
def test_endpoint_is_only_a_fixed_loopback_origin(url):
    with pytest.raises(ValueError):
        ClientSettings(url, 1, 1, 1, 1, LIMITS)
