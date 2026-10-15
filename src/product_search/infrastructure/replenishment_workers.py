"""Owned stage-process adapter; controller remains the sole database writer."""

import math
import threading
import time

from product_search.infrastructure.replenishment_supervisor import OwnedProcesses
from product_search.search.nail_contracts import MODEL_DIMENSIONS
from product_search.search.replenishment_contracts import ReplenishmentError, ResourceObservation


class ProcessStageWorkers:
    def __init__(
        self,
        supervisor,
        grant,
        driver,
        package,
        owner,
        end_at,
        *,
        poll_seconds=0.5,
        clock=time.monotonic,
        operation_log=None,
    ):
        if (
            type(poll_seconds) not in (int, float)
            or not math.isfinite(poll_seconds)
            or not 0 < poll_seconds < package.observation_max_age_seconds
        ):
            raise ReplenishmentError("INVALID_PACKAGE")
        self.supervisor, self.grant, self.driver = supervisor, grant, driver
        self.package, self.owner, self.end_at = package, owner, end_at
        self.clock, self.poll_seconds = clock, poll_seconds
        self.child = self.registry = self.stage = self.thread = None
        self._stop = threading.Event()
        self._registry_lock = threading.Lock()
        self.reason = None
        self.operation_log = operation_log
        self._exit_recorded = False
        self._termination_requested = False

    def _record_exit(self, expected):
        if self.child is None or self._exit_recorded:
            return
        code = self.child.poll()
        if code is None:
            return
        self._exit_recorded = True
        if self.operation_log is not None:
            self.operation_log.emit(
                "worker",
                "exit",
                pid=self.child.pid,
                returncode=code,
                signal=-code if code < 0 else 0,
                expected=expected,
                stage_key=self.stage[0],
                model_key=self.stage[1],
                run_ref=self.owner.run_ref,
                error_code=self.reason or "UNKNOWN",
            )

    def _stop_registry(self, end_at):
        self._record_exit(self._termination_requested)
        if self.child is not None and self.child.poll() is None:
            self._termination_requested = True
        try:
            return self.registry.stop(
                end_at, self.package.stop_grace_seconds, self.package.kill_wait_seconds
            )
        finally:
            # Preserve stop intent even if physical-exit verification raises.
            self._record_exit(self._termination_requested)

    def _owner(self, owner):
        if owner != self.owner:
            raise ReplenishmentError("FENCED")
        self.grant.check_owner(owner, self.package)

    def _observe(self):
        try:
            observation = self.supervisor.observe()
            now = self.clock()
            if (
                not isinstance(observation, ResourceObservation)
                or observation.status not in {"OK", "WARNING"}
                or type(observation.observed_at) not in (int, float)
                or not math.isfinite(observation.observed_at)
                or not 0
                <= now - observation.observed_at
                <= self.package.observation_max_age_seconds
            ):
                raise ValueError
        except Exception:  # noqa: BLE001 -- invalid observation is a terminal hard STOP.
            self.reason = "RESOURCE_STOP"
            self.supervisor.require_recovery()
            raise ReplenishmentError(self.reason) from None

    def _monitor(self):
        while not self._stop.wait(self.poll_seconds):
            try:
                self._owner(self.owner)
                self._observe()
                if self.clock() >= self.end_at - self.package.cleanup_reserve_seconds:
                    raise ReplenishmentError("DEADLINE")
            except Exception as error:  # noqa: BLE001 -- guardian failure closes admission and stops only its registry.
                self.reason = (
                    "RESOURCE_STOP"
                    if self.reason
                    else (
                        str(error) if isinstance(error, ReplenishmentError) else "RECOVERY_REQUIRED"
                    )
                )
                self.supervisor.require_recovery()
                with self._registry_lock:
                    self._stop_registry(self.end_at)
                return

    def open_stage(self, stage, model, owner, package, end_at):
        self._owner(owner)
        if self.registry is not None:
            raise ReplenishmentError("BUSY")
        if self.reason:
            raise ReplenishmentError(self.reason)
        if package != self.package or (stage, model) not in (
            ("localization", ""),
            *(("embedding", key) for key, _ in MODEL_DIMENSIONS),
        ):
            raise ReplenishmentError("INVALID_PACKAGE")
        end_at = min(end_at, self.end_at - package.cleanup_reserve_seconds)
        if not self.clock() < end_at:
            raise ReplenishmentError("DEADLINE")
        argv = self.driver.command(stage, model, owner, package, end_at, self.supervisor.lease.fd)
        self.registry = OwnedProcesses(
            self.supervisor.lease,
            validate_argv=lambda candidate: candidate == argv,
            max_children=1,
            clock=self.clock,
            extra_fds=getattr(self.driver, "inherited_fds", ()),
        )
        self.stage = (stage, model)
        self._exit_recorded = False
        self._termination_requested = False
        if self.operation_log is not None:
            self.operation_log.emit(
                "stage", "before", stage_key=stage, model_key=model, run_ref=owner.run_ref
            )
        self._stop.clear()
        self.child = self.supervisor.launch_build_child(self.registry, argv, package)
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()
        self.driver.ready(self.child, min(end_at, self.clock() + package.http_seconds))
        if self.reason:
            raise ReplenishmentError(self.reason)
        self._observe()
        if self.operation_log is not None:
            self.operation_log.emit(
                "stage",
                "after",
                stage_key=stage,
                model_key=model,
                pid=self.child.pid,
                run_ref=owner.run_ref,
            )

    def process(self, photo, attempt, owner, end_at):
        self._owner(owner)
        if self.reason:
            raise ReplenishmentError(self.reason)
        if (
            self.registry is None
            or self.child.poll() is not None
            or (attempt.stage_key, attempt.model_key) != self.stage
            or (
                attempt.photo_ref,
                attempt.revision_ref,
                attempt.head_version,
                attempt.revision_version,
            )
            != (photo.photo_ref, photo.revision_ref, photo.head_version, photo.revision_version)
        ):
            raise ReplenishmentError("ATTEMPT_MISMATCH")
        operation_end = min(end_at, self.clock() + self.package.http_seconds)
        if not self.clock() < operation_end <= self.end_at - self.package.cleanup_reserve_seconds:
            raise ReplenishmentError("DEADLINE")
        self._observe()
        output = self.driver.exchange(photo, attempt, operation_end)
        if self.reason:
            raise ReplenishmentError(self.reason)
        if self.clock() >= operation_end:
            raise ReplenishmentError("DEADLINE")
        self._observe()
        self._owner(owner)
        return output

    def close_stage(self, owner, end_at):
        # Cleanup cannot depend on an unexpired claim: revoked/expired runs must stop.
        if owner != self.owner:
            raise ReplenishmentError("FENCED")
        if self.registry is None:
            return True
        # End sampling before intentional termination removes the live sample.
        # The registry still owns bounded TERM/KILL and physical-exit checks.
        self._stop.set()
        if self.thread is not None:
            self.thread.join(timeout=self.package.observation_max_age_seconds)
        with self._registry_lock:
            confirmed = self._stop_registry(min(end_at, self.end_at))
        if not confirmed or (self.thread is not None and self.thread.is_alive()):
            self.supervisor.require_recovery()
            return False
        closed = getattr(self.driver, "closed", None)
        if closed is not None:
            closed()
        self.child = self.registry = self.stage = self.thread = None
        return True


