"""Repeat report publication and cleanup for persisted corpus imports."""

from __future__ import annotations

import argparse

from sqlalchemy.exc import SQLAlchemyError

from product_search.core.settings import Settings
from product_search.corpus.import_service import reconcile_operation, reconcile_pending_operations
from product_search.infrastructure.corpus_repository import ImportBootstrapError
from product_search.infrastructure.database import create_database_engine


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--operation")
    group.add_argument("--all-pending", action="store_true")
    arguments = parser.parse_args()
    repository_root = __import__("pathlib").Path(__file__).resolve().parents[1]
    settings = Settings.from_environment(repository_root=repository_root)
    engine = create_database_engine(settings.database_url)
    try:
        results = (reconcile_pending_operations(engine, settings.data_dir) if arguments.all_pending
                   else [reconcile_operation(engine, settings.data_dir, arguments.operation)])
    except (ImportBootstrapError, SQLAlchemyError):
        print("Восстановление не начато: журнал операций недоступен.")
        raise SystemExit(4)
    for result in results:
        print(f"operation_id={result.operation_id}; corpus_replaced={result.corpus_replaced}; report={result.report_path}")
    if any(result.finalization_pending for result in results):
        raise SystemExit(3)
    if any(not result.corpus_replaced for result in results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
