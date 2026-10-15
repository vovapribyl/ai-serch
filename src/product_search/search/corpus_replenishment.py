"""Application policy for finite corpus replenishment runs."""

import math

from .replenishment_contracts import (
    BuildResult,
    CheckpointReceipt,
    ExecutionPackage,
    ExecutionWindow,
    Ownership,
    PhotoOutcome,
    PhotoProcessingError,
    PhotoWork,
    ReplenishmentError,
    ResourceObservation,
    SavedCheckpoint,
    StageAttempt,
    StageOutput,
)
from .replenishment_ports import Artifacts, Clock, Progress, StageWorkers


def select_batch(queue: tuple[PhotoWork, ...], package: ExecutionPackage) -> tuple[PhotoWork, ...]:
    if type(queue) is not tuple:
        raise ReplenishmentError("INVALID_INVENTORY")
    seen = set()
    pending = []
    for photo in queue:
        if (
            not isinstance(photo, PhotoWork)
            or type(photo.photo_ref) is not str
            or not photo.photo_ref
            or type(photo.revision_ref) is not str
            or not photo.revision_ref
            or photo.photo_ref in seen
            or not isinstance(photo.outcome, PhotoOutcome)
        ):
            raise ReplenishmentError("INVALID_INVENTORY")
        seen.add(photo.photo_ref)
        if photo.outcome == PhotoOutcome.RUNNING:
            raise ReplenishmentError("RECOVERY_REQUIRED")
        if photo.outcome == PhotoOutcome.PENDING:
            if photo.semantic_profile_sha != package.semantic_profile_sha:
                raise ReplenishmentError("PROFILE_MISMATCH")
            if (
                type(photo.source_bytes) is not int
                or not 0 < photo.source_bytes <= package.max_source_bytes
            ):
                raise ReplenishmentError("INPUT_LIMIT")
            pending.append(photo)
    return tuple(pending[:5])


def product_readiness(outcomes: tuple[PhotoOutcome, ...]) -> str:
    if type(outcomes) is not tuple or any(not isinstance(o, PhotoOutcome) for o in outcomes):
        raise ReplenishmentError("INVALID_OUTCOME")
    terminal = {PhotoOutcome.OK, PhotoOutcome.NO_NAILS, PhotoOutcome.ERROR}
    if not outcomes or any(o not in terminal for o in outcomes):
        return "WAITING"
    return "READY" if PhotoOutcome.OK in outcomes else "NOT_PUBLISHABLE"


def retry_photo_outcomes(outcomes: tuple[PhotoOutcome, ...], selected: int):
    """Only the explicitly selected ERROR becomes pending in a new revision."""
    if type(selected) is not int or not 0 <= selected < len(outcomes):
        raise ReplenishmentError("INVALID_INPUT")
    if outcomes[selected] != PhotoOutcome.ERROR:
        raise ReplenishmentError("INVALID_SCOPE")
    if any(o == PhotoOutcome.RUNNING for o in outcomes):
        raise ReplenishmentError("RECOVERY_REQUIRED")
    return tuple(PhotoOutcome.PENDING if i == selected else o for i, o in enumerate(outcomes))


