from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine

from product_search.corpus.import_service import import_snapshot
from product_search.corpus.xlsx_reader import ParsedProduct, WorkbookInspection
from product_search.infrastructure.corpus_repository import (
    active_product_ids,
    create_corpus_schema,
)


def inspection(*, duplicate_ids: tuple[str, ...] = ()) -> WorkbookInspection:
    return WorkbookInspection(
        accepted=(ParsedProduct("101", 6, "Накладные ногти", b"image"),),
        rejected=(),
        duplicate_product_ids=duplicate_ids,
    )


def test_critical_xlsx_error_writes_report_without_replacing_corpus(
    tmp_path: Path, monkeypatch
) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    monkeypatch.setattr(
        "product_search.corpus.import_service.inspect_workbook",
        lambda path, layout: inspection(duplicate_ids=("101",)),
    )

    result = import_snapshot(Path("duplicate.xlsx"), "duplicate", tmp_path, engine)

    assert not result.corpus_replaced
    assert active_product_ids(engine) == []
    report = json.loads(result.report_path.read_text())
    assert report["duplicate_product_ids"] == ["101"]
    assert report["critical_error"] == "DUPLICATE_PRODUCT_ID"


def test_successful_import_activates_staged_corpus_and_writes_report(
    tmp_path: Path, monkeypatch
) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    monkeypatch.setattr(
        "product_search.corpus.import_service.inspect_workbook",
        lambda path, layout: inspection(),
    )

    result = import_snapshot(Path("valid.xlsx"), "valid", tmp_path, engine)

    assert result.corpus_replaced
    assert active_product_ids(engine) == ["101"]
    assert json.loads(result.report_path.read_text())["corpus_replaced"] is True


def test_unreadable_xlsx_writes_failure_report(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)

    result = import_snapshot(Path("broken.xlsx"), "broken", tmp_path, engine)

    assert not result.corpus_replaced
    assert json.loads(result.report_path.read_text())["critical_error"] == "UNREADABLE_XLSX"
