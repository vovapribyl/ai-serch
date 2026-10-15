"""Bounded private owner IPC. The client never imports models or runs a build."""

import argparse
import json
import math
import os
import socket
import stat
import sys
import time
from pathlib import Path
from threading import Lock
from uuid import UUID

from product_search.search.replenishment_contracts import ExecutionPackage, ReplenishmentError

JSON_LIMIT = 65536  # Bootstrap format cap, not a default ML/runtime budget.
SCOPES = {
    "start": "START",
    "resume": "RESUME",
    "retry-photo": "RETRY_PHOTO",
    "retry-publication": "RETRY_PUBLICATION",
}
CONFLICTS = {
    "BUSY",
    "VERSION_CONFLICT",
    "ACTIVE_CONFLICT",
    "REVISION_SUPERSEDED",
    "TEMPORARILY_UNAVAILABLE",
}
GUARDS = {"DEADLINE", "RESOURCE_STOP", "ADMISSION_LIMIT", "RECOVERY_REQUIRED", "WAIT_TIMEOUT"}
INVALID = {
    "INVALID_INPUT",
    "INVALID_PACKAGE",
    "INVALID_SCOPE",
    "INPUT_MISMATCH",
    "PROFILE_MISMATCH",
    "CLAIM_MISMATCH",
}
REASONS = (
    CONFLICTS
    | GUARDS
    | INVALID
    | {
        "COMMIT_UNKNOWN",
        "CHECKPOINT_UNKNOWN",
        "CHECKPOINT_INVALID",
        "NOT_IMPLEMENTED",
        "NOT_FOUND",
        "INFRASTRUCTURE_ERROR",
    }
)


class CliError(ValueError):
    def __init__(self, code="INVALID_INPUT"):
        self.code = code
        super().__init__(code)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError()


def _parser():
    parser = Parser(prog="corpus-replenishment", allow_abbrev=False)
    commands = parser.add_subparsers(dest="action", required=True, parser_class=Parser)
    for name in ("start", "resume", "retry-photo", "retry-publication", "status"):
        sub = commands.add_parser(name, allow_abbrev=False)
        if name != "status":
            sub.add_argument("--execution-package", required=True)
        if name == "start":
            sub.add_argument("--inventory", required=True)
        if name in ("status", "resume"):
            sub.add_argument("--run", required=True)
        if name in ("retry-photo", "retry-publication"):
            sub.add_argument("--revision", required=True)
        if name == "retry-photo":
            sub.add_argument("--photo", required=True)
            sub.add_argument("--expected-version", required=True, type=int)
    return parser


def private_json(path):
    try:
        path = Path(path)
        parent = path.parent.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise CliError()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > JSON_LIMIT
            ):
                raise CliError()
            return _json(stream.read(JSON_LIMIT + 1))
    except (OSError, TypeError, ValueError):
        raise CliError() from None


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CliError()
            result[key] = value
        return result

    try:
        return json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(CliError()),
        )
    except (ValueError, TypeError, UnicodeError):
        raise CliError() from None


