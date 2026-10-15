import subprocess

import pytest

from tests.support.replenishment_harness import BoundedCommands, HarnessError


def test_expired_budget_cannot_execute_a_command():
    calls = []
    runner = BoundedCommands(10, clock=lambda: 10, execute=lambda *a, **k: calls.append(a))
    with pytest.raises(HarnessError, match="TEST_DEADLINE"):
        runner.run(["docker", "inspect"])
    assert calls == []


def test_command_timeout_is_capped_by_remaining_time():
    calls = []

    def execute(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, "ok", "")

    runner = BoundedCommands(10, clock=lambda: 8, execute=execute)
    assert runner.run(["docker", "inspect"]).stdout == "ok"
    assert calls[0][1]["timeout"] == 2
    assert calls[0][1]["shell"] is False


def test_subprocess_errors_do_not_expose_private_output():
    def execute(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, "secret", "private DSN")

    with pytest.raises(HarnessError) as error:
        BoundedCommands(10, clock=lambda: 0, execute=execute).run(["docker"])
    assert str(error.value) == "TEST_COMMAND_FAILED"


def test_timeout_is_a_controlled_error():
    def execute(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output="secret")

    with pytest.raises(HarnessError, match="TEST_COMMAND_TIMEOUT"):
        BoundedCommands(10, clock=lambda: 0, execute=execute).run(["docker"])


from tests.support.replenishment_harness import validate_container


def metadata(**changes):
    values = {
        "image": "sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b",
        "labels": {"replenishment-b1": "synthetic-marker"},
        "name": "/replenishment-b1-synthetic-marker",
        "memory": 536870912,
        "cpus": 1000000000,
        "pids": 128,
        "running": True,
        "mounts": [{"Type": "tmpfs", "Destination": "/var/lib/postgresql/data"}],
        "ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "54321"}]},
    }
    values.update(changes)
    return values


@pytest.mark.parametrize(
    "changes",
    [
        {"labels": {"replenishment-b1": "another-owner"}},
        {"image": "other-image"},
        {"name": "/other-container"},
        {"memory": 0},
        {"cpus": 0},
        {"pids": 0},
        {"mounts": [{"Type": "bind", "Destination": "/var/lib/postgresql/data"}]},
        {"ports": {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "54321"}]}},
    ],
)
def test_foreign_or_unbounded_database_container_is_rejected(changes):
    with pytest.raises(HarnessError, match="TEST_CONTAINER_MISMATCH"):
        validate_container(metadata(**changes), "synthetic-marker")


def test_owned_bounded_database_returns_only_local_ephemeral_port():
    assert validate_container(metadata(), "synthetic-marker") == 54321


def test_migration_failure_preserves_private_diagnostic(tmp_path, monkeypatch):
    import time
    from contextlib import nullcontext

    from tests.support.replenishment_harness import SyntheticDatabase

    database = SyntheticDatabase(tmp_path, time.monotonic() + 60)
    database.connect = lambda: nullcontext()
    database.config = {
        "user": "synthetic",
        "password": "synthetic-secret",
        "dbname": "synthetic",
        "port": 54321,
    }
    monkeypatch.setattr(
        "tests.support.replenishment_harness.subprocess.run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "", "migration diagnostic"),
    )
    with pytest.raises(HarnessError):
        database.migrate()
    diagnostic = tmp_path / "diagnostic.log"
    assert diagnostic.exists()
    assert diagnostic.read_text() == "\nmigration diagnostic\n"
    assert diagnostic.stat().st_mode & 0o777 == 0o600


def test_only_one_b1_database_admission_exists_across_helpers(tmp_path):
    import time

    from tests.support.replenishment_harness import SyntheticDatabase

    first = SyntheticDatabase(tmp_path / "one", time.monotonic() + 30)
    second = SyntheticDatabase(tmp_path / "two", time.monotonic() + 30)
    first._acquire_admission()
    try:
        with pytest.raises(HarnessError, match="TEST_DB_BUSY"):
            second._acquire_admission()
    finally:
        first._release_admission()
    second._acquire_admission()
    second._release_admission()
