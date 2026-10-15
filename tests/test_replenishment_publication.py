"""B1 synthetic publication: real temporary PostgreSQL and verified fake stage files."""

import json
import time
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest

from product_search.infrastructure.replenishment_artifacts import CheckpointFiles
from product_search.infrastructure.replenishment_repository import PostgresReplenishment
from product_search.search.nail_contracts import MODEL_DIMENSIONS
from product_search.search.replenishment_contracts import PhotoOutcome, ReplenishmentError
from tests.test_replenishment_artifacts import png
from tests.test_replenishment_contracts import package
from tests.test_replenishment_postgres_integration import (
    canonical_digest,
    fixture_inventory,
    inventory_payload,
    profile_payload,
)
from tests.test_replenishment_postgres_integration import (
    db as db,  # noqa: PLC0414 -- explicit pytest fixture re-export
)


def setup(db, tmp_path, count=1, products=None, epoch=0, profile=None):
    db.migrate()
    if products is None:
        with db.connect() as conn:
            products = fixture_inventory(conn, count)
    profile = profile or profile_payload()
    pkg = package(
        input_set_sha=canonical_digest(inventory_payload(products)),
        semantic_profile_sha=canonical_digest(profile),
        max_admissions=100,
        max_vector_bytes=20000,
        max_wire_bytes=8000,
    )
    repo = PostgresReplenishment(db.connect, pkg, db.end_at, clock=time.monotonic)
    owner = repo.issue_owner("BUILD", epoch)
    repo.register_profile(owner, profile)
    refs = repo.register_inventory(owner, products)
    root = tmp_path / uuid4().hex
    root.mkdir(mode=0o700)
    return repo, owner, products, refs, CheckpointFiles(root)


def complete(repo, owner, store, photo, outcome=PhotoOutcome.OK):
    local = repo.begin_attempt(photo, "localization", "", owner)
    data = (
        {}
        if outcome == PhotoOutcome.NO_NAILS
        else {"crop-1.png": png("RGB"), "mask-1.png": png("L")}
    )
    output = store.write_staging(local, repo.package, len(data) // 2, data)
    store.verify(local, output, repo.package)
    repo.commit_checkpoint(local, output, owner)
    if outcome == PhotoOutcome.OK:
        for model, dim in MODEL_DIMENSIONS:
            work = repo.begin_attempt(photo, "embedding", model, owner)
            raw = json.dumps(
                {"model_key": model, "vectors": [{"ordinal": 1, "values": [0.25] * dim}]}
            ).encode()
            output = store.write_staging(work, repo.package, 1, {"vectors.json": raw})
            store.verify(work, output, repo.package)
            repo.commit_checkpoint(work, output, owner)
    repo.finish_photo(photo, outcome, owner)


def ready(db, tmp_path):
    repo, owner, products, refs, store = setup(db, tmp_path)
    complete(repo, owner, store, repo.read_queue(owner)[0])
    result = repo.prepare_revision(refs[0], owner, store)
    assert result is not None
    return repo, owner, products, result, store


def test_ready_materialization_reads_verified_receipts_and_exact_vectors(db, tmp_path):
    repo, owner, _, revision, store = ready(db, tmp_path)
    assert revision.revision_version == 3
    assert repo.prepare_revision(revision, owner, store) == revision
    with db.connect() as conn:
        assert conn.execute("SELECT state FROM product_revisions").fetchone() == ("READY",)
        assert conn.execute("SELECT count(*) FROM revision_regions").fetchone()[0] == 1
        assert dict(
            conn.execute("SELECT model_key,vector_dims(vector) FROM revision_vectors")
        ) == dict(MODEL_DIMENSIONS)
        vector = json.loads(
            conn.execute(
                "SELECT vector::text FROM revision_vectors WHERE model_key='dinov2_b14'"
            ).fetchone()[0]
        )
        assert vector == [0.25] * 768


def test_unfinished_selected_photo_blocks_readiness(db, tmp_path):
    repo, owner, _, refs, store = setup(db, tmp_path, 2)
    complete(repo, owner, store, repo.read_queue(owner)[0])
    with pytest.raises(ReplenishmentError, match="REVISION_INCOMPLETE"):
        repo.prepare_revision(refs[0], owner, store)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM revision_vectors").fetchone()[0] == 0


def test_no_positive_coverage_is_not_publishable(db, tmp_path):
    repo, owner, _, refs, store = setup(db, tmp_path)
    complete(repo, owner, store, repo.read_queue(owner)[0], PhotoOutcome.NO_NAILS)
    with pytest.raises(ReplenishmentError, match="NOT_PUBLISHABLE"):
        repo.prepare_revision(refs[0], owner, store)
    with db.connect() as conn:
        assert (
            conn.execute("SELECT state FROM product_revisions").fetchone()[0] == "NOT_PUBLISHABLE"
        )


def test_corrupt_confirmed_file_cannot_materialize_ready(db, tmp_path):
    repo, owner, _, refs, store = setup(db, tmp_path)
    complete(repo, owner, store, repo.read_queue(owner)[0])
    next((store.root / "final").glob("*/vectors.json")).write_bytes(b"corrupt")
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_INVALID"):
        repo.prepare_revision(refs[0], owner, store)
    with db.connect() as conn:
        assert conn.execute("SELECT state FROM product_revisions").fetchone() == ("OPEN",)
        assert conn.execute("SELECT count(*) FROM revision_vectors").fetchone()[0] == 0


def test_only_ok_photos_are_materialized(db, tmp_path):
    repo, owner, _, refs, store = setup(db, tmp_path, 2)
    photos = repo.read_queue(owner)
    complete(repo, owner, store, photos[0])
    complete(repo, owner, store, photos[1], PhotoOutcome.NO_NAILS)
    assert repo.prepare_revision(refs[0], owner, store) is not None
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(DISTINCT revision_photo_id) FROM revision_regions"
            ).fetchone()[0]
            == 1
        )


