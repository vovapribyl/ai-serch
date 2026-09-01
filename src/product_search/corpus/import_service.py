from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from product_search.corpus.reports import ImportReport, cleanup_expired_reports, write_report
from product_search.corpus.staging import CorpusStagingError, stage_products
from product_search.corpus.xlsx_reader import (
    SYNTHETIC_LAYOUT,
    WorkbookImportError,
    WorkbookLayout,
    inspect_workbook,
)
from product_search.infrastructure.corpus_repository import (
    CorpusActivationError,
    CorpusCleanupError,
    activate_stage,
)


@dataclass(frozen=True)
class ImportResult:
    report_path: Path
    corpus_replaced: bool


def import_snapshot(
    xlsx_path: Path,
    snapshot_name: str,
    data_dir: Path,
    engine: Engine,
    *,
    layout: WorkbookLayout = SYNTHETIC_LAYOUT,
) -> ImportResult:
    try:
        inspection = inspect_workbook(xlsx_path, layout)
    except WorkbookImportError:
        return _failed_import(snapshot_name, data_dir, "UNREADABLE_XLSX")
    rejected_by_reason = dict(Counter(issue.reason for issue in inspection.rejected))
    rejected_rows = tuple((issue.source_row, issue.reason) for issue in inspection.rejected)
    if inspection.has_critical_error:
        return _failed_import(
            snapshot_name,
            data_dir,
            "DUPLICATE_PRODUCT_ID",
            accepted_rows=len(inspection.accepted),
            rejected_by_reason=rejected_by_reason,
            duplicate_product_ids=inspection.duplicate_product_ids,
            rejected_rows=rejected_rows,
        )

    try:
        stage = stage_products(list(inspection.accepted), data_dir)
        activate_stage(engine, snapshot_name, stage, data_dir / "corpora")
    except (CorpusStagingError, CorpusActivationError):
        return _failed_import(
            snapshot_name,
            data_dir,
            "ACTIVATION_FAILED",
            accepted_rows=len(inspection.accepted),
            rejected_by_reason=rejected_by_reason,
            rejected_rows=rejected_rows,
        )
    except CorpusCleanupError:
        report_path = write_report(
            ImportReport(
                snapshot_name=snapshot_name,
                accepted_rows=len(inspection.accepted),
                rejected_by_reason=rejected_by_reason,
                duplicate_product_ids=(),
                corpus_replaced=True,
                critical_error="CLEANUP_PENDING",
                rejected_rows=rejected_rows,
            ),
            data_dir,
        )
        return ImportResult(report_path, corpus_replaced=True)
    report_path = write_report(
        ImportReport(
            snapshot_name=snapshot_name,
            accepted_rows=len(inspection.accepted),
            rejected_by_reason=rejected_by_reason,
            duplicate_product_ids=(),
            corpus_replaced=True,
            rejected_rows=rejected_rows,
        ),
        data_dir,
    )
    cleanup_expired_reports(data_dir)
    return ImportResult(report_path, corpus_replaced=True)


def _failed_import(
    snapshot_name: str,
    data_dir: Path,
    critical_error: str,
    *,
    accepted_rows: int = 0,
    rejected_by_reason: dict | None = None,
    duplicate_product_ids: tuple[str, ...] = (),
    rejected_rows: tuple[tuple[int, object], ...] = (),
) -> ImportResult:
    report_path = write_report(
        ImportReport(
            snapshot_name=snapshot_name,
            accepted_rows=accepted_rows,
            rejected_by_reason=rejected_by_reason or {},
            duplicate_product_ids=duplicate_product_ids,
            corpus_replaced=False,
            critical_error=critical_error,
            rejected_rows=rejected_rows,
        ),
        data_dir,
    )
    cleanup_expired_reports(data_dir)
    return ImportResult(report_path, corpus_replaced=False)
