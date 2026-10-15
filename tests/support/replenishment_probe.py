"""Read-only bounded interphase checks for disposable runtime probes."""

import math
import subprocess
import time
from pathlib import Path

RUNTIME_SCRIPTS = {
    "host": "run_replenishment_host.py",
    "worker": "run_replenishment_worker.py",
    "monitor": "monitor_replenishment.py",
}


def wait_for_probe_quiescence(
    root, *, seconds=5, command=subprocess.run, clock=time.monotonic, sleep=time.sleep
):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 5:
        raise ValueError("bounded interphase wait required")
    root = str(Path(root))
    started = clock()
    deadline = started + seconds
    result = {
        "check": "INTERPHASE_PROCESSES",
        "status": "OBSERVATION_FAILED",
        "polls": 0,
        "first_candidates": [],
        "candidates": [],
        "error_type": None,
    }
    try:
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                result["status"] = "PROCESS_TIMEOUT"
                break
            sample = command(
                ["ps", "-axo", "pid=,pgid=,command="],
                capture_output=True,
                text=True,
                timeout=min(2, remaining),
                check=True,
            )
            if sample.returncode or len(sample.stdout) > 2 * 1024**2:
                raise ValueError
            candidates = []
            valid_headers = 0
            for line in sample.stdout.splitlines():
                if not line.strip():
                    continue
                relevant = root in line and any(name in line for name in RUNTIME_SCRIPTS.values())
                try:
                    pid, pgid, argv = line.strip().split(None, 2)
                    pid, pgid = int(pid), int(pgid)
                    if pid < 0 or pgid < 0:
                        raise ValueError
                except ValueError:
                    if relevant:
                        raise
                    continue  # ps may print newlines inside an unrelated command argument.
                valid_headers += 1
                if root in argv:
                    for role, name in RUNTIME_SCRIPTS.items():
                        if name in argv:
                            candidates.append({"pid": pid, "pgid": pgid, "role": role})
                            break
            if sample.stdout.strip() and not valid_headers:
                raise ValueError
            result["polls"] += 1
            result["candidates"] = candidates[:64]
            if len(candidates) > 64:
                raise ValueError
            if candidates and not result["first_candidates"]:
                result["first_candidates"] = candidates.copy()
            if clock() > deadline:
                result["status"] = "PROCESS_TIMEOUT"
                break
            if not candidates:
                result["status"] = "QUIESCENT"
                break
            sleep(min(0.05, max(0, deadline - clock())))
    except Exception as error:  # noqa: BLE001 -- unknown process visibility never opens admission.
        result["status"] = "OBSERVATION_FAILED"
        kind = type(error).__name__
        result["error_type"] = (
            kind
            if kind
            in {
                "ValueError",
                "TypeError",
                "TimeoutExpired",
                "CalledProcessError",
                "PermissionError",
                "FileNotFoundError",
                "OSError",
            }
            else "OTHER"
        )
    result["elapsed_seconds"] = round(max(0, clock() - started), 6)
    return result