def test_publication_is_atomic_immutable_and_idempotent(db, tmp_path):
    repo, owner, _, revision, _ = ready(db, tmp_path)
    receipt = repo.publish_revision(revision, None, owner)
    assert receipt is not None and receipt.state == "SUCCEEDED"
    again = repo.publish_revision(revision, None, owner)
    assert again.snapshot_ref == receipt.snapshot_ref
    assert repo.reconcile_publication(receipt.attempt_ref) == receipt
    with db.connect() as conn:
        assert conn.execute(
            "SELECT snapshot_id::text,version FROM active_catalog_snapshots"
        ).fetchone() == (receipt.snapshot_ref, 1)
        assert conn.execute("SELECT state FROM publication_attempts").fetchall() == [("SUCCEEDED",)]
        assert conn.execute("SELECT count(*) FROM catalog_snapshots").fetchone()[0] == 1
        assert conn.execute("SELECT state FROM catalog_snapshots").fetchone()[0] == "READY"
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute("DELETE FROM catalog_snapshot_members")


def test_publish_requires_ready_not_merely_photo_ok(db, tmp_path):
    repo, owner, _, refs, store = setup(db, tmp_path)
    complete(repo, owner, store, repo.read_queue(owner)[0])
    with pytest.raises(ReplenishmentError, match="REVISION_NOT_READY"):
        repo.publish_revision(refs[0], None, owner)


