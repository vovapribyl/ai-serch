import hashlib
import io

import pytest
from PIL import Image

from product_search.infrastructure.nail_build_runner import BuildStop


def fixture_image(path, size=(4, 3), mode="RGB", color="red", exif=None):
    stream = io.BytesIO()
    Image.new(mode, size, color).save(stream, format="PNG", **({"exif": exif} if exif else {}))
    data = stream.getvalue()
    path.write_bytes(data)
    path.chmod(0o600)
    return data, hashlib.sha256(data).hexdigest()


def test_copy_preserves_bytes_source_metadata_and_private_output(tmp_path):
    from product_search.infrastructure.nail_input_preparation import prepare_input

    source = tmp_path / "original.png"
    data, digest = fixture_image(source)
    before = source.stat()
    result = prepare_input(source, tmp_path / "copy.png", digest)
    assert (tmp_path / "copy.png").read_bytes() == data
    after = source.stat()
    assert (before.st_ino, before.st_mtime_ns, before.st_ctime_ns, before.st_mode) == (
        after.st_ino,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_mode,
    )
    assert result["original_sha256"] == result["input_sha256"] == digest
    assert (
        result["transformed"] is False and (tmp_path / "copy.png").stat().st_mode & 0o777 == 0o600
    )


def test_known_oversize_becomes_rgb1536_white_alpha_with_new_hash(tmp_path):
    from product_search.infrastructure.nail_input_preparation import prepare_input

    source = tmp_path / "original.png"
    data, digest = fixture_image(source, (1802, 1802), "RGBA", (255, 0, 0, 0))
    result = prepare_input(source, tmp_path / "prepared.png", digest, transform=True)
    with Image.open(tmp_path / "prepared.png") as image:
        assert (
            image.size == (1536, 1536)
            and image.mode == "RGB"
            and image.getpixel((50, 50)) == (255, 255, 255)
        )
        assert "exif" not in image.info
    assert source.read_bytes() == data and result["original_sha256"] == digest
    assert result["input_sha256"] != digest and result["transformed"] is True


def test_transform_applies_exif_orientation_before_resize(tmp_path):
    from product_search.infrastructure.nail_input_preparation import prepare_input

    image = Image.new("RGB", (1802, 1802), "black")
    image.paste("red", (0, 0, 901, 1802))
    exif = Image.Exif()
    exif[274] = 6
    source = tmp_path / "oriented.png"
    image.save(source, exif=exif)
    source.chmod(0o600)
    prepare_input(
        source,
        tmp_path / "copy.png",
        hashlib.sha256(source.read_bytes()).hexdigest(),
        transform=True,
    )
    with Image.open(tmp_path / "copy.png") as output:
        assert output.getpixel((100, 100)) == (255, 0, 0) and output.getpixel((100, 1400)) == (
            0,
            0,
            0,
        )


@pytest.mark.parametrize(
    "problem", ["hash", "symlink", "existing", "wrong_dimensions", "pixel_cap"]
)
def test_invalid_source_or_destination_stops_without_overwrite(tmp_path, problem):
    from product_search.infrastructure.nail_input_preparation import prepare_input

    source = tmp_path / "original.png"
    data, digest = fixture_image(source, (1802, 1802) if problem == "pixel_cap" else (4, 3))
    dest = tmp_path / "copy.png"
    if problem == "hash":
        digest = "0" * 64
    if problem == "symlink":
        link = tmp_path / "link.png"
        link.symlink_to(source)
        source = link
    if problem == "existing":
        dest.write_bytes(b"keep")
        dest.chmod(0o600)
    with pytest.raises(BuildStop):
        prepare_input(source, dest, digest, transform=problem == "wrong_dimensions")
    assert source.read_bytes() == data
    assert dest.read_bytes() == b"keep" if problem == "existing" else not dest.exists()
