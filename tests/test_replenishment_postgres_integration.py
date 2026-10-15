import signal
import time

import pytest

from tests.support.replenishment_harness import SyntheticDatabase


@pytest.fixture
def db(tmp_path):
    previous = signal.signal(
        signal.SIGALRM, lambda *args: (_ for _ in ()).throw(TimeoutError("B1_DB_CASE_DEADLINE"))
    )
    signal.setitimer(signal.ITIMER_REAL, 60)
    database = SyntheticDatabase(tmp_path / "db-private", time.monotonic() + 55)
    try:
        database.start()
        database.migrate("0009_nail_search_v1")
        yield database
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            database.close()
        finally:
            signal.signal(signal.SIGALRM, previous)


def test_baseline_migrations_apply_only_to_owned_synthetic_database(db):
    with db.connect() as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0009_nail_search_v1",
        )
        assert conn.execute("SELECT count(*) FROM product_records").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM search_representations").fetchone()[0] == 0


from uuid import uuid4

import psycopg


def require_schema(conn):
    assert conn.execute("SELECT to_regclass('replenishment_owner')").fetchone()[0] is not None


def seed(conn):
    require_schema(conn)
    corpus = conn.execute(
        "INSERT INTO corpus_versions(snapshot_name,is_active,operation_id) VALUES ('synthetic',false,%s) RETURNING id",
        (uuid4().hex,),
    ).fetchone()[0]
    product = conn.execute(
        "INSERT INTO product_records(corpus_version_id,product_id,source_row,category,image_path,image_sha256,image_format) VALUES (%s,'synthetic',1,'synthetic','synthetic/photo',%s,'PNG') RETURNING id",
        (corpus, "a" * 64),
    ).fetchone()[0]
    conn.execute("INSERT INTO processing_profiles VALUES (%s,1,'{}'::jsonb)", ("b" * 64,))
    revision = uuid4()
    conn.execute(
        "INSERT INTO product_revisions(id,corpus_version_id,product_record_id,input_set_sha,semantic_profile_sha,version,state) VALUES (%s,%s,%s,%s,%s,1,'OPEN')",
        (revision, corpus, product, "a" * 64, "b" * 64),
    )
    conn.execute(
        "INSERT INTO replenishment_product_heads VALUES (%s,%s,%s,1)", (corpus, product, revision)
    )
    photo = uuid4()
    conn.execute(
        "INSERT INTO revision_photos(id,revision_id,ordinal,source_ref,input_sha,source_bytes,outcome) VALUES (%s,%s,1,'synthetic-ref',%s,100,'PENDING')",
        (photo, revision, "a" * 64),
    )
    run = uuid4()
    token = uuid4()
    conn.execute(
        "UPDATE replenishment_owner SET epoch=1,owner_token=%s,mode='BUILD',version=1", (token,)
    )
    conn.execute(
        "INSERT INTO replenishment_runs(id,package_sha,owner_token,epoch,status) VALUES (%s,%s,%s,1,'RUNNING')",
        (run, "c" * 64, token),
    )
    return corpus, product, revision, photo, run


def test_new_schema_has_separate_progress_and_catalog_storage(db):
    db.migrate()
    expected = {
        "replenishment_owner",
        "replenishment_runs",
        "processing_profiles",
        "replenishment_product_heads",
        "product_revisions",
        "revision_photos",
        "stage_attempts",
        "stage_checkpoints",
        "revision_regions",
        "revision_vectors",
        "catalog_snapshots",
        "catalog_snapshot_members",
        "active_catalog_snapshots",
        "publication_attempts",
        "revision_publications",
    }
    with db.connect() as conn:
        actual = {
            r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        }
        assert expected <= actual


def test_current_head_is_unique_and_revision_must_belong_to_product(db):
    db.migrate()
    with db.connect() as conn:
        corpus, product, revision, _, _ = seed(conn)
        with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
            conn.execute(
                "INSERT INTO replenishment_product_heads VALUES (%s,%s,%s,1)",
                (corpus, product, revision),
            )
        other = conn.execute(
            "INSERT INTO product_records(corpus_version_id,product_id,source_row,category,image_path,image_sha256,image_format) VALUES (%s,'other-synthetic',2,'synthetic','synthetic/other',%s,'PNG') RETURNING id",
            (corpus, "a" * 64),
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.ForeignKeyViolation), conn.transaction():
            conn.execute(
                "INSERT INTO replenishment_product_heads VALUES (%s,%s,%s,1)",
                (corpus, other, revision),
            )


