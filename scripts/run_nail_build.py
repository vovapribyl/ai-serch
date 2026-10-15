"""Supervised model-free fake composition. Native mode remains closed."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fake", "native"), required=True)
    parser.add_argument("--target")
    parser.add_argument("--target-sha256")
    parser.add_argument("--private-parent", default="/private/tmp")
    parser.add_argument("--locator")
    parser.add_argument(
        "--fault",
        choices=("none", "provider_error", "critical", "storage", "stale", "wall"),
        default="none",
    )
    args = parser.parse_args(argv)
    if args.mode == "native":
        print(json.dumps({"status": "NATIVE_EXECUTION_NOT_AUTHORIZED", "ml_executed": False}))
        return 4
    if not args.target or not args.target_sha256 or not args.locator:
        parser.error("fake requires pinned owned target and fresh private locator")
    from PIL import Image

    from product_search.infrastructure.nail_build_composition import (
        HostStorageObserver,
        publish_private_json,
        read_private_json,
        supervise_owned,
    )
    from product_search.infrastructure.nail_build_runner import OwnedTarget
    from product_search.infrastructure.nail_runtime import FileLease
    from tests.support.candidate_i_probe_watchdog import run_owned_probe
    from tests.support.nail_build_fake_worker import fake_runtime

    target = OwnedTarget(args.target, args.target_sha256)
    with target.connect():
        pass
    root = Path(tempfile.mkdtemp(prefix="t051-composition-fake-", dir=args.private_parent))
    root.chmod(0o700)
    for name in ("inputs", "artifacts", "runtime"):
        (root / name).mkdir(mode=0o700)
    locator = Path(args.locator)
    fd = os.open(locator, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(str(root))
    inputs = []
    for color in ("red", "blue"):
        ref = uuid4().hex
        path = root / "inputs" / ref
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream, Image.new("RGB", (2, 2), color) as image:
            image.save(stream, format="PNG")
        inputs.append(
            {
                "ref": ref,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "catalog_photo_id": str(uuid4()),
            }
        )
    code = Path(__file__).resolve().parents[1]
    code_files = [
        Path(__file__),
        code / "src/product_search/infrastructure/nail_build_composition.py",
        code / "src/product_search/infrastructure/nail_build_runner.py",
        code / "tests/support/nail_build_fake_worker.py",
        code / "tests/support/candidate_i_probe_watchdog.py",
        code / "tests/support/candidate_i_runtime_probe.py",
        code / "src/product_search/search/nail_catalog_build.py",
        code / "src/product_search/search/nail_image_processor.py",
        code / "src/product_search/infrastructure/nail_image_store.py",
        code / "src/product_search/infrastructure/nail_ml_adapters.py",
        code / "src/product_search/infrastructure/nail_runtime.py",
        code / "services/candidate_i/app.py",
        code / "services/candidate_i/settings.py",
        code / "src/product_search/search/nail_contracts.py",
        code / "src/product_search/infrastructure/nail_wire.py",
        code / "tests/support/candidate_i_resource_metrics.py",
    ]
    limits = {
        "i_rss_bytes": 6 * 1024**3,
        "backend_rss_bytes": 5 * 1024**3,
        "combined_rss_bytes": 10 * 1024**3,
        "max_storage_bytes": 64 * 1024**2,
        "min_free_bytes": 16 * 1024**2,
        "freshness_s": 1,
        "wall_s": 1 if args.fault == "wall" else 5,
    }
    job = {
        "mode": "fake",
        "fault": args.fault,
        "inputs": inputs,
        "representation_id": str(uuid4()),
        "representation_fingerprint": hashlib.sha256(
            json.dumps(inputs, sort_keys=True).encode()
        ).hexdigest(),
        "inventory_sha256": hashlib.sha256(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "runtime": fake_runtime(),
        "limits": limits,
        "target": {"path": args.target, "sha256": args.target_sha256},
        "code": [
            {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in code_files
        ],
    }
    publish_private_json(root / "job.json", job)
    sha = hashlib.sha256((root / "job.json").read_bytes()).hexdigest()
    command = [
        sys.executable,
        "-B",
        str(code / "tests/support/nail_build_fake_worker.py"),
        str(root / "job.json"),
        sha,
    ]
    publish_private_json(
        root / "command.json",
        {
            "argv": [sys.executable, "-B", str(Path(__file__))] + list(argv or sys.argv[1:]),
            "worker": command,
            "cwd": str(code),
            "job_sha256": sha,
        },
    )
    observer = HostStorageObserver(root / "artifacts", target)

    def observe(pid):
        if args.fault == "stale":
            import time

            time.sleep(3)
        value = observer.sample(pid)
        observe.swapouts_delta = observer.last_swapouts_delta
        if args.fault == "critical":
            value["pressure"] = 4
        if args.fault == "storage":
            value["artifact_bytes"] = limits["max_storage_bytes"]
        return value

    result = supervise_owned(command, root, limits, observe=observe, watchdog=run_owned_probe)
    worker = read_private_json(root / "result.json") if (root / "result.json").exists() else None
    checkpoint = (
        read_private_json(root / "checkpoint.json") if (root / "checkpoint.json").exists() else None
    )
    reacquired = True
    for name in ("coordinator.lock", "device.lock"):
        lease = FileLease(root / "runtime", name)
        acquired = lease.try_acquire()
        reacquired = reacquired and acquired
        if acquired:
            lease.release()
    reserved = (
        read_private_json(root / "admissions.json")["reserved"]
        if (root / "admissions.json").exists()
        else None
    )
    summary = {
        "mode": "fake",
        "reserved_admissions": reserved,
        "job_sha256": sha,
        "supervisor": result,
        "worker": worker,
        "checkpoint": checkpoint,
        "owned_leases_reacquired": reacquired,
        "native_launch": "CLOSED",
        "private_root_saved": True,
    }
    publish_private_json(root / "safe-report.json", summary)
    print(json.dumps(summary, sort_keys=True))
    return (
        0
        if result["exit_code"] == 0
        and result["stop_reason"] is None
        and worker
        and worker["outcome"] == "PASS"
        and reacquired
        else 3
    )


if __name__ == "__main__":
    raise SystemExit(main())
