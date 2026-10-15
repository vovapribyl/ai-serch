"""Compact controller-owned evidence; recovery remains based on SQL/checkpoints."""

import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path
from threading import RLock

from product_search.infrastructure.nail_runtime import validate_runtime_root
from product_search.search.replenishment_contracts import ReplenishmentError

STOP_CODES = {
    "COMPLETED",
    "UNKNOWN",
    "WAIT_TIMEOUT",
    "RESOURCE_STOP",
    "DEADLINE",
    "RECOVERY_REQUIRED",
    "COMMIT_UNKNOWN",
    "CHECKPOINT_UNKNOWN",
    "ADMISSION_LIMIT",
    "FENCED",
    "ATTEMPT_MISMATCH",
    "CHECKPOINT_INVALID",
    "TARGET_NOT_VERIFIED",
    "RUNTIME_MISMATCH",
    "INVALID_SCOPE",
    "BUSY",
}


class OperationLog:
    def __init__(self, root, *, max_bytes=1024**2, backups=2):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError("Private log root required")
        root = validate_runtime_root(root)
        if not 512 <= max_bytes <= 1024**2 or not 0 <= backups <= 2:
            raise ValueError("Invalid log bounds")
        self.root = Path(tempfile.mkdtemp(prefix="operations-", dir=root))
        self.max_bytes, self.backups = max_bytes, backups
        self._salt = secrets.token_bytes(32)
        self._lock = RLock()
        self.incomplete = False
        self.rotations = self.sequence = self._size = 0
        self._fd = self._open()
        # Persist the new directory entry before processing starts.
        for folder in (root, self.root):
            fd = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _open(self):
        return os.open(
            self.root / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )

    def _rotate(self):
        os.fsync(self._fd)
        os.close(self._fd)
        self._fd = None
        for index in range(self.backups, 0, -1):
            source = self.root / ("events.jsonl" if index == 1 else f"events.{index - 1}.jsonl")
            if source.exists():
                os.replace(source, self.root / f"events.{index}.jsonl")
        if not self.backups:
            (self.root / "events.jsonl").unlink()
        self._fd = self._open()
        self._size = 0
        self.rotations += 1
        directory = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def emit(self, event, phase, **fields):
        with self._lock:
            if self._fd is None or self.incomplete:
                return False
            try:
                if event not in {
                    "batch",
                    "photo",
                    "photo_outcome",
                    "stage",
                    "checkpoint",
                    "publication",
                    "worker",
                    "host",
                } or phase not in {"before", "after", "error", "exit", "closed"}:
                    raise ValueError
                self.sequence += 1
                record = {
                    "sequence": self.sequence,
                    "event": event,
                    "phase": phase,
                    "wall_time": time.time(),
                    "monotonic": time.monotonic(),
                }
                for key, value in fields.items():
                    if key in {
                        "photo_ref",
                        "attempt_ref",
                        "revision_ref",
                        "run_ref",
                    } and isinstance(value, str):
                        record[key] = hashlib.sha256(self._salt + value.encode()).hexdigest()[:24]
                    elif (
                        key in {"total_photos", "completed_photos", "ok_photos", "publications"}
                        and type(value) is int
                        and value >= 0
                        or key == "outcome"
                        and isinstance(value, str)
                        and value in {"OK", "NO_NAILS", "ERROR", "PENDING", "RUNNING"}
                        or key == "error_code"
                        and value in STOP_CODES
                        or (
                            key in {"pid", "returncode", "signal", "errno"}
                            and type(value) is int
                            or key in {"expected", "cleanup_confirmed"}
                            and type(value) is bool
                            or key in {"stage_key", "model_key", "error_type", "result_state"}
                            and isinstance(value, str)
                            and re.fullmatch(r"[a-zA-Z0-9_.-]{0,64}", value)
                        )
                    ):
                        record[key] = value
                payload = (json.dumps(record, separators=(",", ":")) + "\n").encode()
                if len(payload) > self.max_bytes:
                    raise ValueError
                if self._size + len(payload) > self.max_bytes:
                    self._rotate()
                if os.write(self._fd, payload) != len(payload):
                    raise OSError("Partial log write")
                self._size += len(payload)
                if phase in {"error", "exit", "closed"} or (
                    event in {"checkpoint", "publication"} and phase == "after"
                ):
                    os.fsync(self._fd)
                return True
            except Exception:  # noqa: BLE001 -- logging must not replace the original processing outcome.
                self.incomplete = True
                return False

    def error(self, event, error, **fields):
        code = str(error) if isinstance(error, ReplenishmentError) else "UNKNOWN"
        self.emit(
            event,
            "error",
            **fields,
            error_type=type(error).__name__,
            error_code=code if code in STOP_CODES else "UNKNOWN",
            errno=error.errno if isinstance(error, OSError) else None,
        )

    def wrap(self, event, function):
        def recorded(*args, **kwargs):
            fields = {}
            for value in args:
                for key in (
                    "photo_ref",
                    "attempt_ref",
                    "revision_ref",
                    "run_ref",
                    "stage_key",
                    "model_key",
                ):
                    candidate = getattr(value, key, None)
                    if isinstance(candidate, str):
                        fields[key] = candidate
            if (
                event == "batch"
                and len(args) > 1
                and isinstance(args[1], list)
                and all(isinstance(p, dict) and isinstance(p.get("photos"), list) for p in args[1])
            ):
                fields["total_photos"] = sum(len(p["photos"]) for p in args[1])
            if event == "photo_outcome" and len(args) > 1:
                fields["outcome"] = getattr(args[1], "value", None)
            self.emit(event, "before", **fields)
            try:
                result = function(*args, **kwargs)
            except Exception as error:
                self.error(event, error, **fields)
                raise
            state = getattr(result, "state", None)
            if (
                event == "batch"
                and isinstance(result, dict)
                and isinstance(result.get("outcomes"), list)
            ):
                state = result.get("status")
                fields.update(
                    total_photos=len(result["outcomes"]),
                    completed_photos=sum(
                        p[1] not in {"PENDING", "RUNNING"} for p in result["outcomes"]
                    ),
                    ok_photos=sum(p[1] == "OK" for p in result["outcomes"]),
                    publications=sum(
                        p["state"] == "SUCCEEDED" for p in result.get("publications", [])
                    ),
                    error_code=result.get("reason") or "UNKNOWN",
                )
            self.emit(event, "after", **fields, result_state=state)
            return result

        return recorded

    def close(self):
        with self._lock:
            if self._fd is None:
                return
            self.emit("host", "closed")
            try:
                os.fsync(self._fd)
                payload = json.dumps(
                    {
                        "incomplete": self.incomplete,
                        "rotations": self.rotations,
                        "events_attempted": self.sequence,
                    }
                ).encode()
                fd = os.open(
                    self.root / "status.json",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                try:
                    if os.write(fd, payload) != len(payload):
                        raise OSError
                    os.fsync(fd)
                finally:
                    os.close(fd)
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                self.incomplete = True
            finally:
                os.close(self._fd)
                self._fd = None
