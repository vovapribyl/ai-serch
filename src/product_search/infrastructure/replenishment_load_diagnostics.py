"""Opt-in measurements; no SDK imports, model arguments or business decisions."""

import json
import math
import os
import re
import subprocess
import time
from collections import Counter
from contextlib import contextmanager
from functools import wraps
from threading import Event, RLock, Thread

from product_search.infrastructure.nail_runtime import validate_runtime_root

METRICS = frozenset(
    {
        "mps_live_bytes",
        "mps_driver_bytes",
        "pressure",
        "swap_used_bytes",
        "pageouts",
        "page_size_bytes",
        "free_bytes",
        "inactive_bytes",
        "db_container_memory_bytes",
        "db_sample_age_seconds",
    }
)


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


class LoadDiagnostics:
    def __init__(self, path, *, sample, max_bytes, backups=0):
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("invalid diagnostic cap")
        if type(backups) is not int or not 0 <= backups <= 2:
            raise ValueError("invalid diagnostic retention")
        validate_runtime_root(path.parent)
        self.backups, self.rotations = backups, 0
        self.path, self.sample, self.max_bytes = path, sample, max_bytes
        self.fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self._lock, self._calls = RLock(), Counter()
        self.incomplete = False

    def emit(self, step, phase, call):
        with self._lock:
            try:
                if (
                    not re.fullmatch(r"[a-z_.]{1,48}", step)
                    or phase not in {"before", "after", "error", "sample"}
                    or type(call) is not int
                    or call < 0
                ):
                    raise ValueError("invalid event")
                okay = True
                sampling_started = time.monotonic()
                try:
                    source = self.sample()
                    metrics = {k: v for k, v in source.items() if k in METRICS and numeric(v)}
                    if "processes" in source:
                        processes = []
                        for item in source["processes"]:
                            if item.get("role") not in {"controller", "worker", "owned_child"}:
                                continue
                            processes.append(
                                {
                                    "role": item["role"],
                                    **{
                                        k: v
                                        for k, v in item.items()
                                        if k in {"pid", "rss_bytes", "cpu_seconds"} and numeric(v)
                                    },
                                }
                            )
                        metrics["processes"] = processes
                    okay = source.get("measurement_ok", True) is True
                except Exception:  # noqa: BLE001 -- diagnostic errors never replace model results.
                    metrics, okay = {}, False
                self.incomplete |= not okay
                payload = (
                    json.dumps(
                        {
                            "step": step,
                            "phase": phase,
                            "call": call,
                            "monotonic": time.monotonic(),
                            "wall_time": time.time(),
                            "sample_seconds": time.monotonic() - sampling_started,
                            "measurement_ok": okay,
                            "metrics": metrics,
                        },
                        allow_nan=False,
                        sort_keys=True,
                    ).encode()
                    + b"\n"
                )
                if len(payload) > 4096 or self.fd < 0 or len(payload) > self.max_bytes:
                    self.incomplete = True
                    return False
                if os.fstat(self.fd).st_size + len(payload) > self.max_bytes:
                    if not self.backups:
                        self.incomplete = True
                        return False
                    self._rotate()
                if os.write(self.fd, payload) != len(payload):
                    self.incomplete = True
                    return False
                os.fsync(self.fd)
                return True
            except Exception:  # noqa: BLE001 -- bounded observational sink is best effort.
                self.incomplete = True
                return False

    def _rotate(self):
        os.fsync(self.fd)
        os.close(self.fd)
        self.fd = -1
        for index in range(self.backups, 0, -1):
            source = (
                self.path
                if index == 1
                else self.path.with_name(f"{self.path.stem}.{index - 1}{self.path.suffix}")
            )
            if source.exists():
                os.replace(
                    source, self.path.with_name(f"{self.path.stem}.{index}{self.path.suffix}")
                )
        self.fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.rotations += 1

    @contextmanager
    def periodic(self, *, interval_seconds=1):
        if not numeric(interval_seconds) or interval_seconds <= 0:
            raise ValueError("invalid sampling interval")
        stopped = Event()

        def sample():
            while not stopped.wait(interval_seconds):
                if not self.emit("resources", "sample", 0):
                    return

        thread = Thread(target=sample, daemon=True, name="resource-log")
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join(timeout=5)
            self.incomplete |= thread.is_alive()

    def wrap(self, step, function):
        @wraps(function)
        def measured(*args, **kwargs):
            with self._lock:
                self._calls[step] += 1
                call = self._calls[step]
            self.emit(step, "before", call)
            try:
                result = function(*args, **kwargs)
            except BaseException:
                self.emit(step, "error", call)
                raise
            self.emit(step, "after", call)
            return result

        return measured

    def close(self):
        with self._lock:
            if self.fd < 0:
                return
            size = os.fstat(self.fd).st_size
            os.close(self.fd)
            self.fd = -1
            try:
                fd = os.open(
                    self.path.with_suffix(".status.json"),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                with os.fdopen(fd, "w") as stream:
                    json.dump(
                        {
                            "incomplete": self.incomplete,
                            "bytes_written": size,
                            "rotations": self.rotations,
                            "history_truncated": self.rotations > self.backups,
                        },
                        stream,
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError:
                self.incomplete = True


def cpu_seconds(value):
    parts = value.split(":")
    if len(parts) not in (2, 3):
        raise ValueError("invalid CPU time")
    total = 0.0
    for part in parts:
        total = total * 60 + float(part)
    if not numeric(total):
        raise ValueError("invalid CPU time")
    return total


def mac_process_sample(controller_pid, worker_pid=None, *, command=subprocess.run):
    result = {"measurement_ok": True}

    def output(argv):
        return command(argv, capture_output=True, text=True, timeout=1, check=True).stdout

    try:
        processes = []
        for line in output(["/bin/ps", "-axo", "pid=,pgid=,rss=,time="]).splitlines():
            pid, pgid, rss, cpu = line.split()
            pid, pgid = int(pid), int(pgid)
            if pid == controller_pid or (worker_pid is not None and pgid == worker_pid):
                role = (
                    "worker"
                    if pid == worker_pid
                    else ("controller" if pid == controller_pid else "owned_child")
                )
                processes.append(
                    {
                        "role": role,
                        "pid": pid,
                        "rss_bytes": int(rss) * 1024,
                        "cpu_seconds": cpu_seconds(cpu),
                    }
                )
        if not any(p["pid"] == controller_pid for p in processes):
            raise ValueError("missing process")
        result["processes"] = processes
        result["pressure"] = int(
            output(["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip()
        )
        vm = output(["/usr/bin/vm_stat"])
        page_size = int(re.search(r"page size of (\d+) bytes", vm)[1])
        result["page_size_bytes"] = page_size
        for label, key, factor in [
            ("Pages free", "free_bytes", page_size),
            ("Pages inactive", "inactive_bytes", page_size),
            ("Pageouts", "pageouts", 1),
        ]:
            result[key] = int(re.search(re.escape(label) + r":\s*(\d+)", vm)[1]) * factor
        swap = output(["/usr/sbin/sysctl", "-n", "vm.swapusage"])
        match = re.search(r"used\s*=\s*([\d.]+)([KMG])", swap)
        result["swap_used_bytes"] = int(
            float(match[1]) * {"K": 1024, "M": 1024**2, "G": 1024**3}[match[2]]
        )
    except Exception:  # noqa: BLE001 -- missing metrics are UNKNOWN, never fabricated zero.
        result["measurement_ok"] = False
    return result


def worker_sample(torch):
    sample = mac_process_sample(os.getpid(), os.getpid())
    if torch is not None:
        sample["mps_live_bytes"] = torch.mps.current_allocated_memory()
        sample["mps_driver_bytes"] = torch.mps.driver_allocated_memory()
    return sample


@contextmanager
def instrument_localizer(recorder, gdino, sam, client, binding, *, after_photo=None):
    originals = []
    try:
        for cls, method, step in [
            (gdino, "build_model", "gdino.load"),
            (sam, "build_model", "sam.load"),
            (gdino, "predict", "gdino.predict"),
            (sam, "predict_batch", "sam.predict"),
            (client, "predict", "localizer.pass"),
            (binding, "__call__", "localizer.photo"),
        ]:
            original = getattr(cls, method)
            originals.append((cls, method, original))
            function = original
            if cls is binding and method == "__call__" and after_photo is not None:
                function = after_success(original, recorder.wrap("mps.empty_cache", after_photo))
            setattr(cls, method, recorder.wrap(step, function))
        yield
    finally:
        for cls, method, original in reversed(originals):
            setattr(cls, method, original)


class ResourceDiagnostics:
    def __init__(self, observe, recorder, *, clock=time.monotonic):
        self.observe, self.recorder, self.clock = observe, recorder, clock
        self.last = float("-inf")

    def __call__(self):
        observation = self.observe()
        now = self.clock()
        if now - self.last >= 1:
            self.last = now
            self.recorder.emit("resources", "sample", 0)
        return observation

    def close(self):
        try:
            self.observe.close()
        finally:
            self.recorder.close()


def db_memory_sample(path, marker, *, command=subprocess.run):
    from product_search.infrastructure.replenishment_cli import private_json

    try:
        data = private_json(path)
        cid = data["container_id"]
        if not marker or data["marker"] != marker or not re.fullmatch(r"[0-9a-f]{64}", cid):
            return None

        def output(args):
            return command(
                ["docker", "--context", "colima", *args],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            ).stdout.strip()

        if (
            output(
                [
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "corpus-replenishment-probe"}}',
                    cid,
                ]
            )
            != marker
        ):
            return None
        usage = output(["stats", "--no-stream", "--format", "{{.MemUsage}}", cid])
        value, unit = re.match(r"([\d.]+)(B|KiB|MiB|GiB|kB|MB|GB)\s*/", usage).groups()
        scales = {
            "B": 1,
            "KiB": 1024,
            "MiB": 1024**2,
            "GiB": 1024**3,
            "kB": 1000,
            "MB": 1000**2,
            "GB": 1000**3,
        }
        return int(float(value) * scales[unit])
    except Exception:  # noqa: BLE001 -- only the pinned owned container is inspected.
        return None


def after_success(function, callback):
    @wraps(function)
    def run(*args, **kwargs):
        result = function(*args, **kwargs)
        callback()
        return result

    return run


def cache_cleanup_enabled(binding):
    from product_search.search.replenishment_contracts import ReplenishmentError

    enabled = binding.get("empty_cache_after_photo", False)
    if type(enabled) is not bool or (enabled and binding.get("load_diagnostics") is not True):
        raise ReplenishmentError("RUNTIME_MISMATCH")
    return enabled


def diagnostic_interval(binding):
    from product_search.search.replenishment_contracts import ReplenishmentError

    enabled = binding.get("load_diagnostics", False)
    interval = binding.get("diagnostic_interval_seconds", 1)
    if type(enabled) is not bool or not numeric(interval) or interval not in (0.5, 1):
        raise ReplenishmentError("RUNTIME_MISMATCH")
    return interval


@contextmanager
def worker_diagnostics(binding, path, *, sample, max_bytes):
    interval = diagnostic_interval(binding)
    if binding.get("load_diagnostics") is not True:
        yield None
        return
    try:
        recorder = LoadDiagnostics(path, sample=sample, max_bytes=max_bytes, backups=2)
    except OSError:
        # Preserve the existing diagnostic prerequisite of the cache experiment.
        if cache_cleanup_enabled(binding):
            raise
        yield None
        return
    try:
        with recorder.periodic(interval_seconds=interval):
            recorder.emit("worker", "before", 0)
            try:
                yield recorder
            except BaseException:
                recorder.emit("worker", "error", 0)
                raise
            else:
                recorder.emit("worker", "after", 0)
    finally:
        recorder.close()
