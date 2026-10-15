"""Finite warning policy uses fake monotonic time; no sleep/model/DB."""

from product_search.search.corpus_replenishment import ResourceWait
from product_search.search.replenishment_contracts import ResourceObservation
from tests.test_replenishment_boundaries import Clock
from tests.test_replenishment_contracts import package


def guard(end=1000):
    clock = Clock(0)
    return ResourceWait(package(overall_seconds=1000), end, clock), clock


def sample(clock, status):
    return ResourceObservation(status, clock.now)


def test_warning_blocks_until_thirty_seconds_of_fresh_ok():
    gate, clock = guard()
    assert not gate.admit(sample(clock, "WARNING"), 5)
    clock.now = 10
    assert not gate.admit(sample(clock, "OK"), 5)
    for now in range(11, 40):
        clock.now = now
        assert not gate.admit(sample(clock, "OK"), 5)
    clock.now = 39.9
    assert not gate.admit(sample(clock, "OK"), 5)
    clock.now = 40
    assert gate.admit(sample(clock, "OK"), 5)


def test_repeated_warning_does_not_extend_three_hundred_second_wait():
    gate, clock = guard()
    assert not gate.admit(sample(clock, "WARNING"), 5)
    clock.now = 270
    assert not gate.admit(sample(clock, "OK"), 5)
    clock.now = 290
    assert not gate.admit(sample(clock, "WARNING"), 5)
    clock.now = 300
    assert not gate.admit(sample(clock, "OK"), 5)
    assert gate.reason == "WAIT_TIMEOUT"
    clock.now = 340
    assert not gate.admit(sample(clock, "OK"), 5)


def test_cleanup_cutoff_wins_before_wait_limit():
    gate, clock = guard(end=50)
    assert not gate.admit(sample(clock, "WARNING"), 5)
    clock.now = 47
    assert not gate.admit(sample(clock, "OK"), 1)
    assert gate.reason == "DEADLINE"


def test_critical_unknown_and_stale_are_terminal_even_after_ok():
    for observation in (
        ResourceObservation("CRITICAL", 0),
        ResourceObservation("UNKNOWN", 0),
        ResourceObservation("OK", -2),
        None,
    ):
        gate, clock = guard()
        assert not gate.admit(observation, 5) and gate.reason == "RESOURCE_STOP"
        clock.now = 40
        assert not gate.admit(sample(clock, "OK"), 5)


def test_warning_resets_stability_without_resetting_window():
    gate, clock = guard()
    assert not gate.admit(sample(clock, "WARNING"), 5)
    clock.now = 100
    assert not gate.admit(sample(clock, "OK"), 5)
    clock.now = 120
    assert not gate.admit(sample(clock, "WARNING"), 5)
    clock.now = 125
    assert not gate.admit(sample(clock, "OK"), 5)
    for now in range(126, 155):
        clock.now = now
        assert not gate.admit(sample(clock, "OK"), 5)
    clock.now = 155
    assert gate.admit(sample(clock, "OK"), 5)


def test_an_operation_must_fit_before_cleanup_and_clock_cannot_reverse():
    gate, clock = guard(end=20)
    clock.now = 12
    assert not gate.admit(sample(clock, "OK"), 5)
    assert gate.reason == "DEADLINE"
    gate, clock = guard()
    clock.now = 10
    assert gate.admit(sample(clock, "OK"), 5)
    clock.now = 9
    assert not gate.admit(sample(clock, "OK"), 5)
    assert gate.reason == "RESOURCE_STOP"