class ReplenishmentController:
    def __init__(
        self, progress: Progress, artifacts: Artifacts, workers: StageWorkers, clock: Clock
    ):
        self.progress = progress
        self.artifacts = artifacts
        self.workers = workers
        self.clock = clock

    def run(
        self,
        queue: tuple[PhotoWork, ...],
        package: ExecutionPackage,
        owner: Ownership,
        *,
        started_at=None,
        admission=None,
    ) -> BuildResult:
        if package.scope not in {"START", "RESUME", "RETRY_PHOTO"}:
            raise ReplenishmentError("INVALID_SCOPE")
        if (
            not isinstance(owner, Ownership)
            or type(owner.run_ref) is not str
            or not owner.run_ref
            or type(owner.owner_token) is not str
            or not owner.owner_token
            or type(owner.epoch) is not int
            or owner.epoch <= 0
        ):
            raise ReplenishmentError("INVALID_OWNERSHIP")
        selected = select_batch(queue, package)
        window = ExecutionWindow(
            package, self.clock, self.clock.monotonic() if started_at is None else started_at
        )
        end_at = window.started_at + package.overall_seconds
        outcomes = {p.photo_ref: p.outcome for p in selected}
        admissions = 0
        reason = "COMPLETED"
        stages = (
            ("localization", ""),
            ("embedding", "openclip_b32"),
            ("embedding", "dinov2_b14"),
            ("embedding", "siglip2_b16_224"),
        )
        saved = {}
        lookup = getattr(self.progress, "lookup_checkpoint", None)
        if package.scope == "RESUME" and lookup is None:
            raise ReplenishmentError("CHECKPOINT_INVALID")
        if lookup is not None:
            for photo in selected:
                for stage, model in stages:
                    if not window.can_start(package.db_seconds):
                        return BuildResult(
                            tuple(p.photo_ref for p in selected),
                            tuple(outcomes.items()),
                            (),
                            "DEADLINE",
                        )
                    checkpoint = lookup(photo, stage, model, owner)
                    if checkpoint is None:
                        continue
                    if (
                        not isinstance(checkpoint, SavedCheckpoint)
                        or (
                            checkpoint.attempt.photo_ref,
                            checkpoint.attempt.revision_ref,
                            checkpoint.attempt.stage_key,
                            checkpoint.attempt.model_key,
                        )
                        != (photo.photo_ref, photo.revision_ref, stage, model)
                        or checkpoint.receipt.attempt_ref != checkpoint.attempt.attempt_ref
                        or checkpoint.receipt.manifest_sha != checkpoint.output.manifest_sha
                    ):
                        raise ReplenishmentError("CHECKPOINT_INVALID")
                    self.artifacts.verify_saved(checkpoint.attempt, checkpoint.output, package)
                    saved[(photo.photo_ref, stage, model)] = checkpoint
            for photo in selected:
                local = saved.get((photo.photo_ref, "localization", ""))
                if local is not None and local.output.region_count == 0:
                    self.progress.finish_photo(photo, PhotoOutcome.NO_NAILS, owner)
                    outcomes[photo.photo_ref] = PhotoOutcome.NO_NAILS
                elif all((photo.photo_ref, stage, model) in saved for stage, model in stages):
                    self.progress.finish_photo(photo, PhotoOutcome.OK, owner)
                    outcomes[photo.photo_ref] = PhotoOutcome.OK
        for stage, model in stages:
            active = tuple(
                p
                for p in selected
                if outcomes[p.photo_ref] == PhotoOutcome.PENDING
                and (p.photo_ref, stage, model) not in saved
            )
            if not active:
                continue
            if admissions >= package.max_admissions:
                reason = "ADMISSION_LIMIT"
                break
            if not window.can_start(package.http_seconds):
                reason = "DEADLINE"
                break
            if admission is not None:
                admission(package.http_seconds)
            admissions += 1
            try:
                self.workers.open_stage(
                    stage, model, owner, package, end_at - package.cleanup_reserve_seconds
                )
                for photo in active:
                    if admissions >= package.max_admissions:
                        reason = "ADMISSION_LIMIT"
                        break
                    if not window.can_start(package.http_seconds):
                        reason = "DEADLINE"
                        break
                    if admission is not None:
                        admission(package.http_seconds)
                    attempt = self.progress.begin_attempt(photo, stage, model, owner)
                    if (
                        not isinstance(attempt, StageAttempt)
                        or type(attempt.attempt_ref) is not str
                        or not attempt.attempt_ref
                        or attempt.revision_ref != photo.revision_ref
                        or (attempt.head_version, attempt.revision_version)
                        != (photo.head_version, photo.revision_version)
                        or type(attempt.expected_version) is not int
                        or attempt.expected_version <= 0
                        or (attempt.photo_ref, attempt.stage_key, attempt.model_key)
                        != (photo.photo_ref, stage, model)
                    ):
                        raise ReplenishmentError("ATTEMPT_MISMATCH")
                    admissions += 1
                    try:
                        output = self.workers.process(
                            photo, attempt, owner, end_at - package.cleanup_reserve_seconds
                        )
                    except PhotoProcessingError:
                        self.progress.fail_attempt(attempt, owner)
                        self.progress.finish_photo(photo, PhotoOutcome.ERROR, owner)
                        outcomes[photo.photo_ref] = PhotoOutcome.ERROR
                        continue
                    if (
                        not isinstance(output, StageOutput)
                        or type(output.region_count) is not int
                        or not 0 <= output.region_count <= package.max_regions
                        or (stage == "embedding" and output.region_count == 0)
                    ):
                        self.progress.fail_attempt(attempt, owner)
                        self.progress.finish_photo(photo, PhotoOutcome.ERROR, owner)
                        outcomes[photo.photo_ref] = PhotoOutcome.ERROR
                        continue
                    if not window.can_start(package.db_seconds):
                        reason = "DEADLINE"
                        break
                    self.artifacts.verify(attempt, output, package)
                    if not window.can_start(package.db_seconds):
                        reason = "DEADLINE"
                        break
                    if admission is not None:
                        admission(package.db_seconds)
                    receipt = self.progress.commit_checkpoint(attempt, output, owner)
                    if (
                        not isinstance(receipt, CheckpointReceipt)
                        or receipt.attempt_ref != attempt.attempt_ref
                        or receipt.manifest_sha != output.manifest_sha
                    ):
                        raise ReplenishmentError("CHECKPOINT_UNKNOWN")
                    if stage == "localization" and output.region_count == 0:
                        outcome = PhotoOutcome.NO_NAILS
                    elif model == "siglip2_b16_224":
                        outcome = PhotoOutcome.OK
                    else:
                        continue
                    if not window.can_start(package.db_seconds):
                        reason = "DEADLINE"
                        break
                    self.progress.finish_photo(photo, outcome, owner)
                    outcomes[photo.photo_ref] = outcome
            finally:
                if self.workers.close_stage(owner, end_at) is not True:
                    raise ReplenishmentError("RECOVERY_REQUIRED")
            if reason != "COMPLETED":
                break
        if reason == "COMPLETED" and not window.can_start(package.db_seconds):
            reason = "DEADLINE"
        if reason == "COMPLETED" and admission is not None:
            admission(package.db_seconds)
        revisions = (
            tuple(dict.fromkeys(p.revision_ref for p in selected)) if reason == "COMPLETED" else ()
        )
        ready = tuple(
            r for r in revisions if product_readiness(self.progress.revision_outcomes(r)) == "READY"
        )
        return BuildResult(
            tuple(p.photo_ref for p in selected), tuple(outcomes.items()), ready, reason
        )


