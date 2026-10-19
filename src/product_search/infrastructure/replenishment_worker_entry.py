"""Private native stage entry; SDK imports occur only after fresh claim validation."""

import hashlib
import os
import stat
import time
from dataclasses import asdict
from pathlib import Path

from product_search.infrastructure.replenishment_cli import private_json
from product_search.infrastructure.replenishment_runtime_binding import (
    FreshGrant,
    canonical,
    verify_code_inventory,
)
from product_search.search.nail_contracts import MODEL_DIMENSIONS
from product_search.search.replenishment_contracts import (
    ExecutionPackage,
    Ownership,
    ReplenishmentError,
)


def _region_diagnostics_enabled(binding):
    value = binding.get("save_localization_diagnostics", False)
    if type(value) is not bool:
        raise ReplenishmentError("RUNTIME_MISMATCH")
    return value


def validate_control(control):
    """Consume this exact child invocation before importing a native SDK."""
    try:
        required = {
            "schema_version",
            "package",
            "owner",
            "stage_key",
            "model_key",
            "grant_path",
            "binding_path",
            "code_inventory_path",
            "profile_path",
            "checkpoint_root",
            "shared_runtime_root",
            "end_at",
            "lease_fd",
            "coordinator_fd",
            "nonce",
            "control_root",
        }
        if (
            set(control) != required
            or type(control["schema_version"]) is not int
            or control["schema_version"] != 1
        ):
            raise ValueError
        package = ExecutionPackage(**control["package"])
        owner = Ownership(**control["owner"])
        guard = FreshGrant(control["grant_path"])
        grant = guard._read(package)
        claim_path = guard.path.parent / (grant["nonce"] + ".claim")
        if private_json(claim_path) != {"grant": grant, "owner": asdict(owner)}:
            raise ValueError
        binding = private_json(control["binding_path"])
        if hashlib.sha256(canonical(binding)).hexdigest() != package.runtime_sha:
            raise ValueError
        from product_search.infrastructure.replenishment_load_diagnostics import (
            cache_cleanup_enabled,
            diagnostic_interval,
        )

        cache_cleanup_enabled(binding)
        diagnostic_interval(binding)
        _region_diagnostics_enabled(binding)
        verify_code_inventory(control["code_inventory_path"], package.code_sha)
        if (
            hashlib.sha256(canonical(private_json(control["profile_path"]))).hexdigest()
            != package.semantic_profile_sha
        ):
            raise ValueError
        if (control["stage_key"], control["model_key"]) not in (
            ("localization", ""),
            *(("embedding", key) for key, _ in MODEL_DIMENSIONS),
        ):
            raise ValueError
        from product_search.infrastructure.nail_runtime import validate_runtime_root

        for name in ("control_root", "checkpoint_root", "shared_runtime_root"):
            validate_runtime_root(Path(control[name]))
        if control["shared_runtime_root"] != binding["shared_runtime_root"]:
            raise ValueError
        fd = control["lease_fd"]
        if type(fd) is not int or fd < 0:
            raise ValueError
        held = os.fstat(fd)
        expected = (Path(control["shared_runtime_root"]) / "mode.lock").lstat()
        if not stat.S_ISREG(held.st_mode) or (held.st_dev, held.st_ino) != (
            expected.st_dev,
            expected.st_ino,
        ):
            raise ValueError
        auxiliary = control["coordinator_fd"]
        if type(auxiliary) is not int or auxiliary < 0 or auxiliary == control["lease_fd"]:
            raise ValueError
        coordinator = os.fstat(auxiliary)
        expected = (Path(control["shared_runtime_root"]) / "coordinator.lock").lstat()
        if (coordinator.st_dev, coordinator.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError
        from math import isfinite

        if (
            type(control["end_at"]) not in (int, float)
            or not isfinite(control["end_at"])
            or not 0
            < control["end_at"] - time.monotonic()
            <= package.overall_seconds - package.cleanup_reserve_seconds
        ):
            raise ValueError
        import re

        if (
            type(control["nonce"]) is not str
            or re.fullmatch("[0-9a-f]{64}", control["nonce"]) is None
        ):
            raise ValueError
        path = Path(control["control_root"]) / "stage.claim"
        claim = {"control_sha": hashlib.sha256(canonical(control)).hexdigest(), "pid": os.getpid()}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(claim))
            stream.flush()
            os.fsync(stream.fileno())
        return package, owner, binding
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        raise ReplenishmentError("CLAIM_MISMATCH") from None