def test_attempts_have_unique_numbers_and_localization_has_empty_model_key(db):
    db.migrate()
    with db.connect() as conn:
        _, _, _, photo, run = seed(conn)

        def add(model, number):
            conn.execute(
                "INSERT INTO stage_attempts(id,photo_id,stage_key,model_key,run_id,epoch,state,attempt_no,version,identity_sha) VALUES (%s,%s,'localization',%s,%s,1,'RUNNING',%s,1,%s)",
                (uuid4(), photo, model, run, number, "d" * 64),
            )

        add("", 1)
        with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
            add("", 1)
        with pytest.raises(psycopg.errors.NotNullViolation), conn.transaction():
            add(None, 2)
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            add("openclip_b32", 2)


def test_ready_revision_and_its_children_are_immutable(db):
    db.migrate()
    with db.connect() as conn:
        _, _, revision, photo, _ = seed(conn)
        # Synthetic administrative fixture; not a claim of complete ML coverage.
        conn.execute("UPDATE revision_photos SET outcome='OK' WHERE id=%s", (photo,))
        conn.execute("UPDATE product_revisions SET state='READY' WHERE id=%s", (revision,))
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute(
                "UPDATE product_revisions SET input_set_sha=%s WHERE id=%s", ("e" * 64, revision)
            )
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute(
                "UPDATE revision_photos SET outcome='ERROR',error_code='SYNTHETIC' WHERE id=%s",
                (photo,),
            )


def test_profile_payload_cannot_be_changed_after_registration(db):
    db.migrate()
    with db.connect() as conn:
        seed(conn)
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute(
                "UPDATE processing_profiles SET canonical_payload='{"
                + '"changed":true'
                + "}'::jsonb"
            )


import hashlib
import json
from dataclasses import replace

from product_search.infrastructure.replenishment_repository import PostgresReplenishment
from product_search.search.replenishment_contracts import (
    Ownership,
    PhotoOutcome,
    ReplenishmentError,
    SelectedPhoto,
    SelectedProduct,
    StageOutput,
)
from tests.test_replenishment_contracts import package


def canonical_digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def fixture_inventory(conn, count=1, expected_head=0):
    corpus = conn.execute(
        "INSERT INTO corpus_versions(snapshot_name,is_active,operation_id) VALUES ('synthetic',false,%s) RETURNING id",
        (uuid4().hex,),
    ).fetchone()[0]
    product = conn.execute(
        "INSERT INTO product_records(corpus_version_id,product_id,source_row,category,image_path,image_sha256,image_format) VALUES (%s,'synthetic',1,'synthetic','synthetic/photo',%s,'PNG') RETURNING id",
        (corpus, "a" * 64),
    ).fetchone()[0]
    photos = tuple(SelectedPhoto(i + 1, f"synthetic-{i + 1}", "a" * 64, 100) for i in range(count))
    return (SelectedProduct(corpus, product, expected_head, photos),)


def profile_payload():
    return {
        "schema_version": 1,
        "crop_version": "synthetic-white-v1",
        "models": [
            {
                "model_key": key,
                "dimension": dim,
                "revision": "synthetic-v1",
                "preprocessing": "synthetic-v1",
                "dtype": "float32",
            }
            for key, dim in [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)]
        ],
    }


def inventory_payload(products):
    return [
        {
            "corpus_version_id": p.corpus_version_id,
            "product_record_id": p.product_record_id,
            "photos": [
                {
                    "ordinal": f.ordinal,
                    "source_ref": f.source_ref,
                    "input_sha": f.input_sha,
                    "source_bytes": f.source_bytes,
                }
                for f in p.photos
            ],
        }
        for p in products
    ]


def repository(db, products):
    pkg = package(
        input_set_sha=canonical_digest(inventory_payload(products)),
        semantic_profile_sha=canonical_digest(profile_payload()),
        max_admissions=100,
    )
    return PostgresReplenishment(db.connect, pkg, db.end_at, clock=time.monotonic)


