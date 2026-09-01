from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from product_search.corpus.reports import ImportReport, cleanup_expired_reports, write_report
from product_search.corpus.rules import RejectionReason


def test_writes_one_human_readable_json_report(tmp_path) -> None:
    path = write_report(
        ImportReport(
            snapshot_name="test-snapshot",
            accepted_rows=2,
            rejected_by_reason={RejectionReason.MISSING_PRIMARY_IMAGE: 1},
            duplicate_product_ids=(),
            corpus_replaced=True,
        ),
        tmp_path,
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )

    assert path.parent == tmp_path / "reports"
    assert json.loads(path.read_text()) == {
        "accepted_rows": 2,
        "corpus_replaced": True,
        "critical_error": None,
        "rejected_rows": [],
        "rejected_rows_count": 0,
        "duplicate_product_ids": [],
        "rejected_by_reason": {"MISSING_PRIMARY_IMAGE": 1},
        "snapshot_name": "test-snapshot",
    }


def test_includes_rejected_row_locators(tmp_path) -> None:
    path = write_report(
        ImportReport(
            "test-snapshot",
            0,
            {RejectionReason.MISSING_PRIMARY_IMAGE: 1},
            (),
            False,
            rejected_rows=((6, RejectionReason.MISSING_PRIMARY_IMAGE),),
        ),
        tmp_path,
    )

    assert json.loads(path.read_text())["rejected_rows"] == [
        {"reason": "MISSING_PRIMARY_IMAGE", "source_row": 6}
    ]


def test_keeps_reports_newer_than_ninety_days(tmp_path) -> None:
    old = write_report(ImportReport("old", 0, {}, (), False), tmp_path)
    recent = write_report(ImportReport("recent", 0, {}, (), False), tmp_path)
    os.utime(old, (0, 0))
    os.utime(recent, (datetime.now(tz=UTC).timestamp(),) * 2)

    deleted = cleanup_expired_reports(tmp_path, now=datetime.now(tz=UTC))

    assert deleted == 1
    assert not old.exists()
    assert recent.exists()
