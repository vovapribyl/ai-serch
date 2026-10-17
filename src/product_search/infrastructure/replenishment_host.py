"""Bounded private owner host; no SDK imports, default DSN or implicit approval."""

import json
import math
import time
from pathlib import Path

from product_search.search.replenishment_contracts import ReplenishmentError


def serve_owner(
    app,
    root,
    package,
    *,
    end_at,
    max_commands,
    timeout_seconds,
    max_bytes,
    server_factory=None,
    clock=time.monotonic,
    on_error=None,
):
    from product_search.infrastructure.replenishment_cli import (
        OwnerDispatcher,
        PrivateCommandServer,
    )

    if type(max_commands) is not int or not 1 <= max_commands <= package.max_admissions:
        raise ReplenishmentError("INVALID_PACKAGE")
    cutoff = end_at - package.cleanup_reserve_seconds
    server = None
    try:
        if clock() >= cutoff:
            raise ReplenishmentError("DEADLINE")
        server = (server_factory or PrivateCommandServer)(
            root,
            app.supervisor.lease,
            OwnerDispatcher(app, role="OWNER", on_error=on_error).handle,
            timeout_seconds=min(timeout_seconds, cutoff - clock()),
            max_bytes=max_bytes,
            on_error=on_error,
        )
        for _ in range(max_commands):
            if clock() >= cutoff:
                break
            try:
                server.serve_once()
            except TimeoutError:
                break
    finally:
        try:
            if server is not None:
                server.close()
        finally:
            app.supervisor.close(
                end_at=end_at,
                stop_grace=package.stop_grace_seconds,
                kill_wait=package.kill_wait_seconds,
            )


class RuntimeTarget:
    """Pinned, uniquely labelled disposable DB. Never accepts the working DSN."""

    def __init__(self, path, policy, *, command=None, connector=None):
        import subprocess

        import psycopg

        self.path, self.policy = Path(path), dict(policy)
        self.command, self.connector = command or subprocess.run, connector or psycopg.connect

    def connect(self, package, end_at, *, clock=time.monotonic):
        from product_search.infrastructure.replenishment_cli import private_json
        from product_search.infrastructure.replenishment_runtime_binding import canonical

        connection = None
        started = clock()
        try:
            data = private_json(self.path)
            before = canonical(data)
            config = data["config"]
            policy = self.policy
            if (
                set(data) != {"marker", "container_id", "config"}
                or data["marker"] != policy["marker"]
                or not data["container_id"]
                or set(config) != {"host", "port", "dbname", "user", "password"}
                or config["host"] != "127.0.0.1"
                or type(config["port"]) is not int
                or not 1 <= config["port"] <= 65535
                or config["dbname"] != policy["dbname"]
                or config["user"] != policy["user"]
                or not config["password"]
            ):
                raise ValueError

            def remaining():
                value = min(
                    end_at - package.cleanup_reserve_seconds - clock(),
                    package.db_seconds - (clock() - started),
                )
                if value <= 0:
                    raise ValueError
                return value

            result = self.command(
                ["docker", "--context", "colima", "inspect", data["container_id"]],
                capture_output=True,
                text=True,
                check=False,
                timeout=min(2, remaining()),
            )
            if result.returncode:
                raise ValueError
            meta = json.loads(result.stdout)
            if len(meta) != 1:
                raise ValueError
            meta = meta[0]
            ports = meta["NetworkSettings"]["Ports"]["5432/tcp"]
            mounts = meta["Mounts"]
            host = meta["HostConfig"]
            if (
                meta["Id"] != data["container_id"]
                or meta["Image"] != policy["image"]
                or meta["Config"]["Labels"].get("corpus-replenishment-probe") != policy["marker"]
                or meta["State"]["Running"] is not True
                or host["Memory"] != 536870912
                or host["NanoCpus"] != 1000000000
                or host["PidsLimit"] != 128
                or len(mounts) != 1
                or mounts[0]["Type"] != "tmpfs"
                or mounts[0]["Destination"] != "/var/lib/postgresql/data"
                or len(ports) != 1
                or ports[0]["HostIp"] != "127.0.0.1"
                or int(ports[0]["HostPort"]) != config["port"]
            ):
                raise ValueError
            budget = remaining()
            connection = self.connector(
                **config,
                connect_timeout=max(1, math.ceil(min(2, budget))),
                options=f"-c statement_timeout={max(1, int(budget * 1000))} -c lock_timeout={max(1, int(budget * 1000))}",
            )
            if connection.execute("SELECT current_database(),current_user").fetchone() != (
                policy["dbname"],
                policy["user"],
            ):
                raise ValueError
            if connection.execute("SELECT version_num FROM alembic_version").fetchone() != (
                "0010_corpus_replenishment_v1",
            ):
                raise ValueError
            if canonical(private_json(self.path)) != before:
                raise ValueError
            remaining()
            return connection
        except Exception:  # noqa: BLE001 -- no target identity, credentials or SQL diagnostics on public channels.
            if connection is not None:
                connection.close()
            raise ReplenishmentError("TARGET_NOT_VERIFIED") from None