def registered(db, count=1):
    db.migrate()
    with db.connect() as conn:
        products = fixture_inventory(conn, count)
    repo = repository(db, products)
    owner = repo.issue_owner("BUILD", 0)
    assert isinstance(owner, Ownership)
    repo.register_profile(owner, profile_payload())
    revisions = repo.register_inventory(owner, products)
    assert revisions is not None and len(revisions) == 1
    queue = repo.read_queue(owner)
    assert queue is not None and len(queue) == min(5, count)
    return repo, owner, products, revisions[0], queue


def test_owner_epoch_and_version_cas_are_atomic(db):
    db.migrate()
    repo = repository(db, ())
    first = repo.issue_owner("BUILD", 0)
    assert isinstance(first, Ownership) and first.epoch == 1
    with pytest.raises(ReplenishmentError, match="VERSION_CONFLICT"):
        repo.issue_owner("BUILD", 0)
    second = repo.issue_owner("BUILD", 1)
    assert second.epoch == 2 and second.owner_token != first.owner_token
    with pytest.raises(ReplenishmentError, match="FENCED"):
        repo.register_profile(first, profile_payload())


def test_queue_binding_is_finite_and_cannot_choose_another_batch_in_same_run(db):
    repo, owner, products, revision, queue = registered(db, 7)
    assert revision.head_version == 1 and revision.revision_version == 1
    with pytest.raises(ReplenishmentError, match="INVENTORY_ALREADY_BOUND"):
        repo.register_inventory(owner, products)
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM revision_photos WHERE revision_id=%s",
                (revision.revision_ref,),
            ).fetchone()[0]
            == 7
        )
        other_id = conn.execute(
            "SELECT id FROM revision_photos WHERE revision_id=%s ORDER BY ordinal OFFSET 5 LIMIT 1",
            (revision.revision_ref,),
        ).fetchone()[0]
    outside = replace(queue[0], photo_ref=str(other_id))
    with pytest.raises(ReplenishmentError, match="INVALID_SCOPE"):
        repo.begin_attempt(outside, "localization", "", owner)


def test_checkpoint_receipt_is_idempotent_and_conflicting_hash_is_refused(db):
    repo, owner, _, _, queue = registered(db)
    attempt = repo.begin_attempt(queue[0], "localization", "", owner)
    assert attempt is not None and attempt.expected_version == 1
    output = StageOutput("synthetic-artifact", "d" * 64, 1)
    receipt = repo.commit_checkpoint(attempt, output, owner)
    assert receipt is not None and receipt.manifest_sha == "d" * 64
    assert repo.commit_checkpoint(attempt, output, owner) == receipt
    with pytest.raises(ReplenishmentError, match="ARTIFACT_CONFLICT"):
        repo.commit_checkpoint(attempt, replace(output, manifest_sha="e" * 64), owner)
    with db.connect() as conn:
        assert conn.execute(
            "SELECT state,version FROM stage_attempts WHERE id=%s", (attempt.attempt_ref,)
        ).fetchone() == ("COMPLETE", 2)
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 1


def test_stale_head_revision_and_attempt_versions_reject_checkpoint(db):
    repo, owner, _, _, queue = registered(db)
    attempt = repo.begin_attempt(queue[0], "localization", "", owner)
    assert attempt is not None
    output = StageOutput("synthetic-artifact", "d" * 64, 1)
    for changed in (
        replace(attempt, head_version=2),
        replace(attempt, revision_version=2),
        replace(attempt, expected_version=2),
    ):
        with pytest.raises(ReplenishmentError, match="VERSION_CONFLICT"):
            repo.commit_checkpoint(changed, output, owner)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 0
        assert conn.execute("SELECT state FROM stage_attempts").fetchone()[0] == "RUNNING"


def test_late_old_owner_cannot_commit_after_new_epoch(db):
    repo, owner, _, _, queue = registered(db)
    attempt = repo.begin_attempt(queue[0], "localization", "", owner)
    assert attempt is not None
    newer = repo.issue_owner("BUILD", owner.epoch)
    assert newer.epoch == 2
    with pytest.raises(ReplenishmentError, match="FENCED"):
        repo.commit_checkpoint(attempt, StageOutput("synthetic-artifact", "d" * 64, 1), owner)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 0


