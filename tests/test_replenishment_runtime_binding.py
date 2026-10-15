"""Model-free tests for fresh grants and runtime resource admission."""

from dataclasses import asdict

import pytest

from product_search.infrastructure.nail_build_composition import publish_private_json
from product_search.infrastructure.replenishment_cli import private_json
from product_search.search.replenishment_contracts import Ownership, ReplenishmentError
from tests.test_replenishment_controller import package


def gate(tmp_path, **changes):
    from product_search.infrastructure.replenishment_runtime_binding import FreshGrant

    tmp_path.chmod(0o700)
    p = package()
    grant = {
        "schema_version": 1,
        "status": "APPROVED_BY_OWNER",
        "nonce": "a" * 64,
        "package_sha": FreshGrant.package_sha(p),
        "scope": p.scope,
        "expires_at": 110.0,
        "search_authorized": False,
    }
    grant.update(changes)
    path = tmp_path / "grant.json"
    publish_private_json(path, grant)
    return FreshGrant(path, wall_clock=lambda: 100.0), p


def test_fresh_grant_is_consumed_once_and_bound_to_owner(tmp_path):
    guard, p = gate(tmp_path)
    assert guard.authorize_build(p)
    owner = Ownership("run", "secret", 1)
    claim = guard.consume(owner, p)
    assert private_json(claim)["owner"] == asdict(owner)
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        guard.consume(owner, p)
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        guard.check_owner(Ownership("other", "secret", 2), p)
    assert guard.check_owner(owner, p) is True


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "PENDING_OWNER_APPROVAL"},
        {"package_sha": "b" * 64},
        {"scope": "RESUME"},
        {"expires_at": 99.0},
        {"expires_at": float("inf")},
        {"nonce": "../unsafe"},
    ],
)
def test_invalid_or_expired_permission_cannot_launch(tmp_path, changes):
    guard, p = gate(tmp_path, **changes)
    assert guard.authorize_build(p) is False
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        guard.consume(Ownership("run", "secret", 1), p)
    assert not tuple(tmp_path.glob("*.claim"))


def test_search_requires_separate_explicit_permission(tmp_path):
    guard, p = gate(tmp_path)
    guard.consume(Ownership("run", "secret", 1), p)
    assert guard.authorize_search(p) is False
    other = tmp_path / "other"
    other.mkdir(mode=0o700)
    allowed, p = gate(other, search_authorized=True)
    assert allowed.authorize_search(p) is False  # No consumed BUILD ownership yet.
    allowed.consume(Ownership("run", "secret", 1), p)
    assert allowed.authorize_search(p) is True


def observer(
    tmp_path,
    *,
    pressure="1",
    rss="10 1 10 100\n20 10 20 200\n21 20 20 300\n99 1 99 999999999\n",
    telemetry=None,
):
    from types import SimpleNamespace

    from product_search.infrastructure.replenishment_runtime_binding import MacResourceObserver

    tmp_path.mkdir(mode=0o700, exist_ok=True)
    tmp_path.chmod(0o700)
    path = tmp_path / "telemetry.json"
    if telemetry is not None:
        publish_private_json(path, telemetry)
    calls = []

    def output(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=rss if argv[0] == "/bin/ps" else pressure)

    sensor = MacResourceObserver(
        package(),
        controller_pid=10,
        owned_worker=lambda: (20, path, "nonce"),
        command=output,
        clock=lambda: 100.0,
    )
    return sensor, calls


def test_resource_observer_counts_owned_group_and_controller_only(tmp_path):
    sensor, calls = observer(
        tmp_path,
        telemetry={
            "pid": 20,
            "nonce": "nonce",
            "observed_at": 99.0,
            "mps_bytes": 100,
        },
    )
    assert sensor().status == "OK"
    assert sensor.last_sample == {"pressure": 1, "rss_bytes": 600 * 1024, "mps_bytes": 100}
    assert all(0 < kwargs["timeout"] <= 2 for _, kwargs in calls)


