from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from product_search.corpus.reports import (
    ImportReport,
    cleanup_expired_reports,
    write_report_payload,
)
from product_search.corpus.staging import CorpusStagingError, stage_products
from product_search.corpus.xlsx_reader import (
    SYNTHETIC_LAYOUT,
    WorkbookImportError,
    WorkbookLayout,
    inspect_workbook,
)
from product_search.infrastructure.corpus_repository import (
    ACTIVATION_ACTIVE,
    ACTIVATION_FAILED,
    ACTIVATION_PENDING,
    ACTIVATION_REGISTERED,
    OUTCOME_FAILED,
    OUTCOME_PENDING,
    OUTCOME_SUCCEEDED,
    CorpusActivationCleanupError,
    CorpusActivationError,
    CorpusActivationUnknownError,
    CorpusCleanupError,
    activate_stage,
    create_import_operation,
    exclusive_import_lock,
    finalize_cleanup,
    get_import_operation,
    mark_report_pending,
    mark_report_published,
    set_operation_result,
)


@dataclass(frozen=True)
class ImportResult:
    operation_id: str
    report_path: Path | None
    corpus_replaced: bool
    finalization_pending: bool


def import_snapshot(xlsx_path: Path, snapshot_name: str, data_dir: Path, engine: Engine,
                    *, layout: WorkbookLayout = SYNTHETIC_LAYOUT) -> ImportResult:
    with exclusive_import_lock(data_dir / "corpora"):
        return _import_snapshot(xlsx_path, snapshot_name, data_dir, engine, layout=layout)


def _import_snapshot(xlsx_path: Path, snapshot_name: str, data_dir: Path, engine: Engine,
                     *, layout: WorkbookLayout) -> ImportResult:
    operation_id = create_import_operation(engine, snapshot_name)
    try:
        inspection = inspect_workbook(xlsx_path, layout)
    except WorkbookImportError:
        return _fail_operation(engine, data_dir, operation_id, snapshot_name, "UNREADABLE_XLSX")

    rejected_by_reason = dict(Counter(issue.reason for issue in inspection.rejected))
    rejected_rows = tuple((issue.source_row, issue.reason) for issue in inspection.rejected)
    report = ImportReport(snapshot_name=snapshot_name, accepted_rows=len(inspection.accepted),
                          rejected_by_reason=rejected_by_reason,
                          duplicate_product_ids=inspection.duplicate_product_ids,
                          corpus_replaced=False, rejected_rows=rejected_rows)
    set_operation_result(engine, operation_id, outcome=OUTCOME_PENDING,
                         activation_status=ACTIVATION_PENDING, report_payload=report.as_json())
    if inspection.has_critical_error:
        return _fail_operation(engine, data_dir, operation_id, snapshot_name,
                               "DUPLICATE_PRODUCT_ID", report=report)
    try:
        stage = stage_products(list(inspection.accepted), data_dir, operation_id)
        activate_stage(engine, snapshot_name, stage, data_dir / "corpora", operation_id,
                       import_lock_held=True)
    except CorpusActivationUnknownError:
        return ImportResult(operation_id, None, corpus_replaced=False, finalization_pending=True)
    except (CorpusStagingError, CorpusActivationError, CorpusActivationCleanupError):
        return _fail_operation(engine, data_dir, operation_id, snapshot_name,
                               "ACTIVATION_FAILED", report=report)
    except CorpusCleanupError:
        return _complete_operation(engine, data_dir, operation_id, report, cleanup_pending=True)
    return _complete_operation(engine, data_dir, operation_id, report)


def reconcile_operation(engine: Engine, data_dir: Path, operation_id: str) -> ImportResult:
    """Repeat finalisation for a persisted operation without importing the XLSX again."""
    with exclusive_import_lock(data_dir / "corpora"):
        return _reconcile_operation(engine, data_dir, operation_id)


