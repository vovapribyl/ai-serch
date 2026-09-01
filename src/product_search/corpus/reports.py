from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from product_search.corpus.rules import RejectionReason


@dataclass(frozen=True)
class ImportReport:
    snapshot_name: str
    accepted_rows: int
    rejected_by_reason: dict[RejectionReason, int]
    duplicate_product_ids: tuple[str, ...]
    corpus_replaced: bool
    critical_error: str | None = None
    rejected_rows: tuple[tuple[int, RejectionReason], ...] = ()

    def as_json(self) -> dict[str, object]:
        return {
            "snapshot_name": self.snapshot_name,
            "accepted_rows": self.accepted_rows,
            "rejected_rows_count": len(self.rejected_rows),
            "rejected_by_reason": {
                reason.value: count for reason, count in sorted(self.rejected_by_reason.items())
            },
            "duplicate_product_ids": list(self.duplicate_product_ids),
            "corpus_replaced": self.corpus_replaced,
            "critical_error": self.critical_error,
            "rejected_rows": [
                {"source_row": source_row, "reason": reason.value}
                for source_row, reason in self.rejected_rows
            ],
        }


def write_report(report: ImportReport, data_dir: Path, *, now: datetime | None = None) -> Path:
    created_at = now or datetime.now(tz=UTC)
    reports_dir = data_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{created_at:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex}.json"
    temporary_path = report_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(report.as_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, report_path)
    return report_path


def cleanup_expired_reports(data_dir: Path, *, now: datetime | None = None) -> int:
    reports_dir = data_dir / "reports"
    if not reports_dir.exists():
        return 0
    threshold = (now or datetime.now(tz=UTC)) - timedelta(days=90)
    deleted = 0
    for report_path in reports_dir.glob("*.json"):
        modified_at = datetime.fromtimestamp(report_path.stat().st_mtime, tz=UTC)
        if modified_at < threshold:
            report_path.unlink()
            deleted += 1
    return deleted
