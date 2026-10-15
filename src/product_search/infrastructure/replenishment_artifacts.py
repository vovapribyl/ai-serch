"""Immutable, private stage files. Only the controller commits database receipts."""

import hashlib
import io
import json
import math
import os
import re
import stat
from pathlib import Path

from PIL import Image

from product_search.search.nail_contracts import MODEL_DIMENSIONS
from product_search.search.replenishment_contracts import ReplenishmentError, StageOutput


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CheckpointFiles:
    def __init__(self, root):
        self.root = Path(root)
        self._private_directory(self.root)
        for name in ("staging", "final"):
            directory = self.root / name
            directory.mkdir(mode=0o700, exist_ok=True)
            self._private_directory(directory)

    @staticmethod
    def _private_directory(path):
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise ReplenishmentError("CHECKPOINT_INVALID")

    @staticmethod
    def _key(attempt):
        if type(attempt.attempt_ref) is not str or not 0 < len(attempt.attempt_ref) <= 128:
            raise ReplenishmentError("CHECKPOINT_INVALID")
        return sha(attempt.attempt_ref.encode())

    def _path(self, parent, output):
        if type(output.artifact_ref) is not str or not re.fullmatch(
            "[0-9a-f]{64}", output.artifact_ref
        ):
            raise ReplenishmentError("CHECKPOINT_INVALID")
        self._private_directory(self.root / parent)
        return self.root / parent / output.artifact_ref

    def staging_path(self, output):
        return self._path("staging", output)

    def is_final(self, output):
        path = self._path("final", output)
        if path.is_symlink():
            raise ReplenishmentError("CHECKPOINT_INVALID")
        return path.exists()

    @staticmethod
    def _read(path, cap):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > cap
                ):
                    raise ReplenishmentError("CHECKPOINT_INVALID")
                data = stream.read(cap + 1)
                if len(data) > cap:
                    raise ReplenishmentError("CHECKPOINT_INVALID")
                return data
        except OSError:
            raise ReplenishmentError("CHECKPOINT_INVALID") from None

    def write_staging(self, attempt, package, region_count, files):
        key = self._key(attempt)
        if type(region_count) is not int or not 0 <= region_count <= package.max_regions:
            raise ReplenishmentError("CHECKPOINT_INVALID")
        cap = (
            package.max_vector_bytes if attempt.stage_key == "embedding" else package.max_wire_bytes
        )
        if (
            type(files) is not dict
            or any(
                type(n) is not str
                or not re.fullmatch(r"[a-z0-9-]+\.(json|png)", n)
                or n == "manifest.json"
                or type(data) is not bytes
                for n, data in files.items()
            )
            or sum(map(len, files.values())) > cap
        ):
            raise ReplenishmentError("CHECKPOINT_INVALID")
        manifest = {
            "schema_version": 1,
            "attempt_ref": attempt.attempt_ref,
            "identity_sha": attempt.identity_sha,
            "semantic_profile_sha": package.semantic_profile_sha,
            "stage_key": attempt.stage_key,
            "model_key": attempt.model_key,
            "region_count": region_count,
            "files": [
                {"name": name, "bytes": len(data), "sha256": sha(data)}
                for name, data in sorted(files.items())
            ],
        }
        raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(raw) > package.max_wire_bytes:
            raise ReplenishmentError("CHECKPOINT_INVALID")
        output = StageOutput(key, sha(raw), region_count)
        if self.is_final(output):
            path = self._path("final", output)
            if self._read(path / "manifest.json", package.max_wire_bytes) != raw:
                raise ReplenishmentError("ARTIFACT_CONFLICT")
            self._check(attempt, output, package, path)
            return output
        path = self.staging_path(output)
        try:
            path.mkdir(mode=0o700)
            for name, data in {**files, "manifest.json": raw}.items():
                fd = os.open(
                    path / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                )
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
        except OSError:
            raise ReplenishmentError("ARTIFACT_CONFLICT") from None
        return output

    def _check(self, attempt, output, package, path):
        self._private_directory(path)
        raw = self._read(path / "manifest.json", package.max_wire_bytes)
        if sha(raw) != output.manifest_sha or self._key(attempt) != output.artifact_ref:
            raise ReplenishmentError("CHECKPOINT_INVALID")
        try:
            manifest = json.loads(raw)
            if (
                manifest["schema_version"] != 1
                or manifest["attempt_ref"] != attempt.attempt_ref
                or manifest["identity_sha"] != attempt.identity_sha
                or not re.fullmatch("[0-9a-f]{64}", manifest["identity_sha"])
                or manifest["semantic_profile_sha"] != package.semantic_profile_sha
                or (manifest["stage_key"], manifest["model_key"])
                != (attempt.stage_key, attempt.model_key)
                or type(manifest["region_count"]) is not int
                or not 0 <= manifest["region_count"] <= package.max_regions
                or manifest["region_count"] != output.region_count
            ):
                raise ReplenishmentError("CHECKPOINT_INVALID")
            cap = (
                package.max_vector_bytes
                if attempt.stage_key == "embedding"
                else package.max_wire_bytes
            )
            payloads = {}
            for item in manifest["files"]:
                name = item["name"]
                if (
                    not re.fullmatch(r"[a-z0-9-]+\.(json|png)", name)
                    or name == "manifest.json"
                    or name in payloads
                    or type(item["bytes"]) is not int
                    or not 0 <= item["bytes"] <= cap
                ):
                    raise ReplenishmentError("CHECKPOINT_INVALID")
                data = self._read(path / name, cap)
                if len(data) != item["bytes"] or sha(data) != item["sha256"]:
                    raise ReplenishmentError("CHECKPOINT_INVALID")
                payloads[name] = data
            if sum(map(len, payloads.values())) > cap or {p.name for p in path.iterdir()} != set(
                payloads
            ) | {"manifest.json"}:
                raise ReplenishmentError("CHECKPOINT_INVALID")
            self._validate_payload(attempt, output.region_count, payloads, package)
            return payloads
        except (
            ValueError,
            TypeError,
            KeyError,
            OSError,
            OverflowError,
            Image.DecompressionBombError,
        ):
            raise ReplenishmentError("CHECKPOINT_INVALID") from None

    @staticmethod
    def _validate_payload(attempt, count, files, package):
        dimensions = dict(MODEL_DIMENSIONS)
        if attempt.stage_key == "embedding":
            if count == 0 or set(files) != {"vectors.json"} or attempt.model_key not in dimensions:
                raise ReplenishmentError("CHECKPOINT_INVALID")
            payload = json.loads(files["vectors.json"])
            if payload["model_key"] != attempt.model_key or len(payload["vectors"]) != count:
                raise ReplenishmentError("CHECKPOINT_INVALID")
            for ordinal, vector in enumerate(payload["vectors"], 1):
                values = vector["values"]
                if (
                    type(vector["ordinal"]) is not int
                    or vector["ordinal"] != ordinal
                    or type(values) is not list
                    or len(values) != dimensions[attempt.model_key]
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                ):
                    raise ReplenishmentError("CHECKPOINT_INVALID")
        elif attempt.stage_key == "localization" and attempt.model_key == "":
            expected = {
                f"{kind}-{ordinal}.png"
                for kind in ("crop", "mask")
                for ordinal in range(1, count + 1)
            }
            if set(files) != expected:
                raise ReplenishmentError("CHECKPOINT_INVALID")
            for name, data in files.items():
                with Image.open(io.BytesIO(data)) as image:
                    mode = "L" if name.startswith("mask") else "RGB"
                    if (
                        image.format != "PNG"
                        or image.mode != mode
                        or image.width * image.height > package.max_pixels
                    ):
                        raise ReplenishmentError("CHECKPOINT_INVALID")
                    image.load()
                    if mode == "L" and (
                        not any(image.tobytes()) or any(v not in (0, 255) for v in image.tobytes())
                    ):
                        raise ReplenishmentError("CHECKPOINT_INVALID")
        else:
            raise ReplenishmentError("CHECKPOINT_INVALID")

    @staticmethod
    def _sync(path, directory=False):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def verify(self, attempt, output, package):
        try:
            if self.is_final(output):
                final = self._path("final", output)
                self._check(attempt, output, package, final)
                # A retry must confirm parent durability after an earlier sync failure.
                self._sync(final, directory=True)
                self._sync(final.parent, directory=True)
                return
            staging = self.staging_path(output)
            self._check(attempt, output, package, staging)
            for file in staging.iterdir():
                self._sync(file)
            self._sync(staging, directory=True)
            final = self._path("final", output)
            os.rename(staging, final)
            self._sync(final.parent, directory=True)
        except OSError:
            raise ReplenishmentError("CHECKPOINT_INVALID") from None

    def read_files(self, attempt, output, package):
        if not self.is_final(output):
            raise ReplenishmentError("CHECKPOINT_INVALID")
        return self._check(attempt, output, package, self._path("final", output))

    def verify_saved(self, attempt, output, package):
        if not self.is_final(output):
            raise ReplenishmentError("CHECKPOINT_INVALID")
        self.verify(attempt, output, package)