def _reconcile_operation(engine: Engine, data_dir: Path, operation_id: str) -> ImportResult:
    operation = get_import_operation(engine, operation_id)
    if operation is None:
        raise ValueError(f"Операция {operation_id} не найдена.")
    payload = dict(operation["report_payload"] or {})
    active = operation["activation_status"] == ACTIVATION_ACTIVE
    if operation["activation_status"] == ACTIVATION_REGISTERED:
        payload = {
            "snapshot_name": operation["snapshot_name"],
            "accepted_rows": 0,
            "rejected_rows_count": 0,
            "rejected_by_reason": {},
            "duplicate_product_ids": [],
            "corpus_replaced": False,
            "critical_error": "IMPORT_NOT_STARTED",
            "rejected_rows": [],
        }
        set_operation_result(engine, operation_id, outcome=OUTCOME_FAILED,
                             activation_status=ACTIVATION_FAILED, report_payload=payload,
                             error_code="IMPORT_NOT_STARTED")
        active = False
        cleanup_complete = finalize_cleanup(
            engine, operation_id, data_dir=data_dir, activated=False
        )
    elif active:
        payload["corpus_replaced"] = True
        if payload.get("critical_error") == "ACTIVATION_FAILED":
            payload["critical_error"] = None
        set_operation_result(engine, operation_id, outcome=OUTCOME_SUCCEEDED,
                             activation_status=ACTIVATION_ACTIVE, report_payload=payload)
        cleanup_complete = finalize_cleanup(engine, operation_id)
        if not cleanup_complete:
            payload["critical_error"] = "CLEANUP_PENDING"
            set_operation_result(engine, operation_id, outcome=OUTCOME_SUCCEEDED,
                                 activation_status=ACTIVATION_ACTIVE, report_payload=payload)
        elif payload.get("critical_error") == "CLEANUP_PENDING":
            payload["critical_error"] = None
            set_operation_result(engine, operation_id, outcome=OUTCOME_SUCCEEDED,
                                 activation_status=ACTIVATION_ACTIVE, report_payload=payload)
    elif operation["activation_status"] == ACTIVATION_PENDING:
        payload["corpus_replaced"] = False
        payload["critical_error"] = "ACTIVATION_OUTCOME_UNKNOWN"
        set_operation_result(engine, operation_id, outcome=OUTCOME_PENDING,
                             activation_status=ACTIVATION_PENDING, report_payload=payload,
                             error_code="ACTIVATION_OUTCOME_UNKNOWN")
        cleanup_complete = False
    else:
        cleanup_complete = finalize_cleanup(
            engine, operation_id, data_dir=data_dir, activated=False
        )
    return _publish_report(engine, data_dir, operation_id, payload, active, cleanup_complete)


def reconcile_pending_operations(engine: Engine, data_dir: Path) -> list[ImportResult]:
    from product_search.infrastructure.corpus_repository import import_operations

    with exclusive_import_lock(data_dir / "corpora"):
        with engine.connect() as connection:
            operation_ids = connection.execute(select(import_operations.c.operation_id).where(or_(
                import_operations.c.report_status != "PUBLISHED",
                import_operations.c.cleanup_status != "COMPLETE",
            ))).scalars().all()
        return [_reconcile_operation(engine, data_dir, operation_id) for operation_id in operation_ids]


def _complete_operation(engine: Engine, data_dir: Path, operation_id: str, report: ImportReport,
                        *, cleanup_pending: bool = False) -> ImportResult:
    payload = report.as_json()
    payload["corpus_replaced"] = True
    cleanup_complete = not cleanup_pending and finalize_cleanup(engine, operation_id)
    if not cleanup_complete:
        payload["critical_error"] = "CLEANUP_PENDING"
    set_operation_result(engine, operation_id, outcome=OUTCOME_SUCCEEDED,
                         activation_status=ACTIVATION_ACTIVE, report_payload=payload)
    return _publish_report(engine, data_dir, operation_id, payload, True, cleanup_complete)


def _fail_operation(engine: Engine, data_dir: Path, operation_id: str, snapshot_name: str,
                    critical_error: str, *, report: ImportReport | None = None) -> ImportResult:
    payload = (report or ImportReport(snapshot_name=snapshot_name, accepted_rows=0,
               rejected_by_reason={}, duplicate_product_ids=(), corpus_replaced=False)).as_json()
    payload["critical_error"] = critical_error
    payload["corpus_replaced"] = False
    set_operation_result(engine, operation_id, outcome=OUTCOME_FAILED,
                         activation_status=ACTIVATION_FAILED, report_payload=payload,
                         error_code=critical_error)
    cleanup_complete = finalize_cleanup(
        engine, operation_id, data_dir=data_dir, activated=False
    )
    if not cleanup_complete:
        payload["critical_error"] = "CLEANUP_PENDING"
        set_operation_result(engine, operation_id, outcome=OUTCOME_FAILED,
                             activation_status=ACTIVATION_FAILED, report_payload=payload,
                             error_code=critical_error)
    return _publish_report(engine, data_dir, operation_id, payload, False, cleanup_complete)


def _publish_report(engine: Engine, data_dir: Path, operation_id: str, payload: dict[str, object],
                    corpus_replaced: bool, cleanup_complete: bool) -> ImportResult:
    try:
        report_path = write_report_payload(payload, data_dir, operation_id)
        mark_report_published(engine, operation_id)
    except (OSError, SQLAlchemyError):
        return ImportResult(operation_id, None, corpus_replaced, finalization_pending=True)
    try:
        cleanup_expired_reports(data_dir)
    except OSError:
        mark_report_pending(engine, operation_id)
        return ImportResult(operation_id, report_path, corpus_replaced, finalization_pending=True)
    pending = not cleanup_complete
    return ImportResult(operation_id, report_path, corpus_replaced, finalization_pending=pending)
