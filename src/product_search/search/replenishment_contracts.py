"""Application-owned immutable DTOs; validation follows tests."""

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .replenishment_ports import Clock


class ReplenishmentError(ValueError):
    pass


class PhotoOutcome(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    OK = "OK"
    NO_NAILS = "NO_NAILS"
    ERROR = "ERROR"


class StageState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True)
class ExecutionPackage:
    schema_version: int
    input_set_sha: str
    semantic_profile_sha: str
    code_sha: str
    model_sha: str
    runtime_sha: str
    claims_sha: str
    scope: str
    overall_seconds: float
    http_seconds: float
    db_seconds: float
    stop_grace_seconds: float
    kill_wait_seconds: float
    cleanup_reserve_seconds: float
    max_source_bytes: int
    max_pixels: int
    max_regions: int
    max_wire_bytes: int
    max_vector_bytes: int
    max_admissions: int
    rss_ceiling_bytes: int
    mps_ceiling_bytes: int
    observation_max_age_seconds: float

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ReplenishmentError("INVALID_PACKAGE")
        if type(self.scope) is not str or self.scope not in {
            "START",
            "RESUME",
            "RETRY_PHOTO",
            "RETRY_PUBLICATION",
        }:
            raise ReplenishmentError("INVALID_PACKAGE")
        for name in (
            "input_set_sha",
            "semantic_profile_sha",
            "code_sha",
            "model_sha",
            "runtime_sha",
            "claims_sha",
        ):
            value = getattr(self, name)
            if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
                raise ReplenishmentError("INVALID_PACKAGE")
        for name in (
            "overall_seconds",
            "http_seconds",
            "db_seconds",
            "stop_grace_seconds",
            "kill_wait_seconds",
            "cleanup_reserve_seconds",
            "observation_max_age_seconds",
        ):
            value = getattr(self, name)
            try:
                valid = type(value) in (int, float) and math.isfinite(value) and value > 0
            except OverflowError:
                valid = False
            if not valid:
                raise ReplenishmentError("INVALID_PACKAGE")
        for name in (
            "max_source_bytes",
            "max_pixels",
            "max_regions",
            "max_wire_bytes",
            "max_vector_bytes",
            "max_admissions",
            "rss_ceiling_bytes",
            "mps_ceiling_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ReplenishmentError("INVALID_PACKAGE")
        usable = self.overall_seconds - self.cleanup_reserve_seconds
        if (
            usable <= 0
            or self.cleanup_reserve_seconds < self.stop_grace_seconds + self.kill_wait_seconds
            or self.http_seconds > usable
            or self.db_seconds > usable
        ):
            raise ReplenishmentError("INVALID_PACKAGE")


@dataclass(frozen=True)
class ExecutionWindow:
    package: ExecutionPackage
    clock: "Clock"
    started_at: float

    def can_start(self, operation_seconds: float) -> bool:
        now = self.clock.monotonic()
        for value in (now, self.started_at, operation_seconds):
            try:
                if type(value) not in (int, float) or not math.isfinite(value):
                    return False
            except OverflowError:
                return False
        return (
            operation_seconds > 0
            and now >= self.started_at
            and now + operation_seconds
            < self.started_at + self.package.overall_seconds - self.package.cleanup_reserve_seconds
        )


@dataclass(frozen=True)
class PhotoWork:
    photo_ref: str
    revision_ref: str
    semantic_profile_sha: str
    source_bytes: int
    outcome: PhotoOutcome
    head_version: int
    revision_version: int


class PhotoProcessingError(ReplenishmentError):
    """A known photo failure; infrastructure failures must not use this type."""


@dataclass(frozen=True)
class Ownership:
    run_ref: str
    owner_token: str
    epoch: int


@dataclass(frozen=True)
class StageAttempt:
    attempt_ref: str
    photo_ref: str
    stage_key: str
    model_key: str
    identity_sha: str
    revision_ref: str
    head_version: int
    revision_version: int
    expected_version: int


@dataclass(frozen=True)
class StageOutput:
    artifact_ref: str
    manifest_sha: str
    region_count: int


@dataclass(frozen=True)
class CheckpointReceipt:
    attempt_ref: str
    manifest_sha: str


@dataclass(frozen=True)
class BuildResult:
    selected_photo_refs: tuple[str, ...]
    outcomes: tuple[tuple[str, PhotoOutcome], ...]
    ready_revision_refs: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ResourceObservation:
    status: str
    observed_at: float


@dataclass(frozen=True)
class SelectedPhoto:
    ordinal: int
    source_ref: str
    input_sha: str
    source_bytes: int


@dataclass(frozen=True)
class SelectedProduct:
    corpus_version_id: int
    product_record_id: int
    expected_head_version: int
    photos: tuple[SelectedPhoto, ...]


@dataclass(frozen=True)
class RevisionReference:
    revision_ref: str
    head_version: int
    revision_version: int


@dataclass(frozen=True)
class PublicationReceipt:
    attempt_ref: str
    revision_ref: str
    snapshot_ref: str | None
    state: str
    error_code: str | None = None


def _digest_identity(value):
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
        raise ReplenishmentError("PROFILE_MISMATCH")


def _snapshot_ref(value):
    if type(value) is not str or not re.fullmatch(
        "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value
    ):
        raise ReplenishmentError("INVALID_SNAPSHOT")


@dataclass(frozen=True)
class SnapshotDescriptor:
    snapshot_ref: str
    content_sha: str
    semantic_profile_sha: str

    def __post_init__(self):
        _snapshot_ref(self.snapshot_ref)
        _digest_identity(self.content_sha)
        _digest_identity(self.semantic_profile_sha)


@dataclass(frozen=True)
class SnapshotEmbeddingProfile:
    crop_version: str
    models: tuple[tuple[str, int, str, str, str], ...]

    def __post_init__(self):
        from .nail_contracts import MODEL_DIMENSIONS

        if (
            type(self.crop_version) is not str
            or not self.crop_version
            or type(self.models) is not tuple
            or len(self.models) != 3
            or any(type(m) is not tuple or len(m) != 5 for m in self.models)
            or tuple((m[0], m[1]) for m in self.models) != MODEL_DIMENSIONS
            or any(
                type(m[1]) is not int
                or type(m[2]) is not str
                or not m[2]
                or type(m[3]) is not str
                or not m[3]
                or m[4] != "float32"
                for m in self.models
            )
        ):
            raise ReplenishmentError("PROFILE_MISMATCH")


@dataclass(frozen=True)
class SnapshotRuntimeIdentity:
    runtime_sha: str
    code_sha: str
    model_sha: str
    extractor_sha: str
    mode: str
    embedding_profile: SnapshotEmbeddingProfile

    def __post_init__(self):
        for value in (self.runtime_sha, self.code_sha, self.model_sha, self.extractor_sha):
            _digest_identity(value)
        if self.mode not in ("fake", "native") or not isinstance(
            self.embedding_profile, SnapshotEmbeddingProfile
        ):
            raise ReplenishmentError("RUNTIME_MISMATCH")


@dataclass(frozen=True)
class SnapshotQueryClaim:
    snapshot_refs: tuple[str, ...]
    inputs: tuple[tuple[int, str], ...]
    runtime_sha: str
    semantic_profile_sha: str
    scope: str

    def __post_init__(self):
        _digest_identity(self.runtime_sha)
        _digest_identity(self.semantic_profile_sha)
        if (
            self.scope != "QUERY"
            or type(self.snapshot_refs) is not tuple
            or not self.snapshot_refs
            or type(self.inputs) is not tuple
            or not 1 <= len(self.inputs) <= 4
            or any(type(p) is not tuple or len(p) != 2 for p in self.inputs)
            or tuple(p[0] for p in self.inputs) != tuple(range(1, len(self.inputs) + 1))
            or any(type(p[0]) is not int for p in self.inputs)
        ):
            raise ReplenishmentError("CLAIM_MISMATCH")
        for ref in self.snapshot_refs:
            _snapshot_ref(ref)
        for _, checksum in self.inputs:
            _digest_identity(checksum)
        if len(set(self.snapshot_refs)) != len(self.snapshot_refs) or len(
            {p[1] for p in self.inputs}
        ) != len(self.inputs):
            raise ReplenishmentError("CLAIM_MISMATCH")


@dataclass(frozen=True)
class VerifiedCatalogBinding:
    descriptor: SnapshotDescriptor
    profile: SnapshotEmbeddingProfile
    runtime: SnapshotRuntimeIdentity
    claim: SnapshotQueryClaim
    max_solver_states: int

    def __post_init__(self):
        if (
            not isinstance(self.descriptor, SnapshotDescriptor)
            or not isinstance(self.profile, SnapshotEmbeddingProfile)
            or not isinstance(self.runtime, SnapshotRuntimeIdentity)
            or not isinstance(self.claim, SnapshotQueryClaim)
            or self.runtime.embedding_profile != self.profile
            or self.runtime.runtime_sha != self.claim.runtime_sha
            or self.descriptor.semantic_profile_sha != self.claim.semantic_profile_sha
            or self.descriptor.snapshot_ref not in self.claim.snapshot_refs
            or type(self.max_solver_states) is not int
            or self.max_solver_states <= 0
        ):
            raise ReplenishmentError("BINDING_MISMATCH")


@dataclass(frozen=True)
class SnapshotSearchRequest:
    photos: tuple
    binding: VerifiedCatalogBinding

    def __post_init__(self):
        from .nail_contracts import PhotoInput

        if (
            not isinstance(self.binding, VerifiedCatalogBinding)
            or type(self.photos) is not tuple
            or any(not isinstance(p, PhotoInput) for p in self.photos)
            or tuple((p.photo_ordinal, p.input_sha256) for p in self.photos)
            != self.binding.claim.inputs
        ):
            raise ReplenishmentError("CLAIM_MISMATCH")


@dataclass(frozen=True)
class SnapshotSearchResult:
    descriptor: SnapshotDescriptor
    status: str
    candidates: tuple
    skipped_photo_ordinals: tuple[int, ...]
    score_kind: str = "nail_assignment_mean_v1"


@dataclass(frozen=True)
class SavedCheckpoint:
    attempt: StageAttempt
    output: StageOutput
    receipt: CheckpointReceipt
