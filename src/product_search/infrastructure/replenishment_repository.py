"""Bounded PostgreSQL progress adapter; accepts a connection factory, never a default DSN."""

import hashlib
import json
import math
import re
from contextlib import contextmanager
from dataclasses import asdict
from itertools import groupby
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from product_search.search.corpus_replenishment import product_readiness, retry_photo_outcomes
from product_search.search.nail_contracts import MODEL_DIMENSIONS
from product_search.search.replenishment_contracts import (
    CheckpointReceipt,
    Ownership,
    PhotoOutcome,
    PhotoWork,
    PublicationReceipt,
    ReplenishmentError,
    RevisionReference,
    SavedCheckpoint,
    SelectedPhoto,
    SelectedProduct,
    SnapshotDescriptor,
    SnapshotEmbeddingProfile,
    SnapshotQueryClaim,
    SnapshotRuntimeIdentity,
    StageAttempt,
    StageOutput,
    VerifiedCatalogBinding,
)


def digest(payload):
    from product_search.infrastructure.replenishment_runtime_binding import canonical

    return hashlib.sha256(canonical(payload)).hexdigest()


def inventory_payload(products):
    return [
        {
            "corpus_version_id": p.corpus_version_id,
            "product_record_id": p.product_record_id,
            "photos": [asdict(f) for f in p.photos],
        }
        for p in products
    ]


def uuid(value):
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ReplenishmentError("INVALID_INPUT") from None


