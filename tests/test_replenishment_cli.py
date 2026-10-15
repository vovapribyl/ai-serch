"""Owner CLI unit and bounded private IPC tests; no real corpus/models."""

import io
import json
import os
import threading
from dataclasses import asdict, replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from product_search.infrastructure.replenishment_cli import (
    CliError,
    OwnerDispatcher,
    PrivateCommandServer,
    UnixCommandClient,
    main,
    parse_command,
)
from product_search.infrastructure.replenishment_supervisor import ModeLease
from product_search.search.replenishment_contracts import ReplenishmentError
from product_search.web.app import create_app
from tests.test_replenishment_contracts import package
from tests.test_replenishment_lifecycle import (
    bounded_case as bounded_case,  # noqa: PLC0414 -- autouse pytest fixture
)

RUN = str(uuid4())
REV = str(uuid4())
PHOTO = str(uuid4())


@pytest.fixture
def inputs(tmp_path):
    tmp_path.chmod(0o700)
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps(asdict(package())))
    pkg.chmod(0o600)
    inventory = tmp_path / "inventory.json"
    inventory.write_text("[]")
    inventory.chmod(0o600)
    return pkg, inventory


@pytest.mark.parametrize(
    "action,extra,scope",
    [
        ("start", ["--inventory", "INVENTORY"], "START"),
        ("resume", ["--run", RUN], "RESUME"),
        (
            "retry-photo",
            ["--revision", REV, "--photo", PHOTO, "--expected-version", "1"],
            "RETRY_PHOTO",
        ),
        ("retry-publication", ["--revision", REV], "RETRY_PUBLICATION"),
    ],
)
def test_cli_grammar_loads_private_package_and_matches_scope(inputs, action, extra, scope):
    pkg, inventory = inputs
    pkg.write_text(json.dumps(asdict(package(scope=scope))))
    extra = [str(inventory) if value == "INVENTORY" else value for value in extra]
    command = parse_command([action, "--execution-package", str(pkg), *extra])
    assert command is not None and command["action"] == action
    assert command["package"]["scope"] == scope
    assert "package_path" not in command and "inventory_path" not in command


@pytest.mark.parametrize(
    "argv",
    [
        ["status"],
        ["status", "--run", RUN, "--run", RUN],
        ["status", "--run", "not-a-uuid"],
        ["status", "--run", RUN, "--force"],
        ["retry-photo", "--expected-version", "0"],
        ["start", "--inventory", "private-path"],
        ["status", "--run", RUN, "--unknown", "secret"],
    ],
)
def test_bad_arguments_are_refused_without_echoing_raw_values(argv):
    output, error = io.StringIO(), io.StringIO()
    assert (
        main(argv, client=lambda _: pytest.fail("must not connect"), stdout=output, stderr=error)
        == 2
    )
    assert "private-path" not in error.getvalue() and "secret" not in error.getvalue()


def test_help_has_no_ipc_database_or_model_side_effects():
    out, err = io.StringIO(), io.StringIO()
    assert (
        main(["--help"], client=lambda _: pytest.fail("help connected"), stdout=out, stderr=err)
        == 0
    )
    assert "start" in out.getvalue() and not err.getvalue()


def test_package_permissions_symlink_and_scope_are_checked_before_ipc(inputs):
    pkg, inventory = inputs
    pkg.chmod(0o644)
    with pytest.raises(CliError):
        parse_command(["start", "--execution-package", str(pkg), "--inventory", str(inventory)])
    pkg.chmod(0o600)
    link = pkg.parent / "link"
    link.symlink_to(pkg)
    with pytest.raises(CliError):
        parse_command(["start", "--execution-package", str(link), "--inventory", str(inventory)])
    with pytest.raises(CliError):
        parse_command(["resume", "--execution-package", str(pkg), "--run", RUN])


def response(status="OK", reason=None):
    return {"schema_version": 1, "status": status, "reason": reason, "summary": None}


@pytest.mark.parametrize(
    "status,reason,code",
    [
        ("OK", None, 0),
        ("REFUSED", "BUSY", 3),
        ("REFUSED", "VERSION_CONFLICT", 3),
        ("STOPPED", "DEADLINE", 4),
        ("ERROR", "INFRASTRUCTURE_ERROR", 5),
        ("UNKNOWN", "COMMIT_UNKNOWN", 6),
    ],
)
def test_exit_codes_and_safe_json(status, reason, code):
    out = io.StringIO()
    assert (
        main(
            ["status", "--run", RUN],
            client=lambda _: response(status, reason),
            stdout=out,
            stderr=io.StringIO(),
        )
        == code
    )
    assert json.loads(out.getvalue()) == response(status, reason)


def test_untrusted_response_cannot_leak_paths_or_secret_fields():
    out, err = io.StringIO(), io.StringIO()
    bad = {**response(), "raw_source_path": "SECRET/private"}
    assert main(["status", "--run", RUN], client=lambda _: bad, stdout=out, stderr=err) == 5
    assert "SECRET" not in out.getvalue() + err.getvalue()


