"""Synchronous core port with bounded async HTTP underneath; no model imports."""

import asyncio
import hashlib
import math
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from product_search.search.nail_contracts import (
    LocalizationProfile,
    NailLocalization,
    NailProcessingError,
    RgbImage,
)

from .nail_wire import (
    MAX_METADATA_BYTES,
    PROBLEM_CODES,
    WireLimits,
    WireValidationError,
    canonical_uuid,
    decode_result,
    encode_metadata,
    encode_png,
    fingerprint,
    strict_object,
)


@dataclass(frozen=True)
class ClientSettings:
    base_url: str
    connect_timeout_s: float
    write_timeout_s: float
    read_timeout_s: float
    overall_timeout_s: float
    limits: WireLimits

    def __post_init__(self) -> None:
        try:
            url = urlsplit(self.base_url)
            valid_origin = (
                url.scheme == "http"
                and url.hostname in ("127.0.0.1", "::1")
                and not url.username
                and not url.password
                and url.path in ("", "/")
                and not url.query
                and not url.fragment
                and (url.port is None or 1 <= url.port <= 65535)
            )
            budgets = (
                self.connect_timeout_s,
                self.write_timeout_s,
                self.read_timeout_s,
                self.overall_timeout_s,
            )
            valid_budgets = all(
                type(v) in (int, float) and math.isfinite(float(v)) and v > 0 for v in budgets
            )
        except (ValueError, TypeError, OverflowError):
            raise ValueError(
                "Valid loopback endpoint and finite positive timeouts required"
            ) from None
        if not valid_origin or not valid_budgets or not isinstance(self.limits, WireLimits):
            raise ValueError("Valid loopback endpoint and finite positive timeouts required")


