"""Regressions for independent review051; no models or working database."""

import hashlib
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from product_search.infrastructure.replenishment_repository import PostgresReplenishment, digest
from product_search.infrastructure.replenishment_runtime_binding import canonical
from product_search.search.replenishment_contracts import Ownership, ReplenishmentError
from tests.test_replenishment_contracts import package
from tests.test_replenishment_runtime_binding import gate


@pytest.mark.parametrize("payload", [{"source_ref": "фото.png"}, {"preprocessing": "нормализация"}])
def test_unicode_identities_use_same_canonical_encoding(payload):
    assert hashlib.sha256(canonical(payload)).hexdigest() == digest(payload)


class Connection:
    def __init__(self, clock):
        self.clock = clock
        self.timeouts = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    @contextmanager
    def transaction(self):
        yield
        self.committed = True

    def execute(self, sql, params=None):
        if "set_config" in sql:
            self.timeouts.append(int(params[0][:-2]))
        elif sql == "FIRST_LOCK":
            self.clock.now += 1.8
        elif sql == "SECOND_LOCK":
            assert self.timeouts[-1] <= 200, "second lock must use remaining budget"
        return SimpleNamespace(fetchone=lambda: None)


def test_sql_budget_is_refreshed_between_sequential_waits():
    clock = SimpleNamespace(now=0.0)
    conn = Connection(clock)
    repo = PostgresReplenishment(lambda: conn, package(), 5.0, clock=lambda: clock.now)
    with repo._transaction() as sql:
        sql.execute("FIRST_LOCK")
        sql.execute("SECOND_LOCK")
    assert conn.committed


@pytest.mark.parametrize("revoke", ["expiry", "grant", "claim"])
def test_lost_authorization_before_commit_rolls_back_and_cleanup_stays_available(tmp_path, revoke):
    grant, pkg = gate(tmp_path)
    owner = Ownership("run", "token", 1)
    claim = grant.consume(owner, pkg)
    conn = Connection(SimpleNamespace(now=0.0))
    repo = PostgresReplenishment(lambda: conn, pkg, 100.0, clock=lambda: 0.0)
    repo.authorize_transaction = lambda: grant.check_owner(owner, pkg)
    with pytest.raises(ReplenishmentError, match="CLAIM_MISMATCH"), repo._transaction():
        if revoke == "expiry":
            grant.wall_clock = lambda: 111.0
        elif revoke == "grant":
            grant.path.unlink()
        else:
            claim.unlink()
    assert not conn.committed
    with repo._transaction(cleanup=True):
        pass
    assert conn.committed


