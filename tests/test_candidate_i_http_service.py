import asyncio
import hashlib
import io
import json
import threading

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from product_search.infrastructure.nail_wire import WireLimits
from product_search.search.nail_contracts import (
    BinaryMask,
    LocalizedRegion,
    NailLocalization,
    NailProcessingError,
)
from services.candidate_i.app import create_app
from services.candidate_i.settings import ServiceSettings

FP = "a" * 64
UID = "11111111-1111-4111-8111-111111111111"
LIMITS = WireLimits(10000, 10, 1024 * 1024)


def image_png(mode="RGB", size=(1, 1), color=(18, 52, 86)):
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, format="PNG")
    return out.getvalue()


def multipart(payload=None, overrides=None):
    payload = image_png() if payload is None else payload
    meta = {
        "api_version": 1,
        "request_id": UID,
        "expected_extractor_fingerprint": FP,
        "image_sha256": hashlib.sha256(payload).hexdigest(),
        "width": 1,
        "height": 1,
    }
    meta.update(overrides or {})
    return {
        "image": ("image.png", payload, "image/png"),
        "metadata": (None, json.dumps(meta), "application/json"),
    }


def success(image, profile):
    return NailLocalization(
        "OK",
        (
            LocalizedRegion(
                1,
                "nail",
                0.9,
                (0, 0, image.width, image.height),
                BinaryMask(image.width, image.height, b"\xff" * (image.width * image.height)),
            ),
        ),
    )


def app(tmp_path, binding=success, ready=True):
    return create_app(ServiceSettings(FP, LIMITS, tmp_path), binding, ready_check=lambda: ready)


def test_ready_and_ok_result_follow_contract(tmp_path):
    with TestClient(app(tmp_path)) as client:
        assert client.get("/health/ready").json() == {
            "api_version": 1,
            "ready": True,
            "busy": False,
            "extractor_fingerprint": FP,
        }
        result = client.post("/v1/localizations", files=multipart())
        assert result.status_code == 200
        body = result.json()
        assert body["status"] == "OK"
        assert body["request_id"] == UID
        assert body["image"] == {"width": 1, "height": 1}
        assert body["regions"][0]["ordinal"] == 1


def test_default_without_verified_readiness_is_not_ready(tmp_path):
    with TestClient(create_app(ServiceSettings(FP, LIMITS, tmp_path), success)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["code"] == "MODEL_NOT_READY"
        assert response.json()["ready"] is False


def test_no_nails_is_200_not_model_error(tmp_path):
    with TestClient(
        app(tmp_path, lambda image, profile: NailLocalization("NO_NAILS", ()))
    ) as client:
        response = client.post("/v1/localizations", files=multipart())
        assert response.status_code == 200
        assert response.json()["status"] == "NO_NAILS"
        assert response.json()["regions"] == []


@pytest.mark.parametrize(
    "code,status",
    [
        ("SEGMENTER_EMPTY", 500),
        ("MODEL_ERROR", 500),
        ("RESOURCE_ERROR", 503),
        ("INVALID_OUTPUT", 500),
    ],
)
def test_binding_error_is_explicit_never_no_nails(tmp_path, code, status):
    def fail(image, profile):
        raise NailProcessingError(code)

    with TestClient(app(tmp_path, fail)) as client:
        response = client.post("/v1/localizations", files=multipart())
        assert response.status_code == status
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["code"] == (
            "INVALID_MODEL_OUTPUT" if code == "INVALID_OUTPUT" else code
        )
        assert "regions" not in response.json()


@pytest.mark.parametrize(
    "overrides,status,code",
    [
        ({"expected_extractor_fingerprint": "b" * 64}, 409, "PROFILE_MISMATCH"),
        ({"image_sha256": "b" * 64}, 422, "INVALID_IMAGE"),
        ({"width": 2}, 422, "INVALID_IMAGE"),
        ({"width": True}, 422, "INVALID_METADATA"),
        ({"image_url": "http://example.invalid"}, 422, "INVALID_METADATA"),
    ],
)
def test_invalid_request_does_not_invoke_binding(tmp_path, overrides, status, code):
    calls = []

    def bind(image, profile):
        calls.append(image)
        return success(image, profile)

    with TestClient(app(tmp_path, bind)) as client:
        response = client.post("/v1/localizations", files=multipart(overrides=overrides))
        assert response.status_code == status
        assert response.json()["code"] == code
        assert not calls


def test_wrong_image_mode_is_rejected_before_binding(tmp_path):
    with TestClient(app(tmp_path)) as client:
        response = client.post(
            "/v1/localizations", files=multipart(image_png("RGBA", color=(0, 0, 0, 255)))
        )
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_IMAGE"


def test_rgb_png_with_color_key_transparency_is_not_a_normalized_input(tmp_path):
    out = io.BytesIO()
    Image.new("RGB", (1, 1), (18, 52, 86)).save(out, format="PNG", transparency=(18, 52, 86))
    calls = []

    def bind(image, profile):
        calls.append(image)
        return success(image, profile)

    with TestClient(app(tmp_path, bind)) as client:
        response = client.post("/v1/localizations", files=multipart(out.getvalue()))
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_IMAGE"
        assert not calls


@pytest.mark.parametrize("chunk", [b"IEND", b"IDAT"])
def test_corrupt_png_crc_is_rejected_before_binding(tmp_path, chunk):
    payload = bytearray(image_png())
    kind_offset = payload.index(chunk)
    length = int.from_bytes(payload[kind_offset - 4 : kind_offset], "big")
    payload[kind_offset + 4 + length] ^= 255
    calls = []

    def bind(image, profile):
        calls.append(image)
        return success(image, profile)

    with TestClient(app(tmp_path, bind)) as client:
        response = client.post("/v1/localizations", files=multipart(bytes(payload)))
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_IMAGE"
        assert not calls


@pytest.mark.parametrize("raw", ['{"api_version":1,"api_version":1}', '{"x":NaN}', "not-json"])
def test_ambiguous_metadata_json_is_400(tmp_path, raw):
    files = multipart()
    files["metadata"] = (None, raw, "application/json")
    with TestClient(app(tmp_path)) as client:
        response = client.post("/v1/localizations", files=files)
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"


def test_unknown_or_duplicate_parts_are_rejected(tmp_path):
    files = list(multipart().items())
    files.append(("image", ("other.png", image_png(), "image/png")))
    with TestClient(app(tmp_path)) as client:
        response = client.post("/v1/localizations", files=files)
        assert response.status_code == 400


def test_bad_media_type_is_415(tmp_path):
    with TestClient(app(tmp_path)) as client:
        response = client.post("/v1/localizations", json={"image": "url"})
        assert response.status_code == 415


def test_actual_stream_limit_not_only_content_length(tmp_path):
    async def check():
        async def chunks():
            for _ in range(22):
                yield b"x" * (1024 * 1024)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app(tmp_path)), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/localizations",
                content=chunks(),
                headers={"Content-Type": "multipart/form-data; boundary=test"},
            )
            assert response.status_code == 413

    asyncio.run(check())