def test_second_product_keeps_previous_members_and_checks_expected_active(db, tmp_path):
    db.migrate()
    with db.connect() as conn:
        products = fixture_inventory(conn) + fixture_inventory(conn)
    repo, owner, _, refs, store = setup(db, tmp_path, products=products)
    for photo in repo.read_queue(owner):
        complete(repo, owner, store, photo)
    revisions = [repo.prepare_revision(r, owner, store) for r in refs]
    first = repo.publish_revision(revisions[0], None, owner)
    assert first is not None
    stale = repo.publish_revision(revisions[1], None, owner)
    assert stale.state == "FAILED" and stale.error_code == "ACTIVE_CONFLICT"
    next_owner = repo.issue_owner("BUILD", 1)
    repo.register_inventory(
        next_owner, tuple(replace(p, expected_head_version=1) for p in products)
    )
    second = repo.publish_revision(revisions[1], first.snapshot_ref, next_owner)
    assert second.state == "SUCCEEDED"
    with db.connect() as conn:
        members = conn.execute(
            "SELECT product_record_id,revision_id::text FROM catalog_snapshot_members WHERE snapshot_id=%s ORDER BY product_record_id",
            (second.snapshot_ref,),
        ).fetchall()
        assert members == [
            (p.product_record_id, r.revision_ref) for p, r in zip(products, revisions)
        ]
        assert (
            conn.execute(
                "SELECT count(*) FROM catalog_snapshot_members WHERE snapshot_id=%s",
                (first.snapshot_ref,),
            ).fetchone()[0]
            == 1
        )


def test_superseded_ready_revision_cannot_publish(db, tmp_path):
    repo, owner, _, revision, _ = ready(db, tmp_path)
    with db.connect() as conn:
        other = uuid4()
        conn.execute(
            "INSERT INTO product_revisions SELECT %s,corpus_version_id,product_record_id,input_set_sha,semantic_profile_sha,1,'OPEN' FROM product_revisions WHERE id=%s",
            (other, revision.revision_ref),
        )
        conn.execute(
            "UPDATE replenishment_product_heads SET current_revision_id=%s,version=version+1",
            (other,),
        )
    with pytest.raises(ReplenishmentError, match="REVISION_SUPERSEDED"):
        repo.publish_revision(revision, None, owner)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM active_catalog_snapshots").fetchone()[0] == 0


def test_stop_before_activation_leaves_failed_attempt_without_pointer(db, tmp_path, monkeypatch):
    repo, owner, _, revision, _ = ready(db, tmp_path)
    activate = repo._activate_publication

    def stop_then_activate(*args):
        with db.connect() as conn:
            conn.execute(
                "UPDATE replenishment_runs SET status='STOPPED' WHERE id=%s", (owner.run_ref,)
            )
        return activate(*args)

    monkeypatch.setattr(repo, "_activate_publication", stop_then_activate)
    receipt = repo.publish_revision(revision, None, owner)
    assert receipt.state == "FAILED" and receipt.error_code == "FENCED"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM active_catalog_snapshots").fetchone()[0] == 0


def test_sql_failure_rolls_back_snapshot_and_keeps_old_active(db, tmp_path):
    repo, owner, _, revision, _ = ready(db, tmp_path)
    with db.connect() as conn:
        conn.execute(
            "CREATE FUNCTION synthetic_fail_active() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'SYNTHETIC_FAILURE' USING ERRCODE='23514'; END$$"
        )
        conn.execute(
            "CREATE TRIGGER fail_active BEFORE INSERT ON active_catalog_snapshots FOR EACH ROW EXECUTE FUNCTION synthetic_fail_active()"
        )
    receipt = repo.publish_revision(revision, None, owner)
    assert receipt.state == "FAILED"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM catalog_snapshots").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 0
        assert conn.execute("SELECT state FROM publication_attempts").fetchone()[0] == "FAILED"


def test_ready_admin_fixture_without_materials_is_rejected(db, tmp_path):
    repo, owner, _, refs, _ = setup(db, tmp_path)
    with db.connect() as conn:
        conn.execute("UPDATE product_revisions SET state='READY',version=version+2")
    with pytest.raises(ReplenishmentError, match="REVISION_INCOMPLETE"):
        repo.publish_revision(replace(refs[0], revision_version=3), None, owner)


