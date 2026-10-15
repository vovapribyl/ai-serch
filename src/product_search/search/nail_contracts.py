"""Immutable application-owned data; no HTTP, image library or model imports."""

import math
import re
from dataclasses import dataclass


class NailProcessingError(ValueError):
    def __init__(self, code: str, *, reason: str | None = None):
        self.code = code
        self.reason = reason
        super().__init__(code)


def _shape(width: int, height: int, pixels: bytes, channels: int, code: str) -> None:
    if (
        type(width) is not int
        or type(height) is not int
        or width <= 0
        or height <= 0
        or type(pixels) is not bytes
        or len(pixels) != width * height * channels
    ):
        raise NailProcessingError(code)


def _number(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class RgbImage:
    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        _shape(self.width, self.height, self.pixels, 3, "INVALID_IMAGE")


@dataclass(frozen=True)
class BinaryMask:
    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        _shape(self.width, self.height, self.pixels, 1, "INVALID_OUTPUT")
        if not any(self.pixels) or any(pixel not in (0, 255) for pixel in self.pixels):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class LocalizedRegion:
    ordinal: int
    label: str
    confidence: float
    detector_box_xyxy: tuple[float, float, float, float]
    mask: BinaryMask

    def __post_init__(self) -> None:
        box = self.detector_box_xyxy
        if (
            type(self.ordinal) is not int
            or self.ordinal < 1
            or not isinstance(self.label, str)
            or not self.label
            or not _number(self.confidence)
            or not 0 <= self.confidence <= 1
            or type(box) is not tuple
            or len(box) != 4
            or not all(_number(v) for v in box)
            or not isinstance(self.mask, BinaryMask)
        ):
            raise NailProcessingError("INVALID_OUTPUT")
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= self.mask.width and 0 <= y0 < y1 <= self.mask.height):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class NailLocalization:
    status: str
    regions: tuple[LocalizedRegion, ...]

    def __post_init__(self) -> None:
        if (
            self.status not in ("OK", "NO_NAILS")
            or type(self.regions) is not tuple
            or (self.status == "OK") != bool(self.regions)
            or any(not isinstance(region, LocalizedRegion) for region in self.regions)
            or tuple(region.ordinal for region in self.regions)
            != tuple(range(1, len(self.regions) + 1))
        ):
            raise NailProcessingError("INVALID_OUTPUT")
        keys = tuple((-r.confidence, *r.detector_box_xyxy, r.label) for r in self.regions)
        if keys != tuple(sorted(keys)):
            raise NailProcessingError("INVALID_OUTPUT")
        if self.regions and len({(r.mask.width, r.mask.height) for r in self.regions}) != 1:
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class LocalizationProfile:
    extractor_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.extractor_fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.extractor_fingerprint
        ):
            raise NailProcessingError("PROFILE_MISMATCH")


@dataclass(frozen=True)
class PhotoInput:
    photo_ordinal: int
    source_ref: str
    input_sha256: str

    def __post_init__(self):
        if (
            type(self.photo_ordinal) is not int
            or self.photo_ordinal < 1
            or not isinstance(self.source_ref, str)
            or not re.fullmatch("[0-9a-f]{32}", self.source_ref)
            or not isinstance(self.input_sha256, str)
            or not re.fullmatch("[0-9a-f]{64}", self.input_sha256)
        ):
            raise NailProcessingError("INVALID_IMAGE")


@dataclass(frozen=True)
class DecodeProfile:
    max_source_bytes: int
    max_decoded_pixels: int

    def __post_init__(self):
        if any(
            type(v) is not int or v <= 0 for v in (self.max_source_bytes, self.max_decoded_pixels)
        ):
            raise NailProcessingError("RESOURCE_LIMIT")


