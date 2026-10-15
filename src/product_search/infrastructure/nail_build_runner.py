"""Outer build boundaries; importing this module never loads model SDKs."""

import hashlib
import io
import math
import os
import stat
import threading
from pathlib import Path

from PIL import Image, ImageOps

from product_search.search.nail_contracts import (
    DecodeProfile,
    NailProcessingError,
    PhotoInput,
    RgbImage,
)


class BuildStop(RuntimeError):
    """Terminal outer stop; deliberately not a recoverable NailProcessingError."""


class SourceImageDecodeError(BuildStop):
    """Frozen bytes are intact, but the individual image cannot be decoded."""


class ManifestImageStore:
    """Read only frozen source basenames; delegate writes to a separate private store."""

    def __init__(self, root, inputs, derivatives):
        self.root = Path(root)
        self.inputs = dict(inputs)
        self.derivatives = derivatives

    def read_rgb(self, photo, profile):
        if not isinstance(photo, PhotoInput) or not isinstance(profile, DecodeProfile):
            raise BuildStop("INVALID_SOURCE")
        name = self.inputs.get(photo.source_ref)
        if not isinstance(name, str) or Path(name).name != name or name in ("", ".", ".."):
            raise BuildStop("INVALID_SOURCE")
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise BuildStop("INVALID_SOURCE_ROOT")
        root = self.root.stat()
        if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid() or root.st_mode & 0o022:
            raise BuildStop("INVALID_SOURCE_ROOT")
        directory = fd = None
        try:
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_mode & 0o022
                or before.st_nlink != 1
                or before.st_size > profile.max_source_bytes
            ):
                raise BuildStop("INVALID_OR_OVERSIZE_SOURCE")
            with os.fdopen(fd, "rb") as stream:
                fd = None
                data = stream.read(profile.max_source_bytes + 1)
                after = os.fstat(stream.fileno())
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise BuildStop("SOURCE_CHANGED")
            if (
                len(data) > profile.max_source_bytes
                or hashlib.sha256(data).hexdigest() != photo.input_sha256
            ):
                raise BuildStop("SOURCE_HASH_MISMATCH")
            try:
                with Image.open(io.BytesIO(data)) as raw:
                    if raw.width * raw.height > profile.max_decoded_pixels:
                        raise BuildStop("SOURCE_PIXEL_LIMIT")
                    if getattr(raw, "n_frames", 1) != 1:
                        raise BuildStop("INVALID_SOURCE")
                    raw.verify()
                with Image.open(io.BytesIO(data)) as raw:
                    image = ImageOps.exif_transpose(raw)
                    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                        foreground = image.convert("RGBA")
                        image = Image.new("RGBA", image.size, "white")
                        image.alpha_composite(foreground)
                    image = image.convert("RGB")
                    return RgbImage(image.width, image.height, image.tobytes())
            except (OSError, ValueError, SyntaxError):
                raise SourceImageDecodeError("INVALID_SOURCE") from None
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise BuildStop("INVALID_SOURCE") from None
        finally:
            if fd is not None:
                os.close(fd)
            if directory is not None:
                os.close(directory)

    def write_region_artifacts(self, *args):
        return self.derivatives.write_region_artifacts(*args)

    def cleanup(self, *args):
        return self.derivatives.cleanup(*args)

    def verify_artifacts(self, *args):
        return self.derivatives.verify_artifacts(*args)

    def cleanup_orphans(self, *args):
        return self.derivatives.cleanup_orphans(*args)


class AdmissionBudget:
    """Sticky terminal state shared by every provider load/encode and I admission."""

    def __init__(self, maximum, deadline, observe, clock):
        if (
            type(maximum) is not int
            or maximum < 1
            or type(deadline) not in (int, float)
            or not math.isfinite(deadline)
        ):
            raise BuildStop("INVALID_BUDGET")
        self.maximum, self.deadline = maximum, deadline
        self.observe, self.clock = observe, clock
        self.used = 0
        self.stopped = False
        self.lock = threading.Lock()

    def admit(self):
        with self.lock:
            if self.stopped:
                raise BuildStop("TERMINAL_STOP")
            try:
                now = self.clock()
                if (
                    not math.isfinite(now)
                    or now >= self.deadline
                    or self.used >= self.maximum
                    or self.observe() is not True
                ):
                    raise BuildStop("BUDGET_OR_RESOURCE_STOP")
                self.used += 1
            except BaseException:
                self.stopped = True
                raise


def run_admitted_build(
    service, identity, inventory, runtime, *, target_check, input_check, runtime_check, coordinator
):
    """Only verifies and builds: no publish, retry, resume, or model construction."""
    if not coordinator.try_acquire():
        raise BuildStop("COORDINATOR_BUSY")
    try:
        for check in (target_check, input_check, runtime_check):
            if check() is not True:
                raise BuildStop("BUILD_NOT_ADMITTED")
        return service.execute(identity, inventory, runtime, resume=False)
    finally:
        coordinator.release()