def test_photo_success_requires_all_three_encoder_receipts(db):
    repo, owner, _, _, queue = registered(db)
    work = queue[0]
    localized = repo.begin_attempt(work, "localization", "", owner)
    assert localized is not None
    repo.commit_checkpoint(localized, StageOutput("synthetic-localization", "d" * 64, 1), owner)
    with pytest.raises(ReplenishmentError, match="PHOTO_INCOMPLETE"):
        repo.finish_photo(work, PhotoOutcome.OK, owner)
    for model in ("openclip_b32", "dinov2_b14", "siglip2_b16_224"):
        encoded = repo.begin_attempt(work, "embedding", model, owner)
        repo.commit_checkpoint(encoded, StageOutput("synthetic-vector", "e" * 64, 1), owner)
    repo.finish_photo(work, PhotoOutcome.OK, owner)
    assert repo.revision_outcomes(work.revision_ref) == (PhotoOutcome.OK,)


def test_empty_localization_finishes_no_nails_without_encoder_attempt(db):
    repo, owner, _, _, queue = registered(db)
    work = queue[0]
    attempt = repo.begin_attempt(work, "localization", "", owner)
    assert attempt is not None
    repo.commit_checkpoint(attempt, StageOutput("synthetic-empty", "d" * 64, 0), owner)
    repo.finish_photo(work, PhotoOutcome.NO_NAILS, owner)
    assert repo.revision_outcomes(work.revision_ref) == (PhotoOutcome.NO_NAILS,)
    with pytest.raises(ReplenishmentError, match="PHOTO_TERMINAL"):
        repo.begin_attempt(work, "embedding", "openclip_b32", owner)


def test_run_package_and_bound_selection_cannot_be_changed(db):
    repo, owner, _, _, _queue = registered(db, 2)
    with db.connect() as conn:
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute(
                "UPDATE replenishment_runs SET package_sha=%s WHERE id=%s",
                ("e" * 64, owner.run_ref),
            )
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute(
                "UPDATE replenishment_runs SET selected_photo_ids=%s WHERE id=%s",
                ([uuid4()], owner.run_ref),
            )
    assert len(repo.read_queue(owner)) == 2


def test_attempt_cannot_be_marked_complete_without_checkpoint(db):
    repo, owner, _, _, queue = registered(db)
    work = repo.begin_attempt(queue[0], "localization", "", owner)
    with db.connect() as conn, pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute(
            "UPDATE stage_attempts SET state='COMPLETE',version=version+1 WHERE id=%s",
            (work.attempt_ref,),
        )


def test_superseded_revision_refuses_late_checkpoint_even_with_current_owner(db):
    repo, owner, products, revision, queue = registered(db)
    attempt = repo.begin_attempt(queue[0], "localization", "", owner)
    with db.connect() as conn:
        replacement = uuid4()
        product = products[0]
        conn.execute(
            "INSERT INTO product_revisions VALUES (%s,%s,%s,%s,%s,1,'OPEN')",
            (
                replacement,
                product.corpus_version_id,
                product.product_record_id,
                "f" * 64,
                repo.package.semantic_profile_sha,
            ),
        )
        conn.execute(
            "UPDATE replenishment_product_heads SET current_revision_id=%s,version=version+1 WHERE current_revision_id=%s",
            (replacement, revision.revision_ref),
        )
    with pytest.raises(ReplenishmentError, match="REVISION_SUPERSEDED"):
        repo.commit_checkpoint(attempt, StageOutput("synthetic-result", "d" * 64, 1), owner)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 0


def test_invalid_inventory_hash_cannot_create_revisions(db):
    db.migrate()
    with db.connect() as conn:
        products = fixture_inventory(conn)
    repo = repository(db, products)
    invalid = PostgresReplenishment(
        db.connect, replace(repo.package, input_set_sha="e" * 64), db.end_at, clock=time.monotonic
    )
    owner = invalid.issue_owner("BUILD", 0)
    invalid.register_profile(owner, profile_payload())
    with pytest.raises(ReplenishmentError, match="INPUT_MISMATCH"):
        invalid.register_inventory(owner, products)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM product_revisions").fetchone()[0] == 0