def test_replacement_preserves_old_snapshot_and_other_product(db, tmp_path):
    db.migrate()
    with db.connect() as conn:
        products = fixture_inventory(conn) + fixture_inventory(conn)
    repo, owner, _, refs, store = setup(db, tmp_path, products=products)
    for photo in repo.read_queue(owner):
        complete(repo, owner, store, photo)
    refs = tuple(repo.prepare_revision(r, owner, store) for r in refs)
    first = repo.publish_revision(refs[0], None, owner)
    second = repo.publish_revision(refs[1], first.snapshot_ref, owner)
    changed = (
        replace(
            products[0],
            expected_head_version=1,
            photos=(replace(products[0].photos[0], input_sha="c" * 64),),
        ),
    )
    newer, next_owner, _, new_refs, new_store = setup(db, tmp_path, products=changed, epoch=1)
    complete(newer, next_owner, new_store, newer.read_queue(next_owner)[0])
    new_ref = newer.prepare_revision(new_refs[0], next_owner, new_store)
    third = newer.publish_revision(new_ref, second.snapshot_ref, next_owner)
    assert third.state == "SUCCEEDED"
    with db.connect() as conn:
        members = dict(
            conn.execute(
                "SELECT product_record_id,revision_id::text FROM catalog_snapshot_members WHERE snapshot_id=%s",
                (third.snapshot_ref,),
            )
        )
        assert members == {
            products[0].product_record_id: new_ref.revision_ref,
            products[1].product_record_id: refs[1].revision_ref,
        }
        assert (
            dict(
                conn.execute(
                    "SELECT product_record_id,revision_id::text FROM catalog_snapshot_members WHERE snapshot_id=%s",
                    (second.snapshot_ref,),
                )
            )[products[0].product_record_id]
            == refs[0].revision_ref
        )


def test_different_profile_cannot_drop_existing_catalog(db, tmp_path):
    repo, owner, _, revision, _ = ready(db, tmp_path)
    first = repo.publish_revision(revision, None, owner)
    with db.connect() as conn:
        products = fixture_inventory(conn)
    profile = profile_payload()
    profile["crop_version"] = "synthetic-other-profile"
    other, next_owner, _, refs, store = setup(
        db, tmp_path, products=products, epoch=1, profile=profile
    )
    complete(other, next_owner, store, other.read_queue(next_owner)[0])
    revision = other.prepare_revision(refs[0], next_owner, store)
    receipt = other.publish_revision(revision, first.snapshot_ref, next_owner)
    assert receipt.state == "FAILED" and receipt.error_code == "PROFILE_MISMATCH"
    with db.connect() as conn:
        assert (
            conn.execute("SELECT snapshot_id::text FROM active_catalog_snapshots").fetchone()[0]
            == first.snapshot_ref
        )
        assert conn.execute("SELECT count(*) FROM catalog_snapshots").fetchone()[0] == 1


def test_lost_commit_and_unavailable_reconciliation_stay_unknown_without_retry(
    db, tmp_path, monkeypatch
):
    from contextlib import contextmanager

    repo, owner, _, revision, _ = ready(db, tmp_path)
    original = repo.connection_factory
    activate = repo._activate_publication
    lost = False

    @contextmanager
    def lose_ack_then_unavailable():
        nonlocal lost
        if lost:
            raise psycopg.OperationalError("SYNTHETIC_DB_UNAVAILABLE")
        with original() as conn:
            yield conn
        lost = True
        raise psycopg.OperationalError("SYNTHETIC_LOST_ACK")

    def with_ack_loss(*args):
        repo.connection_factory = lose_ack_then_unavailable
        return activate(*args)

    monkeypatch.setattr(repo, "_activate_publication", with_ack_loss)
    receipt = repo.publish_revision(revision, None, owner)
    assert receipt.state == "UNKNOWN"
    repo.connection_factory = original
    fact = repo.reconcile_publication(receipt.attempt_ref)
    assert fact.state == "SUCCEEDED"
    monkeypatch.setattr(
        repo, "_activate_publication", lambda *args: pytest.fail("automatic activation retry")
    )
    assert repo.publish_revision(revision, None, owner).snapshot_ref == fact.snapshot_ref
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM catalog_snapshots").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM publication_attempts").fetchone()[0] == 1


