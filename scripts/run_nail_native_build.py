"""Owned native build command; --check cannot reach model/representation writes."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from product_search.infrastructure.nail_build_composition import (
    HostStorageObserver,
    RecordingBudget,
    RuntimeVerifier,
    publish_private_json,
    read_private_json,
    supervise_owned,
)
from product_search.infrastructure.nail_build_runner import AdmissionBudget, BuildStop, OwnedTarget
from product_search.infrastructure.nail_native_job import (
    CurrentObservation,
    backend_runtime,
    claim_execution,
    consume_worker_claim,
    execution_allowed,
    guard_i_application,
    load_job,
    read_pinned,
    safe_target_counts,
    target_precheck,
    validate_input_scope,
)
from product_search.infrastructure.nail_runtime import FileLease, validate_runtime_root


def allowed_run(job, job_sha, args, observation):
    return (
        not args.check
        and args.permit
        and args.permit_sha256
        and execution_allowed(
            {"path": args.permit, "sha256": args.permit_sha256}, job_sha, now=time.time()
        )
        and observation.allowed()
    )


def i_server(job, job_sha, args):
    import uvicorn

    from services.candidate_i.bootstrap import assemble_service

    root = validate_runtime_root(Path(args.run_root))
    leader = read_private_json(root / "worker-pid.json")["pid"]
    if os.getppid() != leader or os.getpgid(os.getpid()) != leader:
        raise BuildStop("OWNED_I_PROCESS_REQUIRED")
    with socket.fromfd(args.fd, socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.getsockname()[0] != "127.0.0.1":
            raise BuildStop("LOOPBACK_REQUIRED")
    assembly = json.loads(read_pinned(job["files"]["assembly"]))
    observation = CurrentObservation(root, job["limits"])
    app = assemble_service(
        assembly["manifest"],
        {k: Path(v) for k, v in assembly["files"].items()},
        runtime_root=root / "runtime",
        gdino_snapshot_path=Path(assembly["gdino_snapshot_path"]),
        sam_checkpoint_path=Path(assembly["sam_checkpoint_path"]),
    )
    app = guard_i_application(
        app, check=args.check, allowed=lambda: allowed_run(job, job_sha, args, observation)
    )
    publish_private_json(
        root / "i-metadata.json",
        {
            "torch_imported": "torch" in sys.modules,
            "transformers_imported": "transformers" in sys.modules,
            "owned_group": True,
        },
    )
    uvicorn.run(app, fd=args.fd, access_log=False, log_level="warning")


def create_budget(job, job_sha, args, observation, root):
    return RecordingBudget(
        AdmissionBudget(
            job["max_admissions"],
            time.monotonic() + job["limits"]["wall_s"],
            lambda: allowed_run(job, job_sha, args, observation),
            time.monotonic,
        ),
        lambda count: publish_private_json(
            root / "admissions.json", {"reserved": count, "before_sdk": True}
        ),
    )


def worker(job, job_sha, args):
    import httpx

    from product_search.infrastructure.nail_native_bindings import native_services
    from product_search.search.nail_contracts import (
        BuildIdentity,
        BuildPhoto,
        DecodeProfile,
        ModelIdentity,
        PhotoInput,
    )

    if (
        os.environ.get("CANDIDATE_I_OWNED_WATCHDOG") != "1"
        or os.getpgid(os.getpid()) != os.getpid()
    ):
        raise BuildStop("OWNED_WATCHDOG_REQUIRED")
    root = validate_runtime_root(Path(args.run_root))
    if not args.check:
        consume_worker_claim(Path(args.job).parent, root, job_sha, os.getppid())
    publish_private_json(root / "worker-pid.json", {"pid": os.getpid(), "parent": os.getppid()})
    observation = CurrentObservation(root, job["limits"])
    until = time.monotonic() + 10
    while not (root / "observation.json").exists():
        if time.monotonic() > until:
            raise BuildStop("INITIAL_OBSERVATION_MISSING")
        time.sleep(0.02)
    if not observation.allowed():
        raise BuildStop("INITIAL_OBSERVATION_STOP")
    if not args.check and not allowed_run(job, job_sha, args, observation):
        raise BuildStop("NATIVE_EXECUTION_NOT_AUTHORIZED")
    target = OwnedTarget(job["files"]["target"]["path"], job["files"]["target"]["sha256"])
    target_precheck(target, job)
    publish_private_json(root / "stage.json", {"stage": "TARGET_VERIFIED"})
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    base_url = "http://127.0.0.1:" + str(sock.getsockname()[1])
    command = [
        job["i_interpreter"],
        "-B",
        str(Path(__file__).resolve()),
        "--role",
        "i",
        "--job",
        args.job,
        "--job-sha256",
        job_sha,
        "--run-root",
        str(root),
        "--fd",
        str(sock.fileno()),
        "--check" if args.check else "--execute",
    ]
    if not args.check:
        command += ["--permit", args.permit, "--permit-sha256", args.permit_sha256]
    server = None
    try:
        with (root / "i.log").open("xb") as log:
            os.fchmod(log.fileno(), 0o600)
            server = subprocess.Popen(command, stdout=log, stderr=log, pass_fds=(sock.fileno(),))
        sock.close()
        with httpx.Client(timeout=1) as client:
            deadline = time.monotonic() + 30
            while True:
                if server.poll() is not None or time.monotonic() > deadline:
                    raise BuildStop("I_READINESS_STOP")
                try:
                    response = client.get(base_url + "/health/ready")
                    health = response.json()
                    if response.status_code == 200 and health.get("ready") is True:
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(0.1)
            if health["extractor_fingerprint"] != job["runtime"]["extractor_fingerprint"]:
                raise BuildStop("I_IDENTITY_CHANGED")
            if args.check and client.post(base_url + "/v1/localizations").status_code != 403:
                raise BuildStop("MODEL_FREE_FIREWALL_FAILED")

            def observe_runtime():
                current = client.get(base_url + "/health/ready")
                current.raise_for_status()
                payload = current.json()
                if payload.get("ready") is not True:
                    raise BuildStop("I_NOT_READY")
                return backend_runtime(job, payload["extractor_fingerprint"])

            publish_private_json(root / "stage.json", {"stage": "I_READY"})
            verifier = RuntimeVerifier(job["runtime"], observe_runtime)
            if not verifier.verify():
                raise BuildStop("RUNTIME_IDENTITY_CHANGED")
            publish_private_json(root / "stage.json", {"stage": "RUNTIME_VERIFIED"})
            budget = create_budget(job, job_sha, args, observation, root)
            inventory_data = json.loads(read_pinned(job["files"]["inventory"]))
            canonical = json.dumps(
                inventory_data["items"], sort_keys=True, separators=(",", ":")
            ).encode()
            if hashlib.sha256(canonical).hexdigest() != job["build"]["inventory_sha256"]:
                raise BuildStop("INVENTORY_IDENTITY_CHANGED")
            inventory = tuple(
                BuildPhoto(i["catalog_photo_id"], i["product_record_id"], PhotoInput(**i["photo"]))
                for i in inventory_data["items"]
            )
            models = tuple(ModelIdentity(*row) for row in job["runtime"]["models"])
            identity = BuildIdentity(
                job["build"]["representation_id"],
                job["build"]["corpus_version_id"],
                job["build"]["fingerprint"],
                job["build"]["inventory_sha256"],
                tuple(tuple(row) for row in job["build"]["profile"]),
                models,
            )
            ports = native_services(
                target_descriptor=job["files"]["target"]["path"],
                target_sha256=job["files"]["target"]["sha256"],
                model_root=job["model_root"],
                models=models,
                source_root=job["inputs_root"],
                source_names=json.loads(read_pinned(job["files"]["names"])),
                artifact_root=root / "artifacts",
                query_root=root / "queries",
                runtime_root=root / "runtime",
                base_url=base_url,
                extractor_fingerprint=health["extractor_fingerprint"],
                representation_fingerprint=identity.fingerprint,
                budget=budget,
                permit=lambda: allowed_run(job, job_sha, args, observation),
            )

            def inputs_ok():
                validate_input_scope(job, inventory)
                for item in inventory:
                    if not observation.allowed():
                        raise BuildStop("INPUT_PREFLIGHT_OBSERVATION_STOP")
                    ports.source_images.read_rgb(item.photo, DecodeProfile(20971520, 2359296))
                return True

            publish_private_json(root / "stage.json", {"stage": "INPUT_PREFLIGHT"})
            inputs_ok()
            if args.check:
                result = {
                    "mode": "check",
                    "outcome": "MODEL_FREE_PASS",
                    "input_count": len(inventory),
                    "reserved_admissions": 0,
                    "i_readiness": True,
                    "i_post_blocked": True,
                    "backend_sdk_imported": "torch" in sys.modules or "transformers" in sys.modules,
                    "i_metadata": read_private_json(root / "i-metadata.json"),
                    "target": safe_target_counts(target, job),
                }
                if result["backend_sdk_imported"] or any(
                    result["i_metadata"].get(k) for k in ("torch_imported", "transformers_imported")
                ):
                    raise BuildStop("UNEXPECTED_SDK_IMPORT")
            else:
                summary = ports.execute_build(
                    identity, inventory, input_check=inputs_ok, runtime_check=verifier.verify
                )
                result = {
                    "mode": "execute",
                    "outcome": "BUILD_FINISHED",
                    "complete": summary.complete,
                    "reserved_admissions": budget.used,
                    "target": safe_target_counts(target, job),
                    "published": False,
                }
        publish_private_json(root / "result.json", result)
    finally:
        sock.close()
        if server is not None:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
            publish_private_json(
                root / "i-exit.json",
                {"owned_exit": server.returncode, "terminated": server.poll() is not None},
            )
        publish_private_json(root / "worker-done.json", {"done": True})


def controller(job, job_sha, args):
    from tests.support.candidate_i_probe_watchdog import run_owned_probe

    job_root = validate_runtime_root(Path(args.job).parent)
    if Path(sys.executable).resolve() != Path(job["backend_interpreter"]).resolve():
        raise BuildStop("BACKEND_INTERPRETER_CHANGED")
    if not args.check and (not args.permit or not args.permit_sha256):
        raise BuildStop("NATIVE_EXECUTION_NOT_AUTHORIZED")
    root = Path(tempfile.mkdtemp(prefix="check-" if args.check else "execution-", dir=job_root))
    root.chmod(0o700)
    if not args.check:
        claim_execution(
            job_root,
            {"path": args.permit, "sha256": args.permit_sha256},
            job_sha,
            now=time.time(),
            run_root=root,
        )
    for name in ("artifacts", "queries", "runtime"):
        (root / name).mkdir(mode=0o700)
    target = OwnedTarget(job["files"]["target"]["path"], job["files"]["target"]["sha256"])
    target_precheck(target, job)
    observer = HostStorageObserver(root / "artifacts", target)

    def observe(pid):
        sample = observer.sample(pid)
        observe.swapouts_delta = observer.last_swapouts_delta
        return sample

    command = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve()),
        "--role",
        "worker",
        "--job",
        args.job,
        "--job-sha256",
        job_sha,
        "--run-root",
        str(root),
        "--check" if args.check else "--execute",
    ]
    if not args.check:
        command += ["--permit", args.permit, "--permit-sha256", args.permit_sha256]
    limits = {
        **job["limits"],
        "wall_s": job["check_wall_s"] if args.check else job["limits"]["wall_s"],
    }
    outcome = supervise_owned(command, root, limits, observe=observe, watchdog=run_owned_probe)
    leases = True
    for name in ("device.lock", "coordinator.lock"):
        lease = FileLease(root / "runtime", name)
        acquired = lease.try_acquire()
        leases = leases and acquired
        if acquired:
            lease.release()
    try:
        counts = safe_target_counts(target, job)
    except BuildStop:
        counts = "UNKNOWN"
    summary = {
        "job_sha256": job_sha,
        "mode": "check" if args.check else "execute",
        "supervisor": outcome,
        "target": counts,
        "owned_leases_reacquired": leases,
        "worker_result": read_private_json(root / "result.json")
        if (root / "result.json").exists()
        else "UNKNOWN",
        "i_exit": read_private_json(root / "i-exit.json")
        if (root / "i-exit.json").exists()
        else "UNKNOWN",
        "reserved": read_private_json(root / "admissions.json")["reserved"]
        if (root / "admissions.json").exists()
        else 0,
    }
    publish_private_json(root / "safe-report.json", summary)
    publish_private_json(
        job_root / "last-check.json" if args.check else job_root / "execution-result.json", summary
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if outcome["exit_code"] == 0 and outcome["stop_reason"] is None and leases else 3


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("controller", "worker", "i"), default="controller")
    parser.add_argument("--job", required=True)
    parser.add_argument("--job-sha256", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--permit")
    parser.add_argument("--permit-sha256")
    parser.add_argument("--run-root")
    parser.add_argument("--fd", type=int)
    args = parser.parse_args(argv)
    try:
        job = load_job(args.job, args.job_sha256)
        if args.role == "controller":
            return controller(job, args.job_sha256, args)
        if args.role == "worker":
            worker(job, args.job_sha256, args)
        else:
            i_server(job, args.job_sha256, args)
        return 0
    except Exception as error:  # noqa: BLE001 -- private failures must be redacted.
        print(
            json.dumps(
                {
                    "outcome": "STOP",
                    "error_type": type(error).__name__,
                    "cause_type": getattr(error, "cause_type", None),
                    "cause_code": getattr(error, "cause_code", None),
                    "reason": str(error) if isinstance(error, BuildStop) else "EXTERNAL_ERROR",
                }
            ),
            flush=True,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