class HttpNailLocalizationAdapter:
    def __init__(
        self, settings: ClientSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.settings = settings
        self.transport = transport

    def localize(self, image: RgbImage, profile: LocalizationProfile) -> NailLocalization:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise NailProcessingError("MODEL_ERROR", reason="CALL_IN_EXECUTOR")
        if image.width * image.height > self.settings.limits.max_decoded_pixels:
            raise NailProcessingError("INVALID_IMAGE")
        started = monotonic()
        try:
            result = asyncio.run(self._localize(image, profile))
        except NailProcessingError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise NailProcessingError("MODEL_ERROR", reason="LOCALIZATION_TIMEOUT") from None
        except httpx.TransportError:
            raise NailProcessingError("MODEL_ERROR", reason="CONNECTION_FAILED") from None
        except (WireValidationError, ValueError, KeyError, TypeError):
            raise NailProcessingError("INVALID_OUTPUT") from None
        if monotonic() - started > self.settings.overall_timeout_s:
            raise NailProcessingError("MODEL_ERROR", reason="LOCALIZATION_TIMEOUT")
        return result

    async def _localize(self, image, profile):
        settings = self.settings
        payload = encode_png(image)
        request_id = str(uuid4())
        metadata = encode_metadata(image, payload, profile, request_id)
        timeout = httpx.Timeout(
            connect=settings.connect_timeout_s,
            write=settings.write_timeout_s,
            read=settings.read_timeout_s,
            pool=settings.connect_timeout_s,
        )
        # A fresh owned client avoids connection pools bound to a closed asyncio.run loop.
        async with asyncio.timeout(settings.overall_timeout_s):
            async with httpx.AsyncClient(
                base_url=settings.base_url,
                timeout=timeout,
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream("GET", "/health/ready") as response:
                    body = await self._body(
                        response, min(MAX_METADATA_BYTES, settings.limits.max_response_bytes)
                    )
                    if response.status_code != 200:
                        self._problem(response, body, readiness=True)
                    self._media(response, "application/json")
                    self._ready(strict_object(body), profile)
                async with client.stream(
                    "POST",
                    "/v1/localizations",
                    files={
                        "image": ("image.png", payload, "image/png"),
                        "metadata": (None, metadata, "application/json"),
                    },
                ) as response:
                    body = await self._body(response, settings.limits.max_response_bytes)
                    if response.status_code != 200:
                        self._problem(response, body)
                    self._media(response, "application/json")
                    return decode_result(
                        body,
                        image,
                        profile,
                        request_id,
                        hashlib.sha256(payload).hexdigest(),
                        settings.limits,
                    )

    @staticmethod
    async def _body(response, cap):
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise NailProcessingError("INVALID_OUTPUT")
        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
            if len(body) + len(chunk) > cap:
                raise NailProcessingError("INVALID_OUTPUT")
            body.extend(chunk)
        return bytes(body)

    @staticmethod
    def _media(response, expected):
        if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != expected:
            raise NailProcessingError("INVALID_OUTPUT")

    @staticmethod
    def _ready(data, profile):
        if (
            set(data) != {"api_version", "ready", "busy", "extractor_fingerprint"}
            or type(data["api_version"]) is not int
            or data["api_version"] != 1
            or data["ready"] is not True
            or type(data["busy"]) is not bool
            or not fingerprint(data["extractor_fingerprint"])
        ):
            raise NailProcessingError("INVALID_OUTPUT")
        if data["extractor_fingerprint"] != profile.extractor_fingerprint:
            raise NailProcessingError("PROFILE_MISMATCH")
        if data["busy"]:
            raise NailProcessingError("BUSY")

    def _problem(self, response, body, *, readiness=False):
        self._media(response, "application/problem+json")
        data = strict_object(body)
        required = {"type", "title", "status", "detail", "code", "request_id"}
        status = response.status_code
        if (
            not required <= data.keys()
            or not data.keys() <= required | {"ready"}
            or data["type"] != "about:blank"
            or type(data["status"]) is not int
            or data["status"] != status
            or data["code"] not in PROBLEM_CODES.get(status, set())
            or not canonical_uuid(data["request_id"])
            or any(type(data[k]) is not str or not data[k] for k in ("title", "detail"))
            or ("ready" in data and data["ready"] is not False)
            or (
                readiness
                and (
                    status != 503
                    or data["code"] != "MODEL_NOT_READY"
                    or data.get("ready") is not False
                )
            )
        ):
            raise NailProcessingError("INVALID_OUTPUT")
        code = data["code"]
        mapped = {
            "MODEL_NOT_READY": "MODEL_ERROR",
            "INVALID_MODEL_OUTPUT": "INVALID_OUTPUT",
            "INVALID_REQUEST": "INVALID_IMAGE",
            "PAYLOAD_TOO_LARGE": "INVALID_IMAGE",
            "UNSUPPORTED_MEDIA_TYPE": "INVALID_IMAGE",
            "INVALID_METADATA": "INVALID_IMAGE",
        }.get(code, code)
        raise NailProcessingError(mapped)


class NailEmbeddingAdapter:
    """Translate plain RGB crops to existing providers; factories stay outside core."""

    def __init__(self, factories):
        self.factories = dict(factories)
        self.providers = {}

    def encode(self, model_key, crops, profile):
        from PIL import Image

        from product_search.search.nail_contracts import MODEL_DIMENSIONS, EmbeddingProfile, _number

        if (
            not isinstance(profile, EmbeddingProfile)
            or model_key not in dict(MODEL_DIMENSIONS)
            or model_key not in self.factories
            or type(crops) is not tuple
            or any(not isinstance(crop, RgbImage) for crop in crops)
        ):
            raise NailProcessingError("PROFILE_MISMATCH")
        try:
            if model_key not in self.providers:
                self.providers[model_key] = self.factories[model_key]()
            provider = self.providers[model_key]
            dimension = dict(MODEL_DIMENSIONS)[model_key]
            if (
                provider.model_key != model_key
                or provider.revision != dict(profile.revisions)[model_key]
                or provider.embedding_dim != dimension
            ):
                raise NailProcessingError("PROFILE_MISMATCH")
            rows = []
            for crop in crops:
                with Image.frombytes("RGB", (crop.width, crop.height), crop.pixels) as image:
                    values = tuple(provider.encode_image(image))
                if (
                    len(values) != dimension
                    or not all(_number(value) for value in values)
                    or not any(values)
                ):
                    raise NailProcessingError("INVALID_EMBEDDING")
                rows.append(tuple(float(value) for value in values))
            return tuple(rows)
        except NailProcessingError:
            raise
        except Exception:  # noqa: BLE001 -- SDK boundary: all provider failures become safe typed errors.
            raise NailProcessingError("MODEL_ERROR") from None