def test_database_error_during_checkpoint_rolls_back_all_its_rows(db):
    repo, owner, _, _, queue = registered(db)
    attempt = repo.begin_attempt(queue[0], "localization", "", owner)
    with db.connect() as conn:
        conn.execute(
            "CREATE FUNCTION synthetic_checkpoint_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'SYNTHETIC_FAILURE' USING ERRCODE='23514'; END $$"
        )
        conn.execute(
            "CREATE TRIGGER synthetic_failure AFTER INSERT ON stage_checkpoints FOR EACH ROW EXECUTE FUNCTION synthetic_checkpoint_failure()"
        )
    with pytest.raises(ReplenishmentError):
        repo.commit_checkpoint(attempt, StageOutput("synthetic-result", "d" * 64, 1), owner)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 0
        assert conn.execute("SELECT state,version FROM stage_attempts").fetchone() == ("RUNNING", 1)
        assert conn.execute("SELECT outcome FROM revision_photos").fetchone()[0] == "RUNNING"


def test_checkpoint_ack_loss_is_unknown_and_receipt_can_be_reconciled(db):
    from contextlib import contextmanager

    repo, owner, _, _, queue = registered(db)
    attempt = repo.begin_attempt(queue[0], "localization", "", owner)
    original = repo.connection_factory

    @contextmanager
    def lost_response():
        with original() as conn:
            yield conn
        raise psycopg.OperationalError("synthetic acknowledgement loss")

    repo.connection_factory = lost_response
    output = StageOutput("synthetic-result", "d" * 64, 1)
    with pytest.raises(ReplenishmentError, match="COMMIT_UNKNOWN"):
        repo.commit_checkpoint(attempt, output, owner)
    repo.connection_factory = original
    receipt = repo.commit_checkpoint(attempt, output, owner)
    assert receipt.manifest_sha == "d" * 64
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 1


def test_snapshot_member_is_unique_and_revision_must_belong_to_member_product(db):
    db.migrate()
    with db.connect() as conn:
        corpus, product, revision, _, _ = seed(conn)
        snapshot = uuid4()
        conn.execute(
            "INSERT INTO catalog_snapshots VALUES (%s,%s,%s,'PREPARED')",
            (snapshot, "b" * 64, "c" * 64),
        )
        conn.execute(
            "INSERT INTO catalog_snapshot_members VALUES (%s,%s,%s)", (snapshot, product, revision)
        )
        with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
            conn.execute(
                "INSERT INTO catalog_snapshot_members VALUES (%s,%s,%s)",
                (snapshot, product, revision),
            )
        other = conn.execute(
            "INSERT INTO product_records(corpus_version_id,product_id,source_row,category,image_path,image_sha256,image_format) VALUES (%s,'other',2,'synthetic','synthetic/other',%s,'PNG') RETURNING id",
            (corpus, "a" * 64),
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.ForeignKeyViolation), conn.transaction():
            conn.execute(
                "INSERT INTO catalog_snapshot_members VALUES (%s,%s,%s)",
                (snapshot, other, revision),
            )


def test_two_owner_requests_with_same_epoch_have_one_winner(db):
    from concurrent.futures import ThreadPoolExecutor

    db.migrate()
    repo = repository(db, ())

    def claim():
        try:
            return repo.issue_owner("BUILD", 0)
        except ReplenishmentError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(isinstance(value, Ownership) for value in results) == 1
    assert results.count("VERSION_CONFLICT") == 1
    with db.connect() as conn:
        assert conn.execute("SELECT epoch FROM replenishment_owner").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM replenishment_runs").fetchone()[0] == 1


def test_expiry_before_commit_rolls_back_checkpoint_and_completion(db):
    from contextlib import contextmanager

    repo, owner, _, _, queue = registered(db)
    attempt = repo.begin_attempt(queue[0], "localization", "", owner)
    now = [time.monotonic()]
    original = repo.connection_factory

    class Connection:
        def __init__(self, conn):
            self.conn = conn

        def transaction(self):
            return self.conn.transaction()

        def execute(self, sql, *args):
            result = self.conn.execute(sql, *args)
            if sql.startswith("INSERT INTO stage_checkpoints"):
                now[0] = repo.end_at
            return result

    @contextmanager
    def connection():
        with original() as conn:
            yield Connection(conn)

    repo.connection_factory = connection
    repo.clock = lambda: now[0]
    with pytest.raises(ReplenishmentError, match="DEADLINE"):
        repo.commit_checkpoint(attempt, StageOutput("synthetic-result", "d" * 64, 1), owner)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 0
        assert conn.execute("SELECT state,version FROM stage_attempts").fetchone() == ("RUNNING", 1)


