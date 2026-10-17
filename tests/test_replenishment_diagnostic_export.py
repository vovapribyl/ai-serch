"""Partial probe data survives validation failures without starting PostgreSQL or ML."""

import json
import sqlite3

import pytest


@pytest.fixture
def catalog():
    # Real SQL executes against the same column names; PostgreSQL/vector behaviour
    # remains covered by the native probe, not claimed by this SQLite fixture.
    with sqlite3.connect(":memory:") as connection:
        connection.executescript("""
            CREATE TABLE product_revisions(id TEXT, product_record_id INTEGER);
            CREATE TABLE revision_photos(id TEXT, revision_id TEXT, ordinal INTEGER,
                                         input_sha TEXT, outcome TEXT);
            CREATE TABLE revision_regions(revision_photo_id TEXT, region_ordinal INTEGER,
                                          mask_ref TEXT, crop_ref TEXT, crop_sha TEXT);
            CREATE TABLE revision_vectors(revision_photo_id TEXT, region_ordinal INTEGER,
                                          model_key TEXT, vector TEXT);
            INSERT INTO product_revisions VALUES ('r1',21),('r2',22),('r3',23);
            INSERT INTO revision_photos VALUES
                ('p1','r1',1,'sha1','OK'),('p2','r2',1,'sha2','NO_NAILS'),
                ('p3','r3',1,'sha3','ERROR');
            INSERT INTO revision_regions VALUES ('p1',1,'mask','crop','crop-sha');
            INSERT INTO revision_vectors VALUES
                ('p1',1,'openclip_b32','[1,0]'),('p1',1,'dinov2_b14','[0,1]'),
                ('p1',1,'siglip2_b16_224','[1,0]');
        """)
        yield connection


def test_partial_export_is_durable_before_failed_verification(tmp_path, catalog):
    from product_search.infrastructure.replenishment_diagnostic_export import (
        export_before_verification,
    )

    tmp_path.chmod(0o700)
    destination = tmp_path / "partial.json"
    failure = AssertionError("batch has an ERROR photo")

    def verify():
        saved = json.loads(destination.read_text())
        assert saved["photo_outcomes"] == [
            ["p1", 21, "OK"],
            ["p2", 22, "NO_NAILS"],
            ["p3", 23, "ERROR"],
        ]
        assert len(saved["vectors"]) == 3
        assert saved["photos"] == [
            ["p1", 21, 1, "sha1"],
            ["p2", 22, 1, "sha2"],
            ["p3", 23, 1, "sha3"],
        ]
        assert saved["regions"] == [["p1", 1, "mask", "crop", "crop-sha"]]
        assert saved["profile"] == {"version": "test"}
        assert destination.stat().st_mode & 0o777 == 0o600
        raise failure

    with pytest.raises(AssertionError) as caught:
        export_before_verification(catalog, destination, {"version": "test"}, verify)
    assert caught.value is failure
    assert destination.is_file()
    assert catalog.execute("SELECT count(*) FROM revision_photos").fetchone() == (3,)


def test_success_returns_verification_result_and_saves_no_nails(tmp_path, catalog):
    from product_search.infrastructure.replenishment_diagnostic_export import (
        export_before_verification,
    )

    tmp_path.chmod(0o700)
    destination = tmp_path / "partial.json"
    assert export_before_verification(catalog, destination, {}, lambda: 42) == 42
    assert json.loads(destination.read_text())["photo_outcomes"][-1] == ["p3", 23, "ERROR"]


def test_failed_export_keeps_previous_file_and_never_verifies(tmp_path, catalog):
    from product_search.infrastructure.replenishment_diagnostic_export import (
        export_before_verification,
    )

    tmp_path.chmod(0o700)
    destination = tmp_path / "partial.json"
    destination.write_text("previous verified export")
    destination.chmod(0o600)

    def must_not_verify():
        pytest.fail("Verification must not run after export failure")

    with pytest.raises(TypeError):
        export_before_verification(catalog, destination, {"invalid": object()}, must_not_verify)
    assert destination.read_text() == "previous verified export"
    assert list(tmp_path.iterdir()) == [destination]


from tests.test_replenishment_postgres_integration import db as postgres_db  # noqa: F401


def test_export_reads_real_postgres_partial_state(postgres_db, tmp_path):  # noqa: F811
    from product_search.infrastructure.replenishment_diagnostic_export import (
        export_before_verification,
    )
    from tests.test_replenishment_postgres_integration import seed

    postgres_db.migrate()
    tmp_path.chmod(0o700)
    destination = tmp_path / "postgres-partial.json"
    with postgres_db.connect() as connection:
        _, product, _, photo, _ = seed(connection)
        connection.execute(
            "UPDATE revision_photos SET outcome='ERROR',error_code='PHOTO_ERROR' WHERE id=%s",
            (photo,),
        )

    def reject_partial():
        assert json.loads(destination.read_text())["photo_outcomes"] == [
            [str(photo), product, "ERROR"]
        ]
        raise AssertionError("PHOTO_NOT_OK")

    with postgres_db.connect() as connection, pytest.raises(AssertionError, match="PHOTO_NOT_OK"):
        export_before_verification(connection, destination, {}, reject_partial)
    assert json.loads(destination.read_text())["vectors"] == []
