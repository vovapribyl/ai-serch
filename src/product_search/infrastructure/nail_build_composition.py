"""Model-free outer composition and owned supervisor; no implicit native launch."""

import json
import math
import threading
from types import MappingProxyType

from product_search.infrastructure.nail_build_runner import (
    BuildStop,
    GuardedEmbedding,
    GuardedLocalization,
    admitted_provider,
    run_admitted_build,
)
from product_search.infrastructure.nail_ml_adapters import NailEmbeddingAdapter
from product_search.search.nail_catalog_build import NailCatalogBuildService
from product_search.search.nail_contracts import MODEL_DIMENSIONS
from product_search.search.nail_image_processor import NailImageProcessor


class ObservationGate:
    """All mandatory observations are fresh; any failure remains terminal."""

    FIELDS = frozenset(
        ("pressure", "i_rss", "backend_rss", "artifact_bytes", "db_bytes", "host_free", "vm_free")
    )

    def __init__(self, limits, clock):
        names = (
            "i_rss_bytes",
            "backend_rss_bytes",
            "combined_rss_bytes",
            "max_storage_bytes",
            "min_free_bytes",
        )
        if any(type(limits.get(key)) is not int or limits[key] <= 0 for key in names):
            raise BuildStop("INVALID_OBSERVATION_LIMITS")
        age = limits.get("freshness_s")
        if type(age) not in (int, float) or not math.isfinite(age) or age <= 0:
            raise BuildStop("INVALID_OBSERVATION_LIMITS")
        self.limits, self.clock = MappingProxyType(dict(limits)), clock
        self.stop_reason = None
        self.observed_at = None
        self.lock = threading.Lock()

    def update(self, sample, observed_at):
        with self.lock:
            if self.stop_reason is not None:
                return
            try:
                now = self.clock()
                if (
                    type(observed_at) not in (int, float)
                    or not math.isfinite(observed_at)
                    or type(now) not in (int, float)
                    or not math.isfinite(now)
                    or observed_at > now
                    or now - observed_at > self.limits["freshness_s"]
                    or set(sample) != self.FIELDS
                    or any(type(sample[key]) is not int or sample[key] < 0 for key in self.FIELDS)
                ):
                    self.stop_reason = "RESOURCE_OBSERVATION_ERROR"
                elif sample["pressure"] not in (1, 2) or (
                    sample["i_rss"] > self.limits["i_rss_bytes"]
                    or sample["backend_rss"] > self.limits["backend_rss_bytes"]
                    or sample["i_rss"] + sample["backend_rss"] > self.limits["combined_rss_bytes"]
                ):
                    self.stop_reason = "RESOURCE_CEILING"
                elif (
                    sample["artifact_bytes"] + sample["db_bytes"]
                    >= self.limits["max_storage_bytes"]
                    or min(sample["host_free"], sample["vm_free"]) < self.limits["min_free_bytes"]
                ):
                    self.stop_reason = "STORAGE_CEILING"
                self.observed_at = observed_at
            except (TypeError, ValueError, KeyError):
                self.stop_reason = "RESOURCE_OBSERVATION_ERROR"

    def invalidate(self):
        with self.lock:
            self.stop_reason = self.stop_reason or "RESOURCE_OBSERVATION_ERROR"

    def allowed(self):
        with self.lock:
            if self.stop_reason is not None or self.observed_at is None:
                return False
            now = self.clock()
            if (
                type(now) not in (int, float)
                or not math.isfinite(now)
                or now < self.observed_at
                or now - self.observed_at > self.limits["freshness_s"]
            ):
                self.stop_reason = "RESOURCE_OBSERVATION_ERROR"
                return False
            return True