def test_native_publication_without_workers_consumes_grant_and_returns_search(
    tmp_path, monkeypatch
):
    import json
    import time
    from dataclasses import asdict, replace

    from product_search.infrastructure import replenishment_application as application
    from product_search.infrastructure import replenishment_host as host
    from product_search.infrastructure import replenishment_runtime_binding as runtime
    from product_search.infrastructure.nail_build_composition import publish_private_json

    tmp_path.chmod(0o700)
    binding = {
        "shared_runtime_root": str(tmp_path),
        "target_policy": {},
        "resource_limits": {"i_rss_bytes": 100, "encoder_rss_bytes": 100},
        "policy": {"poll_seconds": 0.5},
    }
    pkg = replace(
        package(),
        scope="RETRY_PUBLICATION",
        runtime_sha=digest(binding),
        semantic_profile_sha=digest({}),
    )
    publish_private_json(tmp_path / "binding.json", binding)
    publish_private_json(tmp_path / "profile.json", {})
    runtime.issue_grant(
        tmp_path / "grant.json",
        pkg,
        approved_package_sha=runtime.FreshGrant.package_sha(pkg),
        expires_at=time.time() + 30,
        search_authorized=True,
    )
    monkeypatch.setattr(runtime, "verify_code_inventory", lambda *a: None)
    monkeypatch.setattr(runtime, "verify_frozen_inputs", lambda *a: None)
    captured = {}

    class App:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self.supervisor = SimpleNamespace(mode="CLOSED")

        def _start(self, *a, **k):
            return None

        def initialize_search(self, pkg):
            assert captured["authorize_search"](pkg)

    monkeypatch.setattr(application, "LocalReplenishmentApplication", App)

    def serve(*args, **kwargs):
        owner = Ownership("run", "token", 1)
        callback = captured.get("claim_build")
        if callback:
            callback(owner, pkg)
        assert captured["authorize_search"](pkg), "publication-only owner must consume its grant"

    monkeypatch.setattr(host, "serve_owner", serve)
    host.run_native_host(
        {
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
    )
    grant_data = json.loads((tmp_path / "grant.json").read_text())
    assert (tmp_path / (grant_data["nonce"] + ".claim")).exists()


def test_application_claims_owner_before_first_mutation_without_worker_factory(tmp_path):
    from dataclasses import asdict, replace

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.replenishment_application import (
        LocalReplenishmentApplication,
    )
    from product_search.infrastructure.replenishment_runtime_binding import FreshGrant
    from product_search.search.replenishment_contracts import ResourceObservation

    tmp_path.chmod(0o700)
    pkg = replace(package(), scope="RETRY_PUBLICATION", semantic_profile_sha=digest({}))
    publish_private_json(
        tmp_path / "grant.json",
        {
            "schema_version": 1,
            "status": "APPROVED_BY_OWNER",
            "nonce": "a" * 64,
            "package_sha": FreshGrant.package_sha(pkg),
            "scope": pkg.scope,
            "expires_at": 110.0,
            "search_authorized": True,
        },
    )
    grant = FreshGrant(tmp_path / "grant.json", wall_clock=lambda: 100.0)
    owner = Ownership("run", "token", 2)

    class MutationReached(Exception):
        pass

    class Repository:
        def validate_inventory(self, products):
            pass

        def read_retry_inventory(self, *args):
            return (), None

        def read_owner_epoch(self):
            return 0

        def issue_owner(self, mode, *args):
            return owner if mode == "BUILD" else Ownership("search", "query", 1)

        def register_profile(self, actual_owner, profile):
            assert grant._claim is not None, (
                "authorization must be consumed before profile mutation"
            )
            grant.check_owner(actual_owner, pkg)
            raise MutationReached

        def finish_run(self, *args):
            pass

    app = LocalReplenishmentApplication(
        tmp_path,
        lambda *a: Repository(),
        {},
        None,
        lambda *a: pytest.fail("no ML factory"),
        SimpleNamespace(monotonic=lambda: 0.0),
        authorize_build=lambda p: grant.authorize_build(p),
        authorize_search=lambda p: True,
        observe=lambda: ResourceObservation("OK", 0.0),
        quiesce=lambda *a: True,
        summary_reader=lambda *a: None,
    )
    app.claim_build = grant.consume
    app.initialize_search(pkg)
    try:
        with pytest.raises(MutationReached):
            app.retry_publication(asdict(pkg), "revision")
    finally:
        app.supervisor.close(end_at=10.0, stop_grace=1, kill_wait=1)


def test_crash_socket(tmp_path):
    import subprocess
    import sys

    from product_search.infrastructure.replenishment_cli import PrivateCommandServer
    from product_search.infrastructure.replenishment_supervisor import ModeLease

    tmp_path.chmod(0o700)
    code = """
import os,sys
from pathlib import Path
from product_search.infrastructure.replenishment_cli import PrivateCommandServer
from product_search.infrastructure.replenishment_supervisor import ModeLease
root=Path(sys.argv[1]);lease=ModeLease(root)
server=PrivateCommandServer(root,lease,lambda _: {},timeout_seconds=1,max_bytes=65536)
os._exit(0)
"""
    subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)], check=True, timeout=5)
    assert (tmp_path / "owner.sock").exists()
    lease = ModeLease(tmp_path)
    try:
        server = PrivateCommandServer(
            tmp_path, lease, lambda _: {}, timeout_seconds=1, max_bytes=65536
        )
        server.close()
    finally:
        lease.close()
    assert not (tmp_path / "owner.sock").exists()


@pytest.mark.parametrize("replacement", ["file", "socket", "symlink", "live_pid", "lease"])
def test_socket_foreign(tmp_path, replacement):
    import json
    import os
    import socket
    import subprocess
    import sys

    from product_search.infrastructure.replenishment_cli import CliError, PrivateCommandServer
    from product_search.infrastructure.replenishment_supervisor import ModeLease

    tmp_path.chmod(0o700)
    code = """
import os,sys
from pathlib import Path
from product_search.infrastructure.replenishment_cli import PrivateCommandServer
from product_search.infrastructure.replenishment_supervisor import ModeLease
root=Path(sys.argv[1]);lease=ModeLease(root)
server=PrivateCommandServer(root,lease,lambda _: {},timeout_seconds=1,max_bytes=65536)
os._exit(0)
"""
    subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)], check=True, timeout=5)
    path = tmp_path / "owner.sock"
    marker = tmp_path / "owner.socket.json"
    foreign = None
    if replacement in {"file", "socket", "symlink"}:
        path.rename(tmp_path / "original.sock")
        if replacement == "file":
            path.write_text("protected")
        elif replacement == "symlink":
            path.symlink_to(tmp_path / "original.sock")
        else:
            foreign = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            foreign.bind(str(path))
            path.chmod(0o600)
    else:
        data = json.loads(marker.read_text())
        if replacement == "live_pid":
            data["pid"] = os.getpid()
        else:
            data["lease"][1] += 1
        marker.write_text(json.dumps(data))
    lease = ModeLease(tmp_path)
    try:
        with pytest.raises(CliError):
            PrivateCommandServer(tmp_path, lease, lambda _: {}, timeout_seconds=1, max_bytes=65536)
        assert os.path.lexists(path)
    finally:
        lease.close()
        if foreign is not None:
            foreign.close()


def test_stream_cursor_refreshes_budget_before_each_fetch():
    clock = SimpleNamespace(now=0.0)
    conn = Connection(clock)

    class Cursor:
        itersize = 2
        calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, *args):
            pass

        def fetchmany(self, size):
            self.calls += 1
            if self.calls == 1:
                clock.now += 1.8
                return [(1,)]
            assert conn.timeouts[-1] <= 200
            return []

    conn.cursor = lambda **kwargs: Cursor()
    repo = PostgresReplenishment(lambda: conn, package(), 5.0, clock=lambda: clock.now)
    with repo._transaction() as sql, sql.cursor(name="stream") as cursor:
        cursor.execute("SELECT")
        assert list(cursor) == [(1,)]
