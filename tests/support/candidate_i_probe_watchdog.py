"""External watchdog for an owned probe process group, not for existing applications."""

import json
import math
import os
import signal
import subprocess
import time

from tests.support.candidate_i_runtime_probe import resource_violation


def run_owned_probe(command, output_path, host_trace, wall_limit_s, profile):
    profile = json.loads(json.dumps(profile))
    if not math.isfinite(wall_limit_s) or wall_limit_s <= 0 or host_trace.exists():
        raise ValueError("fresh trace and positive deadline required")
    reason = None
    started = time.monotonic()
    offset = 0
    last_sample = None
    stop_sample = None
    termination_action = "NONE"
    max_age = profile.get("resource_sample_max_age_s")
    if max_age is not None and (not math.isfinite(max_age) or max_age <= 0):
        raise ValueError("finite positive telemetry deadline required")

    def trace_failure():
        nonlocal offset, last_sample, stop_sample
        if not host_trace.exists():
            return (
                "RESOURCE_OBSERVATION_ERROR"
                if max_age is not None and time.monotonic() - started > max_age
                else None
            )
        try:
            if host_trace.stat().st_size < offset:
                return "RESOURCE_OBSERVATION_ERROR"
            with host_trace.open("rb") as trace:
                trace.seek(offset)
                while line := trace.readline():
                    if not line.endswith(b"\n"):
                        break
                    sample = json.loads(line)
                    offset = trace.tell()
                    if sample.get("event") == "resource_observation_error":
                        stop_sample = {
                            key: value
                            for key, value in sample.items()
                            if key
                            in {
                                "pressure",
                                "i_rss",
                                "controller_rss",
                                "swapouts_delta",
                                "mps_driver_bytes",
                            }
                            and type(value) is int
                            and value >= 0
                        }
                        reason = sample.get("reason")
                        return (
                            reason
                            if isinstance(reason, str)
                            and reason
                            in {
                                "RESOURCE_CEILING",
                                "STORAGE_CEILING",
                                "RESOURCE_OBSERVATION_ERROR",
                                "PRESSURE_CRITICAL",
                                "RSS_LIMIT",
                                "MPS_LIMIT",
                                "OBSERVATION_FAILED",
                            }
                            else "RESOURCE_OBSERVATION_ERROR"
                        )
                    if max_age is not None:
                        last_sample = float(sample["monotonic"])
                    if resource_violation(
                        sample["pressure"],
                        sample["i_rss"],
                        sample["controller_rss"],
                        profile,
                        sample["swapouts_delta"],
                    ):
                        return "RESOURCE_CEILING"
        except (OSError, ValueError, KeyError, TypeError):
            return "RESOURCE_OBSERVATION_ERROR"
        if (
            max_age is not None
            and time.monotonic() - (last_sample if last_sample is not None else started) > max_age
        ):
            return "RESOURCE_OBSERVATION_ERROR"
        return None

    with output_path.open("xb") as log:
        os.fchmod(log.fileno(), 0o600)
        env = {
            **os.environ,
            "CANDIDATE_I_OWNED_WATCHDOG": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        env.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
        process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True, env=env)
        try:
            while process.poll() is None:
                if time.monotonic() - started >= wall_limit_s:
                    reason = "WALL_CLOCK_LIMIT"
                    break
                reason = trace_failure()
                if reason is not None:
                    break
                time.sleep(0.05)
        finally:
            # Only the new session created above: includes owned I, never existing apps.
            try:
                os.killpg(process.pid, signal.SIGKILL)
                termination_action = "SIGKILL_OWNED_GROUP"
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        if reason is None:
            reason = trace_failure()
        result = {
            "event": "watchdog",
            "exit_code": process.returncode,
            "stop_reason": reason,
            "stop_sample": stop_sample,
            "termination_action": termination_action,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        log.write((json.dumps(result, sort_keys=True) + "\n").encode())
        log.flush()
    return result