@pytest.mark.parametrize(
    "telemetry",
    [
        None,
        {"pid": 20, "nonce": "nonce", "observed_at": 90.0, "mps_bytes": 100},
        {"pid": 99, "nonce": "nonce", "observed_at": 99.0, "mps_bytes": 100},
        {"pid": 20, "nonce": "old", "observed_at": 99.0, "mps_bytes": 100},
        {"pid": 20, "nonce": "nonce", "observed_at": 101.0, "mps_bytes": 100},
        {"pid": 20, "nonce": "nonce", "observed_at": 99.0, "mps_bytes": True},
    ],
)
def test_unknown_stale_or_foreign_mps_observation_stops(tmp_path, telemetry):
    sensor, _ = observer(tmp_path, telemetry=telemetry)
    assert sensor().status == "STOP"


def test_warning_does_not_erase_a_latched_critical_stop(tmp_path):
    data = {"pid": 20, "nonce": "nonce", "observed_at": 99.0, "mps_bytes": 100}
    warning, _ = observer(tmp_path / "warning", pressure="2", telemetry=data)
    assert warning().status == "WARNING"
    critical, _ = observer(tmp_path / "critical", pressure="4", telemetry=data)
    assert critical().status == "STOP"
    critical.command = warning.command
    assert critical().status == "STOP"


def test_removed_or_changed_consumed_claim_cannot_reopen_search(tmp_path):
    guard, p = gate(tmp_path, search_authorized=True)
    claim = guard.consume(Ownership("run", "secret", 1), p)
    claim.unlink()
    assert guard.authorize_search(p) is False


def test_new_guard_cannot_readmit_already_consumed_grant(tmp_path):
    guard, p = gate(tmp_path)
    guard.consume(Ownership("run", "secret", 1), p)
    from product_search.infrastructure.replenishment_runtime_binding import FreshGrant

    assert FreshGrant(guard.path, wall_clock=lambda: 100.0).authorize_build(p) is False


def test_worker_bootstrap_refuses_wrong_inventory_before_any_model_import(tmp_path):
    from product_search.infrastructure.replenishment_runtime_binding import verify_code_inventory

    tmp_path.chmod(0o700)
    inventory = tmp_path / "code.json"
    publish_private_json(
        inventory, {"src/product_search/infrastructure/replenishment_workers.py": "0" * 64}
    )
    with pytest.raises(ReplenishmentError, match="RUNTIME_MISMATCH"):
        verify_code_inventory(inventory, "0" * 64)


def test_search_claim_must_keep_exact_consumed_owner(tmp_path):
    guard, p = gate(tmp_path, search_authorized=True)
    claim = guard.consume(Ownership("run", "secret", 1), p)
    value = private_json(claim)
    value["owner"]["epoch"] = 99
    publish_private_json(claim, value)
    assert guard.authorize_search(p) is False


def test_independent_guard_stops_its_group_on_unknown_signal_with_finite_grace():
    import signal

    from product_search.infrastructure.replenishment_worker_entry import guard_owned_group
    from product_search.search.replenishment_contracts import ResourceObservation

    signals = []
    clock = [10.0]

    def sleep(seconds):
        clock[0] += seconds

    guard_owned_group(
        123,
        package(),
        end_at=20.0,
        observe=lambda: ResourceObservation("STOP", clock[0]),
        signal_group=lambda pid, sig: signals.append((pid, sig)),
        clock=lambda: clock[0],
        sleep=sleep,
        group_id=lambda: 123,
    )
    assert signals == [(123, signal.SIGTERM), (123, signal.SIGKILL)]
    assert clock[0] <= 11.0


def test_independent_guard_never_signals_a_foreign_group():
    import pytest

    from product_search.infrastructure.replenishment_worker_entry import guard_owned_group
    from product_search.search.replenishment_contracts import ResourceObservation

    with pytest.raises(ReplenishmentError, match="FENCED"):
        guard_owned_group(
            123,
            package(),
            end_at=20.0,
            observe=lambda: ResourceObservation("STOP", 10.0),
            signal_group=lambda *args: pytest.fail("foreign signal"),
            clock=lambda: 10.0,
            group_id=lambda: 999,
        )


