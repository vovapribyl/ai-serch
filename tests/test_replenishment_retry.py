"""Explicit retry uses new revisions, preserves published history and never reruns ML for publication."""

from dataclasses import asdict, replace

import pytest

from product_search.infrastructure.replenishment_cli import OwnerDispatcher
from product_search.search.replenishment_contracts import ReplenishmentError
from tests.test_replenishment_flow import command
from tests.test_replenishment_flow import flow as flow  # noqa: PLC0414 -- pytest fixture
from tests.test_replenishment_postgres_integration import db as db  # noqa: PLC0414


def failed_photo(flow):
    app, pkg, products, _, events, workers = flow
    workers["fail"] = True
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))["summary"]
    events.clear()
    workers.clear()
    return first


def photo_request(pkg, summary, version=1):
    return {
        "package": asdict(replace(pkg, scope="RETRY_PHOTO")),
        "revision": summary["revision_refs"][0],
        "photo": summary["selected_photo_refs"][0],
        "expected_version": version,
    }


def test_retry_photo_creates_new_head_and_preserves_published_snapshot(flow, db):
    app, pkg, _, _, events, _ = flow
    first = failed_photo(flow)
    with db.connect() as conn:
        version = conn.execute("SELECT version FROM replenishment_product_heads").fetchone()[0]
        old_cp = conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0]
    result = app.retry_photo(**photo_request(pkg, first, version))
    assert result["revision_refs"] != first["revision_refs"]
    assert [o for _, o in result["outcomes"]] == ["OK"]
    assert result["publications"][0]["state"] == "SUCCEEDED"
    assert len([e for e in events if e[0] == "open"]) == 4
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == old_cp + 4
        assert conn.execute(
            "SELECT outcome FROM revision_photos WHERE revision_id=%s ORDER BY ordinal",
            (first["revision_refs"][0],),
        ).fetchall() == [("ERROR",), ("OK",)]
        assert conn.execute(
            "SELECT outcome FROM revision_photos WHERE revision_id=%s ORDER BY ordinal",
            (result["revision_refs"][0],),
        ).fetchall() == [("OK",), ("OK",)]
        assert conn.execute(
            "SELECT revision_id FROM catalog_snapshot_members WHERE snapshot_id=%s",
            (first["publications"][0]["snapshot_ref"],),
        ).fetchone()[0].hex == first["revision_refs"][0].replace("-", "")
        assert (
            conn.execute("SELECT version FROM replenishment_product_heads").fetchone()[0]
            == version + 1
        )


def test_stale_retry_is_refused_before_epoch_or_workers_change(flow, db):
    app, pkg, _, _, events, _ = flow
    first = failed_photo(flow)
    epoch = app.supervisor.owner.epoch
    with pytest.raises(ReplenishmentError, match="VERSION_CONFLICT"):
        app.retry_photo(**photo_request(pkg, first, 999))
    assert events == [] and app.supervisor.owner.epoch == epoch


def publication_fault(app, *, unknown=False):
    factory = app.repository_factory

    def make(pkg, end):
        repo = factory(pkg, end)
        activate = repo._activate_publication

        def fail(*args):
            if pkg.scope == "START":
                if unknown:
                    activate(*args)
                    raise ReplenishmentError("COMMIT_UNKNOWN")
                raise ReplenishmentError("ACTIVE_CONFLICT")
            return activate(*args)

        repo._activate_publication = fail
        return repo

    app.repository_factory = make


def test_retry_failed_publication_reuses_ready_and_does_not_warm_models(flow, db):
    app, pkg, products, _, events, _ = flow
    publication_fault(app)
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))["summary"]
    assert first["publications"][0]["state"] == "FAILED"
    events.clear()
    result = app.retry_publication(
        package=asdict(replace(pkg, scope="RETRY_PUBLICATION")), revision=first["revision_refs"][0]
    )
    assert events == [] and result["publications"][0]["state"] == "SUCCEEDED"
    with db.connect() as conn:
        assert conn.execute("SELECT state FROM publication_attempts ORDER BY state").fetchall() == [
            ("FAILED",),
            ("SUCCEEDED",),
        ]
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 8


