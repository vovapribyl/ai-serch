"""Large private exports keep file/JSON guards and the small IPC descriptor cap."""

import json

import pytest

from product_search.infrastructure.nail_build_composition import publish_private_json
from product_search.infrastructure.replenishment_cli import JSON_LIMIT, CliError, private_json
from product_search.infrastructure.replenishment_deferred_photos import export_deferred_batch, main
from tests.test_replenishment_diagnostic_export import catalog as catalog  # noqa: PLC0414


@pytest.fixture
def large_catalog(catalog):
    catalog.execute("DELETE FROM revision_regions")
    catalog.execute("DELETE FROM revision_vectors")
    for ordinal in range(1, 9):
        catalog.execute(
            "INSERT INTO revision_regions VALUES ('p1',?,'mask','crop','sha')", (ordinal,)
        )
        for key, dim in [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)]:
            catalog.execute(
                "INSERT INTO revision_vectors VALUES ('p1',?,?,?)",
                (ordinal, key, json.dumps([1 / dim**0.5] * dim)),
            )
    return catalog


@pytest.fixture
def deferred_path(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "deferred.json"
    # The writer permits up to 2 MiB, independently of the IPC descriptor cap.
    publish_private_json(
        path,
        {
            "schema_version": 1,
            "photos": [
                {
                    "photo_ref": "p3",
                    "input_sha": "sha3",
                    "reason": "REGION_COUNT_LIMIT",
                    "source_ref": "private-source-" + "x" * 70_000,
                }
            ],
        },
    )
    assert JSON_LIMIT < path.stat().st_size < 2 * 1024**2
    return path


def test_large_export_and_deferred_list_are_verified_after_sql_export(
    tmp_path, large_catalog, deferred_path
):
    path = tmp_path / "export.json"
    summary = export_deferred_batch(large_catalog, path, {}, deferred_path)
    assert path.stat().st_size > JSON_LIMIT
    assert summary == {
        "ready": 1,
        "deferred": 1,
        "no_nails": 1,
        "other_errors": 0,
        "pending": 0,
        "total": 3,
    }
    saved = json.loads(path.read_text())
    assert len(saved["regions"]) == 8 and len(saved["vectors"]) == 24


def test_report_reads_large_catalog_and_list_without_revealing_source_ids(
    tmp_path, large_catalog, deferred_path, capsys
):
    from product_search.infrastructure.replenishment_diagnostic_export import (
        export_before_verification,
    )

    path = tmp_path / "export.json"
    export_before_verification(large_catalog, path, {}, lambda: None)
    assert path.stat().st_size > JSON_LIMIT
    assert main(["--catalog", str(path), "--deferred", str(deferred_path)]) == 0
    output = capsys.readouterr().out
    assert "private-source" not in output and "p3" not in output
    assert json.loads(output)["ready"] == json.loads(output)["deferred"] == 1


def test_default_descriptor_reader_still_rejects_large_private_files(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "descriptor.json"
    publish_private_json(path, {"padding": "x" * JSON_LIMIT})
    with pytest.raises(CliError):
        private_json(path)


@pytest.mark.parametrize(
    "invalid",
    [
        "mode",
        "parent_mode",
        "symlink",
        "hardlink",
        "duplicate_keys",
        "nonfinite",
        "malformed",
        "utf8",
        "oversize",
    ],
)
def test_catalog_reader_preserves_private_file_and_strict_json_guards(tmp_path, invalid):
    import os

    from product_search.infrastructure.replenishment_diagnostic_export import (
        CATALOG_EXPORT_MAX_BYTES,
        read_catalog_export,
    )

    tmp_path.chmod(0o700)
    path = tmp_path / "export.json"
    publish_private_json(path, {"photos": [], "photo_outcomes": []})
    if invalid == "mode":
        path.chmod(0o644)
    elif invalid == "parent_mode":
        tmp_path.chmod(0o755)
    elif invalid == "symlink":
        target = tmp_path / "target.json"
        path.rename(target)
        path.symlink_to(target)
    elif invalid == "hardlink":
        os.link(path, tmp_path / "second-link.json")
    elif invalid == "duplicate_keys":
        path.write_bytes(b'{"photos": [], "photos": []}')
    elif invalid == "nonfinite":
        path.write_bytes(b'{"score": NaN}')
    elif invalid == "malformed":
        path.write_bytes(b"{")
    elif invalid == "utf8":
        path.write_bytes(b"\xff")
    elif invalid == "oversize":
        with path.open("wb") as stream:
            stream.truncate(CATALOG_EXPORT_MAX_BYTES + 1)
    with pytest.raises(CliError):
        read_catalog_export(path)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, None])
def test_private_reader_refuses_nonpositive_or_noninteger_limits(tmp_path, limit):
    tmp_path.chmod(0o700)
    path = tmp_path / "private.json"
    publish_private_json(path, {})
    with pytest.raises(CliError):
        private_json(path, max_bytes=limit)


def test_reader_accepts_exact_cap_and_refuses_growth_after_stat(tmp_path, monkeypatch):
    import os

    tmp_path.chmod(0o700)
    path = tmp_path / "private.json"
    path.write_bytes(b"{}" + b" " * 126)
    path.chmod(0o600)
    assert private_json(path, max_bytes=128) == {}
    original = os.fstat

    def grow_after_stat(fd):
        observed = original(fd)
        with path.open("ab") as stream:
            stream.write(b" ")
        return observed

    monkeypatch.setattr(os, "fstat", grow_after_stat)
    with pytest.raises(CliError):
        private_json(path, max_bytes=128)


def test_report_refuses_deferred_list_above_its_writer_cap(tmp_path, capsys):
    from product_search.infrastructure.replenishment_deferred_photos import DEFERRED_LIST_MAX_BYTES

    tmp_path.chmod(0o700)
    catalog = tmp_path / "catalog.json"
    deferred = tmp_path / "deferred.json"
    publish_private_json(catalog, {"photos": [], "photo_outcomes": []})
    with deferred.open("wb") as stream:
        stream.truncate(DEFERRED_LIST_MAX_BYTES + 1)
    deferred.chmod(0o600)
    assert main(["--catalog", str(catalog), "--deferred", str(deferred)]) == 1
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED"}
