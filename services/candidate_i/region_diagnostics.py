"""One private, bounded pre-HTTP snapshot; never filters the model's result."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from product_search.infrastructure.nail_build_composition import publish_private_json
from product_search.infrastructure.nail_runtime import validate_runtime_root


class _ByteLimit(Exception):
    pass


class _LimitedFile:
    def __init__(self, stream, limit):
        self.stream, self.limit, self.size = stream, limit, 0

    def write(self, data):
        if self.size + len(data) > self.limit:
            raise _ByteLimit
        written = self.stream.write(data)
        self.size += written
        return written

    def flush(self):
        self.stream.flush()


def _save_image(image, path, limit, format):
    if limit <= 0:
        return None
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            image.save(_LimitedFile(stream, limit), format=format)
            stream.flush()
            os.fsync(stream.fileno())
        with path.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        return {"bytes": path.stat().st_size, "sha256": sha}
    except _ByteLimit:
        path.unlink(missing_ok=True)
        return None
    except Exception:
        path.unlink(missing_ok=True)
        raise


class RegionDiagnostics:
    """HTTP admission serializes calls; at most one snapshot per configured probe."""

    def __init__(self, root, *, max_regions=32, max_bytes=16 * 1024**2):
        if type(max_regions) is not int or not 1 <= max_regions <= 32:
            raise ValueError("Invalid region diagnostic limit")
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 16 * 1024**2:
            raise ValueError("Invalid diagnostic byte limit")
        self.root = validate_runtime_root(Path(root))
        self.max_regions, self.max_bytes = max_regions, max_bytes
        self.last_status = {"status": "NOT_RECORDED"}
        self._recorded = False

    def __call__(self, image, result, profile):
        if self._recorded:
            return self.last_status
        self._recorded = True
        folder = None
        data = {
            "schema_version": 1,
            "status": "COMPLETE",
            "total_regions": len(result.regions),
            "saved_region_count": 0,
            "regions": [],
            "truncated": False,
            "truncation_reasons": [],
            "width": image.width,
            "height": image.height,
            "rgb_sha256": hashlib.sha256(image.pixels).hexdigest(),
            "extractor_fingerprint": profile.extractor_fingerprint,
            "overview_file": None,
        }
        try:
            folder = Path(tempfile.mkdtemp(prefix="localization-", dir=self.root))
            used = 0
            # Reserve bounded metadata before any PNG/JPEG writes; tiny budgets
            # deliberately preserve only metadata with a byte-limit marker.
            remaining = max(0, self.max_bytes - 16384)
            with Image.frombytes("RGB", (image.width, image.height), image.pixels) as overview:
                draw = ImageDraw.Draw(overview)
                for region in result.regions[: self.max_regions]:
                    name = f"mask-{region.ordinal}.png"
                    with Image.frombytes(
                        "L", (region.mask.width, region.mask.height), region.mask.pixels
                    ) as mask:
                        box = mask.getbbox()
                        info = _save_image(mask, folder / name, remaining - used, "PNG")
                    if info is None:
                        data["truncation_reasons"].append("byte_limit")
                        break
                    used += info["bytes"]
                    data["regions"].append(
                        {
                            "ordinal": region.ordinal,
                            "confidence": region.confidence,
                            "detector_box_xyxy": list(region.detector_box_xyxy),
                            "mask_bbox_xyxy": list(box) if box else None,
                            "mask_file": name,
                            "mask_bytes": info["bytes"],
                            "mask_sha256": info["sha256"],
                        }
                    )
                    if box:
                        x0, y0, x1, y1 = box
                        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline="#1976d2", width=1)
                        draw.text((x0, y0), str(region.ordinal), fill="#1976d2")
                if len(result.regions) > self.max_regions:
                    data["truncation_reasons"].append("region_limit")
                info = _save_image(overview, folder / "overview.jpg", remaining - used, "JPEG")
                if info is not None:
                    used += info["bytes"]
                    data.update(
                        overview_file="overview.jpg",
                        overview_bytes=info["bytes"],
                        overview_sha256=info["sha256"],
                    )
                elif "byte_limit" not in data["truncation_reasons"]:
                    data["truncation_reasons"].append("byte_limit")
            data["saved_region_count"] = len(data["regions"])
            data["truncated"] = bool(data["truncation_reasons"])
            if data["truncated"]:
                data["status"] = "PARTIAL"
        except Exception as error:  # noqa: BLE001 -- diagnostic failures cannot replace inference.
            data.update(status="FAILED", error_type=type(error).__name__)
        data["saved_region_count"] = len(data["regions"])
        try:
            if folder is None:
                raise OSError
            payload = json.dumps(data, sort_keys=True, allow_nan=False).encode()
            used = sum(f.stat().st_size for f in folder.iterdir())
            if used + len(payload) > self.max_bytes:
                raise _ByteLimit
            publish_private_json(folder / "diagnostic.json", data)
            directory = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except Exception as error:  # noqa: BLE001 -- diagnostic failures cannot replace inference.
            data.update(status="FAILED", error_type=type(error).__name__)
        self.last_status = data
        return data


class ObservedBinding:
    def __init__(self, binding, diagnostics):
        self.binding, self.diagnostics = binding, diagnostics

    def __call__(self, image, profile):
        result = self.binding(image, profile)
        try:
            self.diagnostics(image, result, profile)
        except Exception as error:  # noqa: BLE001 -- diagnostic failures cannot replace inference.
            self.diagnostics.last_status = {"status": "FAILED", "error_type": type(error).__name__}
        return result