@dataclass(frozen=True)
class RegionCrop:
    ordinal: int
    detector_box_xyxy: tuple[float, float, float, float]
    crop_box_xyxy: tuple[int, int, int, int]
    mask: BinaryMask
    rgb_crop: RgbImage

    def __post_init__(self):
        box = self.crop_box_xyxy
        if (
            type(self.ordinal) is not int
            or self.ordinal < 1
            or not isinstance(self.mask, BinaryMask)
            or not isinstance(self.rgb_crop, RgbImage)
            or type(box) is not tuple
            or len(box) != 4
            or any(type(v) is not int for v in box)
        ):
            raise NailProcessingError("INVALID_OUTPUT")
        LocalizedRegion(self.ordinal, "nail", 0.0, self.detector_box_xyxy, self.mask)
        x0, y0, x1, y1 = box
        if (
            not 0 <= x0 < x1 <= self.mask.width
            or not 0 <= y0 < y1 <= self.mask.height
            or (x1 - x0, y1 - y0) != (self.rgb_crop.width, self.rgb_crop.height)
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class ProcessedPhoto:
    photo_ordinal: int
    input_sha256: str
    status: str
    regions: tuple[RegionCrop, ...]

    def __post_init__(self):
        _photo_identity(self.photo_ordinal, self.input_sha256)
        if (
            self.status not in ("OK", "NO_NAILS")
            or type(self.regions) is not tuple
            or (self.status == "OK") != bool(self.regions)
            or any(not isinstance(r, RegionCrop) for r in self.regions)
            or tuple(r.ordinal for r in self.regions) != tuple(range(1, len(self.regions) + 1))
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class EmbeddingProfile:
    revisions: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if (
            type(self.revisions) is not tuple
            or any(type(item) is not tuple or len(item) != 2 for item in self.revisions)
            or tuple(key for key, _ in self.revisions) != tuple(key for key, _ in MODEL_DIMENSIONS)
            or any(not isinstance(revision, str) or not revision for _, revision in self.revisions)
        ):
            raise NailProcessingError("PROFILE_MISMATCH")


@dataclass(frozen=True)
class PhotoEmbeddings:
    photo_ordinal: int
    input_sha256: str
    region_ordinals: tuple[int, ...]
    vectors: tuple[tuple[str, tuple[tuple[float, ...], ...]], ...]

    def __post_init__(self):
        _photo_identity(self.photo_ordinal, self.input_sha256)
        if (
            type(self.region_ordinals) is not tuple
            or not self.region_ordinals
            or any(type(v) is not int for v in self.region_ordinals)
            or self.region_ordinals != tuple(range(1, len(self.region_ordinals) + 1))
            or type(self.vectors) is not tuple
            or any(type(item) is not tuple or len(item) != 2 for item in self.vectors)
            or tuple(k for k, _ in self.vectors) != tuple(k for k, _ in MODEL_DIMENSIONS)
        ):
            raise NailProcessingError("INVALID_EMBEDDING")
        for (_, rows), (_, dimension) in zip(self.vectors, MODEL_DIMENSIONS):
            if (
                type(rows) is not tuple
                or len(rows) != len(self.region_ordinals)
                or any(
                    type(row) is not tuple
                    or len(row) != dimension
                    or not all(_number(v) for v in row)
                    or not any(row)
                    for row in rows
                )
            ):
                raise NailProcessingError("INVALID_EMBEDDING")


@dataclass(frozen=True)
class PairMatch:
    query_photo_ordinal: int
    catalog_photo_id: str
    pairs: tuple[int | None, ...]
    per_model_pair_scores: tuple[tuple[str, float], ...]
    score: float

    def __post_init__(self):
        if (
            type(self.query_photo_ordinal) is not int
            or self.query_photo_ordinal < 1
            or not isinstance(self.catalog_photo_id, str)
            or not self.catalog_photo_id
            or type(self.pairs) is not tuple
            or not self.pairs
            or any(v is not None and (type(v) is not int or v < 1) for v in self.pairs)
            or len([v for v in self.pairs if v is not None])
            != len({v for v in self.pairs if v is not None})
            or not _number(self.score)
            or not 0 <= self.score <= 1
            or type(self.per_model_pair_scores) is not tuple
            or any(type(item) is not tuple or len(item) != 2 for item in self.per_model_pair_scores)
            or tuple(k for k, _ in self.per_model_pair_scores)
            != tuple(k for k, _ in MODEL_DIMENSIONS)
            or any(not _number(v) or not 0 <= v <= 1 for _, v in self.per_model_pair_scores)
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class CatalogPhoto:
    photo_id: str
    embeddings: PhotoEmbeddings

    def __post_init__(self):
        if (
            not isinstance(self.photo_id, str)
            or not self.photo_id
            or not isinstance(self.embeddings, PhotoEmbeddings)
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class CatalogProduct:
    product_record_id: int
    photos: tuple[CatalogPhoto, ...]

    def __post_init__(self):
        if (
            type(self.product_record_id) is not int
            or self.product_record_id < 1
            or type(self.photos) is not tuple
            or not self.photos
            or any(not isinstance(p, CatalogPhoto) for p in self.photos)
            or len({p.photo_id for p in self.photos}) != len(self.photos)
            or tuple(p.embeddings.photo_ordinal for p in self.photos)
            != tuple(sorted({p.embeddings.photo_ordinal for p in self.photos}))
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class ReadyCatalog:
    representation_id: str
    representation_fingerprint: str
    embedding_profile: EmbeddingProfile
    has_ok_photos: bool

    def __post_init__(self):
        LocalizationProfile(self.representation_fingerprint)
        if (
            not isinstance(self.representation_id, str)
            or not self.representation_id
            or not isinstance(self.embedding_profile, EmbeddingProfile)
            or type(self.has_ok_photos) is not bool
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class NailCandidate:
    product_record_id: int
    match: PairMatch


@dataclass(frozen=True)
class NailSearchResult:
    representation_id: str
    status: str
    candidates: tuple[NailCandidate, ...]
    skipped_photo_ordinals: tuple[int, ...]
    representation_fingerprint: str
    score_kind: str = "nail_assignment_mean_v1"


MODEL_DIMENSIONS = (("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768))


@dataclass(frozen=True)
class SearchProfile:
    representation_fingerprint: str
    embedding_profile: EmbeddingProfile
    max_solver_states: int

    def __post_init__(self):
        LocalizationProfile(self.representation_fingerprint)
        if not isinstance(self.embedding_profile, EmbeddingProfile):
            raise NailProcessingError("PROFILE_MISMATCH")
        if type(self.max_solver_states) is not int or self.max_solver_states <= 0:
            raise NailProcessingError("RESOURCE_LIMIT")


@dataclass(frozen=True)
class SearchRequest:
    photos: tuple[PhotoInput, ...]
    representation_id: str
    verified_runtime: SearchProfile

    def __post_init__(self):
        if (
            type(self.photos) is not tuple
            or not 1 <= len(self.photos) <= 4
            or any(not isinstance(photo, PhotoInput) for photo in self.photos)
            or tuple(photo.photo_ordinal for photo in self.photos)
            != tuple(range(1, len(self.photos) + 1))
            or len({photo.input_sha256 for photo in self.photos}) != len(self.photos)
            or not isinstance(self.representation_id, str)
            or not self.representation_id
            or not isinstance(self.verified_runtime, SearchProfile)
        ):
            raise NailProcessingError("INVALID_REQUEST")


def _photo_identity(ordinal, checksum):
    if (
        type(ordinal) is not int
        or ordinal < 1
        or not isinstance(checksum, str)
        or not re.fullmatch("[0-9a-f]{64}", checksum)
    ):
        raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class ModelIdentity:
    model_key: str
    revision: str
    manifest_sha256: str
    dimension: int

    def __post_init__(self):
        if (
            self.model_key not in dict(MODEL_DIMENSIONS)
            or type(self.dimension) is not int
            or self.dimension != dict(MODEL_DIMENSIONS)[self.model_key]
            or not isinstance(self.revision, str)
            or not self.revision
            or not isinstance(self.manifest_sha256, str)
            or not re.fullmatch("[0-9a-f]{64}", self.manifest_sha256)
        ):
            raise NailProcessingError("PROFILE_MISMATCH")


@dataclass(frozen=True)
class BuildIdentity:
    representation_id: str
    corpus_version_id: int
    fingerprint: str
    inventory_sha256: str
    profile: tuple[tuple[str, str], ...]
    models: tuple[ModelIdentity, ...]

    def __post_init__(self):
        LocalizationProfile(self.fingerprint)
        LocalizationProfile(self.inventory_sha256)
        if (
            not isinstance(self.representation_id, str)
            or not self.representation_id
            or type(self.corpus_version_id) is not int
            or self.corpus_version_id < 1
            or type(self.models) is not tuple
            or any(not isinstance(model, ModelIdentity) for model in self.models)
            or tuple(model.model_key for model in self.models)
            != tuple(key for key, _ in MODEL_DIMENSIONS)
            or type(self.profile) is not tuple
            or any(
                type(pair) is not tuple
                or len(pair) != 2
                or any(not isinstance(v, str) for v in pair)
                for pair in self.profile
            )
            or len({k for k, _ in self.profile}) != len(self.profile)
        ):
            raise NailProcessingError("PROFILE_MISMATCH")
        object.__setattr__(self, "profile", tuple(sorted(self.profile)))


@dataclass(frozen=True)
class BuildPhoto:
    catalog_photo_id: str
    product_record_id: int
    photo: PhotoInput

    def __post_init__(self):
        if (
            not isinstance(self.catalog_photo_id, str)
            or not self.catalog_photo_id
            or type(self.product_record_id) is not int
            or self.product_record_id < 1
            or not isinstance(self.photo, PhotoInput)
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class RegionArtifacts:
    ordinal: int
    mask_ref: str
    crop_ref: str
    crop_sha256: str

    def __post_init__(self):
        if (
            type(self.ordinal) is not int
            or self.ordinal < 1
            or any(
                not isinstance(ref, str) or not re.fullmatch("[0-9a-f]{32}", ref)
                for ref in (self.mask_ref, self.crop_ref)
            )
            or not isinstance(self.crop_sha256, str)
            or not re.fullmatch("[0-9a-f]{64}", self.crop_sha256)
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class BuildPhotoResult:
    representation_id: str
    catalog_photo_id: str
    photo: ProcessedPhoto | None
    embeddings: PhotoEmbeddings | None
    artifacts: tuple[RegionArtifacts, ...]
    error_code: str | None = None

    def __post_init__(self):
        if (
            any(
                not isinstance(value, str) or not value
                for value in (self.representation_id, self.catalog_photo_id)
            )
            or (self.photo is not None and not isinstance(self.photo, ProcessedPhoto))
            or (self.embeddings is not None and not isinstance(self.embeddings, PhotoEmbeddings))
            or type(self.artifacts) is not tuple
            or any(not isinstance(a, RegionArtifacts) for a in self.artifacts)
            or (
                self.error_code is not None
                and (not isinstance(self.error_code, str) or not self.error_code)
            )
            or (self.photo is None and self.error_code is None)
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class BuildSummary:
    representation_id: str
    status: str
    total_photos: int
    ok_photos: int
    no_nails_photos: int
    error_photos: int
    pending_photos: int
    complete: bool
    uncovered_product_ids: tuple[int, ...]

    def __post_init__(self):
        counts = (self.ok_photos, self.no_nails_photos, self.error_photos, self.pending_photos)
        if (
            self.status not in ("BUILDING", "READY", "FAILED")
            or any(type(v) is not int or v < 0 for v in (self.total_photos, *counts))
            or sum(counts) != self.total_photos
            or type(self.complete) is not bool
            or (self.complete and (self.ok_photos == 0 or self.error_photos or self.pending_photos))
            or type(self.uncovered_product_ids) is not tuple
            or any(type(v) is not int or v < 1 for v in self.uncovered_product_ids)
            or self.uncovered_product_ids != tuple(sorted(set(self.uncovered_product_ids)))
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class StoredPhotoState:
    item: BuildPhoto
    status: str
    error_code: str | None
    artifacts: tuple[RegionArtifacts, ...]

    def __post_init__(self):
        if (
            not isinstance(self.item, BuildPhoto)
            or self.status not in ("PENDING", "OK", "NO_NAILS", "ERROR")
            or type(self.artifacts) is not tuple
            or any(not isinstance(a, RegionArtifacts) for a in self.artifacts)
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class EvaluationPhoto:
    ordinal: int
    sha256: str

    def __post_init__(self):
        _photo_identity(self.ordinal, self.sha256)


@dataclass(frozen=True)
class EvaluationCandidate:
    product_record_id: int
    rank: int
    score: float

    def __post_init__(self):
        if (
            type(self.product_record_id) is not int
            or self.product_record_id < 1
            or type(self.rank) is not int
            or not 1 <= self.rank <= 10
            or not _number(self.score)
            or not 0 <= self.score <= 1
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class EvaluationAnnotation:
    product_record_id: int
    relation: str
    variant_reason: str | None

    def __post_init__(self):
        if (
            type(self.product_record_id) is not int
            or self.product_record_id < 1
            or self.relation not in ("SAME_PRODUCT", "VARIANT", "UNRELATED", "NOT_REVIEWED")
            or (
                self.relation == "VARIANT"
                and (not isinstance(self.variant_reason, str) or not self.variant_reason)
            )
            or (self.relation != "VARIANT" and self.variant_reason is not None)
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class EvaluationRun:
    model_revisions: tuple[tuple[str, str], ...]
    search_payload: bytes

    def __post_init__(self):
        EmbeddingProfile(self.model_revisions)
        if type(self.search_payload) is not bytes or not self.search_payload:
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class EvaluationBundle:
    example_id: str
    query_ref: str
    query_sha256: str
    created_at: str
    expires_at: str
    corpus_version_id: int
    representation_id: str
    representation_fingerprint: str
    model_keys: tuple[str, ...]
    search_duration_ms: int
    query_outcome: str
    candidates: tuple[EvaluationCandidate, ...]
    annotations: tuple[EvaluationAnnotation, ...]
    photos: tuple[EvaluationPhoto, ...]
    runs: tuple[EvaluationRun, ...]

    def __post_init__(self):
        LocalizationProfile(self.representation_fingerprint)
        _photo_identity(1, self.query_sha256)
        if (
            any(
                not isinstance(v, str) or not v
                for v in (
                    self.example_id,
                    self.query_ref,
                    self.created_at,
                    self.expires_at,
                    self.representation_id,
                )
            )
            or type(self.corpus_version_id) is not int
            or self.corpus_version_id < 1
            or self.model_keys != tuple(key for key, _ in MODEL_DIMENSIONS)
            or type(self.model_keys) is not tuple
            or type(self.search_duration_ms) is not int
            or self.search_duration_ms < 0
            or self.query_outcome not in ("SAME_PRODUCT", "NEW", "UNCERTAIN")
        ):
            raise NailProcessingError("INVALID_OUTPUT")
        groups = (
            (self.candidates, EvaluationCandidate),
            (self.annotations, EvaluationAnnotation),
            (self.photos, EvaluationPhoto),
            (self.runs, EvaluationRun),
        )
        if (
            any(
                type(items) is not tuple or any(not isinstance(item, kind) for item in items)
                for items, kind in groups
            )
            or not 1 <= len(self.photos) <= 4
            or not 1 <= len(self.candidates) <= 10
            or not self.runs
            or tuple(p.ordinal for p in self.photos) != tuple(range(1, len(self.photos) + 1))
            or self.photos[0].sha256 != self.query_sha256
            or tuple(c.rank for c in self.candidates) != tuple(range(1, len(self.candidates) + 1))
            or len({c.product_record_id for c in self.candidates}) != len(self.candidates)
            or len(self.annotations) != len(self.candidates)
            or {a.product_record_id for a in self.annotations}
            != {c.product_record_id for c in self.candidates}
        ):
            raise NailProcessingError("INVALID_OUTPUT")
        relations = {a.relation for a in self.annotations}
        if (
            (self.query_outcome == "SAME_PRODUCT" and "SAME_PRODUCT" not in relations)
            or (
                self.query_outcome == "NEW"
                and ("SAME_PRODUCT" in relations or "NOT_REVIEWED" in relations)
            )
            or (self.query_outcome == "UNCERTAIN" and "SAME_PRODUCT" in relations)
        ):
            raise NailProcessingError("INVALID_OUTPUT")


@dataclass(frozen=True)
class SavedEvaluation:
    example_id: str