class RuntimeVerifier:
    """Compare independent metadata to frozen complete expected runtime, not a DTO claim."""

    def __init__(self, expected, observe):
        self._expected = json.dumps(expected, sort_keys=True, separators=(",", ":"))
        self.observe = observe
        self.failed = False
        self._validate(expected)

    @staticmethod
    def _validate(value):
        import re

        required = {
            "mode",
            "extractor_fingerprint",
            "backend_inventory_sha256",
            "python",
            "machine",
            "device",
            "dtype",
            "operator_fallback",
            "models",
        }
        if set(value) != required or value["mode"] not in ("fake", "native"):
            raise BuildStop("INVALID_RUNTIME_OBSERVATION")
        if any(
            not isinstance(value[k], str) or not re.fullmatch("[0-9a-f]{64}", value[k])
            for k in ("extractor_fingerprint", "backend_inventory_sha256")
        ):
            raise BuildStop("INVALID_RUNTIME_OBSERVATION")
        if (
            value["operator_fallback"] is not False
            or value["dtype"] != "float32"
            or value["device"] != ("fake" if value["mode"] == "fake" else "mps")
            or not value["python"]
            or not value["machine"]
        ):
            raise BuildStop("INVALID_RUNTIME_OBSERVATION")
        if type(value["models"]) is not list or len(value["models"]) != 3:
            raise BuildStop("INVALID_RUNTIME_OBSERVATION")
        for entry, (key, dim) in zip(value["models"], MODEL_DIMENSIONS):
            if (
                type(entry) is not list
                or len(entry) != 4
                or entry[0] != key
                or entry[3] != dim
                or not isinstance(entry[1], str)
                or not entry[1]
                or not isinstance(entry[2], str)
                or not re.fullmatch("[0-9a-f]{64}", entry[2])
            ):
                raise BuildStop("INVALID_RUNTIME_OBSERVATION")

    def verify(self):
        if self.failed:
            return False
        try:
            value = self.observe()
            self._validate(value)
            self.failed = json.dumps(value, sort_keys=True, separators=(",", ":")) != self._expected
        except Exception:  # noqa: BLE001 -- observation failure is a terminal readiness failure.
            self.failed = True
        return not self.failed


def compose_build(
    *,
    catalog,
    images,
    localization,
    factories,
    identity,
    inventory,
    runtime,
    localization_profile,
    decode_profile,
    max_regions,
    budget,
    device,
    coordinator,
    target_check,
    input_check,
    runtime_check,
):
    """Concrete ports outside core; SDK factories stay lazy until admitted execution."""
    if set(factories) != {key for key, _ in MODEL_DIMENSIONS}:
        raise BuildStop("MODEL_SET_MISMATCH")
    embedding = GuardedEmbedding(
        NailEmbeddingAdapter(
            {key: admitted_provider(factory, budget, device) for key, factory in factories.items()}
        ),
        budget,
    )
    processor = NailImageProcessor(
        images,
        GuardedLocalization(localization, budget),
        decode_profile,
        localization_profile,
        max_regions,
    )
    service = NailCatalogBuildService(catalog, processor, embedding, images)

    def execute():
        return run_admitted_build(
            service,
            identity,
            inventory,
            runtime,
            target_check=target_check,
            input_check=input_check,
            runtime_check=runtime_check,
            coordinator=coordinator,
        )

    return execute


