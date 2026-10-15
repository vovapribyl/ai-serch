"""Model-free runtime guards. An approval proposal never authorizes execution."""

import hashlib
import json
import math
import os
import re
import time
from dataclasses import asdict
from pathlib import Path

from product_search.infrastructure.replenishment_cli import private_json
from product_search.search.replenishment_contracts import (
    ExecutionPackage,
    Ownership,
    ReplenishmentError,
)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


class FreshGrant:
    """Consume one private owner approval; retain no reusable ML authorization.

    The trusted operator supplies the approval file after the owner gate. This
    module cannot promote a proposal, approve a different package or reuse claims.
    """

    def __init__(self, path, *, wall_clock=time.time):
        self.path, self.wall_clock = Path(path), wall_clock
        self._claim = None
        self._grant = None
        self._owner = None

    @staticmethod
    def package_sha(package):
        if not isinstance(package, ExecutionPackage):
            raise ReplenishmentError("CLAIM_MISMATCH")
        return hashlib.sha256(canonical(asdict(package))).hexdigest()

    def _read(self, package):
        try:
            value = private_json(self.path)
            now, expires = self.wall_clock(), value["expires_at"]
            if (
                set(value)
                != {
                    "schema_version",
                    "status",
                    "nonce",
                    "package_sha",
                    "scope",
                    "expires_at",
                    "search_authorized",
                }
                or type(value["schema_version"]) is not int
                or value["schema_version"] != 1
                or value["status"] != "APPROVED_BY_OWNER"
                or type(value["nonce"]) is not str
                or re.fullmatch("[0-9a-f]{64}", value["nonce"]) is None
                or value["package_sha"] != self.package_sha(package)
                or value["scope"] != package.scope
                or type(value["search_authorized"]) is not bool
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in (now, expires))
                or now >= expires
                or (self._grant is not None and value != self._grant)
            ):
                raise ValueError
            return value
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            raise ReplenishmentError("CLAIM_MISMATCH") from None

    def check_authorization(self, package):
        if self._claim is None:
            if not self.authorize_build(package):
                raise ReplenishmentError("CLAIM_MISMATCH")
        else:
            self.check_owner(Ownership(**self._owner), package)
        return True

    def authorize_build(self, package):
        try:
            grant = self._read(package)
            path = self.path.parent / (grant["nonce"] + ".claim")
            return self._claim is None and not os.path.lexists(path)
        except ReplenishmentError:
            return False

    def consume(self, owner, package):
        grant = self._read(package)
        if (
            self._claim is not None
            or not isinstance(owner, Ownership)
            or not owner.run_ref
            or not owner.owner_token
            or type(owner.epoch) is not int
            or owner.epoch <= 0
        ):
            raise ReplenishmentError("CLAIM_MISMATCH")
        path = self.path.parent / (grant["nonce"] + ".claim")
        value = {"grant": grant, "owner": asdict(owner)}
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(canonical(value))
                stream.flush()
                os.fsync(stream.fileno())
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            # Even an incomplete claim remains consumed; never remove it and retry.
            raise ReplenishmentError("CLAIM_MISMATCH") from None
        self._claim, self._grant, self._owner = path, grant, asdict(owner)
        return path

    def check_owner(self, owner, package):
        grant = self._read(package)
        try:
            if self._claim is None or private_json(self._claim) != {
                "grant": grant,
                "owner": asdict(owner),
            }:
                raise ValueError
        except (OSError, ValueError, TypeError):
            raise ReplenishmentError("CLAIM_MISMATCH") from None
        return True

    def authorize_initial_search(self, package):
        try:
            grant = self._read(package)
            if not grant["search_authorized"] or not self.authorize_build(package):
                return False
            path = self.path.parent / (grant["nonce"] + ".initial-search.claim")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(canonical({"grant": grant, "scope": "INITIAL_SEARCH"}))
                stream.flush()
                os.fsync(stream.fileno())
            return True
        except (OSError, ValueError, TypeError):
            return False

    def authorize_search(self, package):
        try:
            grant = self._read(package)
            return (
                self._claim is not None
                and grant["search_authorized"]
                and private_json(self._claim) == {"grant": grant, "owner": self._owner}
            )
        except (OSError, ValueError, TypeError, KeyError):
            return False