def localization_files(processed):
    import io

    from PIL import Image

    payload = {}
    for region in processed.regions:
        for kind, mode, image in (("crop", "RGB", region.rgb_crop), ("mask", "L", region.mask)):
            buffer = io.BytesIO()
            with Image.frombytes(mode, (image.width, image.height), image.pixels) as png:
                png.save(buffer, format="PNG")
            payload[f"{kind}-{region.ordinal}.png"] = buffer.getvalue()
    return payload


def encode_checkpoint(saved, attempt, package, files, embedding, profile):
    import io

    from PIL import Image

    from product_search.infrastructure.replenishment_runtime_binding import canonical
    from product_search.search.nail_contracts import RgbImage

    if (
        (saved.attempt.stage_key, saved.attempt.model_key) != ("localization", "")
        or saved.attempt.photo_ref != attempt.photo_ref
        or saved.attempt.revision_ref != attempt.revision_ref
        or saved.output.region_count <= 0
        or saved.receipt.attempt_ref != saved.attempt.attempt_ref
        or saved.receipt.manifest_sha != saved.output.manifest_sha
        or attempt.stage_key != "embedding"
    ):
        raise ReplenishmentError("CHECKPOINT_INVALID")
    payload = files.read_files(saved.attempt, saved.output, package)
    crops = []
    for ordinal in range(1, saved.output.region_count + 1):
        with Image.open(io.BytesIO(payload[f"crop-{ordinal}.png"])) as image:
            crops.append(RgbImage(image.width, image.height, image.tobytes()))
    vectors = embedding.encode(attempt.model_key, tuple(crops), profile)
    output = {
        "model_key": attempt.model_key,
        "vectors": [{"ordinal": i, "values": list(values)} for i, values in enumerate(vectors, 1)],
    }
    return files.write_staging(attempt, package, len(crops), {"vectors.json": canonical(output)})