def handle_embedding_job(control, job, package, files, embedding, profile):
    from math import isfinite

    from product_search.infrastructure.replenishment_workers import encode_checkpoint
    from product_search.search.replenishment_contracts import (
        CheckpointReceipt,
        SavedCheckpoint,
        StageAttempt,
        StageOutput,
    )

    try:
        if set(job) != {"nonce", "attempt", "saved", "end_at"} or job["nonce"] != control["nonce"]:
            raise ValueError
        end_at = job["end_at"]
        if (
            type(end_at) not in (int, float)
            or not isfinite(end_at)
            or not time.monotonic() < end_at <= control["end_at"]
        ):
            raise ValueError
        attempt = StageAttempt(**job["attempt"])
        if (attempt.stage_key, attempt.model_key) != ("embedding", control["model_key"]):
            raise ValueError
        saved = job["saved"]
        checkpoint = SavedCheckpoint(
            StageAttempt(**saved["attempt"]),
            StageOutput(**saved["output"]),
            CheckpointReceipt(**saved["receipt"]),
        )
    except (ValueError, KeyError, TypeError):
        raise ReplenishmentError("CLAIM_MISMATCH") from None
    return encode_checkpoint(checkpoint, attempt, package, files, embedding, profile)


def run_native(path, *, importer=None):
    import platform
    import threading
    from importlib import import_module

    from product_search.infrastructure.nail_build_composition import publish_private_json

    control = private_json(path)
    package, owner, binding = validate_control(control)
    guard = FreshGrant(control["grant_path"])
    guard._claim = guard.path.parent / (guard._read(package)["nonce"] + ".claim")
    guard._grant, guard._owner = guard._read(package), asdict(owner)
    guard.check_owner(owner, package)
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[name] = "1"
    root = Path(control["control_root"])
    # The verified entry has not imported an SDK or allocated MPS yet. This
    # bootstrap zero expires normally; failed/slow imports never refresh it.
    publish_private_json(
        root / "telemetry.json",
        {
            "pid": os.getpid(),
            "nonce": control["nonce"],
            "observed_at": time.monotonic(),
            "mps_bytes": 0,
        },
    )
    from services.candidate_i.bootstrap import installed_inventory

    role = "localization" if control["stage_key"] == "localization" else "encoder"
    actual = binding["installed_inventories"][role]
    if (
        binding["device"] != "mps"
        or binding["dtype"] != "float32"
        or binding["fallback"] is not False
        or platform.python_version() != actual["python"]
        or platform.machine() != actual["machine"]
        or installed_inventory() != actual["packages"]
        or os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") is not None
    ):
        raise ReplenishmentError("RUNTIME_MISMATCH")

    import subprocess
    import sys

    entry = Path(__file__).resolve().parents[3] / "scripts/run_replenishment_worker.py"
    if os.getpgrp() != os.getpid():
        raise ReplenishmentError("FENCED")
    guardian = subprocess.Popen(
        (
            sys.executable,
            "-I",
            "-B",
            str(entry),
            "--guard",
            str(path),
            str(os.getpid()),
            str(os.getppid()),
        ),
        shell=False,
        pass_fds=(control["lease_fd"], control["coordinator_fd"]),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    from product_search.infrastructure.replenishment_load_diagnostics import (
        worker_diagnostics,
        worker_sample,
    )

    torch = None
    with worker_diagnostics(
        binding,
        root / "load-events.jsonl",
        sample=lambda: worker_sample(torch),
        max_bytes=min(package.max_wire_bytes, 1024**2),
    ) as diagnostics:
        load = importer or import_module
        torch = diagnostics.wrap("torch.import", load)("torch") if diagnostics else load("torch")
        if not torch.backends.mps.is_available():
            raise ReplenishmentError("RESOURCE_STOP")
        stopped = threading.Event()

        def telemetry():
            while not stopped.is_set() and time.monotonic() < control["end_at"]:
                try:
                    guard.check_owner(owner, package)
                    if guardian.poll() is not None:
                        os.killpg(os.getpid(), __import__("signal").SIGKILL)
                    allocated = torch.mps.driver_allocated_memory()
                    if type(allocated) is not int or allocated < 0:
                        raise ValueError
                    publish_private_json(
                        root / "telemetry.json",
                        {
                            "pid": os.getpid(),
                            "nonce": control["nonce"],
                            "observed_at": time.monotonic(),
                            "mps_bytes": allocated,
                        },
                    )
                except Exception:  # noqa: BLE001 -- no fabricated replacement sample after telemetry failure.
                    return
                stopped.wait(binding["policy"]["poll_seconds"])

        thread = threading.Thread(target=telemetry, daemon=True)
        thread.start()
        try:
            if role == "localization":
                from product_search.infrastructure.replenishment_load_diagnostics import (
                    cache_cleanup_enabled,
                )

                _serve_localization(
                    control,
                    package,
                    binding,
                    guard,
                    owner,
                    diagnostics=diagnostics,
                    cache_cleanup=torch.mps.empty_cache if cache_cleanup_enabled(binding) else None,
                )
            else:
                _serve_encoder(control, package, binding, guard, owner, diagnostics=diagnostics)
        finally:
            stopped.set()
            thread.join(timeout=package.observation_max_age_seconds)


def _serve_localization(
    control, package, binding, guard, owner, *, diagnostics=None, cache_cleanup=None
):
    if cache_cleanup is not None and diagnostics is None:
        raise ReplenishmentError("RUNTIME_MISMATCH")
    from product_search.infrastructure.replenishment_load_diagnostics import cache_cleanup_enabled

    pre_sam_cleanup = cache_cleanup_enabled(binding, before_sam=True)
    if pre_sam_cleanup and (cache_cleanup is None or diagnostics is None):
        raise ReplenishmentError("RUNTIME_MISMATCH")
    capture_regions = _region_diagnostics_enabled(binding)
    import socket

    import uvicorn

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from services.candidate_i.bootstrap import assemble_service

    files = {
        key: Path(value if isinstance(value, str) else value["path"])
        for key, value in binding["i_files"].items()
    }
    guard.check_owner(owner, package)
    diagnostic_options = {}
    if capture_regions:
        diagnostic_root = Path(control["control_root"]) / "localized-regions"
        diagnostic_root.mkdir(mode=0o700)
        diagnostic_options["diagnostic_root"] = diagnostic_root
    app = assemble_service(
        binding["i_manifest"],
        files,
        runtime_root=Path(control["shared_runtime_root"]),
        gdino_snapshot_path=files["model/gdino/config.json"].parent,
        sam_checkpoint_path=files["model/sam"],
        **diagnostic_options,
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(2)
        endpoint = "http://127.0.0.1:" + str(sock.getsockname()[1])
        publish_private_json(
            Path(control["control_root"]) / "ready.json",
            {
                "pid": os.getpid(),
                "nonce": control["nonce"],
                "status": "READY",
                "endpoint": endpoint,
            },
        )
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                log_config=None,
                access_log=False,
                timeout_graceful_shutdown=package.stop_grace_seconds,
            )
        )
        if diagnostics is None:
            server.run(sockets=[sock])
        else:

            def load_localizer():
                from lang_sam.models.gdino import GDINO
                from lang_sam.models.sam import SAM

                return GDINO, SAM

            GDINO, SAM = diagnostics.wrap("langsam.import", load_localizer)()
            from experiments.nail_localization.langsam_adapter import LazyLangSAMClient
            from product_search.infrastructure.replenishment_load_diagnostics import (
                instrument_localizer,
            )
            from services.candidate_i.binding import CandidateIBinding

            with instrument_localizer(
                diagnostics,
                GDINO,
                SAM,
                LazyLangSAMClient,
                CandidateIBinding,
                after_photo=cache_cleanup,
                before_sam=cache_cleanup if pre_sam_cleanup else None,
            ):
                server.run(sockets=[sock])


