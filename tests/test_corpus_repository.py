from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from product_search.corpus.staging import stage_products
from product_search.corpus.xlsx_reader import ParsedProduct
from product_search.infrastructure.corpus_repository import (
    CorpusActivationError,
    CorpusCleanupError,
    activate_stage,
    active_product_ids,
    create_corpus_schema,
)


def product(product_id: str) -> ParsedProduct:
    return ParsedProduct(product_id, 6, "Накладные ногти", product_id.encode())


def test_successful_activation_replaces_old_database_records_and_files(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    first = activate_stage(
        engine, "first", stage_products([product("101")], tmp_path), tmp_path / "corpora"
    )

    second = activate_stage(
        engine, "second", stage_products([product("102")], tmp_path), tmp_path / "corpora"
    )

    assert active_product_ids(engine) == ["102"]
    assert second.exists()
    assert not first.exists()


def test_failed_activation_keeps_previous_corpus_active(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    previous = activate_stage(
        engine, "previous", stage_products([product("101")], tmp_path), tmp_path / "corpora"
    )
    invalid_stage = stage_products([product("102"), product("102")], tmp_path)

    with pytest.raises(CorpusActivationError):
        activate_stage(engine, "invalid", invalid_stage, tmp_path / "corpora")

    assert active_product_ids(engine) == ["101"]
    assert previous.exists()


def test_cleanup_failure_keeps_new_corpus_active_and_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    activate_stage(engine, "first", stage_products([product("101")], tmp_path), tmp_path / "corpora")
    original_rmtree = __import__("shutil").rmtree
    failed_once = False

    def fail_once(path: Path) -> None:
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise OSError("cleanup failure")
        original_rmtree(path)

    monkeypatch.setattr("product_search.infrastructure.corpus_repository.shutil.rmtree", fail_once)
    with pytest.raises(CorpusCleanupError):
        activate_stage(engine, "second", stage_products([product("102")], tmp_path), tmp_path / "corpora")

    assert active_product_ids(engine) == ["102"]
    activate_stage(engine, "third", stage_products([product("103")], tmp_path), tmp_path / "corpora")
    assert active_product_ids(engine) == ["103"]