def test_new_run_reuses_same_revision_without_rebinding_old_run(db):
    repo, owner, products, revision, _ = registered(db)
    newer = repo.issue_owner("BUILD", owner.epoch)
    reused = repo.register_inventory(newer, (replace(products[0], expected_head_version=1),))
    assert reused == (revision,)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM product_revisions").fetchone()[0] == 1
        assert (
            conn.execute(
                "SELECT inventory_bound FROM replenishment_runs WHERE id=%s", (owner.run_ref,)
            ).fetchone()[0]
            is True
        )


def test_slow_connection_rechecks_deadline_before_any_progress_sql(db):
    from contextlib import contextmanager

    repo, owner, _, _, _ = registered(db)
    original = repo.connection_factory
    now = [time.monotonic()]
    calls = []

    class Connection:
        def __init__(self, conn):
            self.conn = conn

        def transaction(self):
            return self.conn.transaction()

        def execute(self, sql, *args):
            calls.append(sql)
            return self.conn.execute(sql, *args)

    @contextmanager
    def connection():
        with original() as conn:
            now[0] = repo.end_at
            yield Connection(conn)

    repo.clock = lambda: now[0]
    repo.connection_factory = connection
    with pytest.raises(ReplenishmentError, match="DEADLINE"):
        repo.register_profile(owner, profile_payload())
    assert calls == []


def test_new_run_cannot_silently_skip_unreconciled_running_photo(db):
    repo,owner,products,_,queue=registered(db,2)
    repo.begin_attempt(queue[0],'localization','',owner)
    newer=repo.issue_owner('BUILD',owner.epoch)
    with pytest.raises(ReplenishmentError,match='RECOVERY_REQUIRED'):
        repo.register_inventory(newer,(replace(products[0],expected_head_version=1),))
    with db.connect() as conn:
        assert conn.execute('SELECT inventory_bound FROM replenishment_runs WHERE id=%s',(newer.run_ref,)).fetchone()[0] is False


def test_worker_source_payload_is_fenced_to_current_running_attempt(db):
    repo, owner, _, _, queue = registered(db)
    photo = queue[0]
    attempt = repo.begin_attempt(photo, 'localization', '', owner)
    source = repo.read_stage_source(attempt, owner)
    assert source == SelectedPhoto(1, 'synthetic-1', 'a' * 64, 100)
    repo.fail_attempt(attempt, owner)
    with pytest.raises(ReplenishmentError, match='VERSION_CONFLICT'):
        repo.read_stage_source(attempt, owner)


def test_revoked_grant_before_checkpoint_commit_rolls_back(db, tmp_path):
    from contextlib import contextmanager

    from product_search.infrastructure.replenishment_runtime_binding import FreshGrant, issue_grant

    repo, owner, _, _, queue = registered(db)
    attempt = repo.begin_attempt(queue[0], "localization", "", owner)
    tmp_path.chmod(0o700)
    path = tmp_path / "grant.json"
    issue_grant(path, repo.package, approved_package_sha=FreshGrant.package_sha(repo.package), expires_at=time.time()+20, search_authorized=True)
    grant = FreshGrant(path)
    grant.consume(owner, repo.package)
    repo.authorize_transaction = lambda: grant.check_authorization(repo.package)
    original = repo.connection_factory

    class Connection:
        def __init__(self, conn):
            self.conn = conn

        def transaction(self):
            return self.conn.transaction()

        def execute(self, sql, *args, **kwargs):
            result = self.conn.execute(sql, *args, **kwargs)
            if sql.startswith("INSERT INTO stage_checkpoints"):
                path.unlink()
            return result

    @contextmanager
    def connection():
        with original() as conn:
            yield Connection(conn)

    repo.connection_factory = connection
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        repo.commit_checkpoint(attempt, StageOutput("synthetic-result", "d" * 64, 1), owner)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM stage_checkpoints").fetchone()[0] == 0
        assert conn.execute("SELECT state FROM stage_attempts").fetchone()[0] == "RUNNING"
    repo.finish_run(owner, "RECOVERY_REQUIRED")


