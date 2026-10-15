"""Read-only, bounded terminal view; no SDK, database or process-control calls."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

from product_search.infrastructure.nail_runtime import validate_runtime_root


def _read(path, cap, *, tail=False):
    validate_runtime_root(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            raise ValueError("Unsafe monitor input")
        if info.st_size > cap:
            if not tail:
                raise ValueError("Monitor input exceeds bound")
            stream.seek(-cap, os.SEEK_END)
            stream.readline()  # Discard a potentially partial first line.
        return stream.read(cap)


def _json(path):
    return json.loads(_read(path, 65536))


def _number(value):
    return value if type(value) is int and value >= 0 else None


def snapshot(root, *, now=None):
    root = validate_runtime_root(Path(root))
    now = time.monotonic() if now is None else now
    binding = _json(root / "runtime-binding.json")
    log_root = validate_runtime_root(
        Path(binding.get("operation_log_root", binding.get("shared_runtime_root", root)))
    )
    folders = list(log_root.glob("operations-*"))
    events = []
    if folders:
        folder = max(folders, key=lambda p: p.lstat().st_mtime_ns)
        validate_runtime_root(folder)
        for name in ("events.2.jsonl", "events.1.jsonl", "events.jsonl"):
            path = folder / name
            if not path.exists():
                continue
            for line in _read(path, 1024**2).splitlines(keepends=True):
                if not line.endswith(b"\n"):
                    continue  # Writer may be appending its final record.
                events.append(json.loads(line))
    events.sort(key=lambda e: e["sequence"])
    journal_status = folder / "status.json" if folders else None
    final_incomplete = (
        journal_status is not None
        and journal_status.exists()
        and _json(journal_status).get("incomplete") is not False
    )
    complete = not final_incomplete and (
        not events or [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    )
    view = {
        "state": "WAITING" if not events else "UNKNOWN",
        "history_complete": complete,
        "total_photos": None,
        "completed_photos": None,
        "ok_photos": None,
        "publications": 0,
        "checkpoints": 0,
        "stage": None,
        "model": None,
        "elapsed_seconds": None,
        "stage_seconds": None,
        "heartbeat_age_seconds": None,
        "resources_fresh": False,
        "closed": False,
        "resource_status": "UNKNOWN",
        "rss_bytes": None,
        "mps_bytes": None,
        "pressure": None,
        "error": None,
    }
    begin = end = stage_begin = stage_end = None
    checkpoints = set()
    outcomes = {}
    for event in events:
        kind, phase = event["event"], event["phase"]
        if kind == "batch" and phase == "before":
            view.update(state="RUNNING", total_photos=_number(event.get("total_photos")))
            begin = event["monotonic"]
        if kind == "stage" and phase == "before" and event.get("stage_key"):
            view["stage"], view["model"] = event["stage_key"], event.get("model_key")
            stage_begin = event["monotonic"]
            stage_end = None
        if (
            kind == "worker"
            and phase == "exit"
            and event.get("stage_key") == view["stage"]
            and event.get("model_key") == view["model"]
        ):
            stage_end = event["monotonic"]
        if kind == "host" and phase == "closed":
            view["closed"] = True
        if kind == "checkpoint" and phase == "after":
            checkpoints.add(
                (
                    event.get("attempt_ref"),
                    event.get("photo_ref"),
                    event.get("stage_key"),
                    event.get("model_key"),
                )
            )
        if kind == "photo_outcome" and phase == "after":
            outcomes[event["photo_ref"]] = event.get("outcome")
            view["completed_photos"] = (
                sum(v not in {"PENDING", "RUNNING", None} for v in outcomes.values())
                if complete
                else None
            )
            view["ok_photos"] = sum(v == "OK" for v in outcomes.values()) if complete else None
        if kind == "publication" and phase == "after" and event.get("result_state") == "SUCCEEDED":
            view["publications"] += 1
        if kind == "batch" and phase == "after":
            end = event["monotonic"]
            code = event.get("error_code")
            view["state"] = (
                "COMPLETED"
                if code == "COMPLETED"
                else "STOPPED"
                if code and code != "UNKNOWN"
                else "UNKNOWN"
            )
            for key in ("total_photos", "completed_photos", "ok_photos", "publications"):
                if _number(event.get(key)) is not None:
                    view[key] = event[key]
        if phase == "error":
            view["state"] = "ERROR"
            value = event.get("error_type", "UNKNOWN")
            view["error"] = (
                value
                if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_]{1,64}", value)
                else "UNKNOWN"
            )
            end = event["monotonic"]
    view["checkpoints"] = len(checkpoints) if complete else None
    if begin is not None:
        view["elapsed_seconds"] = max(0, (end if end is not None else now) - begin)
    if stage_begin is not None:
        view["stage_seconds"] = max(
            0,
            (stage_end if stage_end is not None else end if end is not None else now) - stage_begin,
        )
    # Existing operator evidence can confirm historical runs whose logs predate summary fields.
    result_path = root / "probe050-result.json"
    if result_path.exists():
        result = _json(result_path)
        package = _json(root / "execution-package.proposed.json")
        digest = hashlib.sha256(
            json.dumps(package, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        if result.get("package_sha") == digest:
            answer = result.get("answer", {})
            if answer.get("status") in {"OK", "ERROR", "STOPPED", "UNKNOWN"}:
                view["state"] = "COMPLETED" if answer["status"] == "OK" else answer["status"]
                summary = answer.get("summary")
                if not isinstance(summary, dict) or not isinstance(summary.get("outcomes"), list):
                    summary = None
                if summary is None:
                    outcomes = None
                else:
                    outcomes = summary["outcomes"]
                if outcomes is not None:
                    view.update(
                        state="COMPLETED" if answer["status"] == "OK" else answer["status"],
                        total_photos=len(outcomes),
                        completed_photos=sum(p[1] not in {"PENDING", "RUNNING"} for p in outcomes),
                        ok_photos=sum(p[1] == "OK" for p in outcomes),
                        publications=sum(
                            p.get("state") == "SUCCEEDED" for p in summary.get("publications", [])
                        ),
                    )
    resource_path = root / "resource-observations.jsonl"
    if resource_path.exists():
        for line in reversed(_read(resource_path, 8192, tail=True).splitlines()):
            try:
                observation = json.loads(line)
            except json.JSONDecodeError:
                continue
            age = now - observation["observed_at"]
            view["heartbeat_age_seconds"] = age if age >= 0 else None
            limit = 5
            package_path = root / "execution-package.proposed.json"
            if package_path.exists():
                limit = _json(package_path).get("observation_max_age_seconds", 5)
            view["resources_fresh"] = 0 <= age <= limit
            view["resource_status"] = (
                observation["status"]
                if observation["status"] in {"OK", "WARNING", "STOP"}
                else "UNKNOWN"
            )
            sample = observation.get("sample") or {}
            for key in ("rss_bytes", "mps_bytes", "pressure"):
                view[key] = _number(sample.get(key))
            break
    for key in ("stage", "model"):
        value = view[key]
        if value is not None and (
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{0,64}", value)
        ):
            view[key] = "UNKNOWN"
    return view


def render(view):
    def number(value):
        return "UNKNOWN" if value is None else str(value)

    def seconds(value):
        return "UNKNOWN" if value is None else f"{value:.1f} с"

    def memory(value):
        return "UNKNOWN" if value is None else f"{value / 1024**2:.1f} МиБ"

    return "\n".join(
        [
            f"Последнее состояние: {view['state']}",
            f"Фото с итогом: {number(view['completed_photos'])} / {number(view['total_photos'])}; OK: {number(view['ok_photos'])}",
            f"Checkpoint: {number(view['checkpoints'])}; публикации: {number(view['publications'])}",
            f"Последняя стадия: {view['stage'] or 'UNKNOWN'}; модель: {view['model'] or 'UNKNOWN'}",
            f"Длительность партии: {seconds(view['elapsed_seconds'])}; стадии: {seconds(view['stage_seconds'])}",
            f"Возраст heartbeat: {seconds(view['heartbeat_age_seconds'])} — {'свежие данные' if view['resources_fresh'] else 'данные отсутствуют или устарели'}",
            f"Последний guard: {view['resource_status']}; RSS: {memory(view['rss_bytes'])}; MPS: {memory(view['mps_bytes'])}",
            f"Полнота истории: {'подтверждена' if view['history_complete'] else 'неполная, счётчики могут быть неизвестны'}",
            f"Ошибка: {view['error'] or 'не зарегистрирована'}",
        ]
    )


def main(argv=None, *, stdout=None, stderr=None):
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr

    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError("Invalid monitor arguments")

    parser = Parser(prog="monitor-replenishment", allow_abbrev=False)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=3)
    parser.add_argument("--seconds", type=float, default=1200)
    try:
        args = parser.parse_args(argv)
        if not 1 <= args.interval <= 60 or not 1 <= args.seconds <= 3600:
            raise ValueError
        deadline = time.monotonic() + args.seconds
        while True:
            view = snapshot(args.runtime_root)
            if args.watch and stdout.isatty():
                stdout.write("\033[2J\033[H")
            stdout.write(render(view) + "\n")
            stdout.flush()
            if not args.watch or view["closed"] or time.monotonic() >= deadline:
                return 0
            time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        return 0  # Only this viewer stops; it cannot control the worker.
    except Exception:  # noqa: BLE001 -- never expose private paths or JSON contents.
        stderr.write("MONITOR_UNAVAILABLE\n")
        return 5
