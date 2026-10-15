"""One-time offline input copy; product decode policy and originals stay unchanged."""

import hashlib
import io
import os
import stat
from pathlib import Path

from PIL import Image, ImageOps
from PIL import __version__ as pillow_version

from product_search.infrastructure.nail_build_runner import BuildStop


def prepare_input(source, destination, expected_sha256, *, transform=False):
    source, destination = Path(source), Path(destination)
    if any(
        p.is_symlink()
        for p in (source, *source.parents, destination.parent, *destination.parent.parents)
    ):
        raise BuildStop("UNSAFE_INPUT_PATH")
    parent = destination.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
        raise BuildStop("OUTPUT_NOT_PRIVATE")
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_mode & 0o022
            or before.st_size > 20971520
        ):
            raise BuildStop("INVALID_SOURCE")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            data = stream.read(20971521)
            after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise BuildStop("SOURCE_CHANGED")
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise BuildStop("SOURCE_HASH_MISMATCH")
        with Image.open(io.BytesIO(data)) as raw:
            size = raw.size
            if getattr(raw, "n_frames", 1) != 1:
                raise BuildStop("INVALID_SOURCE")
            if transform:
                if size != (1802, 1802):
                    raise BuildStop("UNAPPROVED_TRANSFORM_INPUT")
            elif raw.width * raw.height > 2359296:
                raise BuildStop("SOURCE_PIXEL_LIMIT")
            raw.verify()
        with Image.open(io.BytesIO(data)) as raw:
            raw.load()
            if transform:
                image = ImageOps.exif_transpose(raw)
                if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                    foreground = image.convert("RGBA")
                    image = Image.new("RGBA", image.size, "white")
                    image.alpha_composite(foreground)
                image = image.convert("RGB").resize((1536, 1536), Image.Resampling.LANCZOS)
                image.info.clear()
                output = io.BytesIO()
                image.save(output, format="PNG")
                data = output.getvalue()
        if len(data) > 20971520:
            raise BuildStop("OUTPUT_BYTE_LIMIT")
        output_fd = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        try:
            with os.fdopen(output_fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            destination.unlink()
            raise
        return {
            "original_sha256": expected_sha256,
            "input_sha256": hashlib.sha256(data).hexdigest(),
            "original_size": list(size),
            "input_size": [1536, 1536] if transform else list(size),
            "transformed": transform,
            "algorithm": "exif_white_rgb_lanczos_png_v1" if transform else "byte_copy_v1",
            "pillow_version": pillow_version,
            "size_bytes": len(data),
        }
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise BuildStop("INPUT_PREPARATION_FAILED") from None
    finally:
        if fd is not None:
            os.close(fd)
