"""Run one local, non-UI corpus import operation."""

from __future__ import annotations

import argparse
from pathlib import Path

from product_search.core.settings import Settings
from product_search.corpus.import_service import import_snapshot
from product_search.infrastructure.corpus_repository import ImportBootstrapError
from product_search.corpus.xlsx_reader import PRODUCT_NOVELTIES_LAYOUT, SYNTHETIC_LAYOUT
from product_search.infrastructure.database import create_database_engine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--layout", choices=("product-novelties", "synthetic"), required=True)
    arguments = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    settings = Settings.from_environment(repository_root=repository_root)
    layout = (
        PRODUCT_NOVELTIES_LAYOUT
        if arguments.layout == "product-novelties"
        else SYNTHETIC_LAYOUT
    )
    try:
        result = import_snapshot(
            arguments.xlsx, arguments.snapshot, settings.data_dir,
            create_database_engine(settings.database_url), layout=layout,
        )
    except ImportBootstrapError:
        print("Импорт не начат: журнал операций недоступен.")
        raise SystemExit(4)
    print(f"operation_id={result.operation_id}; corpus_replaced={result.corpus_replaced}; report={result.report_path}")
    if result.finalization_pending:
        raise SystemExit(3)
    if not result.corpus_replaced:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