class PostgresReplenishment:
    def __init__(self, connection_factory, package, end_at, *, clock, authorize_transaction=None):
        self.authorize_transaction = authorize_transaction or (lambda: None)
        self.connection_factory = connection_factory
        self.package = package
        self.end_at = end_at
        self.clock = clock
        self.package_sha = digest(asdict(package))

    def _sql_budget(self, *, cleanup=False):
        reserve = 0 if cleanup else self.package.cleanup_reserve_seconds
        remaining = self.end_at - reserve - self.clock()
        if not math.isfinite(remaining) or remaining <= 0:
            raise ReplenishmentError("DEADLINE")
        milliseconds = int(min(remaining, self.package.db_seconds) * 1000)
        if milliseconds < 1:
            raise ReplenishmentError("DEADLINE")
        return milliseconds

    @contextmanager
    def _transaction(self, *, cleanup=False):
        repo = self

        def refresh(conn):
            if not cleanup:
                self.authorize_transaction()
            milliseconds = self._sql_budget(cleanup=cleanup)
            conn.execute(
                "SELECT set_config('lock_timeout',%s,true),set_config('statement_timeout',%s,true)",
                (f"{milliseconds}ms", f"{milliseconds}ms"),
            )
            if not cleanup:
                self.authorize_transaction()
            self._sql_budget(cleanup=cleanup)

        class BoundedCursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def execute(self, *args, **kwargs):
                refresh(conn)
                self.cursor.execute(*args, **kwargs)
                return self

            def __iter__(self):
                while True:
                    refresh(conn)
                    rows = self.cursor.fetchmany(self.cursor.itersize)
                    if not rows:
                        return
                    yield from rows

        class BoundedSql:
            def execute(self, *args, **kwargs):
                refresh(conn)
                return conn.execute(*args, **kwargs)

            @contextmanager
            def cursor(self, *args, **kwargs):
                with conn.cursor(*args, **kwargs) as cursor:
                    yield BoundedCursor(cursor)

        self._sql_budget(cleanup=cleanup)
        if not cleanup:
            repo.authorize_transaction()
        try:
            with self.connection_factory() as conn, conn.transaction():
                yield BoundedSql()
                # COMMIT is a SQL operation too; use the final remaining budget.
                refresh(conn)
        except psycopg.IntegrityError:
            raise ReplenishmentError("VERSION_CONFLICT") from None
        except psycopg.Error:
            raise ReplenishmentError("COMMIT_UNKNOWN") from None

    def issue_owner(self, mode, expected_epoch):
        if mode not in {"BUILD", "SEARCH"} or type(expected_epoch) is not int or expected_epoch < 0:
            raise ReplenishmentError("INVALID_INPUT")
        with self._transaction() as conn:
            old = conn.execute(
                "SELECT epoch FROM replenishment_owner WHERE singleton_key='local' FOR UPDATE"
            ).fetchone()
            if old[0] != expected_epoch:
                raise ReplenishmentError("VERSION_CONFLICT")
            run_id, token = uuid4(), uuid4()
            epoch = old[0] + 1
            conn.execute(
                "UPDATE replenishment_runs SET status='INTERRUPTED',reason='OWNER_CHANGED',finished_at=now() WHERE status='RUNNING'"
            )
            conn.execute(
                "INSERT INTO replenishment_runs(id,package_sha,owner_token,epoch,status) VALUES (%s,%s,%s,%s,'RUNNING')",
                (run_id, self.package_sha, token, epoch),
            )
            conn.execute(
                "UPDATE replenishment_owner SET epoch=%s,owner_token=%s,mode=%s,version=version+1,updated_at=now() WHERE singleton_key='local'",
                (epoch, token, mode),
            )
        return Ownership(str(run_id), str(token), epoch)

    def _fence(self, conn, owner, *, allow_terminal_audit=False):
        current = conn.execute(
            "SELECT epoch,owner_token,mode FROM replenishment_owner WHERE singleton_key='local' FOR UPDATE"
        ).fetchone()
        if (current[0], str(current[1]), current[2]) != (owner.epoch, owner.owner_token, "BUILD"):
            raise ReplenishmentError("FENCED")
        run = conn.execute(
            "SELECT epoch,owner_token,status,package_sha,inventory_bound,selected_photo_ids,revision_ids FROM replenishment_runs WHERE id=%s FOR UPDATE",
            (uuid(owner.run_ref),),
        ).fetchone()
        if (
            run is None
            or (run[0], str(run[1]), run[3]) != (owner.epoch, owner.owner_token, self.package_sha)
            or (not allow_terminal_audit and run[2] != "RUNNING")
        ):
            raise ReplenishmentError("FENCED")
        return run

    def register_profile(self, owner, payload):
        try:
            models = payload["models"]
            valid = (
                payload["schema_version"] == 1
                and bool(payload["crop_version"])
                and tuple((m["model_key"], m["dimension"]) for m in models) == MODEL_DIMENSIONS
                and all(
                    m["revision"] and m["preprocessing"] and m["dtype"] == "float32" for m in models
                )
                and digest(payload) == self.package.semantic_profile_sha
            )
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            raise ReplenishmentError("PROFILE_MISMATCH")
        with self._transaction() as conn:
            self._fence(conn, owner)
            conn.execute(
                "INSERT INTO processing_profiles VALUES (%s,1,%s) ON CONFLICT DO NOTHING",
                (self.package.semantic_profile_sha, Jsonb(payload)),
            )
            self._profile(conn)

    def _profile(self, conn):
        row = conn.execute(
            "SELECT canonical_payload FROM processing_profiles WHERE semantic_profile_sha=%s",
            (self.package.semantic_profile_sha,),
        ).fetchone()
        if row is None or digest(row[0]) != self.package.semantic_profile_sha:
            raise ReplenishmentError("PROFILE_MISMATCH")
        return row[0]

    def validate_inventory(self, products):
        if self.package.scope not in {"START", "RESUME", "RETRY_PHOTO", "RETRY_PUBLICATION"}:
            raise ReplenishmentError("INVALID_SCOPE")
        if (
            type(products) is not tuple
            or digest(inventory_payload(products)) != self.package.input_set_sha
        ):
            raise ReplenishmentError("INPUT_MISMATCH")
        keys = tuple((p.corpus_version_id, p.product_record_id) for p in products)
        if keys != tuple(sorted(set(keys))):
            raise ReplenishmentError("INVALID_INPUT")
        for product in products:
            if (
                type(product.expected_head_version) is not int
                or product.expected_head_version < 0
                or type(product.photos) is not tuple
                or not product.photos
                or tuple(f.ordinal for f in product.photos)
                != tuple(sorted({f.ordinal for f in product.photos}))
                or any(
                    type(f.ordinal) is not int
                    or f.ordinal <= 0
                    or not f.source_ref
                    or not re.fullmatch("[0-9a-f]{64}", f.input_sha)
                    or type(f.source_bytes) is not int
                    or not 0 < f.source_bytes <= self.package.max_source_bytes
                    for f in product.photos
                )
            ):
                raise ReplenishmentError("INVALID_INPUT")

    def register_inventory(self, owner, products):
        self.validate_inventory(products)
        refs = []
        selected = []
        with self._transaction() as conn:
            run = self._fence(conn, owner)
            if run[4]:
                raise ReplenishmentError("INVENTORY_ALREADY_BOUND")
            self._profile(conn)
            for product in products:
                corpus, record = product.corpus_version_id, product.product_record_id
                conn.execute(
                    "INSERT INTO replenishment_product_heads(corpus_version_id,product_record_id,current_revision_id,version) VALUES (%s,%s,NULL,0) ON CONFLICT DO NOTHING",
                    (corpus, record),
                )
                head = conn.execute(
                    "SELECT current_revision_id,version FROM replenishment_product_heads WHERE corpus_version_id=%s AND product_record_id=%s FOR UPDATE",
                    (corpus, record),
                ).fetchone()
                if head[1] != product.expected_head_version:
                    raise ReplenishmentError("VERSION_CONFLICT")
                input_sha = digest([asdict(f) for f in product.photos])
                existing = (
                    conn.execute(
                        "SELECT input_set_sha,semantic_profile_sha,version FROM product_revisions WHERE id=%s FOR UPDATE",
                        (head[0],),
                    ).fetchone()
                    if head[0]
                    else None
                )
                if (
                    head[0]
                    and conn.execute(
                        "SELECT 1 FROM revision_photos WHERE revision_id=%s AND outcome='RUNNING' LIMIT 1",
                        (head[0],),
                    ).fetchone()
                ):
                    raise ReplenishmentError("RECOVERY_REQUIRED")
                if existing and existing[:2] == (input_sha, self.package.semantic_profile_sha):
                    ref = RevisionReference(str(head[0]), head[1], existing[2])
                else:
                    revision = uuid4()
                    conn.execute(
                        "INSERT INTO product_revisions VALUES (%s,%s,%s,%s,%s,1,'OPEN')",
                        (revision, corpus, record, input_sha, self.package.semantic_profile_sha),
                    )
                    for photo in product.photos:
                        conn.execute(
                            "INSERT INTO revision_photos(id,revision_id,ordinal,source_ref,input_sha,source_bytes,outcome) VALUES (%s,%s,%s,%s,%s,%s,'PENDING')",
                            (
                                uuid4(),
                                revision,
                                photo.ordinal,
                                photo.source_ref,
                                photo.input_sha,
                                photo.source_bytes,
                            ),
                        )
                    conn.execute(
                        "UPDATE replenishment_product_heads SET current_revision_id=%s,version=version+1 WHERE corpus_version_id=%s AND product_record_id=%s",
                        (revision, corpus, record),
                    )
                    ref = RevisionReference(str(revision), head[1] + 1, 1)
                refs.append(ref)
                selected.extend(
                    r[0]
                    for r in conn.execute(
                        "SELECT id FROM revision_photos WHERE revision_id=%s AND outcome='PENDING' ORDER BY ordinal",
                        (uuid(ref.revision_ref),),
                    )
                )
            conn.execute(
                "UPDATE replenishment_runs SET inventory_bound=true,selected_photo_ids=%s,revision_ids=%s WHERE id=%s",
                (selected[:5], [uuid(r.revision_ref) for r in refs], uuid(owner.run_ref)),
            )
        return tuple(refs)

    def read_queue(self, owner):
        with self._transaction() as conn:
            run = self._fence(conn, owner)
            if not run[4]:
                raise ReplenishmentError("INVENTORY_NOT_BOUND")
            rows = conn.execute(
                """SELECT p.id,p.revision_id,r.semantic_profile_sha,p.source_bytes,p.outcome,h.version,r.version
                FROM revision_photos p JOIN product_revisions r ON r.id=p.revision_id
                JOIN replenishment_product_heads h ON h.corpus_version_id=r.corpus_version_id AND h.product_record_id=r.product_record_id
                WHERE p.id=ANY(%s::uuid[]) AND h.current_revision_id=r.id ORDER BY r.corpus_version_id,r.product_record_id,p.ordinal""",
                (run[5],),
            ).fetchall()
            if len(rows) != len(run[5]):
                raise ReplenishmentError("REVISION_SUPERSEDED")
            return tuple(
                PhotoWork(str(p), str(r), profile, size, PhotoOutcome(outcome), hv, rv)
                for p, r, profile, size, outcome, hv, rv in rows
            )

    def _lock_photo(self, conn, owner, photo_ref, revision_ref, head_version, revision_version):
        run = self._fence(conn, owner)
        photo_id = uuid(photo_ref)
        if photo_id not in run[5]:
            raise ReplenishmentError("INVALID_SCOPE")
        revision_id = uuid(revision_ref)
        relation = conn.execute(
            "SELECT corpus_version_id,product_record_id FROM product_revisions WHERE id=%s",
            (revision_id,),
        ).fetchone()
        if relation is None:
            raise ReplenishmentError("VERSION_CONFLICT")
        head = conn.execute(
            "SELECT current_revision_id,version FROM replenishment_product_heads WHERE corpus_version_id=%s AND product_record_id=%s FOR UPDATE",
            relation,
        ).fetchone()
        if head[0] != revision_id:
            raise ReplenishmentError("REVISION_SUPERSEDED")
        if head[1] != head_version:
            raise ReplenishmentError("VERSION_CONFLICT")
        revision = conn.execute(
            "SELECT version,state,semantic_profile_sha FROM product_revisions WHERE id=%s FOR UPDATE",
            (revision_id,),
        ).fetchone()
        if revision[0] != revision_version:
            raise ReplenishmentError("VERSION_CONFLICT")
        if revision[1] != "OPEN" or revision[2] != self.package.semantic_profile_sha:
            raise ReplenishmentError("REVISION_IMMUTABLE")
        photo = conn.execute(
            "SELECT revision_id,outcome,input_sha,source_ref FROM revision_photos WHERE id=%s FOR UPDATE",
            (photo_id,),
        ).fetchone()
        if photo is None or photo[0] != revision_id:
            raise ReplenishmentError("VERSION_CONFLICT")
        return photo

    def begin_attempt(self, photo, stage, model, owner):
        if (stage, model) not in (
            ("localization", ""),
            *(("embedding", k) for k, _ in MODEL_DIMENSIONS),
        ):
            raise ReplenishmentError("INVALID_STAGE")
        with self._transaction() as conn:
            data = self._lock_photo(
                conn,
                owner,
                photo.photo_ref,
                photo.revision_ref,
                photo.head_version,
                photo.revision_version,
            )
            if data[1] in {"OK", "NO_NAILS", "ERROR"}:
                raise ReplenishmentError("PHOTO_TERMINAL")
            if data[1] != "PENDING":
                raise ReplenishmentError("RECOVERY_REQUIRED")
            prior = conn.execute(
                "SELECT state FROM stage_attempts WHERE photo_id=%s AND stage_key=%s AND model_key=%s ORDER BY attempt_no DESC LIMIT 1 FOR UPDATE",
                (uuid(photo.photo_ref), stage, model),
            ).fetchone()
            if prior and prior[0] == "COMPLETE":
                raise ReplenishmentError("CHECKPOINT_AVAILABLE")
            if prior and prior[0] == "RUNNING":
                raise ReplenishmentError("RECOVERY_REQUIRED")
            local_sha = None
            if stage == "embedding":
                row = conn.execute(
                    "SELECT c.manifest_sha,c.region_count FROM stage_attempts a JOIN stage_checkpoints c ON c.attempt_id=a.id WHERE a.photo_id=%s AND a.stage_key='localization' AND a.state='COMPLETE'",
                    (uuid(photo.photo_ref),),
                ).fetchone()
                if row is None or row[1] <= 0:
                    raise ReplenishmentError("PHOTO_INCOMPLETE")
                local_sha = row[0]
            number = conn.execute(
                "SELECT coalesce(max(attempt_no),0)+1 FROM stage_attempts WHERE photo_id=%s AND stage_key=%s AND model_key=%s",
                (uuid(photo.photo_ref), stage, model),
            ).fetchone()[0]
            attempt_id = uuid4()
            identity = digest(
                {
                    "schema_version": 1,
                    "attempt_id": str(attempt_id),
                    "input_sha": data[2],
                    "source_ref": data[3],
                    "semantic_profile_sha": self.package.semantic_profile_sha,
                    "stage_key": stage,
                    "model_key": model,
                    "localization_manifest_sha": local_sha,
                }
            )
            conn.execute(
                "INSERT INTO stage_attempts VALUES (%s,%s,%s,%s,%s,%s,'RUNNING',%s,1,%s)",
                (
                    attempt_id,
                    uuid(photo.photo_ref),
                    stage,
                    model,
                    uuid(owner.run_ref),
                    owner.epoch,
                    number,
                    identity,
                ),
            )
            conn.execute(
                "UPDATE revision_photos SET outcome='RUNNING' WHERE id=%s", (uuid(photo.photo_ref),)
            )
        return StageAttempt(
            str(attempt_id),
            photo.photo_ref,
            stage,
            model,
            identity,
            photo.revision_ref,
            photo.head_version,
            photo.revision_version,
            1,
        )

    def _lock_attempt(self, conn, owner, attempt):
        self._lock_photo(
            conn,
            owner,
            attempt.photo_ref,
            attempt.revision_ref,
            attempt.head_version,
            attempt.revision_version,
        )
        row = conn.execute(
            "SELECT photo_id,stage_key,model_key,run_id,epoch,state,version,identity_sha FROM stage_attempts WHERE id=%s FOR UPDATE",
            (uuid(attempt.attempt_ref),),
        ).fetchone()
        if (
            row is None
            or row[:5]
            != (
                uuid(attempt.photo_ref),
                attempt.stage_key,
                attempt.model_key,
                uuid(owner.run_ref),
                owner.epoch,
            )
            or row[7] != attempt.identity_sha
        ):
            raise ReplenishmentError("FENCED")
        return row

    def read_stage_source(self, attempt, owner):
        """Private source DTO for the current fenced attempt, never a raw SQL row."""
        with self._transaction() as conn:
            row = self._lock_attempt(conn, owner, attempt)
            if row[5] != "RUNNING" or row[6] != attempt.expected_version:
                raise ReplenishmentError("VERSION_CONFLICT")
            source = conn.execute(
                "SELECT ordinal,source_ref,input_sha,source_bytes FROM revision_photos WHERE id=%s",
                (uuid(attempt.photo_ref),),
            ).fetchone()
            return SelectedPhoto(*source)

    def commit_checkpoint(self, attempt, output, owner):
        if (
            type(output.region_count) is not int
            or not 0 <= output.region_count <= self.package.max_regions
            or not re.fullmatch("[0-9a-f]{64}", output.manifest_sha)
            or not output.artifact_ref
        ):
            raise ReplenishmentError("CHECKPOINT_INVALID")
        with self._transaction() as conn:
            row = self._lock_attempt(conn, owner, attempt)
            receipt = conn.execute(
                "SELECT identity_sha,manifest_ref,manifest_sha,region_count FROM stage_checkpoints WHERE attempt_id=%s",
                (uuid(attempt.attempt_ref),),
            ).fetchone()
            expected = (
                attempt.identity_sha,
                output.artifact_ref,
                output.manifest_sha,
                output.region_count,
            )
            if receipt is not None:
                if receipt != expected:
                    raise ReplenishmentError("ARTIFACT_CONFLICT")
                if row[5] != "COMPLETE":
                    raise ReplenishmentError("CHECKPOINT_UNKNOWN")
                return CheckpointReceipt(attempt.attempt_ref, receipt[2])
            if row[6] != attempt.expected_version:
                raise ReplenishmentError("VERSION_CONFLICT")
            if row[5] != "RUNNING":
                raise ReplenishmentError("ATTEMPT_NOT_RUNNING")
            if attempt.stage_key == "embedding":
                local_count = conn.execute(
                    "SELECT c.region_count FROM stage_attempts a JOIN stage_checkpoints c ON c.attempt_id=a.id WHERE a.photo_id=%s AND a.stage_key='localization' AND a.state='COMPLETE'",
                    (uuid(attempt.photo_ref),),
                ).fetchone()[0]
                if local_count <= 0 or output.region_count != local_count:
                    raise ReplenishmentError("CHECKPOINT_INVALID")
            conn.execute(
                "INSERT INTO stage_checkpoints(attempt_id,identity_sha,manifest_ref,manifest_sha,profile_sha,region_count) VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    uuid(attempt.attempt_ref),
                    attempt.identity_sha,
                    output.artifact_ref,
                    output.manifest_sha,
                    self.package.semantic_profile_sha,
                    output.region_count,
                ),
            )
            conn.execute(
                "UPDATE stage_attempts SET state='COMPLETE',version=version+1 WHERE id=%s",
                (uuid(attempt.attempt_ref),),
            )
            conn.execute(
                "UPDATE revision_photos SET outcome='PENDING' WHERE id=%s",
                (uuid(attempt.photo_ref),),
            )
        return CheckpointReceipt(attempt.attempt_ref, output.manifest_sha)

    def fail_attempt(self, attempt, owner):
        with self._transaction() as conn:
            row = self._lock_attempt(conn, owner, attempt)
            if row[6] != attempt.expected_version:
                raise ReplenishmentError("VERSION_CONFLICT")
            if row[5] != "RUNNING":
                raise ReplenishmentError("ATTEMPT_NOT_RUNNING")
            conn.execute(
                "UPDATE stage_attempts SET state='ERROR',version=version+1 WHERE id=%s",
                (uuid(attempt.attempt_ref),),
            )

    def finish_photo(self, photo, outcome, owner):
        if outcome not in (PhotoOutcome.OK, PhotoOutcome.NO_NAILS, PhotoOutcome.ERROR):
            raise ReplenishmentError("INVALID_OUTCOME")
        with self._transaction() as conn:
            current = self._lock_photo(
                conn,
                owner,
                photo.photo_ref,
                photo.revision_ref,
                photo.head_version,
                photo.revision_version,
            )
            if current[1] in {"OK", "NO_NAILS", "ERROR"}:
                if current[1] == outcome:
                    return
                raise ReplenishmentError("PHOTO_TERMINAL")
            completed = conn.execute(
                "SELECT a.stage_key,a.model_key,c.region_count FROM stage_attempts a JOIN stage_checkpoints c ON c.attempt_id=a.id WHERE a.photo_id=%s AND a.state='COMPLETE'",
                (uuid(photo.photo_ref),),
            ).fetchall()
            counts = {(stage, model): count for stage, model, count in completed}
            local = counts.get(("localization", ""))
            if outcome == PhotoOutcome.NO_NAILS and (local != 0 or len(counts) != 1):
                raise ReplenishmentError("PHOTO_INCOMPLETE")
            if outcome == PhotoOutcome.OK and (
                local is None
                or local <= 0
                or len(counts) != 4
                or any(counts.get(("embedding", model)) != local for model, _ in MODEL_DIMENSIONS)
            ):
                raise ReplenishmentError("PHOTO_INCOMPLETE")
            if (
                outcome == PhotoOutcome.ERROR
                and not conn.execute(
                    "SELECT 1 FROM stage_attempts WHERE photo_id=%s AND state='ERROR' LIMIT 1",
                    (uuid(photo.photo_ref),),
                ).fetchone()
            ):
                raise ReplenishmentError("PHOTO_INCOMPLETE")
            conn.execute(
                "UPDATE revision_photos SET outcome=%s,error_code=%s WHERE id=%s",
                (
                    str(outcome),
                    "PHOTO_ERROR" if outcome == PhotoOutcome.ERROR else None,
                    uuid(photo.photo_ref),
                ),
            )

    def revision_outcomes(self, revision_ref):
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT outcome FROM revision_photos WHERE revision_id=%s ORDER BY ordinal",
                (uuid(revision_ref),),
            ).fetchall()
            return tuple(PhotoOutcome(r[0]) for r in rows)

    def _lock_revision(self, conn, revision, owner):
        run = self._fence(conn, owner)
        ref = uuid(revision.revision_ref)
        if ref not in run[6]:
            raise ReplenishmentError("INVALID_SCOPE")
        identity = conn.execute(
            "SELECT corpus_version_id,product_record_id FROM product_revisions WHERE id=%s", (ref,)
        ).fetchone()
        if identity is None:
            raise ReplenishmentError("VERSION_CONFLICT")
        head = conn.execute(
            "SELECT current_revision_id,version FROM replenishment_product_heads WHERE corpus_version_id=%s AND product_record_id=%s FOR UPDATE",
            identity,
        ).fetchone()
        if head[0] != ref:
            raise ReplenishmentError("REVISION_SUPERSEDED")
        if head[1] != revision.head_version:
            raise ReplenishmentError("VERSION_CONFLICT")
        row = conn.execute(
            "SELECT version,state,semantic_profile_sha FROM product_revisions WHERE id=%s FOR UPDATE",
            (ref,),
        ).fetchone()
        if row[0] != revision.revision_version:
            raise ReplenishmentError("VERSION_CONFLICT")
        if row[2] != self.package.semantic_profile_sha:
            raise ReplenishmentError("PROFILE_MISMATCH")
        self._profile(conn)
        return identity, row[1]

    def _revision_sources(self, conn, revision_ref):
        photos = conn.execute(
            "SELECT id,outcome FROM revision_photos WHERE revision_id=%s ORDER BY ordinal",
            (uuid(revision_ref),),
        ).fetchall()
        readiness = product_readiness(tuple(PhotoOutcome(outcome) for _, outcome in photos))
        if readiness != "READY":
            raise ReplenishmentError(
                "NOT_PUBLISHABLE" if readiness == "NOT_PUBLISHABLE" else "REVISION_INCOMPLETE"
            )
        rows = conn.execute(
            """SELECT a.id,p.id,a.stage_key,a.model_key,a.identity_sha,a.version,
            c.manifest_ref,c.manifest_sha,c.region_count,c.profile_sha
            FROM revision_photos p JOIN stage_attempts a ON a.photo_id=coalesce(p.reused_from,p.id)
            JOIN stage_checkpoints c ON c.attempt_id=a.id
            WHERE p.revision_id=%s AND a.state='COMPLETE' ORDER BY p.ordinal,a.stage_key,a.model_key""",
            (uuid(revision_ref),),
        ).fetchall()
        sources = []
        for photo, outcome in photos:
            complete = [r for r in rows if r[1] == photo]
            keys = {(r[2], r[3]): r[8] for r in complete}
            count = keys.get(("localization", ""))
            if outcome == "OK":
                if (
                    count is None
                    or not 0 < count <= self.package.max_regions
                    or len(complete) != 4
                    or any(keys.get(("embedding", model)) != count for model, _ in MODEL_DIMENSIONS)
                ):
                    raise ReplenishmentError("REVISION_INCOMPLETE")
                if any(r[9] != self.package.semantic_profile_sha for r in complete):
                    raise ReplenishmentError("PROFILE_MISMATCH")
                sources.extend(complete)
            elif outcome == "NO_NAILS":
                if keys != {("localization", ""): 0} or len(complete) != 1:
                    raise ReplenishmentError("REVISION_INCOMPLETE")
            elif not conn.execute(
                "SELECT 1 FROM stage_attempts WHERE photo_id=(SELECT coalesce(reused_from,id) FROM revision_photos WHERE id=%s) AND state='ERROR' LIMIT 1",
                (photo,),
            ).fetchone():
                raise ReplenishmentError("REVISION_INCOMPLETE")
        return tuple(sources)

    def _validate_ready(self, conn, revision_ref):
        sources = self._revision_sources(conn, revision_ref)
        expected = {
            (r[1], ordinal)
            for r in sources
            if r[2] == "localization"
            for ordinal in range(1, r[8] + 1)
        }
        regions = set(
            conn.execute(
                "SELECT g.revision_photo_id,g.region_ordinal FROM revision_regions g JOIN revision_photos p ON p.id=g.revision_photo_id WHERE p.revision_id=%s",
                (uuid(revision_ref),),
            ).fetchall()
        )
        vectors = set(
            conn.execute(
                "SELECT v.revision_photo_id,v.region_ordinal,v.model_key,vector_dims(v.vector) FROM revision_vectors v JOIN revision_photos p ON p.id=v.revision_photo_id WHERE p.revision_id=%s",
                (uuid(revision_ref),),
            ).fetchall()
        )
        wanted = {
            (photo, ordinal, model, dim)
            for photo, ordinal in expected
            for model, dim in MODEL_DIMENSIONS
        }
        if regions != expected or vectors != wanted:
            raise ReplenishmentError("REVISION_INCOMPLETE")

    def prepare_revision(self, revision, owner, artifacts):
        with self._transaction() as conn:
            _, state = self._lock_revision(conn, revision, owner)
            if state == "READY":
                self._validate_ready(conn, revision.revision_ref)
                return revision
            if state == "NOT_PUBLISHABLE":
                raise ReplenishmentError("NOT_PUBLISHABLE")
            if state != "OPEN":
                raise ReplenishmentError("REVISION_NOT_OPEN")
            try:
                sources = self._revision_sources(conn, revision.revision_ref)
            except ReplenishmentError as error:
                if str(error) != "NOT_PUBLISHABLE":
                    raise
                conn.execute(
                    "UPDATE product_revisions SET state='NOT_PUBLISHABLE',version=version+1 WHERE id=%s",
                    (uuid(revision.revision_ref),),
                )
                sources = None
        if sources is None:
            raise ReplenishmentError("NOT_PUBLISHABLE")
        # Files are verified outside SQL locks; the immutable receipts and current root
        # are rechecked before writing any materialized result.
        regions, vectors = [], []
        for row in sources:
            self._sql_budget()
            (
                attempt,
                photo,
                stage,
                model,
                identity,
                version,
                manifest_ref,
                manifest_sha,
                count,
                _,
            ) = row
            work = StageAttempt(
                str(attempt),
                str(photo),
                stage,
                model,
                identity,
                revision.revision_ref,
                revision.head_version,
                revision.revision_version,
                version,
            )
            output = StageOutput(manifest_ref, manifest_sha, count)
            data = artifacts.read_files(work, output, self.package)
            if stage == "localization":
                for ordinal in range(1, count + 1):
                    crop = f"crop-{ordinal}.png"
                    regions.append(
                        (
                            photo,
                            ordinal,
                            f"{manifest_ref}/mask-{ordinal}.png",
                            f"{manifest_ref}/{crop}",
                            hashlib.sha256(data[crop]).hexdigest(),
                        )
                    )
            else:
                for item in json.loads(data["vectors.json"])["vectors"]:
                    vectors.append(
                        (photo, item["ordinal"], model, json.dumps(item["values"], allow_nan=False))
                    )
        with self._transaction() as conn:
            _, state = self._lock_revision(conn, revision, owner)
            if state != "OPEN" or self._revision_sources(conn, revision.revision_ref) != sources:
                raise ReplenishmentError("VERSION_CONFLICT")
            conn.execute(
                "UPDATE product_revisions SET state='PREPARED',version=version+1 WHERE id=%s",
                (uuid(revision.revision_ref),),
            )
            for row in regions:
                self._sql_budget()
                conn.execute("INSERT INTO revision_regions VALUES (%s,%s,%s,%s,%s)", row)
            for row in vectors:
                self._sql_budget()
                conn.execute("INSERT INTO revision_vectors VALUES (%s,%s,%s,%s::vector)", row)
            self._validate_ready(conn, revision.revision_ref)
            conn.execute(
                "UPDATE product_revisions SET state='READY',version=version+1 WHERE id=%s",
                (uuid(revision.revision_ref),),
            )
        return RevisionReference(
            revision.revision_ref, revision.head_version, revision.revision_version + 2
        )

    @staticmethod
    def _snapshot_content(profile, members):
        return digest(
            {
                "semantic_profile_sha": profile,
                "members": [
                    {"product_record_id": product, "revision_id": str(revision)}
                    for product, revision in sorted(members.items())
                ],
            }
        )

    @staticmethod
    def _read_publication(conn, attempt_ref):
        row = conn.execute(
            """SELECT a.revision_id,a.state,a.error_code,r.snapshot_id
            FROM publication_attempts a LEFT JOIN revision_publications r
            ON r.revision_id=a.revision_id WHERE a.id=%s""",
            (uuid(attempt_ref),),
        ).fetchone()
        if row is None:
            raise ReplenishmentError("NOT_FOUND")
        revision, state, error, snapshot = row
        # A later successful manual attempt does not turn an older FAILED into a success.
        if state != "FAILED" and snapshot is not None:
            return PublicationReceipt(attempt_ref, str(revision), str(snapshot), "SUCCEEDED")
        if state == "RUNNING":
            state, error = "UNKNOWN", "COMMIT_UNKNOWN"
        return PublicationReceipt(attempt_ref, str(revision), None, state, error)

    def reconcile_publication(self, attempt_ref):
        with self._transaction() as conn:
            return self._read_publication(conn, attempt_ref)

    def publish_revision(self, revision, expected_active, owner):
        expected = uuid(expected_active) if expected_active is not None else None
        attempt = uuid4()
        try:
            with self._transaction() as conn:
                _, state = self._lock_revision(conn, revision, owner)
                if state != "READY":
                    raise ReplenishmentError("REVISION_NOT_READY")
                self._validate_ready(conn, revision.revision_ref)
                existing = conn.execute(
                    "SELECT id FROM publication_attempts WHERE revision_id=%s AND state='SUCCEEDED' ORDER BY id LIMIT 1",
                    (uuid(revision.revision_ref),),
                ).fetchone()
                if existing:
                    return self._read_publication(conn, str(existing[0]))
                failed = conn.execute(
                    "SELECT id FROM publication_attempts WHERE revision_id=%s AND run_id=%s AND state='FAILED' ORDER BY id LIMIT 1",
                    (uuid(revision.revision_ref), uuid(owner.run_ref)),
                ).fetchone()
                if failed:
                    return self._read_publication(conn, str(failed[0]))
                unresolved = conn.execute(
                    "SELECT id FROM publication_attempts WHERE revision_id=%s AND state IN ('RUNNING','UNKNOWN') LIMIT 1",
                    (uuid(revision.revision_ref),),
                ).fetchone()
                if unresolved:
                    # Reconcile first; no automatic second activation attempt.
                    return self._read_publication(conn, str(unresolved[0]))
                conn.execute(
                    "INSERT INTO publication_attempts(id,revision_id,run_id,epoch,expected_active,state) VALUES (%s,%s,%s,%s,%s,'RUNNING')",
                    (
                        attempt,
                        uuid(revision.revision_ref),
                        uuid(owner.run_ref),
                        owner.epoch,
                        expected,
                    ),
                )
        except ReplenishmentError as error:
            if str(error) != "COMMIT_UNKNOWN":
                raise
            return PublicationReceipt(
                str(attempt), revision.revision_ref, None, "UNKNOWN", "COMMIT_UNKNOWN"
            )
        try:
            return self._activate_publication(str(attempt), revision, expected, owner)
        except ReplenishmentError as error:
            state = "UNKNOWN" if str(error) == "COMMIT_UNKNOWN" else "FAILED"
            try:
                with self._transaction() as conn:
                    receipt = self._read_publication(conn, str(attempt))
                    if receipt.state == "SUCCEEDED":
                        return receipt
                    self._fence(conn, owner, allow_terminal_audit=True)
                    conn.execute(
                        "UPDATE publication_attempts SET state=%s,error_code=%s WHERE id=%s AND state='RUNNING'",
                        (state, str(error), attempt),
                    )
            except ReplenishmentError:
                return PublicationReceipt(
                    str(attempt), revision.revision_ref, None, "UNKNOWN", "COMMIT_UNKNOWN"
                )
            return PublicationReceipt(str(attempt), revision.revision_ref, None, state, str(error))

    def _activate_publication(self, attempt_ref, revision, expected_active, owner):
        with self._transaction() as conn:
            (_, product), state = self._lock_revision(conn, revision, owner)
            if state != "READY":
                raise ReplenishmentError("REVISION_NOT_READY")
            self._validate_ready(conn, revision.revision_ref)
            active = conn.execute(
                "SELECT snapshot_id,version FROM active_catalog_snapshots WHERE mode_key='nail-search-v1' FOR UPDATE"
            ).fetchone()
            current = active[0] if active else None
            if current != expected_active:
                raise ReplenishmentError("ACTIVE_CONFLICT")
            attempt = conn.execute(
                "SELECT revision_id,run_id,epoch,expected_active,state FROM publication_attempts WHERE id=%s FOR UPDATE",
                (uuid(attempt_ref),),
            ).fetchone()
            if attempt != (
                uuid(revision.revision_ref),
                uuid(owner.run_ref),
                owner.epoch,
                expected_active,
                "RUNNING",
            ):
                raise ReplenishmentError("VERSION_CONFLICT")
            members = {}
            if current:
                snapshot = conn.execute(
                    "SELECT semantic_profile_sha,content_sha,state FROM catalog_snapshots WHERE id=%s",
                    (current,),
                ).fetchone()
                if snapshot[0] != self.package.semantic_profile_sha:
                    raise ReplenishmentError("PROFILE_MISMATCH")
                members = dict(
                    conn.execute(
                        "SELECT product_record_id,revision_id FROM catalog_snapshot_members WHERE snapshot_id=%s ORDER BY product_record_id",
                        (current,),
                    ).fetchall()
                )
                if snapshot[2] != "READY" or snapshot[1] != self._snapshot_content(
                    snapshot[0], members
                ):
                    raise ReplenishmentError("CATALOG_INVALID")
            members[product] = uuid(revision.revision_ref)
            for member in members.values():
                self._sql_budget()
                row = conn.execute(
                    "SELECT state,semantic_profile_sha FROM product_revisions WHERE id=%s",
                    (member,),
                ).fetchone()
                if row != ("READY", self.package.semantic_profile_sha):
                    raise ReplenishmentError("PROFILE_MISMATCH")
                self._validate_ready(conn, str(member))
            snapshot = uuid4()
            conn.execute(
                "INSERT INTO catalog_snapshots VALUES (%s,%s,%s,'PREPARED')",
                (
                    snapshot,
                    self.package.semantic_profile_sha,
                    self._snapshot_content(self.package.semantic_profile_sha, members),
                ),
            )
            for key, value in sorted(members.items()):
                self._sql_budget()
                conn.execute(
                    "INSERT INTO catalog_snapshot_members VALUES (%s,%s,%s)", (snapshot, key, value)
                )
            conn.execute("UPDATE catalog_snapshots SET state='READY' WHERE id=%s", (snapshot,))
            conn.execute(
                "INSERT INTO revision_publications(revision_id,snapshot_id,run_id) VALUES (%s,%s,%s)",
                (uuid(revision.revision_ref), snapshot, uuid(owner.run_ref)),
            )
            conn.execute(
                "UPDATE publication_attempts SET state='SUCCEEDED',receipt_id=%s,error_code=NULL WHERE id=%s",
                (snapshot, uuid(attempt_ref)),
            )
            if active:
                conn.execute(
                    "UPDATE active_catalog_snapshots SET snapshot_id=%s,version=version+1 WHERE mode_key='nail-search-v1'",
                    (snapshot,),
                )
            else:
                conn.execute(
                    "INSERT INTO active_catalog_snapshots VALUES ('nail-search-v1',%s,1)",
                    (snapshot,),
                )
        return PublicationReceipt(attempt_ref, revision.revision_ref, str(snapshot), "SUCCEEDED")

    @staticmethod
    def _snapshot_profile(payload):
        try:
            if payload["schema_version"] != 1:
                raise ReplenishmentError("PROFILE_MISMATCH")
            return SnapshotEmbeddingProfile(
                payload["crop_version"],
                tuple(
                    (m["model_key"], m["dimension"], m["revision"], m["preprocessing"], m["dtype"])
                    for m in payload["models"]
                ),
            )
        except (KeyError, TypeError, ValueError):
            raise ReplenishmentError("PROFILE_MISMATCH") from None

    def _read_snapshot_header(self, conn, descriptor):
        if not isinstance(descriptor, SnapshotDescriptor):
            raise ReplenishmentError("INVALID_SNAPSHOT")
        row = conn.execute(
            "SELECT semantic_profile_sha,content_sha,state FROM catalog_snapshots WHERE id=%s",
            (uuid(descriptor.snapshot_ref),),
        ).fetchone()
        if row != (descriptor.semantic_profile_sha, descriptor.content_sha, "READY"):
            raise ReplenishmentError("CATALOG_MISMATCH")
        # The SQL budget package must also refer to this profile; no silent cross-profile read.
        if self.package.semantic_profile_sha != descriptor.semantic_profile_sha:
            raise ReplenishmentError("PROFILE_MISMATCH")
        members = dict(
            conn.execute(
                "SELECT product_record_id,revision_id FROM catalog_snapshot_members WHERE snapshot_id=%s ORDER BY product_record_id",
                (uuid(descriptor.snapshot_ref),),
            ).fetchall()
        )
        if (
            self._snapshot_content(descriptor.semantic_profile_sha, members)
            != descriptor.content_sha
        ):
            raise ReplenishmentError("CATALOG_MISMATCH")
        if not members:
            raise ReplenishmentError("INDEX_EMPTY")
        for revision in members.values():
            self._sql_budget()
            data = conn.execute(
                "SELECT state,semantic_profile_sha FROM product_revisions WHERE id=%s", (revision,)
            ).fetchone()
            if data != ("READY", descriptor.semantic_profile_sha):
                raise ReplenishmentError("PROFILE_MISMATCH")
            self._validate_ready(conn, str(revision))
        payload = self._profile(conn)
        return payload

    def resolve_active(self, mode):
        if mode != "nail-search-v1":
            raise ReplenishmentError("INVALID_SCOPE")
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT s.id,s.content_sha,s.semantic_profile_sha FROM active_catalog_snapshots a JOIN catalog_snapshots s ON s.id=a.snapshot_id WHERE a.mode_key=%s AND s.state='READY'",
                (mode,),
            ).fetchone()
            if row is None:
                raise ReplenishmentError("INDEX_NOT_READY")
            descriptor = SnapshotDescriptor(str(row[0]), row[1], row[2])
            self._read_snapshot_header(conn, descriptor)
            return descriptor

    def read_snapshot_profile(self, descriptor):
        with self._transaction() as conn:
            return self._snapshot_profile(self._read_snapshot_header(conn, descriptor))

    def read_snapshot(self, descriptor):
        from product_search.search.nail_contracts import (
            CatalogPhoto,
            CatalogProduct,
            NailProcessingError,
            PhotoEmbeddings,
        )

        try:
            with self._transaction() as conn:
                self._read_snapshot_header(conn, descriptor)
                with conn.cursor(name="snapshot_photo_groups") as cursor:
                    cursor.execute(
                        """SELECT m.product_record_id,p.id,p.ordinal,p.input_sha,v.region_ordinal,v.model_key,v.vector::text
                        FROM catalog_snapshot_members m JOIN revision_photos p ON p.revision_id=m.revision_id
                        JOIN revision_vectors v ON v.revision_photo_id=p.id
                        WHERE m.snapshot_id=%s AND p.outcome='OK'
                        ORDER BY m.product_record_id,p.ordinal,v.region_ordinal,
                        CASE v.model_key WHEN 'openclip_b32' THEN 0 WHEN 'dinov2_b14' THEN 1 ELSE 2 END""",
                        (uuid(descriptor.snapshot_ref),),
                    )
                    for product, product_rows in groupby(cursor, key=lambda r: r[0]):
                        self._sql_budget()
                        photos = []
                        for photo, photo_rows in groupby(product_rows, key=lambda r: r[1]):
                            self._sql_budget()
                            rows = list(photo_rows)
                            ordinals = tuple(sorted({r[4] for r in rows}))
                            vectors = tuple(
                                (key, tuple(tuple(json.loads(r[6])) for r in rows if r[5] == key))
                                for key, _ in MODEL_DIMENSIONS
                            )
                            photos.append(
                                CatalogPhoto(
                                    str(photo),
                                    PhotoEmbeddings(rows[0][2], rows[0][3], ordinals, vectors),
                                )
                            )
                        yield CatalogProduct(product, tuple(photos))
        except (NailProcessingError, ValueError, TypeError) as error:
            if isinstance(error, ReplenishmentError):
                raise
            raise ReplenishmentError("CATALOG_INVALID") from None

    def bind_snapshot(
        self,
        descriptor,
        photos,
        claim,
        *,
        expected_claim_sha,
        expected_runtime,
        observe_runtime,
        expected_runtime_sha,
        expected_code_sha,
        expected_model_sha,
        max_solver_states,
    ):
        from product_search.infrastructure.nail_build_composition import RuntimeVerifier
        from product_search.infrastructure.nail_build_runner import BuildStop

        profile = self.read_snapshot_profile(descriptor)
        try:
            if (
                not isinstance(claim, SnapshotQueryClaim)
                or digest(asdict(claim)) != expected_claim_sha
            ):
                raise ReplenishmentError("CLAIM_MISMATCH")
            self._sql_budget()
            try:
                observation = observe_runtime()
            except Exception:  # noqa: BLE001 -- a failed independent observation closes admission.
                raise ReplenishmentError("RUNTIME_MISMATCH") from None
            verifier = RuntimeVerifier(expected_runtime, lambda: observation["runtime"])
            if not verifier.verify() or digest(observation) != expected_runtime_sha:
                raise ReplenishmentError("RUNTIME_MISMATCH")
            if (
                observation["runtime"]["backend_inventory_sha256"] != expected_code_sha
                or digest(observation["runtime"]["models"]) != expected_model_sha
                or self._snapshot_profile(observation["embedding_profile"]) != profile
                or digest(observation["embedding_profile"]) != descriptor.semantic_profile_sha
                or tuple((m[0], m[3], m[1]) for m in observation["runtime"]["models"])
                != tuple((m[0], m[1], m[2]) for m in profile.models)
            ):
                raise ReplenishmentError("RUNTIME_MISMATCH")
            runtime = SnapshotRuntimeIdentity(
                expected_runtime_sha,
                expected_code_sha,
                expected_model_sha,
                observation["runtime"]["extractor_fingerprint"],
                observation["runtime"]["mode"],
                profile,
            )
            binding = VerifiedCatalogBinding(descriptor, profile, runtime, claim, max_solver_states)
            from product_search.search.replenishment_contracts import SnapshotSearchRequest

            SnapshotSearchRequest(photos, binding)
            self._sql_budget()
            return binding
        except (BuildStop, KeyError, TypeError, ValueError) as error:
            if isinstance(error, ReplenishmentError):
                raise
            raise ReplenishmentError("RUNTIME_MISMATCH") from None

    def finish_run(self, owner, reason):
        states = {
            "COMPLETED": "COMPLETED",
            "DEADLINE": "EXPIRED",
            "RESOURCE_STOP": "STOPPED",
            "WAIT_TIMEOUT": "STOPPED",
            "ADMISSION_LIMIT": "STOPPED",
            "RECOVERY_REQUIRED": "FAILED",
        }
        if reason not in states:
            raise ReplenishmentError("INVALID_INPUT")
        # Only termination audit may use the cleanup reserve; never checkpoints/publication.
        with self._transaction(cleanup=True) as conn:
            self._fence(conn, owner)
            conn.execute(
                "UPDATE replenishment_runs SET status=%s,reason=%s,finished_at=now() WHERE id=%s",
                (states[reason], reason, uuid(owner.run_ref)),
            )

    def read_summary(self, run_ref, *, search_state):
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT status,reason,selected_photo_ids,revision_ids FROM replenishment_runs WHERE id=%s",
                (uuid(run_ref),),
            ).fetchone()
            if row is None:
                raise ReplenishmentError("NOT_FOUND")
            outcomes = conn.execute(
                "SELECT id,outcome FROM revision_photos WHERE id=ANY(%s::uuid[]) ORDER BY array_position(%s::uuid[],id)",
                (row[2], row[2]),
            ).fetchall()
            completed = set(
                conn.execute(
                    "SELECT photo_id,stage_key,model_key FROM stage_attempts WHERE photo_id=ANY(%s::uuid[]) AND state='COMPLETE'",
                    (row[2],),
                ).fetchall()
            )
            stages = (
                ("localization", ""),
                *(("embedding", model) for model, _ in MODEL_DIMENSIONS),
            )
            remaining = [
                [str(photo), stage, model]
                for photo, outcome in outcomes
                if outcome in {"PENDING", "RUNNING"}
                for stage, model in stages
                if (photo, stage, model) not in completed
            ]
            publications = []
            for revision, state, error, snapshot, published_run in conn.execute(
                "SELECT a.revision_id,a.state,a.error_code,r.snapshot_id,r.run_id FROM publication_attempts a LEFT JOIN revision_publications r ON r.revision_id=a.revision_id WHERE a.run_id=%s ORDER BY a.revision_id",
                (uuid(run_ref),),
            ):
                if snapshot is not None and published_run == uuid(run_ref) and state != "FAILED":
                    state, error = "SUCCEEDED", None
                if state == "RUNNING":
                    state, error = "UNKNOWN", "COMMIT_UNKNOWN"
                publications.append(
                    {
                        "revision_ref": str(revision),
                        "snapshot_ref": str(snapshot)
                        if state == "SUCCEEDED" and snapshot
                        else None,
                        "state": state,
                        "error_code": error,
                    }
                )
            seen = {p["revision_ref"] for p in publications}
            for revision, snapshot in conn.execute(
                "SELECT revision_id,snapshot_id FROM revision_publications WHERE revision_id=ANY(%s::uuid[])",
                (row[3],),
            ):
                if str(revision) not in seen:
                    publications.append(
                        {
                            "revision_ref": str(revision),
                            "snapshot_ref": str(snapshot),
                            "state": "SUCCEEDED",
                            "error_code": None,
                        }
                    )
            products = []
            for revision in row[3]:
                photos = conn.execute(
                    "SELECT id,outcome FROM revision_photos WHERE revision_id=%s ORDER BY ordinal",
                    (revision,),
                ).fetchall()
                readiness = product_readiness(tuple(PhotoOutcome(p[1]) for p in photos))
                attempts = [p["state"] for p in publications if p["revision_ref"] == str(revision)]
                state = (
                    "PUBLISHED"
                    if "SUCCEEDED" in attempts
                    else "PUBLICATION_UNKNOWN"
                    if "UNKNOWN" in attempts
                    else "PUBLICATION_FAILED"
                    if "FAILED" in attempts
                    else "WAITING_PHOTOS"
                    if readiness == "WAITING"
                    else readiness
                )
                products.append(
                    {
                        "revision_ref": str(revision),
                        "state": state,
                        "remaining_photo_refs": [
                            str(p) for p, outcome in photos if outcome in {"PENDING", "RUNNING"}
                        ],
                    }
                )
            return {
                "run_ref": run_ref,
                "status": row[0],
                "reason": row[1],
                "selected_photo_refs": [str(p) for p in row[2]],
                "revision_refs": [str(r) for r in row[3]],
                "outcomes": [[str(p), outcome] for p, outcome in outcomes],
                "publications": publications,
                "remaining_stages": remaining,
                "products": products,
                "search_state": search_state,
            }

    def lookup_checkpoint(self, photo, stage, model, owner):
        with self._transaction() as conn:
            data = self._lock_photo(
                conn,
                owner,
                photo.photo_ref,
                photo.revision_ref,
                photo.head_version,
                photo.revision_version,
            )
            row = conn.execute(
                """SELECT a.id,a.identity_sha,a.version,c.identity_sha,c.manifest_ref,c.manifest_sha,c.region_count,c.profile_sha
                FROM stage_attempts a JOIN stage_checkpoints c ON c.attempt_id=a.id
                WHERE a.photo_id=%s AND a.stage_key=%s AND a.model_key=%s AND a.state='COMPLETE' """,
                (uuid(photo.photo_ref), stage, model),
            ).fetchone()
            if row is None:
                return None
            local_sha = None
            if stage == "embedding":
                local = conn.execute(
                    "SELECT c.manifest_sha FROM stage_attempts a JOIN stage_checkpoints c ON c.attempt_id=a.id WHERE a.photo_id=%s AND a.stage_key='localization' AND a.state='COMPLETE'",
                    (uuid(photo.photo_ref),),
                ).fetchone()
                if local is None:
                    raise ReplenishmentError("CHECKPOINT_INVALID")
                local_sha = local[0]
            expected = digest(
                {
                    "schema_version": 1,
                    "attempt_id": str(row[0]),
                    "input_sha": data[2],
                    "source_ref": data[3],
                    "semantic_profile_sha": self.package.semantic_profile_sha,
                    "stage_key": stage,
                    "model_key": model,
                    "localization_manifest_sha": local_sha,
                }
            )
            if (
                row[1] != expected
                or row[3] != expected
                or row[7] != self.package.semantic_profile_sha
            ):
                raise ReplenishmentError("CHECKPOINT_INVALID")
            attempt = StageAttempt(
                str(row[0]),
                photo.photo_ref,
                stage,
                model,
                row[1],
                photo.revision_ref,
                photo.head_version,
                photo.revision_version,
                row[2],
            )
            output = StageOutput(row[4], row[5], row[6])
            return SavedCheckpoint(attempt, output, CheckpointReceipt(str(row[0]), row[5]))

    def _resume_inventory(self, conn, run_ref):
        saved = conn.execute(
            "SELECT inventory_bound,selected_photo_ids,revision_ids FROM replenishment_runs WHERE id=%s",
            (uuid(run_ref),),
        ).fetchone()
        if saved is None or not saved[0]:
            raise ReplenishmentError("NOT_FOUND")
        products = []
        refs = []
        for revision in saved[2]:
            row = conn.execute(
                """SELECT r.corpus_version_id,r.product_record_id,r.semantic_profile_sha,r.version,h.current_revision_id,h.version
                FROM product_revisions r JOIN replenishment_product_heads h ON h.corpus_version_id=r.corpus_version_id AND h.product_record_id=r.product_record_id WHERE r.id=%s""",
                (revision,),
            ).fetchone()
            if row is None or row[4] != revision:
                raise ReplenishmentError("REVISION_SUPERSEDED")
            if row[2] != self.package.semantic_profile_sha:
                raise ReplenishmentError("PROFILE_MISMATCH")
            photos = tuple(
                SelectedPhoto(*p)
                for p in conn.execute(
                    "SELECT ordinal,source_ref,input_sha,source_bytes FROM revision_photos WHERE revision_id=%s ORDER BY ordinal",
                    (revision,),
                )
            )
            products.append(SelectedProduct(row[0], row[1], row[5], photos))
            refs.append(RevisionReference(str(revision), row[5], row[3]))
        products = tuple(sorted(products, key=lambda p: (p.corpus_version_id, p.product_record_id)))
        self.validate_inventory(products)
        return products, tuple(refs), saved[1], saved[2]

    def read_resume_inventory(self, run_ref):
        with self._transaction() as conn:
            products, refs, _, _ = self._resume_inventory(conn, run_ref)
            return products, refs

    def bind_resume(self, owner, run_ref, revisions):
        with self._transaction() as conn:
            run = self._fence(conn, owner)
            if run[4] or owner.run_ref == run_ref:
                raise ReplenishmentError("INVALID_SCOPE")
            _, current, photos, refs = self._resume_inventory(conn, run_ref)
            if current != revisions:
                raise ReplenishmentError("VERSION_CONFLICT")
            conn.execute(
                "UPDATE replenishment_runs SET inventory_bound=true,selected_photo_ids=%s,revision_ids=%s WHERE id=%s",
                (photos, refs, uuid(owner.run_ref)),
            )
            for revision in revisions:
                self._lock_revision(conn, revision, owner)
            running = conn.execute(
                "SELECT id,photo_id,epoch FROM stage_attempts WHERE photo_id=ANY(%s::uuid[]) AND state='RUNNING' FOR UPDATE",
                (photos,),
            ).fetchall()
            for attempt, photo, epoch in running:
                if (
                    epoch >= owner.epoch
                    or conn.execute(
                        "SELECT 1 FROM stage_checkpoints WHERE attempt_id=%s", (attempt,)
                    ).fetchone()
                ):
                    raise ReplenishmentError("CHECKPOINT_UNKNOWN")
                conn.execute(
                    "UPDATE stage_attempts SET state='INTERRUPTED',version=version+1 WHERE id=%s",
                    (attempt,),
                )
            conn.execute(
                "UPDATE revision_photos SET outcome='PENDING' WHERE id=ANY(%s::uuid[]) AND outcome='RUNNING'",
                (photos,),
            )
        return revisions

    def read_owner_epoch(self):
        with self._transaction() as conn:
            return conn.execute(
                "SELECT epoch FROM replenishment_owner WHERE singleton_key='local'"
            ).fetchone()[0]

    def _retry_inventory(self, conn, revision_ref, photo_ref=None, expected_version=None):
        row = conn.execute(
            """SELECT r.corpus_version_id,r.product_record_id,r.semantic_profile_sha,r.version,
            h.current_revision_id,h.version,r.state FROM product_revisions r
            JOIN replenishment_product_heads h ON h.corpus_version_id=r.corpus_version_id
            AND h.product_record_id=r.product_record_id WHERE r.id=%s""",
            (uuid(revision_ref),),
        ).fetchone()
        if row is None:
            raise ReplenishmentError("NOT_FOUND")
        if row[4] != uuid(revision_ref):
            raise ReplenishmentError("REVISION_SUPERSEDED")
        if row[2] != self.package.semantic_profile_sha:
            raise ReplenishmentError("PROFILE_MISMATCH")
        photos = conn.execute(
            "SELECT id,ordinal,source_ref,input_sha,source_bytes,outcome,error_code,reused_from FROM revision_photos WHERE revision_id=%s ORDER BY ordinal",
            (uuid(revision_ref),),
        ).fetchall()
        products = (
            SelectedProduct(row[0], row[1], row[5], tuple(SelectedPhoto(*p[1:5]) for p in photos)),
        )
        self.validate_inventory(products)
        if photo_ref is not None:
            if type(expected_version) is not int or expected_version <= 0:
                raise ReplenishmentError("INVALID_INPUT")
            if row[5] != expected_version:
                raise ReplenishmentError("VERSION_CONFLICT")
            ids = [str(p[0]) for p in photos]
            if photo_ref not in ids:
                raise ReplenishmentError("INVALID_SCOPE")
            retry_photo_outcomes(tuple(PhotoOutcome(p[5]) for p in photos), ids.index(photo_ref))
        elif row[6] != "READY":
            raise ReplenishmentError("REVISION_NOT_READY")
        return products, RevisionReference(revision_ref, row[5], row[3]), photos

    def read_retry_inventory(self, revision_ref, photo_ref=None, expected_version=None):
        with self._transaction() as conn:
            products, ref, _ = self._retry_inventory(
                conn, revision_ref, photo_ref, expected_version
            )
            return products, (ref,)

    def bind_retry_photo(self, owner, revision_ref, photo_ref, expected_version, refs):
        with self._transaction() as conn:
            run = self._fence(conn, owner)
            if run[4] or self.package.scope != "RETRY_PHOTO":
                raise ReplenishmentError("INVALID_SCOPE")
            self._lock_retry_head(conn, refs[0], owner, bind=True)
            products, old, photos = self._retry_inventory(
                conn, revision_ref, photo_ref, expected_version
            )
            if (old,) != refs:
                raise ReplenishmentError("VERSION_CONFLICT")
            product = products[0]
            revision = uuid4()
            conn.execute(
                "INSERT INTO product_revisions VALUES (%s,%s,%s,%s,%s,1,'OPEN')",
                (
                    revision,
                    product.corpus_version_id,
                    product.product_record_id,
                    digest([asdict(p) for p in product.photos]),
                    self.package.semantic_profile_sha,
                ),
            )
            selected = []
            for source, ordinal, source_ref, input_sha, size, outcome, error, reused in photos:
                chosen = str(source) == photo_ref
                new_photo = uuid4()
                conn.execute(
                    "INSERT INTO revision_photos(id,revision_id,ordinal,source_ref,input_sha,source_bytes,outcome,error_code,reused_from) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        new_photo,
                        revision,
                        ordinal,
                        source_ref,
                        input_sha,
                        size,
                        "PENDING" if chosen else outcome,
                        None if chosen else error,
                        None if chosen or outcome == "PENDING" else (reused or source),
                    ),
                )
                if chosen:
                    selected.append(new_photo)
            conn.execute(
                "UPDATE replenishment_product_heads SET current_revision_id=%s,version=version+1 WHERE corpus_version_id=%s AND product_record_id=%s AND version=%s",
                (revision, product.corpus_version_id, product.product_record_id, expected_version),
            )
            conn.execute(
                "UPDATE replenishment_runs SET inventory_bound=true,selected_photo_ids=%s,revision_ids=%s WHERE id=%s",
                (selected, [revision], uuid(owner.run_ref)),
            )
        return (RevisionReference(str(revision), expected_version + 1, 1),)

    def _lock_retry_head(self, conn, revision, owner, *, bind=False):
        if bind:
            conn.execute(
                "UPDATE replenishment_runs SET revision_ids=%s WHERE id=%s",
                ([uuid(revision.revision_ref)], uuid(owner.run_ref)),
            )
        return self._lock_revision(conn, revision, owner)

    def bind_retry_publication(self, owner, revision_ref, refs):
        with self._transaction() as conn:
            run = self._fence(conn, owner)
            if run[4] or self.package.scope != "RETRY_PUBLICATION":
                raise ReplenishmentError("INVALID_SCOPE")
            self._lock_retry_head(conn, refs[0], owner, bind=True)
            _, current, _ = self._retry_inventory(conn, revision_ref)
            if (current,) != refs:
                raise ReplenishmentError("VERSION_CONFLICT")
            self._validate_ready(conn, revision_ref)
            conn.execute(
                "UPDATE replenishment_runs SET inventory_bound=true WHERE id=%s",
                (uuid(owner.run_ref),),
            )
            # New epoch + physical quiescence fence every previous writer. Under
            # the owner/root locks, absence of a receipt now confirms rollback.
            receipt = conn.execute(
                "SELECT 1 FROM revision_publications WHERE revision_id=%s", (uuid(revision_ref),)
            ).fetchone()
            if not receipt:
                conn.execute(
                    "UPDATE publication_attempts SET state='FAILED',error_code='RECONCILED_ROLLBACK' WHERE revision_id=%s AND epoch<%s AND state IN ('RUNNING','UNKNOWN')",
                    (uuid(revision_ref), owner.epoch),
                )
        return refs