class MacResourceObserver:
    """Read bounded OS observations and fresh telemetry from the owned ML child.

    The registry supplies the live owned handle's PID, never an adopted PID file.
    Zero MPS is valid only when that registry confirms no remaining ML children.
    Any unknown signal latches STOP for this observer's execution window.
    """

    def __init__(
        self,
        package,
        *,
        controller_pid,
        owned_worker,
        command=None,
        clock=time.monotonic,
    ):
        import subprocess

        if (
            not isinstance(package, ExecutionPackage)
            or type(controller_pid) is not int
            or controller_pid <= 0
        ):
            raise ReplenishmentError("INVALID_PACKAGE")
        self.package, self.controller_pid = package, controller_pid
        self.owned_worker, self.command, self.clock = owned_worker, command or subprocess.run, clock
        import threading

        self._sample_lock = threading.Lock()
        self.stopped, self.last_sample = False, None
        self.last_diagnostic = None
        self.worker_rss_ceiling = lambda: package.rss_ceiling_bytes

    def __call__(self):
        with self._sample_lock:
            return self._sample()

    def _sample(self):
        from product_search.search.replenishment_contracts import ResourceObservation

        started = self.clock()
        if self.stopped:
            return ResourceObservation("STOP", started)
        check, sample_current = "PROCESS_TABLE", False
        error_type = None
        try:

            def output(argv):
                remaining = self.package.observation_max_age_seconds - (self.clock() - started)
                if remaining <= 0:
                    raise ValueError
                result = self.command(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=min(2, remaining),
                    check=False,
                )
                if result.returncode:
                    raise ValueError
                return result.stdout

            processes = [
                tuple(map(int, line.split()))
                for line in output(["/bin/ps", "-axo", "pid=,ppid=,pgid=,rss="]).splitlines()
                if line.strip()
            ]
            if any(len(row) != 4 or any(v < 0 for v in row) for row in processes):
                raise ValueError
            if len({row[0] for row in processes}) != len(processes):
                raise ValueError
            check = "CONTROLLER_IDENTITY"
            controller = next(row for row in processes if row[0] == self.controller_pid)
            rss, mps = controller[3] * 1024, 0
            check = "WORKER_IDENTITY"
            worker = self.owned_worker()
            if worker is not None:
                pid, telemetry_path, nonce = worker
                leader = next(row for row in processes if row[0] == pid)
                if leader[1] != self.controller_pid or leader[2] != pid:
                    raise ValueError
                check = "WORKER_RSS"
                worker_rss = sum(row[3] * 1024 for row in processes if row[2] == pid)
                ceiling = self.worker_rss_ceiling()
                if type(ceiling) is not int or ceiling <= 0 or worker_rss > ceiling:
                    raise ValueError
                rss += worker_rss
                check = "TELEMETRY_READ"
                telemetry = private_json(telemetry_path)
                check = "TELEMETRY_IDENTITY"
                observed = telemetry["observed_at"]
                mps = telemetry["mps_bytes"]
                if (
                    set(telemetry) != {"pid", "nonce", "observed_at", "mps_bytes"}
                    or type(telemetry["pid"]) is not int
                    or telemetry["pid"] != pid
                    or telemetry["nonce"] != nonce
                    or type(mps) is not int
                    or mps < 0
                    or type(observed) not in (int, float)
                    or not math.isfinite(observed)
                ):
                    raise ValueError
                check = "TELEMETRY_FRESHNESS"
                if not 0 <= self.clock() - observed <= self.package.observation_max_age_seconds:
                    raise ValueError
            check = "PRESSURE_READ"
            pressure = int(
                output(["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip()
            )
            if pressure not in (1, 2, 4):
                raise ValueError
            check = "OBSERVATION_FRESHNESS"
            if not 0 <= self.clock() - started <= self.package.observation_max_age_seconds:
                raise ValueError
            self.last_sample = {"pressure": pressure, "rss_bytes": rss, "mps_bytes": mps}
            sample_current = True
            check = "RESOURCE_LIMITS"
            status = "WARNING" if pressure == 2 else "OK"
            reason = status
            if (
                pressure == 4
                or rss > self.package.rss_ceiling_bytes
                or mps > self.package.mps_ceiling_bytes
            ):
                status = "STOP"
                reason = (
                    "PRESSURE_CRITICAL"
                    if pressure == 4
                    else "RSS_LIMIT"
                    if rss > self.package.rss_ceiling_bytes
                    else "MPS_LIMIT"
                )
        except Exception as error:  # noqa: BLE001 -- failed mandatory observation is never evidence of safe resources.
            status, reason = "STOP", "OBSERVATION_FAILED"
            kind = type(error).__name__
            error_type = (
                kind
                if kind
                in {
                    "ValueError",
                    "TypeError",
                    "KeyError",
                    "StopIteration",
                    "TimeoutExpired",
                    "OSError",
                    "PermissionError",
                    "FileNotFoundError",
                    "JSONDecodeError",
                    "ReplenishmentError",
                }
                else "OTHER"
            )
        self.last_diagnostic = {
            "reason": reason,
            "check": check,
            "sample_current": sample_current,
            "error_type": error_type,
        }
        self.stopped = status == "STOP"
        return ResourceObservation(status, started)


def verify_code_inventory(path, expected_sha):
    try:
        inventory = private_json(path)
        if not inventory or hashlib.sha256(canonical(inventory)).hexdigest() != expected_sha:
            raise ValueError
        root = Path(__file__).resolve().parents[3]
        for name, checksum in inventory.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".py":
                raise ValueError
            target = root / relative
            if target.is_symlink() or not target.is_file():
                raise ValueError
            with target.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
                    raise ValueError
        return True
    except (OSError, ValueError, TypeError):
        raise ReplenishmentError("RUNTIME_MISMATCH") from None


def issue_grant(
    path, package, *, approved_package_sha, expires_at, search_authorized, wall_clock=time.time
):
    """Call only after the human approves this SHA; proposals cannot be promoted implicitly."""
    import secrets

    from product_search.infrastructure.nail_runtime import validate_runtime_root

    try:
        now = wall_clock()
        if (
            approved_package_sha != FreshGrant.package_sha(package)
            or type(search_authorized) is not bool
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in (now, expires_at))
            or not now < expires_at <= now + package.overall_seconds
        ):
            raise ValueError
        path = Path(path)
        validate_runtime_root(path.parent)
        value = {
            "schema_version": 1,
            "status": "APPROVED_BY_OWNER",
            "nonce": secrets.token_hex(32),
            "package_sha": approved_package_sha,
            "scope": package.scope,
            "expires_at": expires_at,
            "search_authorized": search_authorized,
        }
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return path
    except (OSError, ValueError, TypeError):
        raise ReplenishmentError("CLAIM_MISMATCH") from None


def verify_frozen_inputs(path, binding, package):
    from product_search.infrastructure.nail_runtime import validate_runtime_root
    from product_search.infrastructure.replenishment_artifacts import CheckpointFiles

    try:
        inventory = private_json(path)
        root = validate_runtime_root(Path(binding["frozen_input_root"]))
        if inventory["frozen_input_root"] != str(root):
            raise ValueError
        products = [
            {
                "corpus_version_id": p["corpus_version_id"],
                "product_record_id": p["product_record_id"],
                "photos": p["photos"],
            }
            for p in inventory["products"]
        ]
        if not products or hashlib.sha256(canonical(products)).hexdigest() != package.input_set_sha:
            raise ValueError
        for product in products:
            for photo in product["photos"]:
                name = photo["source_ref"]
                size = photo["source_bytes"]
                if (
                    type(name) is not str
                    or Path(name).name != name
                    or name in ("", ".", "..")
                    or type(size) is not int
                    or not 0 < size <= package.max_source_bytes
                ):
                    raise ValueError
                data = CheckpointFiles._read(root / name, package.max_source_bytes)
                if len(data) != size or hashlib.sha256(data).hexdigest() != photo["input_sha"]:
                    raise ValueError
        return True
    except (OSError, ValueError, TypeError, KeyError):
        raise ReplenishmentError("INPUT_MISMATCH") from None


class RecordingResourceObserver:
    """Keep bounded private observations; recording failure closes admission."""

    def __init__(self, observe, path, *, max_bytes, context=dict):
        import threading

        from product_search.infrastructure.nail_runtime import validate_runtime_root

        if type(max_bytes) is not int or max_bytes <= 0:
            raise ReplenishmentError("INVALID_PACKAGE")
        path = Path(path)
        validate_runtime_root(path.parent)
        self.fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.observe, self.max_bytes, self.context = observe, max_bytes, context
        self._lock = threading.Lock()
        self.stopped = False

    def __call__(self):
        from product_search.search.replenishment_contracts import ResourceObservation

        with self._lock:
            if self.stopped:
                return ResourceObservation("STOP", time.monotonic())
            try:
                observation = self.observe()
                payload = (
                    canonical(
                        {
                            "status": observation.status,
                            "observed_at": observation.observed_at,
                            "sample": self.observe.last_sample,
                            "diagnostic": getattr(self.observe, "last_diagnostic", None),
                            "context": self.context(),
                        }
                    )
                    + b"\n"
                )
                if self.fd < 0 or os.fstat(self.fd).st_size + len(payload) > self.max_bytes:
                    raise ValueError
                if os.write(self.fd, payload) != len(payload):
                    raise ValueError
                os.fsync(self.fd)
                return observation
            except Exception:  # noqa: BLE001 -- incomplete evidence is never silently discarded.
                self.stopped = True
                return ResourceObservation("STOP", time.monotonic())

    def close(self):
        with self._lock:
            if self.fd >= 0:
                os.close(self.fd)
                self.fd = -1


def record_command_failure(root, error, *, max_bytes):
    """First failure metadata only: no messages, source text, values or full paths."""
    from collections import deque

    from product_search.infrastructure.nail_runtime import validate_runtime_root

    root = validate_runtime_root(Path(root))
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ReplenishmentError("INVALID_PACKAGE")
    exceptions, seen = [], set()
    while error is not None and id(error) not in seen and len(exceptions) < 4:
        seen.add(id(error))
        frames = deque(maxlen=32)
        tb, count = error.__traceback__, 0
        while tb is not None and count < 1024:
            code = tb.tb_frame.f_code
            frames.append(
                {
                    "file": Path(code.co_filename).name[:128],
                    "function": code.co_name[:128],
                    "line": tb.tb_lineno,
                }
            )
            count += 1
            tb = tb.tb_next
        exceptions.append(
            {
                "type": type(error).__name__[:128],
                "frames": list(frames),
                "frames_truncated": count > 32 or tb is not None,
            }
        )
        error = error.__cause__ if error.__cause__ is not None else error.__context__
    raw = canonical(
        {"schema_version": 1, "exceptions": exceptions, "chain_truncated": error is not None}
    )
    if len(raw) > max_bytes:
        raise ReplenishmentError("DIAGNOSTIC_LIMIT")
    fd = os.open(
        root / "command-failure.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
