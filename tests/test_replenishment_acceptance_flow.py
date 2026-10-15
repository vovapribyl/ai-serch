"""Remaining B1 acceptance scenarios; real receipts and OS, synthetic ML only."""

import io
from dataclasses import replace

import pytest

from product_search.infrastructure.replenishment_cli import OwnerDispatcher, main
from product_search.infrastructure.replenishment_repository import digest, inventory_payload
from product_search.search.replenishment_contracts import SelectedPhoto
from tests.test_replenishment_flow import command
from tests.test_replenishment_flow import flow as flow  # noqa: PLC0414 -- pytest fixture
from tests.test_replenishment_postgres_integration import db as db  # noqa: PLC0414


def test_seven_photos_wait_for_explicit_second_batch_and_summary_explains_waiting(flow, db):
    app, pkg, products, _, events, _ = flow
    products = (
        replace(
            products[0],
            photos=tuple(SelectedPhoto(i, f"synthetic-{i}", "a" * 64, 100) for i in range(1, 8)),
        ),
    )
    pkg = replace(pkg, input_set_sha=digest(inventory_payload(products)))
    dispatcher = OwnerDispatcher(app, role="OWNER")
    first = dispatcher.handle(command(pkg, products))
    assert first["status"] == "OK"
    summary = first["summary"]
    assert len(summary["selected_photo_refs"]) == 5 and summary["publications"] == []
    assert summary["products"][0]["state"] == "WAITING_PHOTOS"
    assert len(summary["products"][0]["remaining_photo_refs"]) == 2
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 20
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 0
    events.clear()
    second = dispatcher.handle(command(pkg, (replace(products[0], expected_head_version=1),)))
    assert second["status"] == "OK"
    assert len(second["summary"]["selected_photo_refs"]) == 2
    assert second["summary"]["revision_refs"] == summary["revision_refs"]
    assert second["summary"]["products"][0]["state"] == "PUBLISHED"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 28
        assert conn.execute("SELECT count(*) FROM revision_vectors").fetchone()[0] == 21
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 1


def test_summary_distinguishes_no_ready_photo_from_publication_failure(flow):
    app, pkg, products, _, _, workers = flow
    workers["fail"] = "all"
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "OK"
    assert answer["summary"]["products"] == [
        {
            "revision_ref": answer["summary"]["revision_refs"][0],
            "state": "NOT_PUBLISHABLE",
            "remaining_photo_refs": [],
        }
    ]


def test_changed_selected_input_creates_new_revision_and_keeps_old_snapshot(flow, db):
    app, pkg, products, _, _, _ = flow
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))["summary"]
    changed = (
        replace(
            products[0],
            expected_head_version=1,
            photos=(replace(products[0].photos[0], input_sha="c" * 64), products[0].photos[1]),
        ),
    )
    pkg = replace(pkg, input_set_sha=digest(inventory_payload(changed)))
    second = OwnerDispatcher(app, role="OWNER").handle(command(pkg, changed))["summary"]
    assert second["revision_refs"] != first["revision_refs"]
    assert second["publications"][0]["state"] == "SUCCEEDED"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM catalog_snapshots").fetchone()[0] == 2
        assert (
            str(
                conn.execute(
                    "SELECT revision_id FROM catalog_snapshot_members WHERE snapshot_id=%s",
                    (first["publications"][0]["snapshot_ref"],),
                ).fetchone()[0]
            )
            == first["revision_refs"][0]
        )


def test_migration_downgrade_and_reupgrade_preserve_synthetic_legacy_records(flow, db):
    app, pkg, products, _, _, _ = flow
    result = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert result["status"] == "OK"
    with db.connect() as conn:
        before = conn.execute(
            "SELECT id,product_id,image_sha256 FROM product_records ORDER BY id"
        ).fetchall()
    db.migrate("0009_nail_search_v1", direction="downgrade")
    with db.connect() as conn:
        assert conn.execute("SELECT to_regclass('product_revisions')").fetchone()[0] is None
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "0009_nail_search_v1"
        )
        assert (
            conn.execute(
                "SELECT id,product_id,image_sha256 FROM product_records ORDER BY id"
            ).fetchall()
            == before
        )
    db.migrate()
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM product_revisions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM active_catalog_snapshots").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT id,product_id,image_sha256 FROM product_records ORDER BY id"
            ).fetchall()
            == before
        )


from tests.test_replenishment_postgres_integration import fixture_inventory
from tests.test_replenishment_retry import publication_fault


def test_independent_failed_product_does_not_block_successful_product(flow, db):
    from product_search.search.replenishment_contracts import PhotoProcessingError

    app, pkg, products, _, _, _ = flow
    with db.connect() as conn:
        products += fixture_inventory(conn, 1)
    pkg = replace(pkg, input_set_sha=digest(inventory_payload(products)))
    factory = app.worker_factory

    def make(*args):
        worker = factory(*args)
        process = worker.process

        def per_product(photo, *rest):
            if photo.revision_ref == app.queue[0].revision_ref:
                raise PhotoProcessingError("synthetic-photo-error")
            return process(photo, *rest)

        worker.process = per_product
        return worker

    app.worker_factory = make
    result = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert result["status"] == "OK"
    assert [p["state"] for p in result["summary"]["products"]] == ["NOT_PUBLISHABLE", "PUBLISHED"]
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 1


def test_changed_profile_creates_new_revision_without_replacing_incompatible_active(flow, db):
    app, pkg, products, _, _, _ = flow
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))["summary"]
    app.profile = {**app.profile, "crop_version": "synthetic-white-v2"}
    pkg = replace(pkg, semantic_profile_sha=digest(app.profile))
    second = OwnerDispatcher(app, role="OWNER").handle(
        command(pkg, (replace(products[0], expected_head_version=1),))
    )
    assert second["status"] == "REFUSED" and second["reason"] == "PROFILE_MISMATCH"
    with db.connect() as conn:
        head = conn.execute(
            "SELECT h.current_revision_id,r.semantic_profile_sha FROM replenishment_product_heads h JOIN product_revisions r ON r.id=h.current_revision_id"
        ).fetchone()
        assert str(head[0]) != first["revision_refs"][0] and head[1] == pkg.semantic_profile_sha
        assert (
            str(conn.execute("SELECT snapshot_id FROM active_catalog_snapshots").fetchone()[0])
            == first["publications"][0]["snapshot_ref"]
        )


@pytest.mark.parametrize("corrupt", [False, True])
def test_cli_summary_shows_publication_failure_and_refuses_extra_product_fields(flow, corrupt):
    app, pkg, products, _, _, _ = flow
    publication_fault(app)
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["summary"]["products"][0]["state"] == "PUBLICATION_FAILED"
    if corrupt:
        answer["summary"]["products"][0]["raw_path"] = "SECRET/private"
    out = io.StringIO()
    code = main(
        ["status", "--run", answer["summary"]["run_ref"]],
        client=lambda _: answer,
        stdout=out,
        stderr=io.StringIO(),
    )
    assert code == 5
    assert "SECRET" not in out.getvalue()
    if not corrupt:
        assert "PUBLICATION_FAILED" in out.getvalue()