def test_initial_search_permission_is_explicit_and_consumed_separately(tmp_path):
    guard, p = gate(tmp_path, search_authorized=True)
    assert guard.authorize_initial_search(p) is True
    assert guard.authorize_initial_search(p) is False
    assert guard.authorize_build(p) is True
    guard.consume(Ownership("run", "token", 1), p)
    assert guard.authorize_search(p) is True


def test_component_rss_ceiling_is_not_weakened_by_larger_package_ceiling(tmp_path):
    sensor, _ = observer(
        tmp_path, telemetry={"pid": 20, "nonce": "nonce", "observed_at": 99.0, "mps_bytes": 100}
    )
    sensor.worker_rss_ceiling = lambda: 400000
    assert sensor().status == "STOP"


def test_grant_issuer_requires_exact_owner_approved_package_and_never_overwrites(tmp_path):
    from product_search.infrastructure.replenishment_runtime_binding import FreshGrant, issue_grant

    tmp_path.chmod(0o700)
    p = package()
    path = tmp_path / "owner-grant.json"
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        issue_grant(
            path,
            p,
            approved_package_sha="PENDING_OWNER_APPROVAL",
            expires_at=110.0,
            search_authorized=False,
            wall_clock=lambda: 100.0,
        )
    assert not path.exists()
    issue_grant(
        path,
        p,
        approved_package_sha=FreshGrant.package_sha(p),
        expires_at=110.0,
        search_authorized=False,
        wall_clock=lambda: 100.0,
    )
    guard = FreshGrant(path, wall_clock=lambda: 100.0)
    assert guard.authorize_build(p)
    original = path.read_bytes()
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        issue_grant(
            path,
            p,
            approved_package_sha=FreshGrant.package_sha(p),
            expires_at=110.0,
            search_authorized=False,
            wall_clock=lambda: 100.0,
        )
    assert path.read_bytes() == original


def test_frozen_source_hash_is_checked_before_runtime_admission(tmp_path):
    import hashlib
    from dataclasses import replace

    from product_search.infrastructure.replenishment_runtime_binding import (
        canonical,
        verify_frozen_inputs,
    )

    tmp_path.chmod(0o700)
    folder = tmp_path / "input"
    folder.mkdir(mode=0o700)
    source = folder / "photo.png"
    source.write_bytes(b"frozen")
    source.chmod(0o600)
    photo = {
        "ordinal": 1,
        "source_ref": "photo.png",
        "input_sha": hashlib.sha256(b"frozen").hexdigest(),
        "source_bytes": 6,
    }
    product = {
        "corpus_version_id": 1,
        "product_record_id": 1,
        "expected_head_version": 0,
        "photos": [photo],
    }
    inventory = {"products": [product], "frozen_input_root": str(folder)}
    path = tmp_path / "inputs.json"
    publish_private_json(path, inventory)
    hashed = [{"corpus_version_id": 1, "product_record_id": 1, "photos": [photo]}]
    p = replace(package(), input_set_sha=hashlib.sha256(canonical(hashed)).hexdigest())
    assert verify_frozen_inputs(path, {"frozen_input_root": str(folder)}, p)
    source.write_bytes(b"changed")
    with pytest.raises(ReplenishmentError, match="INPUT_MISMATCH"):
        verify_frozen_inputs(path, {"frozen_input_root": str(folder)}, p)


def test_resource_samples_are_serialized_across_guard_and_command_threads(tmp_path):
    import threading

    sensor, _ = observer(
        tmp_path, telemetry={"pid": 20, "nonce": "nonce", "observed_at": 99.0, "mps_bytes": 100}
    )
    base = sensor.command
    first_entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
    count = [0]

    def command(argv, **kwargs):
        if argv[0] == "/bin/ps":
            count[0] += 1
            if count[0] == 1:
                first_entered.set()
                assert release.wait(1)
            else:
                second_entered.set()
        return base(argv, **kwargs)

    sensor.command = command
    first = threading.Thread(target=sensor)
    second = threading.Thread(target=sensor)
    first.start()
    assert first_entered.wait(1)
    second.start()
    try:
        assert not second_entered.wait(0.05)
    finally:
        release.set()
        first.join(1)
        second.join(1)
    assert not first.is_alive() and not second.is_alive()