def _ref(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise CliError()
    except (ValueError, TypeError, AttributeError):
        raise CliError() from None


def validate_command(command):
    if (
        type(command) is not dict
        or type(command.get("schema_version")) is not int
        or command.get("schema_version") != 1
        or type(command.get("action")) is not str
        or command.get("action") not in {*SCOPES, "status"}
    ):
        raise CliError()
    action = command["action"]
    fields = {"schema_version", "action"}
    fields |= (
        {"run"}
        if action in ("resume", "status")
        else {"inventory"}
        if action == "start"
        else {"revision"}
    )
    if action != "status":
        fields.add("package")
    if action == "retry-photo":
        fields |= {"photo", "expected_version"}
    if set(command) != fields:
        raise CliError()
    for key in ("run", "revision", "photo"):
        if key in command:
            _ref(command[key])
    if action == "retry-photo" and (
        type(command["expected_version"]) is not int or command["expected_version"] <= 0
    ):
        raise CliError()
    if action != "status":
        try:
            pkg = ExecutionPackage(**command["package"])
        except (TypeError, ValueError):
            raise CliError() from None
        if pkg.scope != SCOPES[action]:
            raise CliError("INVALID_SCOPE")
    if action == "start" and type(command["inventory"]) is not list:
        raise CliError()
    return command


def parse_command(argv):
    options = [a.split("=")[0] for a in argv if a.startswith("--")]
    if len(options) != len(set(options)):
        raise CliError()
    args = vars(_parser().parse_args(argv))
    action = args.pop("action")
    command = {"schema_version": 1, "action": action}
    if "execution_package" in args:
        command["package"] = private_json(args.pop("execution_package"))
    if "inventory" in args:
        command["inventory"] = private_json(args.pop("inventory"))
    command.update(args)
    return validate_command(command)


def _answer(status, reason=None, summary=None):
    return {"schema_version": 1, "status": status, "reason": reason, "summary": summary}


def _error_answer(error):
    reason = (
        str(error)
        if isinstance(error, (ReplenishmentError, CliError)) and str(error) in REASONS
        else "INFRASTRUCTURE_ERROR"
    )
    status = (
        "REFUSED"
        if reason in INVALID | CONFLICTS
        else "STOPPED"
        if reason in GUARDS
        else "UNKNOWN"
        if reason in {"COMMIT_UNKNOWN", "CHECKPOINT_UNKNOWN"}
        else "ERROR"
    )
    return _answer(status, reason)


def validate_answer(answer):
    if (
        type(answer) is not dict
        or set(answer) != {"schema_version", "status", "reason", "summary"}
        or type(answer["schema_version"]) is not int
        or answer["schema_version"] != 1
    ):
        raise CliError("INFRASTRUCTURE_ERROR")
    codes = {"OK": 0, "REFUSED": 3, "STOPPED": 4, "ERROR": 5, "UNKNOWN": 6}
    if answer["status"] not in codes or (
        answer["reason"] is not None and answer["reason"] not in REASONS
    ):
        raise CliError("INFRASTRUCTURE_ERROR")
    if answer["status"] == "OK" and answer["reason"] is not None:
        raise CliError("INFRASTRUCTURE_ERROR")
    summary = answer["summary"]
    if summary is not None:
        if type(summary) is not dict or set(summary) != {
            "run_ref",
            "status",
            "reason",
            "selected_photo_refs",
            "outcomes",
            "revision_refs",
            "publications",
            "search_state",
            "remaining_stages",
            "products",
        }:
            raise CliError("INFRASTRUCTURE_ERROR")
        _ref(summary["run_ref"])
        if summary["status"] not in {
            "RUNNING",
            "STOPPED",
            "EXPIRED",
            "INTERRUPTED",
            "COMPLETED",
            "FAILED",
        } or summary["search_state"] not in {
            "SEARCH",
            "DRAINING",
            "BUILD",
            "RECOVERY_REQUIRED",
            "CLOSED",
        }:
            raise CliError("INFRASTRUCTURE_ERROR")
        if summary["reason"] is not None and summary["reason"] not in REASONS | {
            "COMPLETED",
            "OWNER_CHANGED",
        }:
            raise CliError("INFRASTRUCTURE_ERROR")
        for key in (
            "selected_photo_refs",
            "revision_refs",
            "outcomes",
            "publications",
            "remaining_stages",
            "products",
        ):
            if type(summary[key]) is not list:
                raise CliError("INFRASTRUCTURE_ERROR")
        for key in ("selected_photo_refs", "revision_refs"):
            for ref in summary[key]:
                _ref(ref)
        for row in summary["remaining_stages"]:
            if (
                type(row) is not list
                or len(row) != 3
                or (row[1], row[2])
                not in {
                    ("localization", ""),
                    ("embedding", "openclip_b32"),
                    ("embedding", "dinov2_b14"),
                    ("embedding", "siglip2_b16_224"),
                }
            ):
                raise CliError("INFRASTRUCTURE_ERROR")
            _ref(row[0])
        for row in summary["outcomes"]:
            if (
                type(row) is not list
                or len(row) != 2
                or row[1] not in {"PENDING", "RUNNING", "OK", "NO_NAILS", "ERROR"}
            ):
                raise CliError("INFRASTRUCTURE_ERROR")
            _ref(row[0])
        for row in summary["products"]:
            if (
                type(row) is not dict
                or set(row) != {"revision_ref", "state", "remaining_photo_refs"}
                or row["state"]
                not in {
                    "WAITING_PHOTOS",
                    "READY",
                    "NOT_PUBLISHABLE",
                    "PUBLISHED",
                    "PUBLICATION_FAILED",
                    "PUBLICATION_UNKNOWN",
                }
                or type(row["remaining_photo_refs"]) is not list
                or row["revision_ref"] not in summary["revision_refs"]
            ):
                raise CliError("INFRASTRUCTURE_ERROR")
            _ref(row["revision_ref"])
            for ref in row["remaining_photo_refs"]:
                _ref(ref)
        for row in summary["publications"]:
            if (
                type(row) is not dict
                or set(row) != {"revision_ref", "snapshot_ref", "state", "error_code"}
                or row["state"] not in {"SUCCEEDED", "FAILED", "UNKNOWN"}
            ):
                raise CliError("INFRASTRUCTURE_ERROR")
            _ref(row["revision_ref"])
            if row["snapshot_ref"] is not None:
                _ref(row["snapshot_ref"])
            if row["error_code"] is not None and row["error_code"] not in REASONS:
                raise CliError("INFRASTRUCTURE_ERROR")
    return 2 if answer["reason"] in INVALID else codes[answer["status"]]


def _record_private_error(callback, error):
    if callback is not None:
        try:
            callback(error)
        except Exception:  # noqa: BLE001, S110 -- preserve original failure; never expose diagnostic errors.
            pass


class OwnerDispatcher:
    def __init__(self, application, *, role, on_error=None):
        if role not in ("OWNER", "CHECK"):
            raise CliError("INVALID_SCOPE")
        self.on_error = on_error
        self.application, self.role = application, role
        self._mutation = Lock()

    def handle(self, command):
        try:
            command = validate_command(command)
            action = command["action"]
            if action != "status" and self.role != "OWNER":
                return _answer("REFUSED", "INVALID_SCOPE")
            if action == "status":
                return _answer("OK", summary=self.application.status(command["run"]))
            if not self._mutation.acquire(blocking=False):
                return _answer("REFUSED", "BUSY")
            try:
                payload = {
                    k: v for k, v in command.items() if k not in {"action", "schema_version"}
                }
                summary = getattr(self.application, action.replace("-", "_"))(**payload)
                if summary["reason"] in GUARDS:
                    return _answer("STOPPED", summary["reason"], summary)
                if any(p["state"] == "UNKNOWN" for p in summary["publications"]):
                    return _answer("UNKNOWN", "COMMIT_UNKNOWN", summary)
                if any(p["state"] == "FAILED" for p in summary["publications"]):
                    return _answer("ERROR", "INFRASTRUCTURE_ERROR", summary)
                return _answer("OK", summary=summary)
            finally:
                self._mutation.release()
        except CliError:
            return _answer("REFUSED", "INVALID_INPUT")
        except Exception as error:  # noqa: BLE001 -- never expose handler exceptions across IPC.
            _record_private_error(self.on_error, error)
            return _error_answer(error)


def _root(root):
    root = Path(root)
    try:
        info = root.lstat()
        if (
            not root.is_absolute()
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise CliError("INFRASTRUCTURE_ERROR")
    except OSError:
        raise CliError("INFRASTRUCTURE_ERROR") from None
    return root


def _limits(timeout, max_bytes):
    if (
        type(timeout) not in (int, float)
        or not math.isfinite(timeout)
        or timeout <= 0
        or type(max_bytes) is not int
        or not 0 < max_bytes <= JSON_LIMIT
    ):
        raise CliError()


def _receive(sock, end_at, max_bytes):
    data = bytearray()
    while True:
        remaining = end_at - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        sock.settimeout(remaining)
        block = sock.recv(min(4096, max_bytes + 1 - len(data)))
        if not block:
            raise CliError("INFRASTRUCTURE_ERROR")
        data.extend(block)
        if len(data) > max_bytes:
            raise CliError()
        if b"\n" in data:
            if not data.endswith(b"\n") or data.count(b"\n") != 1:
                raise CliError()
            return _json(bytes(data[:-1]))


def _wire(value, max_bytes):
    data = json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(data) > max_bytes:
        raise CliError()
    return data


class UnixCommandClient:
    def __init__(self, root, *, timeout_seconds, max_bytes):
        self.root = _root(root)
        _limits(timeout_seconds, max_bytes)
        self.timeout, self.max_bytes = timeout_seconds, max_bytes

    def send(self, command):
        packet = _wire(validate_command(command), self.max_bytes)
        try:
            info = (self.root / "owner.sock").lstat()
            if (
                not stat.S_ISSOCK(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise CliError("INFRASTRUCTURE_ERROR")
        except OSError:
            raise CliError("INFRASTRUCTURE_ERROR") from None
        sent = False
        end_at = time.monotonic() + self.timeout
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.settimeout(self.timeout)
                channel.connect(str(self.root / "owner.sock"))
                sent = True
                channel.sendall(packet)
                answer = _receive(channel, end_at, self.max_bytes)
                validate_answer(answer)
                return answer
        except OSError:
            return (
                _answer("UNKNOWN", "COMMIT_UNKNOWN")
                if sent
                else _answer("ERROR", "INFRASTRUCTURE_ERROR")
            )


def _reconcile_socket(path, marker, lease_identity):
    """Recover only an inode recorded by a dead owner under the same lease."""
    if not os.path.lexists(path) and not os.path.lexists(marker):
        return
    try:
        proof = private_json(marker)
        if (
            set(proof) != {"schema_version", "pid", "socket", "lease"}
            or proof["schema_version"] != 1
            or type(proof["pid"]) is not int
            or proof["pid"] <= 0
            or proof["lease"] != list(lease_identity)
        ):
            raise ValueError
        try:
            os.kill(proof["pid"], 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError
        if os.path.lexists(path):
            info = path.lstat()
            if (
                not stat.S_ISSOCK(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or proof["socket"] != [info.st_dev, info.st_ino]
            ):
                raise ValueError
            # A replacement never inherits the prior endpoint's ownership.
            again = path.lstat()
            if (again.st_dev, again.st_ino) != (info.st_dev, info.st_ino):
                raise ValueError
            path.unlink()
        marker.unlink()
    except (OSError, ValueError, TypeError, KeyError):
        raise CliError("INFRASTRUCTURE_ERROR") from None


class PrivateCommandServer:
    def __init__(self, root, lease, handler, *, timeout_seconds, max_bytes, on_error=None):
        from .replenishment_supervisor import ModeLease

        self.root = _root(root)
        _limits(timeout_seconds, max_bytes)
        self.on_error = on_error
        self.timeout, self.max_bytes, self.handler = timeout_seconds, max_bytes, handler
        if not isinstance(lease, ModeLease) or lease.fd < 0:
            raise CliError("INFRASTRUCTURE_ERROR")
        held = os.fstat(lease.fd)
        actual = (self.root / "mode.lock").lstat()
        if (held.st_dev, held.st_ino) != (actual.st_dev, actual.st_ino):
            raise CliError("INFRASTRUCTURE_ERROR")
        self.path = self.root / "owner.sock"
        self.marker = self.root / "owner.socket.json"
        _reconcile_socket(self.path, self.marker, (held.st_dev, held.st_ino))
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.bind(str(self.path))
            self.path.chmod(0o600)
            info = self.path.lstat()
            self.identity = (info.st_dev, info.st_ino)
            self.sock.listen(2)
            self.sock.settimeout(self.timeout)
            self.proof = {
                "schema_version": 1,
                "pid": os.getpid(),
                "socket": list(self.identity),
                "lease": [held.st_dev, held.st_ino],
            }
            fd = os.open(self.marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(self.proof, stream)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            self.sock.close()
            raise CliError("INFRASTRUCTURE_ERROR") from None

    def serve_once(self):
        with self.sock.accept()[0] as channel:
            end_at = time.monotonic() + self.timeout
            try:
                command = validate_command(_receive(channel, end_at, self.max_bytes))
                answer = self.handler(command)
                validate_answer(answer)
                packet = _wire(answer, self.max_bytes)
            except Exception as error:  # noqa: BLE001 -- protocol failures never disclose private input.
                _record_private_error(self.on_error, error)
                packet = _wire(_error_answer(error), self.max_bytes)
            channel.settimeout(max(0.001, end_at - time.monotonic()))
            channel.sendall(packet)

    def close(self):
        self.sock.close()
        try:
            info = self.path.lstat()
            if (
                (info.st_dev, info.st_ino) != self.identity
                or not stat.S_ISSOCK(info.st_mode)
                or info.st_uid != os.getuid()
            ):
                raise CliError("INFRASTRUCTURE_ERROR")
            if private_json(self.marker) != self.proof:
                raise CliError("INFRASTRUCTURE_ERROR")
            self.path.unlink()
            self.marker.unlink()
        except FileNotFoundError:
            pass


def main(argv=None, *, client=None, stdout=None, stderr=None):
    from contextlib import redirect_stdout

    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    try:
        with redirect_stdout(stdout):
            command = parse_command(sys.argv[1:] if argv is None else argv)
    except SystemExit as error:
        return int(error.code)
    except CliError:
        stderr.write("INVALID_INPUT\n")
        return 2
    try:
        if client is None:
            config = private_json(os.environ["REPLENISHMENT_CLIENT_CONFIG"])
            if set(config) != {"root", "timeout_seconds", "max_bytes"}:
                raise CliError()
            client = UnixCommandClient(**config).send
        answer = client(command)
        code = validate_answer(answer)
        stdout.write(json.dumps(answer, ensure_ascii=False, allow_nan=False) + "\n")
        return code
    except Exception:  # noqa: BLE001 -- no paths, credentials or raw replies on stdout/stderr.
        stderr.write("INFRASTRUCTURE_ERROR\n")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
