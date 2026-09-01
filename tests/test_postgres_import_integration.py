from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from product_search.corpus.staging import stage_products
from product_search.corpus.xlsx_reader import ParsedProduct
from product_search.infrastructure.corpus_repository import (
    ACTIVATION_ACTIVE,
    CLEANUP_COMPLETE,
    activate_stage,
    active_product_ids,
    create_import_operation,
    get_import_operation,
)


@pytest.mark.integration
def test_postgresql_operation_journal_and_activation(tmp_path: Path) -> None:
    database_url = os.environ.get("GATE2_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("GATE2_TEST_DATABASE_URL is not configured")
    engine = create_engine(database_url)
    if engine.url.database != "gate2_test":
        pytest.fail("Integration test requires the isolated gate2_test database.")
    operation_id = create_import_operation(engine, "postgres-integration")
    stage = stage_products(
        [ParsedProduct("101", 6, "Накладные ногти", b"image")], tmp_path, operation_id
    )

    activate_stage(engine, "postgres-integration", stage, tmp_path / "corpora", operation_id)

    operation = get_import_operation(engine, operation_id)
    assert active_product_ids(engine) == ["101"]
    assert operation is not None
    assert operation["activation_status"] == ACTIVATION_ACTIVE
    assert operation["cleanup_status"] == CLEANUP_COMPLETE