class ResourceWait:
    """A warning episode is bounded; only consecutive fresh samples restore admission."""

    def __init__(self, package, end_at, clock):
        self.package, self.end_at, self.clock = package, end_at, clock
        self.reason = None
        self.wait_started = self.stable_since = None
        self.last_now = clock.monotonic()

    def admit(self, observation, operation_seconds):
        if self.reason:
            return False
        now = self.clock.monotonic()
        try:
            valid = (
                isinstance(observation, ResourceObservation)
                and type(observation.status) is str
                and observation.status in {"OK", "WARNING"}
                and all(
                    type(v) in (int, float) and math.isfinite(v)
                    for v in (
                        now,
                        self.last_now,
                        observation.observed_at,
                        operation_seconds,
                        self.end_at,
                    )
                )
                and now >= self.last_now
                and operation_seconds > 0
                and 0 <= now - observation.observed_at <= self.package.observation_max_age_seconds
            )
        except (TypeError, OverflowError):
            valid = False
        if not valid:
            self.reason = "RESOURCE_STOP"
            return False
        gap = now - self.last_now
        self.last_now = now
        cutoff = self.end_at - self.package.cleanup_reserve_seconds
        if now >= cutoff:
            self.reason = "DEADLINE"
            return False
        if self.wait_started is not None and now >= self.wait_started + 300:
            self.reason = "WAIT_TIMEOUT"
            return False
        if observation.status == "WARNING":
            if self.wait_started is None:
                self.wait_started = now
            self.stable_since = None
            return False
        if self.wait_started is not None:
            if self.stable_since is None or gap > self.package.observation_max_age_seconds:
                self.stable_since = now
            if now - self.stable_since < 30:
                return False
            self.wait_started = self.stable_since = None
        if now + operation_seconds >= cutoff:
            self.reason = "DEADLINE"
            return False
        return True
