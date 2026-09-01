from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from product_search.corpus.import_service import import_snapshot, reconcile_operation
from product_search.corpus.xlsx_reader import ParsedProduct, WorkbookInspection
from product_search.infrastructure.corpus_repository import (
    CorpusActivationCleanupError,
    active_product_ids,
    create_corpus_schema,
    create_import_operation,
    get_import_operation,
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


def test_lost_commit_confirmation_is_reconciled_without_deleting_active_corpus(
    tmp_path: Path, monkeypatch
) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    monkeypatch.setattr(
        "product_search.corpus.import_service.inspect_workbook", lambda path, layout: inspection()
    )

    def commit_then_lose_confirmation(transaction) -> None:
        transaction.commit()
        raise SQLAlchemyError("connection dropped after COMMIT")

    monkeypatch.setattr(
        "product_search.infrastructure.corpus_repository._commit_activation",
        commit_then_lose_confirmation,
    )
    result = import_snapshot(Path("valid.xlsx"), "valid", tmp_path, engine)

    assert result.corpus_replaced
    assert not result.finalization_pending
    assert active_product_ids(engine) == ["101"]
    assert result.report_path and result.report_path.exists()


def test_report_write_failure_is_persisted_and_retried(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    monkeypatch.setattr(
        "product_search.corpus.import_service.inspect_workbook", lambda path, layout: inspection()
    )
    original_write = __import__(
        "product_search.corpus.import_service", fromlist=["write_report_payload"]
    ).write_report_payload
    monkeypatch.setattr(
        "product_search.corpus.import_service.write_report_payload",
        lambda *args: (_ for _ in ()).throw(OSError("reports unavailable")),
    )
    result = import_snapshot(Path("valid.xlsx"), "valid", tmp_path, engine)

    assert result.corpus_replaced
    assert result.finalization_pending
    assert result.report_path is None
    monkeypatch.setattr("product_search.corpus.import_service.write_report_payload", original_write)
    retried = reconcile_operation(engine, tmp_path, result.operation_id)
    assert retried.report_path and retried.report_path.exists()
    assert not retried.finalization_pending


def test_failed_activation_cleanup_is_not_reported_as_a_replaced_corpus(
    tmp_path: Path, monkeypatch
) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    monkeypatch.setattr(
        "product_search.corpus.import_service.inspect_workbook", lambda path, layout: inspection()
    )
    monkeypatch.setattr(
        "product_search.corpus.import_service.activate_stage",
        lambda *args, **kwargs: (_ for _ in ()).throw(CorpusActivationCleanupError()),
    )

    result = import_snapshot(Path("valid.xlsx"), "valid", tmp_path, engine)

    assert not result.corpus_replaced
    assert result.report_path
    assert json.loads(result.report_path.read_text())["critical_error"] == "ACTIVATION_FAILED"


def test_reconciliation_replaces_a_pending_cleanup_report(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    monkeypatch.setattr(
        "product_search.corpus.import_service.inspect_workbook", lambda path, layout: inspection()
    )
    monkeypatch.setattr("product_search.corpus.import_service.finalize_cleanup", lambda *args, **kwargs: False)
    pending = import_snapshot(Path("valid.xlsx"), "valid", tmp_path, engine)
    assert json.loads(pending.report_path.read_text())["critical_error"] == "CLEANUP_PENDING"

    monkeypatch.setattr("product_search.corpus.import_service.finalize_cleanup", lambda *args, **kwargs: True)
    completed = reconcile_operation(engine, tmp_path, pending.operation_id)
    assert completed.report_path
    assert json.loads(completed.report_path.read_text())["critical_error"] is None


def test_registered_operation_is_reported_as_not_started_when_reconciled(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    create_corpus_schema(engine)
    operation_id = create_import_operation(engine, "interrupted-before-inspection")

    result = reconcile_operation(engine, tmp_path, operation_id)

    assert not result.corpus_replaced
    assert result.report_path
    assert json.loads(result.report_path.read_text())["critical_error"] == "IMPORT_NOT_STARTED"
    assert get_import_operation(engine, operation_id)["activation_status"] == "FAILED"
