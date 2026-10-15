import hashlib
import io
import os
from dataclasses import FrozenInstanceError

import pytest
from PIL import Image

from product_search.infrastructure.nail_image_store import NailImageStore
from product_search.search.nail_contracts import (
    BinaryMask,
    DecodeProfile,
    NailProcessingError,
    PhotoInput,
    ProcessedPhoto,
    RegionCrop,
    RgbImage,
)


def source(tmp_path, image, fmt="PNG"):
    tmp_path.chmod(0o700)
    out = io.BytesIO()
    image.save(out, format=fmt, exif=image.getexif())
    data = out.getvalue()
    path = tmp_path / ("a" * 32)
    path.write_bytes(data)
    path.chmod(0o600)
    return PhotoInput(1, path.name, hashlib.sha256(data).hexdigest())


def test_decode_alpha_white_and_checksum(tmp_path):
    photo = source(tmp_path, Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
    store = NailImageStore(tmp_path)
    result = store.read_rgb(photo, DecodeProfile(10000, 100))
    assert result == RgbImage(1, 1, b"\xff\xff\xff")
    with pytest.raises(NailProcessingError):
        store.read_rgb(PhotoInput(1, photo.source_ref, "0" * 64), DecodeProfile(10000, 100))


def test_exif_before_frame_dimensions(tmp_path):
    image = Image.new("RGB", (2, 3), "red")
    image.getexif()[274] = 6
    photo = source(tmp_path, image)
    result = NailImageStore(tmp_path).read_rgb(photo, DecodeProfile(10000, 100))
    assert result is not None
    assert (result.width, result.height) == (3, 2)


@pytest.mark.parametrize("ref", ["../escape", "/tmp/file", "", "a" * 31, "A" * 32])
def test_opaque_refs_reject_paths(ref):
    with pytest.raises(NailProcessingError):
        PhotoInput(1, ref, "a" * 64)


def test_symlink_and_hardlink_are_not_source(tmp_path):
    photo = source(tmp_path, Image.new("RGB", (1, 1)))
    original = tmp_path / photo.source_ref
    original.rename(tmp_path / "outside")
    original.symlink_to(tmp_path / "outside")
    with pytest.raises(NailProcessingError):
        NailImageStore(tmp_path).read_rgb(photo, DecodeProfile(10000, 100))
    original.unlink()
    os.link(tmp_path / "outside", original)
    with pytest.raises(NailProcessingError):
        NailImageStore(tmp_path).read_rgb(photo, DecodeProfile(10000, 100))


@pytest.mark.parametrize("limits", [(1, 100), (10000, 1)])
def test_source_and_pixel_caps(tmp_path, limits):
    photo = source(tmp_path, Image.new("RGB", (2, 2)))
    with pytest.raises(NailProcessingError):
        NailImageStore(tmp_path).read_rgb(photo, DecodeProfile(*limits))


def test_derivative_private_owned_cleanup(tmp_path):
    tmp_path.chmod(0o700)
    store = NailImageStore(tmp_path)
    mask = BinaryMask(1, 1, b"\xff")
    crop = RegionCrop(1, (0.0, 0.0, 1.0, 1.0), (0, 0, 1, 1), mask, RgbImage(1, 1, b"abc"))
    photo = ProcessedPhoto(1, "a" * 64, "OK", (crop,))
    refs = store.write_derivatives("b" * 32, photo)
    assert refs is not None
    assert len(refs) == 1
    path = tmp_path / refs[0]
    assert path.stat().st_mode & 0o777 == 0o600
    assert (
        store.read_rgb(
            PhotoInput(1, refs[0], hashlib.sha256(path.read_bytes()).hexdigest()),
            DecodeProfile(10000, 100),
        ).pixels
        == b"abc"
    )
    other = tmp_path / ("c" * 32)
    other.write_bytes(b"untouched")
    other.chmod(0o600)
    with pytest.raises(NailProcessingError):
        store.cleanup((other.name,))
    assert other.read_bytes() == b"untouched"
    store.cleanup(refs)
    assert not path.exists()


def test_photo_and_limits_validation():
    with pytest.raises(NailProcessingError):
        PhotoInput(True, "a" * 32, "a" * 64)
    with pytest.raises(NailProcessingError):
        PhotoInput(1, "a" * 32, "bad")
    with pytest.raises(NailProcessingError):
        DecodeProfile(0, 10)
    with pytest.raises(FrozenInstanceError):
        PhotoInput(1, "a" * 32, "a" * 64).source_ref = "b" * 32


def test_derivative_failure_rolls_back_only_owned_files(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    existing = tmp_path / ("e" * 32)
    existing.write_bytes(b"keep")
    existing.chmod(0o600)
    store = NailImageStore(tmp_path)
    crop = RegionCrop(
        1, (0.0, 0.0, 1.0, 1.0), (0, 0, 1, 1), BinaryMask(1, 1, b"\xff"), RgbImage(1, 1, b"abc")
    )
    second = RegionCrop(2, crop.detector_box_xyxy, crop.crop_box_xyxy, crop.mask, crop.rgb_crop)
    photo = ProcessedPhoto(1, "a" * 64, "OK", (crop, second))
    save = Image.Image.save
    calls = 0

    def fail_second(image, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return save(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", fail_second)
    with pytest.raises(NailProcessingError):
        store.write_derivatives("b" * 32, photo)
    assert tuple(tmp_path.iterdir()) == (existing,)


def test_cleanup_does_not_delete_replaced_derivative(tmp_path):
    tmp_path.chmod(0o700)
    store = NailImageStore(tmp_path)
    crop = RegionCrop(
        1, (0.0, 0.0, 1.0, 1.0), (0, 0, 1, 1), BinaryMask(1, 1, b"\xff"), RgbImage(1, 1, b"abc")
    )
    refs = store.write_derivatives("b" * 32, ProcessedPhoto(1, "a" * 64, "OK", (crop,)))
    assert refs is not None
    path = tmp_path / refs[0]
    path.rename(tmp_path / "original")
    path.write_bytes(b"keep")
    path.chmod(0o600)
    with pytest.raises(NailProcessingError):
        store.cleanup(refs)
    assert path.read_bytes() == b"keep"


def test_mask_and_crop_artifacts_manifest_supports_new_store_resume(tmp_path):
    from product_search.search.nail_contracts import RegionArtifacts

    tmp_path.chmod(0o700)
    store = NailImageStore(tmp_path, max_manifest_bytes=10000)
    crop = RegionCrop(
        1, (0.0, 0.0, 1.0, 1.0), (0, 0, 1, 1), BinaryMask(1, 1, b"\xff"), RgbImage(1, 1, b"abc")
    )
    artifacts = store.write_region_artifacts("b" * 32, ProcessedPhoto(1, "a" * 64, "OK", (crop,)))
    assert artifacts is not None and isinstance(artifacts[0], RegionArtifacts)
    mask_path = tmp_path / artifacts[0].mask_ref
    with Image.open(mask_path) as mask:
        assert mask.mode == "L" and mask.tobytes() == b"\xff"
    assert (
        hashlib.sha256((tmp_path / artifacts[0].crop_ref).read_bytes()).hexdigest()
        == artifacts[0].crop_sha256
    )
    fresh = NailImageStore(tmp_path, max_manifest_bytes=10000)
    fresh.verify_artifacts("b" * 32, artifacts, DecodeProfile(10000, 100))
    mask_path.write_bytes(b"corrupt")
    with pytest.raises(NailProcessingError):
        fresh.verify_artifacts("b" * 32, artifacts, DecodeProfile(10000, 100))


def test_artifact_manifest_does_not_accept_foreign_files(tmp_path):
    from product_search.search.nail_contracts import RegionArtifacts

    tmp_path.chmod(0o700)
    unrelated = tmp_path / ("a" * 32)
    unrelated.write_bytes(b"keep")
    unrelated.chmod(0o600)
    with pytest.raises(NailProcessingError):
        NailImageStore(tmp_path, max_manifest_bytes=10000).verify_artifacts(
            "b" * 32,
            (RegionArtifacts(1, unrelated.name, unrelated.name, "c" * 64),),
            DecodeProfile(10000, 100),
        )
    assert unrelated.read_bytes() == b"keep"


def test_crashed_artifact_writer_cleanup_uses_persisted_ownership_only(tmp_path):
    import subprocess
    import sys

    tmp_path.chmod(0o700)
    unrelated = tmp_path / ("a" * 32)
    unrelated.write_bytes(b"keep")
    unrelated.chmod(0o600)
    script = """import os,sys
from pathlib import Path
from PIL import Image
from product_search.infrastructure.nail_image_store import NailImageStore
from product_search.search.nail_contracts import BinaryMask,RgbImage,RegionCrop,ProcessedPhoto
store=NailImageStore(Path(sys.argv[1]),max_manifest_bytes=10000)
Image.Image.save=lambda *args,**kwargs:os._exit(7)
crop=RegionCrop(1,(0.,0.,1.,1.),(0,0,1,1),BinaryMask(1,1,b'\\xff'),RgbImage(1,1,b'abc'))
store.write_region_artifacts('b'*32,ProcessedPhoto(1,'c'*64,'OK',(crop,)))
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", script, str(tmp_path)], capture_output=True, text=True, check=False
    )
    assert child.returncode == 7, child.stderr
    fresh = NailImageStore(tmp_path, max_manifest_bytes=10000)
    assert fresh.cleanup_orphans("b" * 32, ()) == 1
    assert unrelated.read_bytes() == b"keep"
    assert not tuple(tmp_path.glob(".*.tmp"))


def test_import_source_maps_private_copy_and_preserves_original(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir(mode=0o700)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    path = inputs / "input.png"
    Image.new("RGB", (1, 1), (1, 2, 3)).save(path)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    store = NailImageStore(runtime)
    imported = store.import_source(inputs, path, 10000)
    assert imported is not None
    ref, actual = imported
    assert actual == checksum
    assert (runtime / ref).stat().st_mode & 0o777 == 0o600
    assert store.read_rgb(PhotoInput(1, ref, actual), DecodeProfile(10000, 100)).pixels == bytes(
        [1, 2, 3]
    )
    store.cleanup((ref,))
    assert path.is_file()


@pytest.mark.parametrize("kind", ["outside", "symlink", "too-large"])
def test_import_source_rejects_escape_symlink_or_limit(tmp_path, kind):
    inputs = tmp_path / "inputs"
    inputs.mkdir(mode=0o700)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.write_bytes(b"bytes")
    path = inputs / "input.png"
    if kind == "symlink":
        path.symlink_to(outside)
    elif kind == "outside":
        path = outside
    else:
        path.write_bytes(b"bytes")
    with pytest.raises(NailProcessingError):
        NailImageStore(runtime).import_source(inputs, path, 1 if kind == "too-large" else 100)
    assert not tuple(runtime.iterdir())