class HostStorageObserver:
    def __init__(self, artifact_root, target):
        self.root, self.target = artifact_root, target
        self._swapouts_baseline = None
        self.last_swapouts_delta = None

    def sample(self, pid):
        import hashlib
        import os
        import re
        import shutil
        import stat
        import subprocess
        from pathlib import Path

        def output(argv):
            completed = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=2)
            if completed.returncode:
                raise BuildStop("OBSERVATION_COMMAND_FAILED")
            return completed.stdout

        processes = []
        for line in output(["ps", "-axo", "pid=,ppid=,pgid=,rss="]).splitlines():
            if line.strip():
                values = tuple(map(int, line.split()))
                if len(values) != 4:
                    raise BuildStop("INVALID_PROCESS_OBSERVATION")
                processes.append(values)
        leader = next((item for item in processes if item[0] == pid), None)
        if leader is None or leader[1] != os.getpid() or leader[2] != pid:
            raise BuildStop("OWNED_PROCESS_NOT_OBSERVED")
        backend = leader[3] * 1024
        descendants = sum(item[3] * 1024 for item in processes if item[2] == pid and item[0] != pid)
        pressure = int(output(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip())
        swap = re.search(r"Swapouts:\s+(\d+)\.", output(["vm_stat"]))
        if swap is None:
            raise BuildStop("SWAP_DIAGNOSTIC_UNAVAILABLE")
        swapouts = int(swap.group(1))
        if self._swapouts_baseline is None:
            self._swapouts_baseline = swapouts
        self.last_swapouts_delta = swapouts - self._swapouts_baseline
        if self.last_swapouts_delta < 0:
            raise BuildStop("INVALID_SWAP_DIAGNOSTIC")
        folder = Path(self.root)
        original_root = folder.lstat()
        if not stat.S_ISDIR(original_root.st_mode) or original_root.st_uid != os.getuid():
            raise BuildStop("INVALID_STORAGE_ROOT")
        payload = 0
        for path in folder.rglob("*"):
            try:
                mode = path.lstat()
            except FileNotFoundError:
                # The owned writer atomically renames/removes staging files.
                continue
            if stat.S_ISREG(mode.st_mode):
                payload += mode.st_size
            elif not stat.S_ISDIR(mode.st_mode):
                raise BuildStop("INVALID_STORAGE_ENTRY")
        current_root = folder.lstat()
        if (current_root.st_dev, current_root.st_ino, current_root.st_uid) != (
            original_root.st_dev,
            original_root.st_ino,
            original_root.st_uid,
        ) or not stat.S_ISDIR(current_root.st_mode):
            raise BuildStop("STORAGE_ROOT_CHANGED")
        if self.target is None:
            raise BuildStop("VM_STORAGE_OBSERVATION_REQUIRED")
        blob = self.target.path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != self.target.sha256:
            raise BuildStop("TARGET_DESCRIPTOR_CHANGED")
        descriptor = json.loads(blob)
        with self.target.connect() as connection:
            db_bytes = connection.execute("SELECT pg_database_size(current_database())").fetchone()[
                0
            ]
        lines = output(
            [
                "docker",
                "--context",
                "colima",
                "exec",
                descriptor["container_id"],
                "df",
                "-Pk",
                "/var/lib/postgresql/data",
            ]
        ).splitlines()
        if len(lines) != 2 or len(lines[1].split()) != 6:
            raise BuildStop("VM_STORAGE_UNAVAILABLE")
        vm_free = int(lines[1].split()[3]) * 1024
        return {
            "pressure": pressure,
            "i_rss": descendants,
            "backend_rss": backend,
            "artifact_bytes": payload,
            "db_bytes": db_bytes,
            "host_free": shutil.disk_usage(folder).free,
            "vm_free": vm_free,
        }


def supervise_owned(command, root, limits, *, observe, watchdog):
    import os
    import time
    from pathlib import Path

    from product_search.infrastructure.nail_runtime import validate_runtime_root

    root = validate_runtime_root(Path(root))
    policy = json.loads(json.dumps(limits))
    wall = policy.get("wall_s")
    if type(wall) not in (int, float) or not math.isfinite(wall) or wall <= 0:
        raise BuildStop("INVALID_WALL_LIMIT")
    for name in ("worker-pid.json", "observation.json", "supervisor-trace.jsonl", "worker.log"):
        if (root / name).exists():
            raise BuildStop("FRESH_SUPERVISOR_NAMESPACE_REQUIRED")
    gate = ObservationGate(policy, time.monotonic)
    stop = threading.Event()
    trace = root / "supervisor-trace.jsonl"

    def monitor():
        stream = None
        try:
            while not stop.wait(0.02):
                if (root / "worker-done.json").exists():
                    return
                pid_file = root / "worker-pid.json"
                if not pid_file.exists():
                    continue
                started = time.monotonic()
                try:
                    info = read_private_json(pid_file)
                    if (
                        type(info["pid"]) is not int
                        or info["pid"] <= 0
                        or info["parent"] != os.getpid()
                    ):
                        raise BuildStop("INVALID_OWNED_PID")
                    sample = observe(info["pid"])
                    gate.update(sample, started)
                    event = {
                        "monotonic": started,
                        "pressure": sample["pressure"],
                        "i_rss": sample["i_rss"],
                        "controller_rss": sample["backend_rss"],
                        **{
                            key: sample[key]
                            for key in ("artifact_bytes", "db_bytes", "host_free", "vm_free")
                        },
                        "swapouts_delta": getattr(observe, "swapouts_delta", 0),
                        "swapouts_source": "whole_host"
                        if hasattr(observe, "swapouts_delta")
                        else "synthetic_compatibility_value",
                    }
                except Exception as error:  # noqa: BLE001 -- mandatory observation failures cannot expose private data or recover.
                    gate.invalidate()
                    sample = None
                    event = {
                        "event": "resource_observation_error",
                        "error_class": type(error).__name__,
                    }
                if stop.is_set():
                    return
                if not gate.allowed():
                    event.update(
                        {"event": "resource_observation_error", "reason": gate.stop_reason}
                    )
                if stream is None:
                    stream = trace.open("x")
                    os.fchmod(stream.fileno(), 0o600)
                # Forward STOP to the independent guardian before worker notification.
                stream.write(json.dumps(event, sort_keys=True) + "\n")
                stream.flush()
                publish_private_json(
                    root / "observation.json",
                    {"sample": sample, "observed_at": started, "stop_reason": gate.stop_reason},
                )
                if gate.stop_reason:
                    return
                stop.wait(0.1)
        except Exception:  # noqa: BLE001 -- even publication failure leaves independent freshness guardian active.
            gate.invalidate()
        finally:
            if stream is not None:
                stream.close()

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    profile = {
        "resource_policy": "scenario_suitability_v1",
        "i_rss_bytes": policy["i_rss_bytes"],
        "backend_rss_bytes": policy["backend_rss_bytes"],
        "combined_rss_bytes": policy["combined_rss_bytes"],
        "resource_sample_max_age_s": policy["freshness_s"],
    }
    try:
        result = watchdog(command, root / "worker.log", trace, wall, profile)
    finally:
        stop.set()
        thread.join(timeout=0.1)
    # A blocked observer cannot hold teardown hostage or publish after completion.
    if (
        result["stop_reason"] == "RESOURCE_OBSERVATION_ERROR"
        or thread.is_alive()
        or gate.observed_at is None
    ):
        gate.invalidate()
    gate.allowed()
    if result["stop_reason"] is None and gate.stop_reason is not None:
        result["stop_reason"] = gate.stop_reason
    result["observation_stop"] = gate.stop_reason
    return result


def read_private_json(path, *, allow_replaced=False):
    import os
    import stat

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink not in ((0, 1) if allow_replaced else (1,))
            or info.st_size > 8388608
        ):
            raise BuildStop("UNSAFE_CONTROL_FILE")
        return json.loads(stream.read(8388609))


def publish_private_json(path, value):
    import os
    from pathlib import Path
    from uuid import uuid4

    path = Path(path)
    temp = path.parent / (".control-" + uuid4().hex)
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class RecordingBudget:
    def __init__(self, budget, record):
        self.budget, self.record = budget, record
        self._record_lock = threading.Lock()

    @property
    def stopped(self):
        return self.budget.stopped

    @stopped.setter
    def stopped(self, value):
        self.budget.stopped = value

    @property
    def used(self):
        return self.budget.used

    def admit(self):
        with self._record_lock:
            self.budget.admit()
            try:
                self.record(self.budget.used)
            except BaseException:  # noqa: BLE001 -- failed reservation durability must stop before SDK.
                self.budget.stopped = True
                raise BuildStop("ADMISSION_RECORD_FAILURE") from None