def test_check_role_never_dispatches_mutating_command(inputs):
    pkg, inventory = inputs

    class App:
        def start(self, *args):
            pytest.fail("CHECK ran build")

        def status(self, run):
            return None

    dispatcher = OwnerDispatcher(App(), role="CHECK")
    answer = dispatcher.handle(
        parse_command(["start", "--execution-package", str(pkg), "--inventory", str(inventory)])
    )
    assert answer["status"] == "REFUSED" and answer["reason"] == "INVALID_SCOPE"
    assert dispatcher.handle(parse_command(["status", "--run", RUN]))["status"] == "OK"


def test_web_unavailable_is_503_without_search_or_database_calls():
    app = create_app(
        lambda: pytest.fail("DB probe from landing"), object(), search_available=lambda: False
    )
    reply = TestClient(app).get("/")
    assert reply.status_code == 503 and "Поиск временно недоступен" in reply.text


def test_private_unix_socket_uses_existing_lease_and_removes_only_owned_socket(tmp_path):
    tmp_path.chmod(0o700)
    lease = ModeLease(tmp_path)
    server = PrivateCommandServer(
        tmp_path, lease, lambda _: response(), timeout_seconds=2, max_bytes=65536
    )
    errors = []

    def serve():
        try:
            server.serve_once()
        except (OSError, CliError) as error:
            errors.append(error)

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        assert os.stat(tmp_path / "owner.sock").st_mode & 0o777 == 0o600
        client = UnixCommandClient(tmp_path, timeout_seconds=2, max_bytes=65536)
        answer = client.send(parse_command(["status", "--run", RUN]))
        assert answer == response()
        thread.join(3)
        assert not thread.is_alive() and not errors
        with pytest.raises(ReplenishmentError, match="BUSY"):
            ModeLease(tmp_path)
    finally:
        server.close()
        lease.close()
        thread.join(3)
    assert not (tmp_path / "owner.sock").exists()


def test_existing_socket_and_foreign_replacement_are_never_unlinked(tmp_path):
    tmp_path.chmod(0o700)
    lease = ModeLease(tmp_path)
    server = PrivateCommandServer(
        tmp_path, lease, lambda _: response(), timeout_seconds=1, max_bytes=65536
    )
    moved = tmp_path / "saved.sock"
    try:
        with pytest.raises(CliError):
            PrivateCommandServer(
                tmp_path, lease, lambda _: response(), timeout_seconds=1, max_bytes=65536
            )
        (tmp_path / "owner.sock").rename(moved)
        (tmp_path / "owner.sock").write_text("protected")
        with pytest.raises(CliError):
            server.close()
        assert (tmp_path / "owner.sock").read_text() == "protected"
    finally:
        server.sock.close()
        lease.close()
        moved.unlink(missing_ok=True)


def test_client_timeout_is_unknown_and_never_repeats_sent_command(tmp_path):
    tmp_path.chmod(0o700)
    lease = ModeLease(tmp_path)
    server = PrivateCommandServer(
        tmp_path, lease, lambda _: response(), timeout_seconds=1, max_bytes=65536
    )
    try:
        answer = UnixCommandClient(tmp_path, timeout_seconds=0.05, max_bytes=65536).send(
            parse_command(["status", "--run", RUN])
        )
        assert answer["status"] == "UNKNOWN"
    finally:
        server.close()
        lease.close()


def test_boolean_protocol_version_is_not_schema_one():
    from product_search.infrastructure.replenishment_cli import validate_command

    with pytest.raises(CliError):
        validate_command({"schema_version": True, "action": "status", "run": RUN})


from tests.test_replenishment_flow import command
from tests.test_replenishment_flow import flow as flow  # noqa: PLC0414 -- pytest fixture
from tests.test_replenishment_postgres_integration import db as db  # noqa: PLC0414
from tests.test_replenishment_retry import failed_photo, photo_request, publication_fault


@pytest.mark.parametrize("action", ["retry-photo", "retry-publication"])
def test_cli_retry_routes_to_completed_operation(flow, db, action):
    app, pkg, products, _, _, _ = flow
    if action == "retry-photo":
        first = failed_photo(flow)
        with db.connect() as conn:
            version = conn.execute("SELECT version FROM replenishment_product_heads").fetchone()[0]
        payload = photo_request(pkg, first, version)
    else:
        publication_fault(app)
        first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))["summary"]
        payload = {
            "package": asdict(replace(pkg, scope="RETRY_PUBLICATION")),
            "revision": first["revision_refs"][0],
        }
    answer = OwnerDispatcher(app, role="OWNER").handle(
        dict(schema_version=1, action=action, **payload)
    )
    assert answer["status"] == "OK" and answer["summary"]["publications"][0]["state"] == "SUCCEEDED"
