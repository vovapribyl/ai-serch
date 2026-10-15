"""Application-owned roles; only immutable plain data crosses the boundary."""

from collections.abc import Iterable
from typing import Protocol

from .nail_contracts import (
    BuildIdentity,
    BuildPhoto,
    BuildPhotoResult,
    BuildSummary,
    CatalogProduct,
    DecodeProfile,
    EmbeddingProfile,
    EvaluationBundle,
    LocalizationProfile,
    NailLocalization,
    PhotoInput,
    ProcessedPhoto,
    ReadyCatalog,
    RegionArtifacts,
    RgbImage,
    SavedEvaluation,
    StoredPhotoState,
)


class NailLocalizationPort(Protocol):
    def localize(self, image: RgbImage, profile: LocalizationProfile) -> NailLocalization: ...


class NailImageStorePort(Protocol):
    def read_rgb(self, photo: PhotoInput, profile: DecodeProfile) -> RgbImage: ...
    def write_derivatives(self, build_id: str, photo: ProcessedPhoto) -> tuple[str, ...]: ...
    def write_region_artifacts(
        self, build_id: str, photo: ProcessedPhoto
    ) -> tuple[RegionArtifacts, ...]: ...
    def verify_artifacts(
        self, build_id: str, artifacts: tuple[RegionArtifacts, ...], profile: DecodeProfile
    ) -> None: ...
    def cleanup(self, refs: tuple[str, ...]) -> None: ...
    def cleanup_orphans(self, build_id: str, keep_refs: tuple[str, ...]) -> int: ...


class NailEmbeddingPort(Protocol):
    def encode(
        self, model_key: str, crops: tuple[RgbImage, ...], profile: EmbeddingProfile
    ) -> tuple[tuple[float, ...], ...]: ...


class NailCatalogPort(Protocol):
    def read_ready(self, representation_id: str) -> ReadyCatalog: ...
    def iter_photo_groups(self, representation_id: str) -> Iterable[CatalogProduct]: ...
    def begin_build(self, identity: BuildIdentity, inventory: tuple[BuildPhoto, ...]) -> None: ...
    def write_photo_outcome(self, outcome: BuildPhotoResult) -> None: ...
    def read_build_identity(self, representation_id: str) -> BuildIdentity: ...
    def read_photo_states(self, representation_id: str) -> tuple[StoredPhotoState, ...]: ...
    def read_build_summary(self, representation_id: str) -> BuildSummary: ...
    def publish(self, representation_id: str, expected_active_id: str | None) -> bool: ...


class NailEvaluationPort(Protocol):
    def save_finalized(self, bundle: EvaluationBundle) -> SavedEvaluation: ...
