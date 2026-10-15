"""Missing guards would admit unbounded work or a mismatched runtime identity."""

from dataclasses import FrozenInstanceError, replace

import pytest

from product_search.search.replenishment_contracts import (
    ExecutionPackage,
    PhotoOutcome,
    ReplenishmentError,
    StageState,
)


def package(**changes):
    values = {
        "schema_version": 1,
        "input_set_sha": "a" * 64,
        "semantic_profile_sha": "b" * 64,
        "code_sha": "c" * 64,
        "model_sha": "d" * 64,
        "runtime_sha": "e" * 64,
        "claims_sha": "f" * 64,
        "scope": "START",
        "overall_seconds": 60.0,
        "http_seconds": 5.0,
        "db_seconds": 2.0,
        "stop_grace_seconds": 1.0,
        "kill_wait_seconds": 1.0,
        "cleanup_reserve_seconds": 3.0,
        "max_source_bytes": 1000,
        "max_pixels": 100,
        "max_regions": 10,
        "max_wire_bytes": 2000,
        "max_vector_bytes": 3000,
        "max_admissions": 20,
        "rss_ceiling_bytes": 1000000,
        "mps_ceiling_bytes": 1000000,
        "observation_max_age_seconds": 1.0,
    }
    values.update(changes)
    return ExecutionPackage(**values)


@pytest.mark.parametrize(
    "field",
    [
        "overall_seconds",
        "http_seconds",
        "db_seconds",
        "stop_grace_seconds",
        "kill_wait_seconds",
        "cleanup_reserve_seconds",
        "observation_max_age_seconds",
    ],
)
@pytest.mark.parametrize("value", [None, 0, -1, float("nan"), float("inf"), True, "5"])
def test_deadlines_must_be_positive_finite_numbers(field, value):
    with pytest.raises(ReplenishmentError, match="INVALID_PACKAGE"):
        package(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "max_source_bytes",
        "max_pixels",
        "max_regions",
        "max_wire_bytes",
        "max_vector_bytes",
        "max_admissions",
        "rss_ceiling_bytes",
        "mps_ceiling_bytes",
    ],
)
@pytest.mark.parametrize("value", [None, 0, -1, 1.5, True, float("inf")])
def test_caps_must_be_positive_integers(field, value):
    with pytest.raises(ReplenishmentError, match="INVALID_PACKAGE"):
        package(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "input_set_sha",
        "semantic_profile_sha",
        "code_sha",
        "model_sha",
        "runtime_sha",
        "claims_sha",
    ],
)
@pytest.mark.parametrize("value", ["", None, "g" * 64, "a" * 63])
def test_identity_must_be_complete_sha256(field, value):
    with pytest.raises(ReplenishmentError, match="INVALID_PACKAGE"):
        package(**{field: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"schema_version": True},
        {"scope": "CHECK"},
        {"scope": "UNKNOWN"},
        {"cleanup_reserve_seconds": 60},
        {"cleanup_reserve_seconds": 1},
        {"http_seconds": 60},
        {"db_seconds": 60},
    ],
)
def test_invalid_scope_or_inconsistent_deadlines_are_refused(changes):
    with pytest.raises(ReplenishmentError, match="INVALID_PACKAGE"):
        package(**changes)


def test_valid_package_is_immutable():
    value = package()
    with pytest.raises(FrozenInstanceError):
        value.overall_seconds = 0
    assert replace(value, scope="RESUME").scope == "RESUME"


@pytest.mark.parametrize("kind", [PhotoOutcome, StageState])
def test_unknown_state_is_refused(kind):
    with pytest.raises(ValueError):
        kind("DONE_MAYBE")


@pytest.mark.parametrize("scope", [[], {}, 1])
def test_malformed_scope_is_a_controlled_package_error(scope):
    with pytest.raises(ReplenishmentError, match="INVALID_PACKAGE"):
        package(scope=scope)
