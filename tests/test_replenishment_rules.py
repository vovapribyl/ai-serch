"""Readiness is derived from every selected photo, not the current batch only."""

import pytest

from product_search.search.corpus_replenishment import product_readiness, select_batch
from product_search.search.replenishment_contracts import (
    PhotoOutcome,
    PhotoWork,
    ReplenishmentError,
)
from tests.test_replenishment_contracts import package


def photo(index, outcome=PhotoOutcome.PENDING, **changes):
    values = {
        "photo_ref": f"photo-{index}",
        "revision_ref": "revision-1",
        "semantic_profile_sha": "b" * 64,
        "source_bytes": 100,
        "outcome": outcome,
        "head_version": 1,
        "revision_version": 1,
    }
    values.update(changes)
    return PhotoWork(**values)


def test_one_call_selects_only_five_of_seven_without_mutating_queue():
    queue = tuple(photo(i) for i in range(7))
    selected = select_batch(queue, package())
    assert [p.photo_ref for p in selected] == [f"photo-{i}" for i in range(5)]
    assert all(p.outcome == PhotoOutcome.PENDING for p in queue)


def test_empty_queue_is_an_empty_batch():
    assert select_batch((), package()) == ()


def test_terminal_errors_are_not_automatically_retried():
    queue = tuple(
        photo(i, outcome)
        for i, outcome in enumerate(
            [PhotoOutcome.OK, PhotoOutcome.ERROR, PhotoOutcome.NO_NAILS, PhotoOutcome.PENDING]
        )
    )
    assert [p.photo_ref for p in select_batch(queue, package())] == ["photo-3"]


@pytest.mark.parametrize("changes", [{"source_bytes": 1001}, {"semantic_profile_sha": "c" * 64}])
def test_invalid_input_is_refused_before_admission(changes):
    with pytest.raises(ReplenishmentError):
        select_batch((photo(0, **changes),), package())


def test_running_photo_requires_reconciliation_before_selection():
    with pytest.raises(ReplenishmentError, match="RECOVERY_REQUIRED"):
        select_batch((photo(0, PhotoOutcome.RUNNING),), package())


def test_duplicate_photo_is_not_admitted_twice():
    with pytest.raises(ReplenishmentError):
        select_batch((photo(0), photo(0)), package())


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        ([], "WAITING"),
        (["OK", "PENDING"], "WAITING"),
        (["OK", "RUNNING"], "WAITING"),
        (["OK", "ERROR", "NO_NAILS"], "READY"),
        (["OK"], "READY"),
        (["ERROR", "NO_NAILS"], "NOT_PUBLISHABLE"),
        (["NO_NAILS"], "NOT_PUBLISHABLE"),
    ],
)
def test_readiness_requires_all_terminal_and_at_least_one_ok(outcomes, expected):
    assert product_readiness(tuple(PhotoOutcome(o) for o in outcomes)) == expected


def test_seven_photo_product_is_not_ready_after_first_five():
    assert product_readiness((PhotoOutcome.OK,) * 5 + (PhotoOutcome.PENDING,) * 2) == "WAITING"


def test_unknown_outcome_is_not_treated_as_terminal_success():
    with pytest.raises(ReplenishmentError):
        product_readiness(("UNKNOWN",))