def run_native_host(config):
    import hashlib
    import os
    from types import SimpleNamespace

    from product_search.infrastructure.nail_runtime import FileLease
    from product_search.infrastructure.replenishment_application import (
        LocalReplenishmentApplication,
    )
    from product_search.infrastructure.replenishment_artifacts import CheckpointFiles
    from product_search.infrastructure.replenishment_cli import private_json
    from product_search.infrastructure.replenishment_repository import PostgresReplenishment
    from product_search.infrastructure.replenishment_runtime_binding import (
        FreshGrant,
        MacResourceObserver,
        RecordingResourceObserver,
        canonical,
        record_command_failure,
        verify_code_inventory,
        verify_frozen_inputs,
    )
    from product_search.infrastructure.replenishment_workers import (
        NativeStageDriver,
        ProcessStageWorkers,
    )
    from product_search.search.replenishment_contracts import ExecutionPackage

    package = ExecutionPackage(**config["package"])
    grant = FreshGrant(config["grant_path"])
    if not grant.authorize_build(package):
        raise ReplenishmentError("CLAIM_MISMATCH")
    binding = private_json(config["binding_path"])
    if hashlib.sha256(canonical(binding)).hexdigest() != package.runtime_sha:
        raise ReplenishmentError("RUNTIME_MISMATCH")
    verify_code_inventory(config["code_inventory_path"], package.code_sha)
    profile = private_json(config["profile_path"])
    if hashlib.sha256(canonical(profile)).hexdigest() != package.semantic_profile_sha:
        raise ReplenishmentError("PROFILE_MISMATCH")
    verify_frozen_inputs(config["input_inventory_path"], binding, package)
    defer = binding.get("defer_region_limit", False)
    if type(defer) is not bool:
        raise ReplenishmentError("RUNTIME_MISMATCH")
    if (
        defer
        and "src/product_search/infrastructure/replenishment_deferred_photos.py"
        not in private_json(config["code_inventory_path"])
    ):
        raise ReplenishmentError("RUNTIME_MISMATCH")
    deferred_inventory = None
    if defer:
        deferred_inventory = private_json(config["input_inventory_path"])
        if hashlib.sha256(canonical(deferred_inventory)).hexdigest() != binding.get(
            "deferred_inventory_sha256"
        ):
            raise ReplenishmentError("RUNTIME_MISMATCH")
    root = Path(binding["shared_runtime_root"])
    private_root = Path(config["private_root"])
    end = time.monotonic() + package.overall_seconds
    target = RuntimeTarget(config["target_descriptor_path"], binding["target_policy"])
    state = SimpleNamespace(workers=None, driver=None, observer=None, initial=True)
    clock = SimpleNamespace(monotonic=time.monotonic)
    coordinator = FileLease(root, "coordinator.lock")
    if not coordinator.try_acquire():
        raise ReplenishmentError("BUSY")
    app = None
    operation_log = None
    recording = None
    confirmed = False
    try:
        from product_search.infrastructure.replenishment_operation_log import OperationLog

        operation_log = OperationLog(Path(binding.get("operation_log_root", root)))
        operation_log.emit("host", "before", pid=os.getpid())

        def repository_factory(pkg, requested_end):
            limit = min(end, requested_end)
            repository = PostgresReplenishment(
                lambda: target.connect(pkg, limit),
                pkg,
                limit,
                clock=time.monotonic,
                authorize_transaction=lambda: grant.check_authorization(pkg),
            )
            if binding.get("load_diagnostics") is True:
                repository.commit_checkpoint = recording.recorder.wrap(
                    "checkpoint", repository.commit_checkpoint
                )
            repository.commit_checkpoint = operation_log.wrap(
                "checkpoint", repository.commit_checkpoint
            )
            repository.finish_photo = operation_log.wrap("photo_outcome", repository.finish_photo)
            repository.publish_revision = operation_log.wrap(
                "publication", repository.publish_revision
            )
            return repository

        def owned_worker():
            return state.driver.owned_worker() if state.driver else None

        state.observer = MacResourceObserver(
            package, controller_pid=os.getpid(), owned_worker=owned_worker
        )
        state.observer.worker_rss_ceiling = lambda: binding["resource_limits"][
            "i_rss_bytes"
            if state.driver and state.driver.control["stage_key"] == "localization"
            else "encoder_rss_bytes"
        ]

        recording = RecordingResourceObserver(
            state.observer,
            private_root / "resource-observations.jsonl",
            max_bytes=package.max_wire_bytes,
            context=lambda: (
                {
                    "stage_key": state.driver.control["stage_key"],
                    "model_key": state.driver.control["model_key"],
                    "worker_pid": state.driver.child.pid if state.driver.child else None,
                }
                if state.driver and state.driver.control is not None
                else {}
            ),
        )
        if binding.get("load_diagnostics") is True:
            from product_search.infrastructure.replenishment_load_diagnostics import (
                LoadDiagnostics,
                ResourceDiagnostics,
                db_memory_sample,
                mac_process_sample,
            )

            db_sample = {"at": float("-inf"), "bytes": None}

            def diagnostic_sample():
                worker = owned_worker()
                metrics = mac_process_sample(os.getpid(), worker[0] if worker else None)
                now = time.monotonic()
                if now - db_sample["at"] >= 5:
                    db_sample["bytes"] = db_memory_sample(
                        target.path, binding["target_policy"].get("marker")
                    )
                    db_sample["at"] = time.monotonic()
                if db_sample["bytes"] is None:
                    metrics["measurement_ok"] = False
                else:
                    metrics["db_container_memory_bytes"] = db_sample["bytes"]
                    metrics["db_sample_age_seconds"] = time.monotonic() - db_sample["at"]
                return metrics

            recording = ResourceDiagnostics(
                recording,
                LoadDiagnostics(
                    private_root / "load-resources.jsonl",
                    sample=diagnostic_sample,
                    max_bytes=min(package.max_wire_bytes, 1024**2),
                    backups=2,
                ),
            )

        def quiesce(limit, stop, kill):
            return state.workers is None or state.workers.close_stage(
                state.workers.owner, min(limit, end)
            )

        def authorize_search(pkg):
            if pkg != package:
                return False
            if state.initial:
                state.initial = False
                return grant.authorize_initial_search(pkg)
            return grant.authorize_search(pkg)

        files = CheckpointFiles(config["checkpoint_root"])

        deferred = None
        if defer:
            from product_search.infrastructure.replenishment_deferred_photos import DeferredPhotos

            deferred = DeferredPhotos(private_root, deferred_inventory)

        def worker_factory(repo, owner, pkg, limit):
            driver = NativeStageDriver(
                private_root,
                grant,
                config["binding_path"],
                config["code_inventory_path"],
                config["profile_path"],
                files,
                repo,
            )
            driver.inherited_fds = (coordinator._fd,)
            state.driver = driver
            state.workers = ProcessStageWorkers(
                app.supervisor,
                grant,
                driver,
                pkg,
                owner,
                min(limit, end),
                poll_seconds=binding["policy"]["poll_seconds"],
                operation_log=operation_log,
            )
            if deferred is not None:
                deferred.attach(state.workers, repo)
            state.workers.process = operation_log.wrap("photo", state.workers.process)
            state.workers.open_stage = operation_log.wrap("stage", state.workers.open_stage)
            return state.workers

        app = LocalReplenishmentApplication(
            root,
            repository_factory,
            profile,
            files,
            worker_factory,
            clock,
            authorize_build=lambda pkg: pkg == package and grant.authorize_build(pkg),
            claim_build=grant.consume,
            authorize_search=authorize_search,
            observe=recording,
            quiesce=quiesce,
            summary_reader=lambda run, mode: app.repository.read_summary(run, search_state=mode),
        )
        if binding.get("load_diagnostics") is True:
            app._admit_resources = recording.recorder.wrap("admission", app._admit_resources)
        app._start = operation_log.wrap("batch", app._start)
        app.poll_resources = lambda cutoff: time.sleep(
            min(binding["policy"]["poll_seconds"], max(0, cutoff - time.monotonic()))
        )
        app.initialize_search(package)
        serve_owner(
            app,
            root,
            package,
            end_at=end,
            max_commands=config["max_commands"],
            timeout_seconds=config["timeout_seconds"],
            max_bytes=config["max_bytes"],
            on_error=lambda error: record_command_failure(
                private_root, error, max_bytes=config["max_bytes"]
            ),
        )
        confirmed = app.supervisor.mode == "CLOSED"
    except Exception as error:
        if operation_log is not None:
            operation_log.error("host", error)
        raise
    finally:
        if app is not None and app.supervisor.mode != "CLOSED":
            try:
                app.supervisor.close(
                    end_at=end,
                    stop_grace=package.stop_grace_seconds,
                    kill_wait=package.kill_wait_seconds,
                )
                confirmed = True
            except ReplenishmentError:
                pass  # Retain coordinator ownership while any handle remains unconfirmed.
        if recording is not None:
            recording.close()
        if operation_log is not None:
            operation_log.emit("host", "after", cleanup_confirmed=confirmed)
            operation_log.close()
        if app is None or confirmed:
            coordinator.release()
