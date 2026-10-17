"""Finite private host wiring, without sockets, SQL or model imports."""

from types import SimpleNamespace

import pytest

from tests.test_replenishment_contracts import package


def test_host_processes_a_finite_number_of_commands_and_closes_in_order():
    from product_search.infrastructure.replenishment_host import serve_owner

    events = []
    app = SimpleNamespace(
        supervisor=SimpleNamespace(
            lease=object(),
            close=lambda **kwargs: events.append("supervisor-close"),
        )
    )

    class Server:
        def __init__(self, *args, **kwargs):
            events.append("listen")

        def serve_once(self):
            events.append("command")

        def close(self):
            events.append("socket-close")

    serve_owner(
        app,
        "/unused",
        package(),
        end_at=50.0,
        max_commands=1,
        timeout_seconds=2.0,
        max_bytes=65536,
        server_factory=Server,
        clock=lambda: 1.0,
    )
    assert events == ["listen", "command", "socket-close", "supervisor-close"]


def test_runtime_target_refuses_external_endpoint_before_docker_or_sql(tmp_path):
    import pytest

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.replenishment_host import RuntimeTarget
    from product_search.search.replenishment_contracts import ReplenishmentError

    tmp_path.chmod(0o700)
    path = tmp_path / "target.json"
    publish_private_json(
        path,
        {
            "marker": "owned",
            "container_id": "own",
            "config": {
                "host": "production.example",
                "port": 5432,
                "dbname": "owned",
                "user": "owned",
                "password": "private",
            },
        },
    )
    target = RuntimeTarget(
        path,
        {"marker": "owned", "image": "pin", "dbname": "owned", "user": "owned"},
        command=lambda *a, **k: pytest.fail("Docker must not run"),
        connector=lambda **k: pytest.fail("SQL must not run"),
    )
    with pytest.raises(ReplenishmentError, match="TARGET_NOT_VERIFIED"):
        target.connect(package(), 50.0, clock=lambda: 1.0)


def test_native_host_rejects_proposal_before_creating_locks_or_sql(tmp_path):
    from dataclasses import asdict

    import pytest

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.replenishment_host import run_native_host
    from product_search.search.replenishment_contracts import ReplenishmentError

    tmp_path.chmod(0o700)
    publish_private_json(tmp_path / "grant.json", {"status": "PENDING_OWNER_APPROVAL"})
    config = {"package": asdict(package()), "grant_path": str(tmp_path / "grant.json")}
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"):
        run_native_host(config)
    assert not (tmp_path / "mode.lock").exists()


