from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine, Transaction
from sqlalchemy.exc import SQLAlchemyError

from product_search.corpus.staging import CorpusStage, discard_stage


class ImportBootstrapError(RuntimeError):
    """До устойчивой регистрации операции импорт начинать нельзя."""


class CorpusActivationError(RuntimeError):
    """Новая версия корпуса не активирована; прежняя версия сохранена."""


class CorpusActivationUnknownError(RuntimeError):
    """Результат активации неизвестен и должен быть reconciled по operation_id."""


class CorpusActivationCleanupError(RuntimeError):
    """Активация не подтверждена, а её staging/final-каталог ещё не очищен."""


class CorpusCleanupError(RuntimeError):
    """Новая версия активна, но очистка прежнего корпуса требует повтора."""


ACTIVATION_PENDING = "PENDING"
ACTIVATION_REGISTERED = "REGISTERED"
ACTIVATION_ACTIVE = "ACTIVE"
ACTIVATION_FAILED = "FAILED"
CLEANUP_PENDING = "PENDING"
CLEANUP_COMPLETE = "COMPLETE"
REPORT_PENDING = "PENDING"
REPORT_PUBLISHED = "PUBLISHED"
OUTCOME_PENDING = "PENDING"
OUTCOME_SUCCEEDED = "SUCCEEDED"
OUTCOME_FAILED = "FAILED"