class OwnedTarget:
    """Pinned private descriptor plus independent Docker/SQL observations."""

    def __init__(self, descriptor, expected_sha256, *, inspect=None):
        self.path, self.sha256 = Path(descriptor), expected_sha256
        self.inspect = inspect or self._inspect

    @staticmethod
    def _inspect(kind, identity):
        import json
        import subprocess

        args = ["docker", "--context", "colima"]
        args += ["volume", "inspect", identity] if kind == "volume" else ["inspect", identity]
        result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
        if result.returncode:
            raise BuildStop("TARGET_UNAVAILABLE")
        return json.loads(result.stdout)[0]

    def connect(self):
        import json

        import psycopg

        conn = None
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1
                    or info.st_size > 1048576
                ):
                    raise BuildStop("INVALID_TARGET_DESCRIPTOR")
                blob = stream.read(1048577)
            if hashlib.sha256(blob).hexdigest() != self.sha256:
                raise BuildStop("TARGET_DESCRIPTOR_CHANGED")
            data = json.loads(blob)
            config = data["config"]
            if (
                config["host"] != "127.0.0.1"
                or type(config["port"]) is not int
                or not 1 <= config["port"] <= 65535
            ):
                raise BuildStop("INVALID_TARGET_ENDPOINT")
            meta = self.inspect("container", data["container_id"])
            if (
                meta["Id"] != data["container_id"]
                or meta["Image"] != data["image"]
                or meta["Config"]["Labels"].get("candidate-i-g5-owner") != data["marker"]
                or not meta["State"]["Running"]
            ):
                raise BuildStop("TARGET_IDENTITY_MISMATCH")
            mounts = meta["Mounts"]
            if (
                len(mounts) != 1
                or mounts[0]["Type"] != "volume"
                or mounts[0]["Name"] != data["volume"]
                or mounts[0]["Destination"] != "/var/lib/postgresql/data"
            ):
                raise BuildStop("TARGET_VOLUME_MISMATCH")
            volume = self.inspect("volume", data["volume"])
            if volume["Labels"].get("candidate-i-g5-owner") != data["marker"]:
                raise BuildStop("TARGET_VOLUME_MISMATCH")
            bindings = meta["NetworkSettings"]["Ports"]["5432/tcp"]
            if (
                len(bindings) != 1
                or bindings[0]["HostIp"] != "127.0.0.1"
                or int(bindings[0]["HostPort"]) != config["port"]
            ):
                raise BuildStop("TARGET_ENDPOINT_MISMATCH")
            conn = psycopg.connect(**config)
            if conn.execute("SELECT current_database(),current_user").fetchone() != (
                config["dbname"],
                config["user"],
            ):
                raise BuildStop("TARGET_SQL_IDENTITY_MISMATCH")
            if conn.execute("SELECT version_num FROM alembic_version").fetchone() != (
                "0009_nail_search_v1",
            ):
                raise BuildStop("TARGET_SCHEMA_MISMATCH")
            return conn
        except Exception:  # noqa: BLE001 -- external boundary errors must be terminal and redact private details.
            if conn is not None:
                conn.close()
            raise BuildStop("TARGET_NOT_VERIFIED") from None


class GuardedEmbedding:
    """SDK exception translation must never turn terminal stop into photo ERROR."""

    def __init__(self, adapter, budget):
        self.adapter, self.budget = adapter, budget

    def encode(self, *args):
        if self.budget.stopped:
            raise BuildStop("TERMINAL_STOP")
        try:
            return self.adapter.encode(*args)
        except Exception:  # noqa: BLE001 -- external boundary errors must be terminal and redact private details.
            self.budget.stopped = True
            raise BuildStop("EMBEDDING_STOP") from None


def admitted_provider(factory, budget, device):
    from types import SimpleNamespace

    def call(operation, *args):
        if not device.try_acquire():
            budget.stopped = True
            raise BuildStop("DEVICE_BUSY")
        try:
            budget.admit()
            return operation(*args)
        except BaseException:
            budget.stopped = True
            raise
        finally:
            device.release()

    def load():
        provider = call(factory)
        return SimpleNamespace(
            model_key=provider.model_key,
            revision=provider.revision,
            embedding_dim=provider.embedding_dim,
            encode_image=lambda image: call(provider.encode_image, image),
        )

    return load