def test_runtime_target_verifies_owned_container_and_sql_identity(tmp_path):
    import json
    from types import SimpleNamespace

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.replenishment_host import RuntimeTarget

    tmp_path.chmod(0o700)
    policy = {"marker": "owned", "image": "pin", "dbname": "owned", "user": "owned"}
    config = {
        "host": "127.0.0.1",
        "port": 55001,
        "dbname": "owned",
        "user": "owned",
        "password": "private",
    }
    path = tmp_path / "target.json"
    publish_private_json(path, {"marker": "owned", "container_id": "own", "config": config})
    meta = {
        "Id": "own",
        "Image": "pin",
        "Config": {"Labels": {"corpus-replenishment-probe": "owned"}},
        "State": {"Running": True},
        "HostConfig": {"Memory": 536870912, "NanoCpus": 1000000000, "PidsLimit": 128},
        "Mounts": [{"Type": "tmpfs", "Destination": "/var/lib/postgresql/data"}],
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55001"}]}},
    }
    calls = []

    class Connection:
        def execute(self, sql):
            return SimpleNamespace(
                fetchone=lambda: (
                    ("owned", "owned")
                    if sql.startswith("SELECT current")
                    else ("0010_corpus_replenishment_v1",)
                )
            )

        def close(self):
            calls.append("close")

    connection = Connection()

    def connect(**kwargs):
        calls.append(kwargs)
        return connection

    target = RuntimeTarget(
        path,
        policy,
        command=lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps([meta])),
        connector=connect,
    )
    assert target.connect(package(), 50.0, clock=lambda: 1.0) is connection
    assert 0 < calls[0]["connect_timeout"] <= package().db_seconds
    assert "statement_timeout=" in calls[0]["options"]


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("defer", [False, True, "bad-pin"])
def test_host_records_resources_after_driver_creation_before_first_stage(
    tmp_path, monkeypatch, diagnostics, defer
):
    """Actual host wiring must admit the idle driver before it has control data."""
    import hashlib
    from dataclasses import asdict, replace

    from product_search.infrastructure import replenishment_application as application
    from product_search.infrastructure import replenishment_host as host
    from product_search.infrastructure import replenishment_runtime_binding as binding_module
    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.search.replenishment_contracts import ResourceObservation

    tmp_path.chmod(0o700)
    log_root = tmp_path / "logs"
    log_root.mkdir(mode=0o700)
    binding = {
        "load_diagnostics": diagnostics,
        "defer_region_limit": bool(defer),
        "shared_runtime_root": str(tmp_path),
        "operation_log_root": str(log_root),
        "target_policy": {},
        "policy": {"poll_seconds": 0.5},
        "resource_limits": {"i_rss_bytes": 100, "encoder_rss_bytes": 100},
    }
    if defer:
        publish_private_json(tmp_path / "inputs.json", {"products": []})
        binding["deferred_inventory_sha256"] = (
            hashlib.sha256(binding_module.canonical({"products": []})).hexdigest()
            if defer is True
            else "wrong"
        )
        publish_private_json(
            tmp_path / "code.json",
            {"src/product_search/infrastructure/replenishment_deferred_photos.py": "pinned"},
        )
    profile = {}
    pkg = replace(
        package(),
        runtime_sha=hashlib.sha256(binding_module.canonical(binding)).hexdigest(),
        semantic_profile_sha=hashlib.sha256(binding_module.canonical(profile)).hexdigest(),
    )
    publish_private_json(tmp_path / "binding.json", binding)
    publish_private_json(tmp_path / "profile.json", profile)
    monkeypatch.setattr(
        binding_module,
        "FreshGrant",
        lambda _: SimpleNamespace(authorize_build=lambda _: True, consume=lambda *a: None),
    )
    monkeypatch.setattr(binding_module, "verify_code_inventory", lambda *a: None)
    monkeypatch.setattr(binding_module, "verify_frozen_inputs", lambda *a: None)

    class Sensor:
        def __init__(self, *a, **k):
            self.last_sample = {"rss_bytes": 1, "mps_bytes": 0, "pressure": 1}

        def __call__(self):
            return ResourceObservation("OK", 1.0)

    monkeypatch.setattr(binding_module, "MacResourceObserver", Sensor)
    from product_search.infrastructure import replenishment_load_diagnostics as load

    monkeypatch.setattr(load, "mac_process_sample", lambda *a: {"pressure": 1})
    observations = []
    from product_search.infrastructure import replenishment_repository as repository_module

    monkeypatch.setattr(
        repository_module,
        "PostgresReplenishment",
        lambda *a, **k: SimpleNamespace(
            commit_checkpoint=lambda *a: "checkpoint-receipt",
            finish_photo=lambda *a: None,
            publish_revision=lambda *a: SimpleNamespace(state="UNKNOWN"),
        ),
    )

    class App:
        def __init__(
            self, root, repository_factory, profile, files, worker_factory, clock, **kwargs
        ):
            self.repository_factory = repository_factory
            self.worker_factory, self.observe = worker_factory, kwargs["observe"]
            self.supervisor = SimpleNamespace(mode="CLOSED")

        def initialize_search(self, package):
            repository = self.repository_factory(package, 50.0)
            assert (
                repository.commit_checkpoint(SimpleNamespace(photo_ref="private-photo"), None, None)
                == "checkpoint-receipt"
            )
            assert (
                repository.publish_revision(
                    SimpleNamespace(revision_ref="private-revision"), None, None
                ).state
                == "UNKNOWN"
            )
            self.worker_factory(repository, None, package, 50.0)
            observations.append(self.observe().status)

        def _start(self, *a, **k):
            return 42

        def _admit_resources(self, operation_seconds):
            return True

    monkeypatch.setattr(application, "LocalReplenishmentApplication", App)
    monkeypatch.setattr(host, "serve_owner", lambda app, *a, **k: app._start())
    config = {
        "package": asdict(pkg),
        "grant_path": str(tmp_path / "grant.json"),
        "binding_path": str(tmp_path / "binding.json"),
        "profile_path": str(tmp_path / "profile.json"),
        "code_inventory_path": str(tmp_path / "code.json"),
        "input_inventory_path": str(tmp_path / "inputs.json"),
        "target_descriptor_path": str(tmp_path / "target.json"),
        "private_root": str(tmp_path),
        "checkpoint_root": str(tmp_path),
        "max_commands": 1,
        "timeout_seconds": 2,
        "max_bytes": 65536,
    }
    if defer == "bad-pin":
        from product_search.search.replenishment_contracts import ReplenishmentError

        with pytest.raises(ReplenishmentError, match="RUNTIME_MISMATCH"):
            host.run_native_host(config)
        assert not (tmp_path / "deferred-photos.json").exists()
        return
    host.run_native_host(config)
    assert observations == ["OK"]
    assert (tmp_path / "deferred-photos.json").exists() is defer
    import json

    journals = list(log_root.glob("operations-*/events.jsonl"))
    assert len(journals) == 1
    events = [json.loads(line) for line in journals[0].read_text().splitlines()]
    assert {e["event"] for e in events} == {"host", "checkpoint", "publication", "batch"}
    assert (
        next(e for e in events if e["event"] == "publication" and e["phase"] == "after")[
            "result_state"
        ]
        == "UNKNOWN"
    )
    assert "private-photo" not in journals[0].read_text()