def test_native_host_composition_publishes_fake_stages(db, tmp_path, monkeypatch):
    import json
    from dataclasses import asdict, replace
    from types import SimpleNamespace

    from product_search.infrastructure import replenishment_host as host
    from product_search.infrastructure import replenishment_runtime_binding as runtime
    from product_search.infrastructure import replenishment_workers as workers
    from product_search.infrastructure.replenishment_repository import digest
    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.search.nail_contracts import MODEL_DIMENSIONS
    from product_search.search.replenishment_contracts import ResourceObservation
    from tests.test_replenishment_artifacts import png

    db.migrate()
    with db.connect() as conn:
        products = fixture_inventory(conn)
    pkg = repository(db, products).package
    tmp_path.chmod(0o700)
    binding = {"shared_runtime_root": str(tmp_path), "target_policy": {}, "resource_limits": {"i_rss_bytes": 1000000, "encoder_rss_bytes": 1000000}, "policy": {"poll_seconds": 0.5}}
    pkg = replace(pkg, runtime_sha=digest(binding), max_vector_bytes=20000, max_wire_bytes=8000)
    publish_private_json(tmp_path / "binding.json", binding)
    publish_private_json(tmp_path / "profile.json", profile_payload())
    runtime.issue_grant(tmp_path / "grant.json", pkg, approved_package_sha=runtime.FreshGrant.package_sha(pkg), expires_at=time.time()+20, search_authorized=True)
    monkeypatch.setattr(runtime, "verify_code_inventory", lambda *a: None)
    monkeypatch.setattr(runtime, "verify_frozen_inputs", lambda *a: None)
    monkeypatch.setattr(host, "RuntimeTarget", lambda *a: SimpleNamespace(connect=lambda *a: db.connect()))

    class Sensor:
        last_sample = None

        def __init__(self, *a, **kw):
            pass

        def __call__(self):
            return ResourceObservation("OK", time.monotonic())

    monkeypatch.setattr(runtime, "MacResourceObserver", Sensor)
    monkeypatch.setattr(workers, "NativeStageDriver", lambda *a: SimpleNamespace(files=a[5], control=None, child=None, owned_worker=lambda: None))

    class Stages:
        def __init__(self, supervisor, grant, driver, package, owner, *a, **kw):
            self.owner, self.files, self.pkg = owner, driver.files, package

        def open_stage(self, *args):
            pass

        def close_stage(self, *args):
            return True

        def process(self, photo, attempt, *args):
            if attempt.stage_key == "localization":
                payload = {"crop-1.png": png("RGB"), "mask-1.png": png("L")}
            else:
                dim = dict(MODEL_DIMENSIONS)[attempt.model_key]
                payload = {"vectors.json": json.dumps({"model_key": attempt.model_key, "vectors": [{"ordinal": 1, "values": [0.25]*dim}]}).encode()}
            return self.files.write_staging(attempt, self.pkg, 1, payload)

    monkeypatch.setattr(workers, "ProcessStageWorkers", Stages)
    summaries = []

    def serve(app, *args, **kwargs):
        try:
            summaries.append(app.start(asdict(pkg), [asdict(p) for p in products]))
        finally:
            app.supervisor.close(end_at=time.monotonic()+5, stop_grace=1, kill_wait=1)

    monkeypatch.setattr(host, "serve_owner", serve)
    host.run_native_host({"package": asdict(pkg), "grant_path": str(tmp_path / "grant.json"), "binding_path": str(tmp_path / "binding.json"), "profile_path": str(tmp_path / "profile.json"), "code_inventory_path": str(tmp_path / "code.json"), "input_inventory_path": str(tmp_path / "inputs.json"), "target_descriptor_path": str(tmp_path / "target.json"), "private_root": str(tmp_path), "checkpoint_root": str(tmp_path), "max_commands": 1, "timeout_seconds": 2, "max_bytes": 65536})
    assert summaries[0]["publications"][0]["state"] == "SUCCEEDED"