def test_unresolved_attempt_does_not_start_another_activation(db, tmp_path, monkeypatch):
    repo, owner, _, revision, _ = ready(db, tmp_path)
    attempt = uuid4()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO publication_attempts(id,revision_id,run_id,epoch,state) VALUES (%s,%s,%s,%s,'RUNNING')",
            (attempt, revision.revision_ref, owner.run_ref, owner.epoch),
        )
    monkeypatch.setattr(
        repo, "_activate_publication", lambda *args: pytest.fail("activation of unknown attempt")
    )
    receipt = repo.publish_revision(revision, None, owner)
    assert receipt.state == "UNKNOWN" and receipt.attempt_ref == str(attempt)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM publication_attempts").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM active_catalog_snapshots").fetchone()[0] == 0


def test_late_owner_cannot_prepare_or_publish(db, tmp_path):
    repo, owner, _, refs, store = setup(db, tmp_path)
    complete(repo, owner, store, repo.read_queue(owner)[0])
    repo.issue_owner("BUILD", 1)
    with pytest.raises(ReplenishmentError, match="FENCED"):
        repo.prepare_revision(refs[0], owner, store)
    with pytest.raises(ReplenishmentError, match="FENCED"):
        repo.publish_revision(refs[0], None, owner)


def test_commit_before_stop_remains_a_publication_fact(db, tmp_path, monkeypatch):
    import threading
    from contextlib import contextmanager

    repo, owner, _, revision, _ = ready(db, tmp_path)
    original = repo.connection_factory
    stop_started, stop_done = threading.Event(), threading.Event()
    errors, threads = [], []

    def stop():
        try:
            with db.connect() as conn:
                stop_started.set()
                conn.execute(
                    "SELECT epoch FROM replenishment_owner WHERE singleton_key='local' FOR UPDATE"
                )
                conn.execute(
                    "SELECT id FROM replenishment_runs WHERE id=%s FOR UPDATE", (owner.run_ref,)
                )
                conn.execute(
                    "UPDATE replenishment_runs SET status='STOPPED' WHERE id=%s", (owner.run_ref,)
                )
        except psycopg.Error as error:
            errors.append(error)
        finally:
            stop_done.set()

    class Proxy:
        def __init__(self, conn):
            self.conn = conn

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def execute(self, sql, params=None):
            if sql.startswith("INSERT INTO active_catalog_snapshots"):
                thread = threading.Thread(target=stop)
                threads.append(thread)
                thread.start()
                assert stop_started.wait(1)
                assert not stop_done.is_set()
            return self.conn.execute(sql, params)

    @contextmanager
    def connection():
        with original() as conn:
            yield Proxy(conn)

    repo.connection_factory = connection
    try:
        receipt = repo.publish_revision(revision, None, owner)
        assert receipt.state == "SUCCEEDED"
    finally:
        for thread in threads:
            thread.join(3)
            assert not thread.is_alive()
    assert stop_done.is_set() and not errors
    assert repo.reconcile_publication(receipt.attempt_ref).state == "SUCCEEDED"
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT status FROM replenishment_runs WHERE id=%s", (owner.run_ref,)
            ).fetchone()[0]
            == "STOPPED"
        )