class NativeStageDriver:
    """One persistent child per stage; I retains the approved HTTP contract."""

    def __init__(self, root, grant, binding_path, code_path, profile_path, files, repository):
        from pathlib import Path

        self.root, self.grant = Path(root), grant
        self.binding_path, self.code_path, self.profile_path = map(
            Path, (binding_path, code_path, profile_path)
        )
        self.files, self.repository = files, repository
        self.control = self.child = None
        self.job_number = 0

    def command(self, stage, model, owner, package, end_at, lease_fd):
        import hashlib
        import secrets
        from dataclasses import asdict
        from pathlib import Path

        from product_search.infrastructure.nail_build_composition import publish_private_json
        from product_search.infrastructure.nail_runtime import validate_runtime_root
        from product_search.infrastructure.replenishment_cli import private_json
        from product_search.infrastructure.replenishment_runtime_binding import (
            canonical,
            verify_code_inventory,
        )

        self.grant.check_owner(owner, package)
        binding = private_json(self.binding_path)
        if hashlib.sha256(canonical(binding)).hexdigest() != package.runtime_sha:
            raise ReplenishmentError("RUNTIME_MISMATCH")
        verify_code_inventory(self.code_path, package.code_sha)
        self.binding, self.package, self.owner = binding, package, owner
        folder = validate_runtime_root(self.root) / ("stage-" + secrets.token_hex(16))
        folder.mkdir(mode=0o700)
        self.control_root = folder
        self.control = {
            "schema_version": 1,
            "package": asdict(package),
            "owner": asdict(owner),
            "stage_key": stage,
            "model_key": model,
            "grant_path": str(self.grant.path),
            "binding_path": str(self.binding_path),
            "code_inventory_path": str(self.code_path),
            "profile_path": str(self.profile_path),
            "checkpoint_root": str(self.files.root),
            "shared_runtime_root": binding["shared_runtime_root"],
            "end_at": end_at,
            "lease_fd": lease_fd,
            "coordinator_fd": getattr(self, "inherited_fds", (-1,))[0],
            "nonce": secrets.token_hex(32),
            "control_root": str(folder),
        }
        path = folder / "control.json"
        publish_private_json(path, self.control)
        interpreter = binding["interpreters"][
            "localization" if stage == "localization" else "encoder"
        ]
        entry = Path(__file__).resolve().parents[3] / "scripts/run_replenishment_worker.py"
        self.job_number = 0
        return (interpreter, "-I", "-B", str(entry), str(path))

    def closed(self):
        self.child = None

    def owned_worker(self):
        if self.child is None:
            return None
        return self.child.pid, self.control_root / "telemetry.json", self.control["nonce"]

    def _wait(self, path, end_at):
        from product_search.infrastructure.replenishment_cli import private_json

        while time.monotonic() < end_at:
            if self.child.poll() is not None:
                raise ReplenishmentError("RECOVERY_REQUIRED")
            if path.exists():
                value = private_json(path)
                if (
                    value.get("nonce") != self.control["nonce"]
                    or value.get("pid") != self.child.pid
                ):
                    raise ReplenishmentError("CLAIM_MISMATCH")
                return value
            time.sleep(min(0.02, max(0, end_at - time.monotonic())))
        raise ReplenishmentError("DEADLINE")

    def ready(self, child, end_at):
        self.child = child
        answer = self._wait(self.control_root / "ready.json", end_at)
        if answer.get("status") != "READY":
            raise ReplenishmentError("RECOVERY_REQUIRED")
        self.endpoint = answer.get("endpoint")

    def exchange(self, photo, attempt, end_at):
        from dataclasses import asdict

        from product_search.infrastructure.nail_build_composition import publish_private_json
        from product_search.search.replenishment_contracts import StageOutput

        if attempt.stage_key == "localization":
            from product_search.infrastructure.nail_build_runner import SourceImageDecodeError
            from product_search.search.nail_contracts import NailProcessingError
            from product_search.search.replenishment_contracts import PhotoProcessingError

            try:
                return self._localize(photo, attempt, end_at)
            except SourceImageDecodeError:
                raise PhotoProcessingError("INVALID_IMAGE") from None
            except NailProcessingError as error:
                if error.code == "PROFILE_MISMATCH":
                    raise ReplenishmentError("PROFILE_MISMATCH") from None
                if error.reason is not None or error.code == "BUSY":
                    raise ReplenishmentError("RECOVERY_REQUIRED") from None
                raise PhotoProcessingError(error.code) from None
        saved = self.repository.lookup_checkpoint(photo, "localization", "", self.owner)
        if saved is None:
            raise ReplenishmentError("CHECKPOINT_INVALID")
        self.files.verify_saved(saved.attempt, saved.output, self.package)
        self.job_number += 1
        number = self.job_number
        publish_private_json(
            self.control_root / f"job-{number}.json",
            {
                "nonce": self.control["nonce"],
                "attempt": asdict(attempt),
                "saved": asdict(saved),
                "end_at": end_at,
            },
        )
        answer = self._wait(self.control_root / f"result-{number}.json", end_at)
        if answer.get("attempt_ref") != attempt.attempt_ref:
            raise ReplenishmentError("ATTEMPT_MISMATCH")
        if answer.get("status") != "OK":
            from product_search.search.replenishment_contracts import PhotoProcessingError

            raise PhotoProcessingError("MODEL_ERROR")
        return StageOutput(**answer["output"])

    def _localize(self, photo, attempt, end_at):
        import hashlib

        from product_search.infrastructure.nail_build_runner import ManifestImageStore
        from product_search.infrastructure.nail_ml_adapters import (
            ClientSettings,
            HttpNailLocalizationAdapter,
        )
        from product_search.infrastructure.nail_wire import WireLimits
        from product_search.search.nail_contracts import (
            DecodeProfile,
            LocalizationProfile,
            PhotoInput,
        )
        from product_search.search.nail_image_processor import NailImageProcessor

        source = self.repository.read_stage_source(attempt, self.owner)
        if source.source_bytes != photo.source_bytes:
            raise ReplenishmentError("INPUT_MISMATCH")
        alias = hashlib.sha256(source.source_ref.encode()).hexdigest()[:32]
        images = ManifestImageStore(
            self.binding["frozen_input_root"], {alias: source.source_ref}, None
        )
        remaining = min(self.package.http_seconds, end_at - time.monotonic())
        if remaining <= 0:
            raise ReplenishmentError("DEADLINE")
        adapter = HttpNailLocalizationAdapter(
            ClientSettings(
                self.endpoint,
                min(1, remaining),
                remaining,
                remaining,
                remaining,
                WireLimits(
                    self.package.max_pixels, self.package.max_regions, self.package.max_wire_bytes
                ),
            )
        )
        processor = NailImageProcessor(
            images,
            adapter,
            DecodeProfile(self.package.max_source_bytes, self.package.max_pixels),
            LocalizationProfile(self.binding["extractor_fingerprint"]),
            self.package.max_regions,
        )
        processed = processor.process(PhotoInput(source.ordinal, alias, source.input_sha))
        return self.files.write_staging(
            attempt, self.package, len(processed.regions), localization_files(processed)
        )