def test_unknown_publication_checks_receipt_without_second_publication(flow, db):
    app, pkg, products, _, events, _ = flow
    publication_fault(app, unknown=True)
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))["summary"]
    events.clear()
    result = app.retry_publication(
        package=asdict(replace(pkg, scope="RETRY_PUBLICATION")), revision=first["revision_refs"][0]
    )
    assert result["publications"][0]["state"] == "SUCCEEDED" and events == []
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM publication_attempts").fetchone()[0] == 1


def test_only_selected_error_retries_and_a_second_manual_retry_reuses_first_result(flow, db):
    app, pkg, products, _, events, workers = flow
    workers["fail"] = "all"
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))["summary"]
    workers.clear()
    events.clear()
    result = app.retry_photo(**photo_request(pkg, first, 1))
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id,outcome FROM revision_photos WHERE revision_id=%s ORDER BY ordinal",
            (result["revision_refs"][0],),
        ).fetchall()
        assert [r[1] for r in rows] == ["OK", "ERROR"]
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 4
        version = conn.execute("SELECT version FROM replenishment_product_heads").fetchone()[0]
    events.clear()
    second = app.retry_photo(
        package=asdict(replace(pkg, scope="RETRY_PHOTO")),
        revision=result["revision_refs"][0],
        photo=str(rows[1][0]),
        expected_version=version,
    )
    assert second["publications"][0]["state"] == "SUCCEEDED"
    with db.connect() as conn:
        assert conn.execute(
            "SELECT outcome FROM revision_photos WHERE revision_id=%s ORDER BY ordinal",
            (second["revision_refs"][0],),
        ).fetchall() == [("OK",), ("OK",)]
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 8
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 2


def test_unknown_rollback_is_confirmed_only_after_new_owner_then_retries_without_ml(flow, db):
    app, pkg, products, _, events, _ = flow
    factory = app.repository_factory
    old = []

    def make(package, end):
        repo = factory(package, end)
        if package.scope == "START":
            old.append(repo)

            def uncertain(*args):
                raise ReplenishmentError("COMMIT_UNKNOWN")

            repo._activate_publication = uncertain
        return repo

    app.repository_factory = make
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert first["status"] == "UNKNOWN"
    owner = app.supervisor.owner
    revision = first["summary"]["revision_refs"][0]
    events.clear()
    result = app.retry_publication(
        package=asdict(replace(pkg, scope="RETRY_PUBLICATION")), revision=revision
    )
    assert result["publications"][0]["state"] == "SUCCEEDED" and events == []
    with db.connect() as conn:
        assert conn.execute(
            "SELECT state,error_code FROM publication_attempts WHERE run_id=%s", (owner.run_ref,)
        ).fetchone() == ("FAILED", "RECONCILED_ROLLBACK")
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 1


def test_retry_head_race_rolls_back_clone_and_preserves_active_catalog(flow, db):
    app, pkg, _, _, events, _ = flow
    first = failed_photo(flow)
    factory = app.repository_factory

    def make(package, end):
        repo = factory(package, end)
        issue = repo.issue_owner

        def race(*args):
            owner = issue(*args)
            with db.connect() as conn:
                conn.execute("UPDATE replenishment_product_heads SET version=version+1")
            return owner

        repo.issue_owner = race
        return repo

    app.repository_factory = make
    with pytest.raises(ReplenishmentError, match="VERSION_CONFLICT"):
        app.retry_photo(**photo_request(pkg, first, 1))
    assert events == []
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM product_revisions").fetchone()[0] == 1
        assert (
            str(conn.execute("SELECT snapshot_id FROM active_catalog_snapshots").fetchone()[0])
            == first["publications"][0]["snapshot_ref"]
        )


def test_retry_refuses_successful_photo_without_mutating_owner(flow, db):
    app, pkg, products, _, events, _ = flow
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))["summary"]
    epoch = app.supervisor.owner.epoch
    events.clear()
    with pytest.raises(ReplenishmentError, match="INVALID_SCOPE"):
        app.retry_photo(**photo_request(pkg, first, 1))
    assert events == [] and app.supervisor.owner.epoch == epoch
