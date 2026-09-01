from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
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
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from product_search.corpus.staging import CorpusStage, discard_stage


class CorpusActivationError(RuntimeError):
    """Новая версия корпуса не активирована; прежняя версия сохранена."""


class CorpusCleanupError(RuntimeError):
    """Новая версия активна, но очистка прежнего корпуса требует повтора."""


metadata = MetaData()
corpus_versions = Table(
    "corpus_versions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("snapshot_name", String(255), nullable=False),
    Column("operation_id", String(32), nullable=False, unique=True),
    Column("is_active", Boolean, nullable=False, default=False),
)
product_records = Table(
    "product_records",
    metadata,
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


def create_corpus_schema(engine: Engine) -> None:
    metadata.create_all(engine)


def active_product_ids(engine: Engine) -> list[str]:
    query = (
        select(product_records.c.product_id)
        .join(corpus_versions)
        .where(corpus_versions.c.is_active.is_(True))
        .order_by(product_records.c.product_id)
    )
    with engine.connect() as connection:
        return list(connection.execute(query).scalars())


def activate_stage(
    engine: Engine, snapshot_name: str, stage: CorpusStage, corpora_directory: Path
) -> Path:
    corpora_directory.mkdir(parents=True, exist_ok=True)
    operation_id = uuid.uuid4().hex
    final_directory = corpora_directory / operation_id
    try:
        with _exclusive_import_lock(corpora_directory), engine.begin() as connection:
            result = connection.execute(
                insert(corpus_versions).values(
                    snapshot_name=snapshot_name, operation_id=operation_id, is_active=False
                )
            )
            version_id = result.inserted_primary_key[0]
            connection.execute(
                insert(product_records),
                [
                    {
                        "corpus_version_id": version_id,
                        "product_id": item.product_id,
                        "source_row": item.source_row,
                        "category": item.category,
                        "image_path": str(final_directory / item.image_path.name),
                        "image_sha256": item.image_sha256,
                        "image_format": item.image_format,
                    }
                    for item in stage.products
                ],
            )
            shutil.move(str(stage.directory), final_directory)
            connection.execute(update(corpus_versions).values(is_active=False))
            connection.execute(
                update(corpus_versions).where(corpus_versions.c.id == version_id).values(is_active=True)
            )
    except (OSError, SQLAlchemyError) as error:
        if _operation_is_active(engine, operation_id):
            try:
                _cleanup_inactive_versions(engine)
            except OSError as cleanup_error:
                raise CorpusCleanupError() from cleanup_error
            return final_directory
        if final_directory.exists():
            shutil.rmtree(final_directory)
        discard_stage(stage)
        raise CorpusActivationError() from error

    try:
        _cleanup_inactive_versions(engine)
    except OSError as error:
        raise CorpusCleanupError() from error
    return final_directory


def _cleanup_inactive_versions(engine: Engine) -> None:
    with engine.begin() as connection:
        inactive_ids = connection.execute(
            select(corpus_versions.c.id).where(corpus_versions.c.is_active.is_(False))
        ).scalars().all()
        for version_id in inactive_ids:
            paths = connection.execute(
                select(product_records.c.image_path).where(product_records.c.corpus_version_id == version_id)
            ).scalars().all()
            for directory in {Path(path).parent for path in paths}:
                if directory.exists():
                    shutil.rmtree(directory)
        if inactive_ids:
            connection.execute(delete(product_records).where(product_records.c.corpus_version_id.in_(inactive_ids)))
            connection.execute(delete(corpus_versions).where(corpus_versions.c.id.in_(inactive_ids)))


def _operation_is_active(engine: Engine, operation_id: str) -> bool:
    with engine.connect() as connection:
        return bool(
            connection.execute(
                select(corpus_versions.c.id).where(
                    corpus_versions.c.operation_id == operation_id,
                    corpus_versions.c.is_active.is_(True),
                )
            ).scalar_one_or_none()
        )


@contextmanager
def _exclusive_import_lock(corpora_directory: Path):
    import fcntl

    lock_path = corpora_directory / ".import.lock"
    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
