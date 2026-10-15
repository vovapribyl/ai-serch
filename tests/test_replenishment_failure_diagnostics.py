"""Private command diagnostics never change the public error or load SDKs."""

from dataclasses import asdict
from types import SimpleNamespace

from product_search.infrastructure.replenishment_cli import OwnerDispatcher
from tests.test_replenishment_contracts import package


def test_dispatcher_reports_exception_privately_and_keeps_reply_sanitized():
    def fail(**kwargs):
        raise RuntimeError("password=private-secret source=/private/photo.png")

    dispatcher = OwnerDispatcher(SimpleNamespace(start=fail), role="OWNER")
    seen = []
    dispatcher.on_error = seen.append
    reply = dispatcher.handle(
        {"schema_version": 1, "action": "start", "package": asdict(package()), "inventory": []}
    )
    assert reply == {
        "schema_version": 1,
        "status": "ERROR",
        "reason": "INFRASTRUCTURE_ERROR",
        "summary": None,
    }
    assert len(seen) == 1
    assert isinstance(seen[0], RuntimeError)


def test_record_contains_locations_and_chain_but_no_secrets(tmp_path):
    import json

    from product_search.infrastructure.replenishment_runtime_binding import record_command_failure

    tmp_path.chmod(0o700)
    try:
        try:
            raise ValueError("SQL password=private-secret photo=/private/source.png")
        except ValueError as cause:
            raise RuntimeError("private-token") from cause
    except RuntimeError as error:
        record_command_failure(tmp_path, error, max_bytes=65536)
    path = tmp_path / "command-failure.json"
    raw = path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    assert len(raw) <= 65536
    assert not any(
        value in raw
        for value in [b"private-secret", b"private-token", b"/private/source.png", b"SQL"]
    )
    data = json.loads(raw)
    assert [x["type"] for x in data["exceptions"]] == ["RuntimeError", "ValueError"]
    assert all(x["frames"] for x in data["exceptions"])
    assert all(
        set(frame) == {"file", "function", "line"}
        for x in data["exceptions"]
        for frame in x["frames"]
    )


def test_failure_record_size_and_existing_files_are_protected(tmp_path):
    import pytest

    from product_search.infrastructure.replenishment_runtime_binding import record_command_failure
    from product_search.search.replenishment_contracts import ReplenishmentError

    tmp_path.chmod(0o700)
    error = RuntimeError("secret")
    with pytest.raises(ReplenishmentError, match="DIAGNOSTIC_LIMIT"):
        record_command_failure(tmp_path, error, max_bytes=1)
    assert not (tmp_path / "command-failure.json").exists()
    target = tmp_path / "protected"
    target.write_bytes(b"protected")
    path = tmp_path / "command-failure.json"
    path.symlink_to(target)
    with pytest.raises(OSError):
        record_command_failure(tmp_path, error, max_bytes=65536)
    assert target.read_bytes() == b"protected"
    path.unlink()
    path.write_bytes(b"prior evidence")
    with pytest.raises(OSError):
        record_command_failure(tmp_path, error, max_bytes=65536)
    assert path.read_bytes() == b"prior evidence"


def test_sink_failure_does_not_replace_original_public_error():
    def fail(**kwargs):
        raise RuntimeError("secret")

    def unavailable(error):
        raise OSError("secret path")

    dispatcher = OwnerDispatcher(SimpleNamespace(start=fail), role="OWNER", on_error=unavailable)
    answer = dispatcher.handle(
        {"schema_version": 1, "action": "start", "package": asdict(package()), "inventory": []}
    )
    assert answer["status"] == "ERROR" and answer["reason"] == "INFRASTRUCTURE_ERROR"
    assert answer["summary"] is None


def test_finite_host_passes_failure_to_private_recorder(tmp_path):
    import json

    from product_search.infrastructure.replenishment_host import serve_owner
    from product_search.infrastructure.replenishment_runtime_binding import record_command_failure

    tmp_path.chmod(0o700)

    def fail(**kwargs):
        raise RuntimeError("private-secret")

    replies = []
    app = SimpleNamespace(
        start=fail, supervisor=SimpleNamespace(lease=object(), close=lambda **kwargs: None)
    )

    class Server:
        def __init__(self, root, lease, handler, **kwargs):
            self.handler = handler

        def serve_once(self):
            replies.append(
                self.handler(
                    {
                        "schema_version": 1,
                        "action": "start",
                        "package": asdict(package()),
                        "inventory": [],
                    }
                )
            )

        def close(self):
            pass

    serve_owner(
        app,
        tmp_path,
        package(),
        end_at=50,
        max_commands=1,
        timeout_seconds=2,
        max_bytes=65536,
        server_factory=Server,
        clock=lambda: 1,
        on_error=lambda error: record_command_failure(tmp_path, error, max_bytes=65536),
    )
    assert replies[0]["reason"] == "INFRASTRUCTURE_ERROR"
    data = json.loads((tmp_path / "command-failure.json").read_text())
    assert data["exceptions"][0]["type"] == "RuntimeError"


def test_socket_boundary_records_unhandled_error_before_sanitized_reply():
    import json

    from product_search.infrastructure.replenishment_cli import PrivateCommandServer

    class Channel:
        reply = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, value):
            pass

        def recv(self, size):
            return (
                json.dumps(
                    {
                        "schema_version": 1,
                        "action": "start",
                        "package": asdict(package()),
                        "inventory": [],
                    }
                )
                + "\n"
            ).encode()

        def sendall(self, raw):
            self.reply = json.loads(raw)

    def fail(command):
        raise RuntimeError("private-secret")

    channel = Channel()
    server = PrivateCommandServer.__new__(PrivateCommandServer)
    server.sock = SimpleNamespace(accept=lambda: (channel, None))
    server.timeout, server.max_bytes, server.handler = 2, 65536, fail
    seen = []
    server.on_error = seen.append
    server.serve_once()
    assert len(seen) == 1
    assert channel.reply["reason"] == "INFRASTRUCTURE_ERROR"


def test_deep_stack_and_exception_chain_are_bounded(tmp_path):
    import json

    from product_search.infrastructure.replenishment_runtime_binding import record_command_failure

    tmp_path.chmod(0o700)

    def recurse(depth):
        if depth:
            return recurse(depth - 1)
        raise RuntimeError("private-secret")

    try:
        recurse(40)
    except RuntimeError as error:
        previous = error
        for _ in range(6):
            next_error = ValueError("private-secret")
            previous.__context__ = next_error
            previous = next_error
        record_command_failure(tmp_path, error, max_bytes=65536)
    data = json.loads((tmp_path / "command-failure.json").read_text())
    assert len(data["exceptions"]) == 4 and data["chain_truncated"]
    assert len(data["exceptions"][0]["frames"]) == 32
    assert data["exceptions"][0]["frames_truncated"]