def test_resource_evidence_is_private_and_its_size_limit_stops_new_work(tmp_path):
    from product_search.infrastructure.replenishment_runtime_binding import (
        RecordingResourceObserver,
    )

    sensor, _ = observer(
        tmp_path, telemetry={"pid": 20, "nonce": "nonce", "observed_at": 99.0, "mps_bytes": 100}
    )
    path = tmp_path / "observations.jsonl"
    record = RecordingResourceObserver(sensor, path, max_bytes=320)
    try:
        assert record().status == "OK"
        original = path.read_bytes()
        assert path.stat().st_mode & 0o777 == 0o600
        assert record().status == "STOP"
        assert path.read_bytes() == original
        assert len(original) <= 320
    finally:
        record.close()


@pytest.mark.parametrize(
    ("case", "expected_check", "expected_reason"),
    [
        ("command", "PROCESS_TABLE", "OBSERVATION_FAILED"),
        ("stale", "TELEMETRY_FRESHNESS", "OBSERVATION_FAILED"),
        ("pressure", "RESOURCE_LIMITS", "PRESSURE_CRITICAL"),
        ("mps", "RESOURCE_LIMITS", "MPS_LIMIT"),
        ("worker_rss", "WORKER_RSS", "OBSERVATION_FAILED"),
    ],
)
def test_stop_records_safe_first_cause_and_sample_validity(
    tmp_path, case, expected_check, expected_reason
):
    import json
    import subprocess

    from product_search.infrastructure.replenishment_runtime_binding import (
        RecordingResourceObserver,
    )

    data = {"pid": 20, "nonce": "nonce", "observed_at": 99.0, "mps_bytes": 100}
    sensor, _ = observer(tmp_path, telemetry=data)
    assert sensor().status == "OK"
    previous = sensor.last_sample.copy()
    if case == "command":

        def fail(*args, **kwargs):
            raise subprocess.TimeoutExpired("SECRET_COMMAND_PATH", 2, stderr="SECRET_ERROR")

        sensor.command = fail
    elif case == "stale":
        publish_private_json(tmp_path / "telemetry.json", dict(data, observed_at=90.0))
    elif case == "worker_rss":
        sensor.worker_rss_ceiling = lambda: 1
    elif case == "pressure":
        from types import SimpleNamespace

        original = sensor.command
        sensor.command = lambda argv, **kw: (
            SimpleNamespace(returncode=0, stdout="4")
            if argv[0] != "/bin/ps"
            else original(argv, **kw)
        )
    else:
        publish_private_json(
            tmp_path / "telemetry.json", dict(data, mps_bytes=sensor.package.mps_ceiling_bytes + 1)
        )
    path = tmp_path / "observations.jsonl"
    record = RecordingResourceObserver(sensor, path, max_bytes=4096)
    try:
        assert record().status == "STOP"
        diagnostic = sensor.last_diagnostic.copy()
        assert diagnostic["check"] == expected_check
        assert diagnostic["reason"] == expected_reason
        assert diagnostic["sample_current"] == (case in ("pressure", "mps"))
        assert diagnostic["error_type"] == (
            "TimeoutExpired"
            if case == "command"
            else "ValueError"
            if case in ("stale", "worker_rss")
            else None
        )
        if not diagnostic["sample_current"]:
            assert sensor.last_sample == previous
        assert record().status == "STOP"
        assert sensor.last_diagnostic == diagnostic
    finally:
        record.close()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert all(row["diagnostic"] == diagnostic for row in rows)
    assert "SECRET" not in path.read_text() and "nonce" not in path.read_text()
