"""Bounded HTTP facade. No model imports and no implicit model readiness."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from product_search.infrastructure.nail_runtime import FileLease
from product_search.infrastructure.nail_wire import (
    MAX_BODY_BYTES,
    PROBLEM_CODES,
    WireValidationError,
    decode_metadata,
    decode_rgb_png,
    encode_result,
)
from product_search.search.nail_contracts import LocalizationProfile, NailProcessingError


def problem(code, request_id, *, unready=False):
    status = next(status for status, codes in PROBLEM_CODES.items() if code in codes)
    body = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": "The operation could not be completed.",
        "code": code,
        "request_id": request_id,
    }
    if unready:
        body["ready"] = False
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


async def bounded_body(request):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise WireValidationError("PAYLOAD_TOO_LARGE")
        body.extend(chunk)
    return bytes(body)


def parse_parts(content_type, body):
    if content_type.split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise WireValidationError("UNSUPPORTED_MEDIA_TYPE")
    try:
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: "
            + content_type.encode("ascii")
            + b"\r\nMIME-Version: 1.0\r\n\r\n"
            + body
        )
        if not message.is_multipart() or message.defects:
            raise WireValidationError("INVALID_REQUEST")
        parts = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if (
                name in parts
                or name not in ("image", "metadata")
                or part.is_multipart()
                or part.get_content_disposition() != "form-data"
                or part.defects
                or part.get("Content-Transfer-Encoding") not in (None, "binary", "8bit")
            ):
                raise WireValidationError("INVALID_REQUEST")
            parts[name] = part
        if set(parts) != {"image", "metadata"}:
            raise WireValidationError("INVALID_REQUEST")
        if (
            parts["image"].get_content_type() != "image/png"
            or parts["metadata"].get_content_type() != "application/json"
        ):
            raise WireValidationError("UNSUPPORTED_MEDIA_TYPE")
        if (
            parts["image"].get_filename() != "image.png"
            or parts["metadata"].get_filename() is not None
        ):
            raise WireValidationError("INVALID_REQUEST")
        return parts["image"].get_payload(decode=True), parts["metadata"].get_payload(decode=True)
    except (UnicodeError, ValueError, TypeError) as error:
        if isinstance(error, WireValidationError):
            raise
        raise WireValidationError("INVALID_REQUEST") from error


def create_app(settings, binding=None, *, ready_check=None):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="candidate-i")
    admission = threading.Lock()
    closing = threading.Event()

    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            closing.set()
            await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=False)

    application = FastAPI(lifespan=lifespan)
    profile = LocalizationProfile(settings.extractor_fingerprint)

    def ready():
        try:
            return (
                not closing.is_set()
                and binding is not None
                and ready_check is not None
                and getattr(ready_check, "extractor_fingerprint", settings.extractor_fingerprint)
                == settings.extractor_fingerprint
                and ready_check() is True
            )
        except Exception:  # noqa: BLE001 - readiness failures must never attest a ready model.
            return False

    @application.get("/health/ready")
    async def health():
        if not ready():
            return problem("MODEL_NOT_READY", str(uuid4()), unready=True)
        return {
            "api_version": 1,
            "ready": True,
            "busy": admission.locked(),
            "extractor_fingerprint": settings.extractor_fingerprint,
        }

    @application.post("/v1/localizations")
    async def localize(request: Request):
        request_id = str(uuid4())
        if not ready():
            return problem("MODEL_NOT_READY", request_id)
        if not admission.acquire(blocking=False):
            return problem("BUSY", request_id)
        submitted = False
        lease = None
        try:
            payload, raw_metadata = parse_parts(
                request.headers.get("content-type", ""), await bounded_body(request)
            )
            metadata = decode_metadata(raw_metadata)
            request_id = metadata["request_id"]
            if metadata["expected_extractor_fingerprint"] != settings.extractor_fingerprint:
                return problem("PROFILE_MISMATCH", request_id)
            image = decode_rgb_png(payload, metadata, settings.limits)
            try:
                lease = FileLease(settings.runtime_root, "device.lock")
                acquired = lease.try_acquire()
            except ValueError:
                raise WireValidationError("RESOURCE_ERROR") from None
            if not acquired:
                return problem("BUSY", request_id)

            def work():
                try:
                    result = binding(image, profile)
                    return encode_result(
                        result, metadata, settings.extractor_fingerprint, settings.limits
                    )
                finally:
                    lease.release()
                    admission.release()

            future = executor.submit(work)
            submitted = True
            wrapped = asyncio.wrap_future(future)
            wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            # Shield the native worker; the worker owns both leases after submission.
            return JSONResponse(await asyncio.shield(wrapped))
        except WireValidationError as error:
            return problem(error.code, request_id)
        except NailProcessingError as error:
            code = "INVALID_MODEL_OUTPUT" if error.code == "INVALID_OUTPUT" else error.code
            return problem(
                code if any(code in codes for codes in PROBLEM_CODES.values()) else "MODEL_ERROR",
                request_id,
            )
        except Exception:  # noqa: BLE001 - sanitize unknown binding failures at the HTTP boundary.
            return problem("MODEL_ERROR", request_id)
        finally:
            if not submitted:
                if lease is not None:
                    lease.release()
                admission.release()

    return application
