"""Manual resume reuses committed files; no automatic ERROR retry or next batch."""

from dataclasses import asdict, replace

from product_search.infrastructure.replenishment_cli import OwnerDispatcher
from product_search.search.replenishment_contracts import ReplenishmentError
from tests.test_replenishment_flow import command
from tests.test_replenishment_flow import flow as flow  # noqa: PLC0414 -- pytest fixture
from tests.test_replenishment_postgres_integration import (
    db as db,  # noqa: PLC0414 -- pytest fixture
)


def resume(app, pkg, old):
    return OwnerDispatcher(app, role="OWNER").handle(
        {
            "schema_version": 1,
            "action": "resume",
            "run": old,
            "package": asdict(replace(pkg, scope="RESUME")),
        }
    )


def lost_ack(app):
    factory = app.repository_factory

    def make(p, end):
        repo = factory(p, end)
        commit = repo.commit_checkpoint

        def uncertain(work, output, owner):
            receipt = commit(work, output, owner)
            if p.scope == "START" and work.model_key == "siglip2_b16_224":
                raise ReplenishmentError("COMMIT_UNKNOWN")
            return receipt

        repo.commit_checkpoint = uncertain
        return repo

    app.repository_factory = make


def test_unknown_commit_is_reconciled_without_repeating_completed_models(flow, db):
    app, pkg, products, _, events, _ = flow
    lost_ack(app)
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert first["status"] == "UNKNOWN"
    old = app.supervisor.owner.run_ref
    events.clear()
    answer = resume(app, pkg, old)
    assert answer["status"] == "OK"
    assert [e[1:] for e in events if e[0] == "open"] == [("embedding", "siglip2_b16_224")]
    assert [o for _, o in answer["summary"]["outcomes"]] == ["OK", "OK"]
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 8
        assert (
            conn.execute("SELECT status FROM replenishment_runs WHERE id=%s", (old,)).fetchone()[0]
            == "INTERRUPTED"
        )


def test_damaged_checkpoint_blocks_all_model_warmups(flow):
    app, pkg, products, _, events, _ = flow
    lost_ack(app)
    OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    old = app.supervisor.owner.run_ref
    next((app.artifacts.root / "final").glob("*/vectors.json")).write_bytes(b"damaged")
    events.clear()
    answer = resume(app, pkg, old)
    assert answer["reason"] == "CHECKPOINT_INVALID" and events == []


def test_error_photos_and_published_ready_survive_resume(flow, db):
    app, pkg, products, _, events, workers = flow
    workers["fail"] = True
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    old = first["summary"]["run_ref"]
    snapshot = first["summary"]["publications"][0]["snapshot_ref"]
    events.clear()
    workers.clear()
    answer = resume(app, pkg, old)
    assert answer["status"] == "OK" and events == []
    assert [o for _, o in answer["summary"]["outcomes"]] == ["ERROR", "OK"]
    assert answer["summary"]["publications"][0]["snapshot_ref"] == snapshot
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 1


def test_unconfirmed_old_worker_refuses_resume_before_epoch_change(flow, db):
    app, pkg, products, _, events, _ = flow
    lost_ack(app)
    OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    old = app.supervisor.owner.run_ref
    epoch = app.supervisor.owner.epoch
    app.supervisor.quiesce = lambda *args: False
    events.clear()
    try:
        answer = resume(app, pkg, old)
        assert answer["status"] == "STOPPED" and events == []
        with db.connect() as conn:
            assert conn.execute("SELECT epoch FROM replenishment_owner").fetchone()[0] == epoch
    finally:
        app.supervisor.quiesce = lambda *args: True


def test_resume_keeps_frozen_five_photos_and_does_not_take_next_batch(flow, db):
    from product_search.infrastructure.replenishment_repository import digest, inventory_payload
    from product_search.search.replenishment_contracts import SelectedPhoto

    app, pkg, products, _, _events, _ = flow
    products = (
        replace(
            products[0],
            photos=tuple(SelectedPhoto(i, f"synthetic-{i}", "a" * 64, 100) for i in range(1, 8)),
        ),
    )
    pkg = replace(pkg, input_set_sha=digest(inventory_payload(products)))
    lost_ack(app)
    OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    old = app.supervisor.owner.run_ref
    selected = app.status(old)["selected_photo_refs"]
    answer = resume(app, pkg, old)
    assert answer["status"] == "OK"
    assert answer["summary"]["selected_photo_refs"] == selected and len(selected) == 5
    with db.connect() as conn:
        assert conn.execute(
            "SELECT ordinal,outcome FROM revision_photos ORDER BY ordinal"
        ).fetchall() == [(i, "OK" if i <= 5 else "PENDING") for i in range(1, 8)]
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 0


def test_interrupted_attempt_is_not_error_and_orphan_staging_is_not_reused(flow, db):
    app, pkg, products, clock, events, workers = flow
    clock.value = 0
    workers["expire"] = True
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert first["status"] == "STOPPED"
    old = first["summary"]["run_ref"]
    workers.clear()
    events.clear()
    answer = resume(app, pkg, old)
    assert answer["status"] == "OK"
    with db.connect() as conn:
        assert conn.execute(
            "SELECT state FROM stage_attempts WHERE run_id=%s", (old,)
        ).fetchall() == [("INTERRUPTED",)]
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 8


def test_profile_mismatch_is_rejected_before_resume_epoch(flow, db):
    app, pkg, products, _, events, _ = flow
    lost_ack(app)
    OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    old = app.supervisor.owner.run_ref
    epoch = app.supervisor.owner.epoch
    events.clear()
    answer = resume(app, replace(pkg, semantic_profile_sha="f" * 64), old)
    assert answer["reason"] == "PROFILE_MISMATCH" and events == []
    with db.connect() as conn:
        assert conn.execute("SELECT epoch FROM replenishment_owner").fetchone()[0] == epoch