def test_owner_change_blocks_even_failure_audit_writes(db, tmp_path, monkeypatch):
    repo, owner, _, revision, _ = ready(db, tmp_path)
    activate = repo._activate_publication

    def new_owner_then_activate(*args):
        repo.issue_owner("BUILD", 1)
        return activate(*args)

    monkeypatch.setattr(repo, "_activate_publication", new_owner_then_activate)
    receipt = repo.publish_revision(revision, None, owner)
    assert receipt.state == "UNKNOWN"
    with db.connect() as conn:
        assert conn.execute("SELECT state FROM publication_attempts").fetchone()[0] == "RUNNING"
        assert conn.execute("SELECT count(*) FROM active_catalog_snapshots").fetchone()[0] == 0


def test_failed_publication_is_not_automatically_repeated_in_same_run(db, tmp_path, monkeypatch):
    repo, owner, _, revision, _ = ready(db, tmp_path)

    def conflict(*args):
        raise ReplenishmentError("ACTIVE_CONFLICT")

    monkeypatch.setattr(repo, "_activate_publication", conflict)
    first = repo.publish_revision(revision, None, owner)
    assert first.state == "FAILED"
    monkeypatch.setattr(
        repo, "_activate_publication", lambda *args: pytest.fail("automatic retry of FAILED")
    )
    second = repo.publish_revision(revision, None, owner)
    assert second == first
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM publication_attempts").fetchone()[0] == 1


def test_error_photo_does_not_prevent_other_ok_photo_from_publication(db, tmp_path):
    repo, owner, _, refs, store = setup(db, tmp_path, 2)
    photos = repo.read_queue(owner)
    complete(repo, owner, store, photos[0])
    failed = repo.begin_attempt(photos[1], "localization", "", owner)
    repo.fail_attempt(failed, owner)
    repo.finish_photo(photos[1], PhotoOutcome.ERROR, owner)
    revision = repo.prepare_revision(refs[0], owner, store)
    assert repo.publish_revision(revision, None, owner).state == "SUCCEEDED"
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(DISTINCT revision_photo_id) FROM revision_vectors"
            ).fetchone()[0]
            == 1
        )


def test_materialization_sql_failure_rolls_back_prepared_and_vectors(db, tmp_path):
    repo, owner, _, refs, store = setup(db, tmp_path)
    complete(repo, owner, store, repo.read_queue(owner)[0])
    with db.connect() as conn:
        conn.execute(
            "CREATE FUNCTION synthetic_fail_vector() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'SYNTHETIC_FAILURE' USING ERRCODE='23514'; END$$"
        )
        conn.execute(
            "CREATE TRIGGER fail_vector AFTER INSERT ON revision_vectors FOR EACH ROW EXECUTE FUNCTION synthetic_fail_vector()"
        )
    with pytest.raises(ReplenishmentError):
        repo.prepare_revision(refs[0], owner, store)
    with db.connect() as conn:
        assert conn.execute("SELECT state,version FROM product_revisions").fetchone() == ("OPEN", 1)
        assert conn.execute("SELECT count(*) FROM revision_regions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM revision_vectors").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 4


def test_deadline_before_activation_commit_rolls_back_pointer_and_receipt(db, tmp_path):
    from contextlib import contextmanager

    repo, owner, _, revision, _ = ready(db, tmp_path)
    original = repo.connection_factory
    now = time.monotonic()
    repo.clock = lambda: now

    class Proxy:
        def __init__(self, conn):
            self.conn = conn

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def execute(self, sql, params=None):
            nonlocal now
            result = self.conn.execute(sql, params)
            if sql.startswith("INSERT INTO active_catalog_snapshots"):
                now = repo.end_at - repo.package.cleanup_reserve_seconds
            return result

    @contextmanager
    def connection():
        with original() as conn:
            yield Proxy(conn)

    repo.connection_factory = connection
    receipt = repo.publish_revision(revision, None, owner)
    assert receipt.state == "UNKNOWN"  # Deadline also prevents a new audit transaction.
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM active_catalog_snapshots").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM catalog_snapshots").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 0
        assert conn.execute("SELECT state FROM publication_attempts").fetchone()[0] == "RUNNING"