def _serve_encoder(control, package, binding, guard, owner, *, diagnostics=None):
    from types import SimpleNamespace

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.nail_ml_adapters import NailEmbeddingAdapter
    from product_search.infrastructure.nail_native_bindings import MODEL_PINS, native_factories
    from product_search.infrastructure.nail_runtime import FileLease
    from product_search.infrastructure.replenishment_artifacts import CheckpointFiles
    from product_search.search.nail_contracts import EmbeddingProfile, NailProcessingError

    pins = tuple(
        SimpleNamespace(model_key=k, revision=r, manifest_sha256=s, dimension=d)
        for k, r, s, d in MODEL_PINS
    )
    factories = native_factories(
        binding["model_root"], pins, permit=lambda: guard.check_owner(owner, package)
    )
    if diagnostics is not None:
        factories = {
            key: diagnostics.wrap("encoder.load", factory) for key, factory in factories.items()
        }
    embedding = NailEmbeddingAdapter({control["model_key"]: factories[control["model_key"]]})
    semantic = private_json(control["profile_path"])
    profile = EmbeddingProfile(tuple((m["model_key"], m["revision"]) for m in semantic["models"]))
    files = CheckpointFiles(control["checkpoint_root"])
    root = Path(control["control_root"])
    publish_private_json(
        root / "ready.json", {"pid": os.getpid(), "nonce": control["nonce"], "status": "READY"}
    )
    number = 1
    while time.monotonic() < control["end_at"]:
        guard.check_owner(owner, package)
        job_path = root / f"job-{number}.json"
        if not job_path.exists():
            time.sleep(min(0.02, max(0, control["end_at"] - time.monotonic())))
            continue
        if number > min(5, package.max_admissions):
            raise ReplenishmentError("ADMISSION_LIMIT")
        job = private_json(job_path)
        device = FileLease(Path(control["shared_runtime_root"]), "device.lock")
        if not device.try_acquire():
            raise ReplenishmentError("BUSY")
        answer = {
            "pid": os.getpid(),
            "nonce": control["nonce"],
            "attempt_ref": job["attempt"]["attempt_ref"],
        }
        try:
            guard.check_owner(owner, package)
            operation = handle_embedding_job
            if diagnostics is not None:
                operation = diagnostics.wrap("encoder.photo", operation)
            output = operation(control, job, package, files, embedding, profile)
            answer.update(status="OK", output=asdict(output))
        except NailProcessingError:
            answer.update(status="ERROR")
        finally:
            device.release()
        publish_private_json(root / f"result-{number}.json", answer)
        number += 1