class GuardedLocalization:
    def __init__(self, adapter, budget):
        self.adapter, self.budget = adapter, budget

    def localize(self, *args):
        try:
            self.budget.admit()
            return self.adapter.localize(*args)
        except Exception as error:  # noqa: BLE001 -- unknown boundary failures remain terminal.
            if isinstance(error, NailProcessingError) and error.code in {
                "REGION_COUNT_LIMIT",
                "RESPONSE_SIZE_LIMIT",
            }:
                # The core records this photo ERROR and continues; preserve safe code only.
                raise NailProcessingError(error.code) from None
            self.budget.stopped = True
            from product_search.infrastructure.nail_wire import PROBLEM_CODES

            stop = BuildStop("LOCALIZATION_STOP")
            stop.cause_type = type(error).__name__
            allowed = {code for codes in PROBLEM_CODES.values() for code in codes} | {
                "INVALID_OUTPUT",
                "RESOURCE_LIMIT",
            }
            stop.cause_code = (
                error.code
                if isinstance(error, NailProcessingError) and error.code in allowed
                else None
            )
            raise stop from None


def verify_preparation(bundle_path, expected_sha256):
    import json

    from product_search.search.nail_contracts import BuildPhoto

    def read_pinned(path, expected, *, private=True):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or info.st_size > 8388608
                or (private and stat.S_IMODE(info.st_mode) != 0o600)
            ):
                raise BuildStop("UNSAFE_PREPARATION_FILE")
            blob = stream.read(8388609)
        if hashlib.sha256(blob).hexdigest() != expected:
            raise BuildStop("PREPARATION_FILE_CHANGED")
        return blob

    try:
        bundle = json.loads(read_pinned(bundle_path, expected_sha256))
        for item in bundle["code"]:
            read_pinned(item["path"], item["sha256"], private=False)
        files = {
            name: json.loads(read_pinned(ref["path"], ref["sha256"]))
            for name, ref in bundle["files"].items()
        }
        source, decode, parent = files["source"], files["decode"], files["parent"]
        items = files["inventory"]["items"]
        inventory = tuple(
            BuildPhoto(
                item["catalog_photo_id"], item["product_record_id"], PhotoInput(**item["photo"])
            )
            for item in items
        )
        ids = [item.product_record_id for item in inventory]
        expected_ids = sorted(row["record_id"] for row in source["inputs"])
        if ids != expected_ids or len(ids) != 674 or len(set(ids)) != 674:
            raise BuildStop("PREPARATION_INVENTORY_MISMATCH")
        original = {row["record_id"]: row for row in source["inputs"]}
        if any(
            item.photo.input_sha256 != original[item.product_record_id]["actual_sha256"]
            for item in inventory
        ):
            raise BuildStop("PREPARATION_INVENTORY_MISMATCH")
        canonical_sha = hashlib.sha256(
            json.dumps(items, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if canonical_sha != bundle["inventory_sha256"]:
            raise BuildStop("PREPARATION_INVENTORY_MISMATCH")
        fields = (
            "id",
            "corpus_version_id",
            "product_id",
            "source_row",
            "category",
            "image_path",
            "image_sha256",
            "image_format",
        )
        with OwnedTarget(
            bundle["files"]["target"]["path"], bundle["files"]["target"]["sha256"]
        ).connect() as conn:
            rows = conn.execute(
                "SELECT "
                + ",".join(fields)
                + " FROM product_records WHERE corpus_version_id=%s ORDER BY id",
                (parent["parent"]["id"],),
            ).fetchall()
            expected_rows = [tuple(row[key] for key in fields) for row in parent["records"]]
            if rows != expected_rows:
                raise BuildStop("TARGET_PARENT_MISMATCH")
            if conn.execute("SELECT count(*) FROM search_representations").fetchone() != (
                0,
            ) or conn.execute("SELECT count(*) FROM search_active_representations").fetchone() != (
                0,
            ):
                raise BuildStop("TARGET_NOT_EMPTY_FOR_FIRST_BUILD")
        by_id = {row["record_id"]: row for row in decode["inputs"]}
        if (
            len(decode["inputs"]) != 674
            or set(by_id) != set(expected_ids)
            or any(by_id[key]["sha256"] != original[key]["actual_sha256"] for key in expected_ids)
        ):
            raise BuildStop("DECODE_SNAPSHOT_MISMATCH")
        ok = sum(row["outcome"] == "OK" for row in decode["inputs"])
        return {
            "target_records": len(rows),
            "decode_ok": ok,
            "decode_blocked": 674 - ok,
            "preparation_status": "PASS" if ok == 674 else "BLOCKED_INPUT_POLICY",
            "native_launch": "NOT_APPROVED_OR_ASSEMBLED",
            "ml_executed": False,
        }
    except BuildStop:
        raise
    except Exception:  # noqa: BLE001 -- external boundary errors must be terminal and redact private details.
        raise BuildStop("PREPARATION_NOT_VERIFIED") from None
