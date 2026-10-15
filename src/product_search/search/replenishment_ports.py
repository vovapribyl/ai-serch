"""Policy-owned output ports; implementations belong to infrastructure."""

from collections.abc import Iterable
from typing import Protocol

from .nail_contracts import CatalogProduct


class Clock(Protocol):
    def monotonic(self) -> float: ...


from .replenishment_contracts import (
    CheckpointReceipt,
    ExecutionPackage,
    Ownership,
    PhotoOutcome,
    PhotoWork,
    SavedCheckpoint,
    SnapshotDescriptor,
    SnapshotEmbeddingProfile,
    StageAttempt,
    StageOutput,
)


class Progress(Protocol):
    def lookup_checkpoint(
        self, photo: PhotoWork, stage: str, model: str, owner: Ownership
    ) -> SavedCheckpoint | None: ...

    def begin_attempt(
        self, photo: PhotoWork, stage: str, model: str, owner: Ownership
    ) -> StageAttempt: ...

    def commit_checkpoint(
        self, attempt: StageAttempt, output: StageOutput, owner: Ownership
    ) -> CheckpointReceipt: ...

    def fail_attempt(self, attempt: StageAttempt, owner: Ownership) -> None: ...

    def finish_photo(self, photo: PhotoWork, outcome: PhotoOutcome, owner: Ownership) -> None: ...

    def revision_outcomes(self, revision_ref: str) -> tuple[PhotoOutcome, ...]: ...


class Artifacts(Protocol):
    def verify_saved(
        self, attempt: StageAttempt, output: StageOutput, package: ExecutionPackage
    ) -> None: ...

    def verify(
        self, attempt: StageAttempt, output: StageOutput, package: ExecutionPackage
    ) -> None: ...


class StageWorkers(Protocol):
    def open_stage(
        self, stage: str, model: str, owner: Ownership, package: ExecutionPackage, end_at: float
    ) -> None: ...

    def process(
        self, photo: PhotoWork, attempt: StageAttempt, owner: Ownership, end_at: float
    ) -> StageOutput: ...

    def close_stage(self, owner: Ownership, end_at: float) -> bool: ...


class SnapshotCatalogPort(Protocol):
    def read_snapshot_profile(self, descriptor: SnapshotDescriptor) -> SnapshotEmbeddingProfile: ...

    def read_snapshot(self, descriptor: SnapshotDescriptor) -> Iterable[CatalogProduct]: ...