def guard_owned_group(
    leader_pid,
    package,
    *,
    end_at,
    observe,
    signal_group=None,
    clock=time.monotonic,
    sleep=time.sleep,
    group_id=os.getpgrp,
):
    import math
    import signal

    from product_search.search.replenishment_contracts import ResourceObservation

    if type(leader_pid) is not int or leader_pid <= 0 or group_id() != leader_pid:
        raise ReplenishmentError("FENCED")
    signal_group = signal_group or os.killpg
    while clock() < end_at:
        try:
            observation = observe()
            if (
                not isinstance(observation, ResourceObservation)
                or observation.status not in {"OK", "WARNING"}
                or type(observation.observed_at) not in (int, float)
                or not math.isfinite(observation.observed_at)
                or not 0 <= clock() - observation.observed_at <= package.observation_max_age_seconds
            ):
                break
        except Exception:  # noqa: BLE001 -- unknown observations must terminate the owned group.
            break
        sleep(min(0.5, max(0, end_at - clock())))
    if group_id() != leader_pid:
        raise ReplenishmentError("FENCED")
    signal_group(leader_pid, signal.SIGTERM)
    cutoff = clock() + package.stop_grace_seconds
    while clock() < cutoff:
        sleep(min(0.05, max(0, cutoff - clock())))
    signal_group(leader_pid, signal.SIGKILL)


def run_guard(path, leader_pid, controller_pid):
    import signal

    from product_search.infrastructure.replenishment_runtime_binding import MacResourceObserver
    from product_search.search.replenishment_contracts import ResourceObservation

    control = private_json(path)
    package = ExecutionPackage(**control["package"])
    owner = Ownership(**control["owner"])
    grant = FreshGrant(control["grant_path"])
    grant._grant = grant._read(package)
    grant._claim = grant.path.parent / (grant._grant["nonce"] + ".claim")
    grant._owner = asdict(owner)
    grant.check_owner(owner, package)
    stage_claim = private_json(Path(control["control_root"]) / "stage.claim")
    if stage_claim != {
        "control_sha": hashlib.sha256(canonical(control)).hexdigest(),
        "pid": leader_pid,
    }:
        raise ReplenishmentError("CLAIM_MISMATCH")
    if os.getpgrp() != leader_pid:
        raise ReplenishmentError("FENCED")
    held = os.fstat(control["lease_fd"])
    actual = (Path(control["shared_runtime_root"]) / "mode.lock").lstat()
    if (held.st_dev, held.st_ino) != (actual.st_dev, actual.st_ino):
        raise ReplenishmentError("FENCED")
    sensor = MacResourceObserver(
        package,
        controller_pid=controller_pid,
        owned_worker=lambda: (
            leader_pid,
            Path(control["control_root"]) / "telemetry.json",
            control["nonce"],
        ),
    )
    binding = private_json(control["binding_path"])
    if hashlib.sha256(canonical(binding)).hexdigest() != package.runtime_sha:
        raise ReplenishmentError("RUNTIME_MISMATCH")
    sensor.worker_rss_ceiling = lambda: binding["resource_limits"][
        "i_rss_bytes" if control["stage_key"] == "localization" else "encoder_rss_bytes"
    ]
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def observe():
        try:
            grant.check_owner(owner, package)
        except ReplenishmentError:
            return ResourceObservation("STOP", time.monotonic())
        return sensor()

    guard_owned_group(leader_pid, package, end_at=control["end_at"], observe=observe)