metadata = MetaData()
corpus_versions = Table(
    "corpus_versions", metadata,
    Column("id", Integer, primary_key=True),
    Column("snapshot_name", String(255), nullable=False),
    Column("operation_id", String(32), nullable=False, unique=True),
    Column("is_active", Boolean, nullable=False, default=False),
)
product_records = Table(
    "product_records", metadata,
    Column("id", Integer, primary_key=True),
    Column("corpus_version_id", ForeignKey("corpus_versions.id", ondelete="CASCADE"), nullable=False),
    Column("product_id", String(255), nullable=False),
    Column("source_row", Integer, nullable=False),
    Column("category", String(255), nullable=False),
    Column("image_path", String(1024), nullable=False),
    Column("image_sha256", String(64), nullable=False),
    Column("image_format", String(16), nullable=False),
    UniqueConstraint("corpus_version_id", "product_id"),
)
import_operations = Table(
    "import_operations", metadata,
    Column("operation_id", String(32), primary_key=True),
    Column("snapshot_name", String(255), nullable=False),
    Column("corpus_version_id", ForeignKey("corpus_versions.id", ondelete="SET NULL")),
    Column("outcome", String(16), nullable=False),
    Column("activation_status", String(16), nullable=False),
    Column("cleanup_status", String(16), nullable=False),
    Column("report_status", String(16), nullable=False),
    Column("report_payload", JSON, nullable=True),
    Column("error_code", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


def create_corpus_schema(engine: Engine) -> None:
    metadata.create_all(engine)


def create_import_operation(engine: Engine, snapshot_name: str) -> str:
    operation_id = uuid.uuid4().hex
    now = datetime.now(tz=UTC)
    try:
        with engine.begin() as connection:
            connection.execute(insert(import_operations).values(
                operation_id=operation_id, snapshot_name=snapshot_name,
                outcome=OUTCOME_PENDING, activation_status=ACTIVATION_REGISTERED,
                cleanup_status=CLEANUP_PENDING, report_status=REPORT_PENDING,
                created_at=now, updated_at=now,
            ))
    except SQLAlchemyError as error:
        raise ImportBootstrapError() from error
    return operation_id


def get_import_operation(engine: Engine, operation_id: str) -> dict[str, object] | None:
    with engine.connect() as connection:
        row = connection.execute(select(import_operations).where(
            import_operations.c.operation_id == operation_id
        )).mappings().one_or_none()
    return dict(row) if row else None


def set_operation_result(engine: Engine, operation_id: str, *, outcome: str,
                         activation_status: str, report_payload: dict[str, object],
                         error_code: str | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(update(import_operations).where(
            import_operations.c.operation_id == operation_id
        ).values(outcome=outcome, activation_status=activation_status,
                 report_payload=report_payload, error_code=error_code,
                 updated_at=datetime.now(tz=UTC)))


def mark_report_published(engine: Engine, operation_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(update(import_operations).where(
            import_operations.c.operation_id == operation_id
        ).values(report_status=REPORT_PUBLISHED, updated_at=datetime.now(tz=UTC)))


def mark_report_pending(engine: Engine, operation_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(update(import_operations).where(
            import_operations.c.operation_id == operation_id
        ).values(report_status=REPORT_PENDING, updated_at=datetime.now(tz=UTC)))


def active_product_ids(engine: Engine) -> list[str]:
    query = select(product_records.c.product_id).join(corpus_versions).where(
        corpus_versions.c.is_active.is_(True)
    ).order_by(product_records.c.product_id)
    with engine.connect() as connection:
        return list(connection.execute(query).scalars())


def activate_stage(engine: Engine, snapshot_name: str, stage: CorpusStage,
                   corpora_directory: Path, operation_id: str | None = None,
                   *, import_lock_held: bool = False) -> Path:
    """Activate one staged corpus and atomically record its durable state."""
    operation_id = operation_id or create_import_operation(engine, snapshot_name)
    corpora_directory.mkdir(parents=True, exist_ok=True)
    final_directory = corpora_directory / operation_id
    connection: Connection | None = None
    transaction: Transaction | None = None
    try:
        with (nullcontext() if import_lock_held else exclusive_import_lock(corpora_directory)):
            connection = engine.connect()
            transaction = connection.begin()
            _postgres_advisory_lock(connection)
            result = connection.execute(insert(corpus_versions).values(
                snapshot_name=snapshot_name, operation_id=operation_id, is_active=False
            ))
            version_id = result.inserted_primary_key[0]
            connection.execute(insert(product_records), [{
                "corpus_version_id": version_id, "product_id": item.product_id,
                "source_row": item.source_row, "category": item.category,
                "image_path": str(final_directory / item.image_path.name),
                "image_sha256": item.image_sha256, "image_format": item.image_format,
            } for item in stage.products])
            shutil.move(str(stage.directory), final_directory)
            connection.execute(update(corpus_versions).values(is_active=False))
            connection.execute(update(corpus_versions).where(
                corpus_versions.c.id == version_id
            ).values(is_active=True))
            connection.execute(update(import_operations).where(
                import_operations.c.operation_id == operation_id
            ).values(corpus_version_id=version_id, activation_status=ACTIVATION_ACTIVE,
                     outcome=OUTCOME_SUCCEEDED, cleanup_status=CLEANUP_PENDING,
                     updated_at=datetime.now(tz=UTC)))
            _commit_activation(transaction)
            transaction = None
    except (OSError, SQLAlchemyError) as error:
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        try:
            operation = get_import_operation(engine, operation_id)
        except SQLAlchemyError as lookup_error:
            raise CorpusActivationUnknownError() from lookup_error
        if operation and operation["activation_status"] == ACTIVATION_ACTIVE:
            return final_directory
        try:
            if final_directory.exists():
                shutil.rmtree(final_directory)
            if stage.directory.exists():
                discard_stage(stage)
        except OSError as cleanup_error:
            raise CorpusActivationCleanupError() from cleanup_error
        raise CorpusActivationError() from error
    finally:
        if connection is not None:
            connection.close()
    if not finalize_cleanup(engine, operation_id):
        raise CorpusCleanupError()
    return final_directory


def finalize_cleanup(
    engine: Engine,
    operation_id: str,
    *,
    data_dir: Path | None = None,
    activated: bool = True,
) -> bool:
    """Remove inactive corpora before deleting their DB records; safe to repeat."""
    try:
        if activated:
            _cleanup_inactive_versions(engine)
        elif data_dir is not None:
            for directory in (data_dir / "staging" / operation_id, data_dir / "corpora" / operation_id):
                if directory.exists():
                    shutil.rmtree(directory)
    except (OSError, SQLAlchemyError):
        return False
    with engine.begin() as connection:
        connection.execute(update(import_operations).where(
            import_operations.c.operation_id == operation_id
        ).values(cleanup_status=CLEANUP_COMPLETE, updated_at=datetime.now(tz=UTC)))
    return True


def _cleanup_inactive_versions(engine: Engine) -> None:
    with engine.connect() as connection:
        inactive_ids = connection.execute(select(corpus_versions.c.id).where(
            corpus_versions.c.is_active.is_(False)
        )).scalars().all()
        directories: set[Path] = set()
        for version_id in inactive_ids:
            paths = connection.execute(select(product_records.c.image_path).where(
                product_records.c.corpus_version_id == version_id
            )).scalars().all()
            directories.update(Path(path).parent for path in paths)
    for directory in directories:
        if directory.exists():
            shutil.rmtree(directory)
    if inactive_ids:
        with engine.begin() as connection:
            connection.execute(delete(product_records).where(
                product_records.c.corpus_version_id.in_(inactive_ids)
            ))
            connection.execute(delete(corpus_versions).where(
                corpus_versions.c.id.in_(inactive_ids)
            ))


def _commit_activation(transaction: Transaction) -> None:
    transaction.commit()


def _postgres_advisory_lock(connection: Connection) -> None:
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(73422619)")


@contextmanager
def exclusive_import_lock(corpora_directory: Path):
    import fcntl

    corpora_directory.mkdir(parents=True, exist_ok=True)
    lock_path = corpora_directory / ".import.lock"
    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