def test_unexpected_exception_does_not_leak_private_detail(tmp_path):
    def fail(image, profile):
        raise RuntimeError("/private/secret/model/file")

    with TestClient(app(tmp_path, fail)) as client:
        response = client.post("/v1/localizations", files=multipart())
        assert response.status_code == 500
        assert response.json()["code"] == "MODEL_ERROR"
        assert "private" not in response.text


def test_server_does_not_spool_image_or_masks(tmp_path):
    with TestClient(app(tmp_path)) as client:
        assert client.post("/v1/localizations", files=multipart()).status_code == 200
    assert not any(p.suffix in (".png", ".jpg", ".json") for p in tmp_path.rglob("*"))


def test_region_budget_is_photo_limit_not_partial_model_output(tmp_path):
    def two(image, profile):
        first = success(image, profile).regions[0]
        second = LocalizedRegion(
            2, first.label, first.confidence, first.detector_box_xyxy, first.mask
        )
        return NailLocalization("OK", (first, second))

    configured = create_app(
        ServiceSettings(FP, WireLimits(100, 1, 1024), tmp_path), two, ready_check=lambda: True
    )
    with TestClient(configured) as client:
        response = client.post("/v1/localizations", files=multipart())
        assert response.status_code == 503
        assert response.json()["code"] == "REGION_COUNT_LIMIT"
        assert "regions" not in response.json()
        assert client.get("/health/ready").json()["busy"] is False


def test_unsafe_lease_is_resource_failure_without_touching_target(tmp_path):
    target = tmp_path / "safe"
    target.write_text("untouched")
    (tmp_path / "device.lock").symlink_to(target)
    with TestClient(app(tmp_path)) as client:
        response = client.post("/v1/localizations", files=multipart())
        assert response.status_code == 503
        assert response.json()["code"] == "RESOURCE_ERROR"
        assert client.get("/health/ready").json()["busy"] is False
    assert target.read_text() == "untouched"


def test_cancelled_http_does_not_release_native_device_or_admission(tmp_path):
    from product_search.infrastructure.nail_runtime import FileLease

    entered, release = threading.Event(), threading.Event()

    def bind(image, profile):
        entered.set()
        assert release.wait(5)
        return success(image, profile)

    async def check():
        configured = app(tmp_path, bind)
        async with (
            configured.router.lifespan_context(configured),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=configured), base_url="http://test"
            ) as client,
        ):
            request = asyncio.create_task(client.post("/v1/localizations", files=multipart()))
            assert await asyncio.to_thread(entered.wait, 2)
            try:
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request
                assert (await client.get("/health/ready")).json()["busy"] is True
                competitor = FileLease(tmp_path, "device.lock")
                assert not competitor.try_acquire()
                competitor.release()
                blocked = await client.post("/v1/localizations", files=multipart())
                assert blocked.status_code == 503
                assert blocked.json()["code"] == "BUSY"
            finally:
                release.set()
            async with asyncio.timeout(2):
                while (await client.get("/health/ready")).json()["busy"]:
                    await asyncio.sleep(0)
            assert (await client.post("/v1/localizations", files=multipart())).status_code == 200

    asyncio.run(check())


def test_response_size_limit_is_distinct_from_device_resource_failure(tmp_path):
    configured = create_app(
        ServiceSettings(FP, WireLimits(100, 10, 1), tmp_path), success, ready_check=lambda: True
    )
    with TestClient(configured) as client:
        response = client.post("/v1/localizations", files=multipart())
        assert response.status_code == 503
        assert response.json()["code"] == "RESPONSE_SIZE_LIMIT"
        assert "regions" not in response.json()
