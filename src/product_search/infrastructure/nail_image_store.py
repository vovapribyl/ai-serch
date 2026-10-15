"""Private file adapter; core sees only opaque references and immutable RGB bytes."""

import hashlib
import io
import os
import stat
from uuid import uuid4

from PIL import Image, ImageOps

from product_search.search.nail_contracts import NailProcessingError, RgbImage

from .nail_runtime import validate_runtime_root


class NailImageStore:
    def __init__(self, root, *, max_manifest_bytes=None):
        self.root = validate_runtime_root(root)
        # ponytail: this instance owns its derivatives; persisted build ownership belongs to US3.
        self._owned = {}
        self.max_manifest_bytes = max_manifest_bytes

    def _directory(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        details = os.fstat(fd)
        if details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700:
            os.close(fd)
            raise NailProcessingError("INVALID_IMAGE")
        return fd

    @staticmethod
    def _private(fd):
        details = os.fstat(fd)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_nlink != 1
        ):
            raise NailProcessingError("INVALID_IMAGE")
        return details

    def read_rgb(self, photo, profile):
        from product_search.search.nail_contracts import DecodeProfile, PhotoInput

        if not isinstance(photo, PhotoInput) or not isinstance(profile, DecodeProfile):
            raise NailProcessingError("INVALID_IMAGE")
        try:
            directory = self._directory()
            try:
                fd = os.open(
                    photo.source_ref, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
                )
                with os.fdopen(fd, "rb") as stream:
                    details = self._private(stream.fileno())
                    if details.st_size > profile.max_source_bytes:
                        raise NailProcessingError("RESOURCE_LIMIT")
                    data = stream.read(profile.max_source_bytes + 1)
            finally:
                os.close(directory)
            if len(data) > profile.max_source_bytes:
                raise NailProcessingError("RESOURCE_LIMIT")
            if hashlib.sha256(data).hexdigest() != photo.input_sha256:
                raise NailProcessingError("INVALID_IMAGE", reason="CHECKSUM_MISMATCH")
            with Image.open(io.BytesIO(data)) as raw:
                if raw.width * raw.height > profile.max_decoded_pixels:
                    raise NailProcessingError("RESOURCE_LIMIT")
                if getattr(raw, "n_frames", 1) != 1:
                    raise NailProcessingError("INVALID_IMAGE")
                raw.verify()
            with Image.open(io.BytesIO(data)) as raw:
                image = ImageOps.exif_transpose(raw)
                if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                    foreground = image.convert("RGBA")
                    image = Image.new("RGBA", image.size, "white")
                    image.alpha_composite(foreground)
                image = image.convert("RGB")
                return RgbImage(image.width, image.height, image.tobytes())
        except NailProcessingError:
            raise
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise NailProcessingError("INVALID_IMAGE") from None

    def write_derivatives(self, build_id, photo):
        import re

        if not isinstance(build_id, str) or not re.fullmatch("[0-9a-f]{32}", build_id):
            raise NailProcessingError("INVALID_OUTPUT")
        refs = []
        try:
            directory = self._directory()
            try:
                for crop in photo.regions:
                    ref = uuid4().hex
                    fd = os.open(
                        ref,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=directory,
                    )
                    with os.fdopen(fd, "wb") as stream:
                        details = self._private(stream.fileno())
                        self._owned[ref] = (details.st_dev, details.st_ino)
                        refs.append(ref)
                        image = Image.frombytes(
                            "RGB", (crop.rgb_crop.width, crop.rgb_crop.height), crop.rgb_crop.pixels
                        )
                        image.save(stream, format="PNG")
                return tuple(refs)
            finally:
                os.close(directory)
        except (OSError, ValueError):
            self.cleanup(tuple(refs))
            raise NailProcessingError("RESOURCE_ERROR") from None

    def cleanup(self, refs):
        if any(ref not in self._owned for ref in refs):
            raise NailProcessingError("INVALID_OUTPUT")
        try:
            directory = self._directory()
            try:
                for ref in refs:
                    details = os.stat(ref, dir_fd=directory, follow_symlinks=False)
                    if (details.st_dev, details.st_ino) != self._owned[ref] or not stat.S_ISREG(
                        details.st_mode
                    ):
                        raise NailProcessingError("INVALID_OUTPUT")
                    os.unlink(ref, dir_fd=directory)
                    del self._owned[ref]
            finally:
                os.close(directory)
        except OSError:
            raise NailProcessingError("RESOURCE_ERROR") from None

    def _manifest(self, directory, build_id, *, allow_missing=False):
        import json
        import re

        if (
            not isinstance(build_id, str)
            or not re.fullmatch("[0-9a-f]{32}", build_id)
            or type(self.max_manifest_bytes) is not int
            or self.max_manifest_bytes <= 0
        ):
            raise NailProcessingError("RESOURCE_LIMIT")
        name = ".manifest-" + build_id + ".json"
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            if allow_missing:
                return {}
            raise NailProcessingError("INVALID_OUTPUT") from None
        with os.fdopen(fd, "rb") as stream:
            details = self._private(stream.fileno())
            if details.st_size > self.max_manifest_bytes:
                raise NailProcessingError("RESOURCE_LIMIT")
            data = stream.read(self.max_manifest_bytes + 1)
        if len(data) > self.max_manifest_bytes:
            raise NailProcessingError("RESOURCE_LIMIT")
        value = json.loads(data)
        if (
            type(value) is not dict
            or value.get("build_id") != build_id
            or value.get("version") != 1
            or type(value.get("files")) is not dict
        ):
            raise NailProcessingError("INVALID_OUTPUT")
        return value["files"]

    def _save_manifest(self, directory, build_id, files):
        import json

        data = json.dumps(
            {"version": 1, "build_id": build_id, "files": files},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if len(data) > self.max_manifest_bytes:
            raise NailProcessingError("RESOURCE_LIMIT")
        temporary = ".manifest-" + uuid4().hex + ".tmp"
        try:
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(
                temporary,
                ".manifest-" + build_id + ".json",
                src_dir_fd=directory,
                dst_dir_fd=directory,
            )
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass

    def _save_png(self, directory, image, build_id, files):
        ref = uuid4().hex
        staging = "." + ref + ".tmp"
        returned = False
        try:
            fd = os.open(
                staging, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
            )
            with os.fdopen(fd, "w+b") as stream:
                details = self._private(stream.fileno())
                intent = {
                    "sha256": None,
                    "dev": details.st_dev,
                    "ino": details.st_ino,
                    "mode": image.mode,
                    "width": image.width,
                    "height": image.height,
                }
                # Both aliases are recorded before data/rename: either crash location remains owned.
                files[staging] = files[ref] = intent
                self._save_manifest(directory, build_id, files)
                image.save(stream, format="PNG")
                stream.flush()
                stream.seek(0)
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                os.fsync(stream.fileno())
            os.rename(staging, ref, src_dir_fd=directory, dst_dir_fd=directory)
            self._owned[ref] = (details.st_dev, details.st_ino)
            info = dict(intent, sha256=checksum)
            files[ref] = info
            del files[staging]
            self._save_manifest(directory, build_id, files)
            returned = True
            return ref, info
        finally:
            try:
                os.unlink(staging, dir_fd=directory)
            except FileNotFoundError:
                pass
            if not returned and ref in self._owned:
                self.cleanup((ref,))

    def write_region_artifacts(self, build_id, photo):
        from product_search.search.nail_contracts import RegionArtifacts

        created = []
        directory = self._directory()
        temporary = None
        try:
            files = self._manifest(directory, build_id, allow_missing=True)
            artifacts = []
            for crop in photo.regions:
                with Image.frombytes(
                    "L", (crop.mask.width, crop.mask.height), crop.mask.pixels
                ) as mask:
                    mask_ref, mask_info = self._save_png(directory, mask, build_id, files)
                created.append(mask_ref)
                with Image.frombytes(
                    "RGB", (crop.rgb_crop.width, crop.rgb_crop.height), crop.rgb_crop.pixels
                ) as image:
                    crop_ref, crop_info = self._save_png(directory, image, build_id, files)
                created.append(crop_ref)
                files[mask_ref], files[crop_ref] = mask_info, crop_info
                artifacts.append(
                    RegionArtifacts(crop.ordinal, mask_ref, crop_ref, crop_info["sha256"])
                )
            return tuple(artifacts)
        except NailProcessingError:
            if created:
                self.cleanup(tuple(created))
            raise
        except (OSError, ValueError):
            if created:
                self.cleanup(tuple(created))
            raise NailProcessingError("RESOURCE_ERROR") from None
        finally:
            if temporary:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
            os.close(directory)

    def verify_artifacts(self, build_id, artifacts, profile):
        directory = self._directory()
        try:
            files = self._manifest(directory, build_id)
            for artifact in artifacts:
                for ref, mode in ((artifact.mask_ref, "L"), (artifact.crop_ref, "RGB")):
                    info = files.get(ref)
                    if (
                        not isinstance(info, dict)
                        or info.get("mode") != mode
                        or (mode == "RGB" and info.get("sha256") != artifact.crop_sha256)
                    ):
                        raise NailProcessingError("INVALID_OUTPUT")
                    fd = os.open(ref, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                    with os.fdopen(fd, "rb") as stream:
                        details = self._private(stream.fileno())
                        if (details.st_dev, details.st_ino) != (
                            info["dev"],
                            info["ino"],
                        ) or details.st_size > profile.max_source_bytes:
                            raise NailProcessingError("INVALID_OUTPUT")
                        data = stream.read(profile.max_source_bytes + 1)
                    if (
                        len(data) > profile.max_source_bytes
                        or hashlib.sha256(data).hexdigest() != info["sha256"]
                    ):
                        raise NailProcessingError("INVALID_OUTPUT")
                    with Image.open(io.BytesIO(data)) as image:
                        if (
                            image.format != "PNG"
                            or image.mode != mode
                            or image.size != (info["width"], info["height"])
                            or image.width * image.height > profile.max_decoded_pixels
                            or "exif" in image.info
                            or "transparency" in image.info
                        ):
                            raise NailProcessingError("INVALID_OUTPUT")
                        image.verify()
                    with Image.open(io.BytesIO(data)) as image:
                        if mode == "L":
                            pixels = image.tobytes()
                            if not any(pixels) or any(p not in (0, 255) for p in pixels):
                                raise NailProcessingError("INVALID_OUTPUT")
        except (OSError, ValueError, KeyError, SyntaxError, Image.DecompressionBombError):
            raise NailProcessingError("INVALID_OUTPUT") from None
        finally:
            os.close(directory)

    def cleanup_orphans(self, build_id, keep_refs):
        import re

        directory = self._directory()
        try:
            files = self._manifest(directory, build_id, allow_missing=True)
            removed = 0
            for ref, info in tuple(files.items()):
                if ref in keep_refs:
                    continue
                if not re.fullmatch(r"(?:[0-9a-f]{32}|\.[0-9a-f]{32}\.tmp)", ref):
                    raise NailProcessingError("INVALID_OUTPUT")
                try:
                    fd = os.open(ref, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                except FileNotFoundError:
                    del files[ref]
                    continue
                with os.fdopen(fd, "rb") as stream:
                    details = self._private(stream.fileno())
                    if (details.st_dev, details.st_ino) != (info["dev"], info["ino"]):
                        raise NailProcessingError("INVALID_OUTPUT")
                os.unlink(ref, dir_fd=directory)
                self._owned.pop(ref, None)
                del files[ref]
                removed += 1
            self._save_manifest(directory, build_id, files)
            return removed
        except (OSError, ValueError, KeyError):
            raise NailProcessingError("INVALID_OUTPUT") from None
        finally:
            os.close(directory)

    def import_source(self, input_root, path, max_bytes):
        from pathlib import Path

        input_root = validate_runtime_root(input_root)
        path = Path(path)
        if path.parent.resolve() != input_root or type(max_bytes) is not int or max_bytes <= 0:
            raise NailProcessingError("INVALID_IMAGE")
        ref = uuid4().hex
        source_dir = target_dir = None
        owned = False
        done = False
        try:
            source_dir = os.open(input_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            source_fd = os.open(
                path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=source_dir
            )
            with os.fdopen(source_fd, "rb") as source:
                source_info = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(source_info.st_mode)
                    or source_info.st_uid != os.getuid()
                    or source_info.st_nlink != 1
                    or source_info.st_size > max_bytes
                ):
                    raise NailProcessingError("INVALID_IMAGE")
                target_dir = self._directory()
                target_fd = os.open(
                    ref,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=target_dir,
                )
                with os.fdopen(target_fd, "wb") as target:
                    target_info = self._private(target.fileno())
                    self._owned[ref] = (target_info.st_dev, target_info.st_ino)
                    owned = True
                    digest = hashlib.sha256()
                    count = 0
                    for chunk in iter(lambda: source.read(64 * 1024), b""):
                        count += len(chunk)
                        if count > max_bytes:
                            raise NailProcessingError("RESOURCE_LIMIT")
                        target.write(chunk)
                        digest.update(chunk)
                done = True
                return ref, digest.hexdigest()
        except NailProcessingError:
            raise
        except OSError:
            raise NailProcessingError("INVALID_IMAGE") from None
        finally:
            if source_dir is not None:
                os.close(source_dir)
            if target_dir is not None:
                os.close(target_dir)
            if owned and not done:
                self.cleanup((ref,))
