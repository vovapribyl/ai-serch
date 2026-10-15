"""Application orchestration and bounded ranking; no framework, storage or clock."""

from itertools import chain

from .nail_contracts import (
    MODEL_DIMENSIONS,
    CatalogProduct,
    EmbeddingProfile,
    NailCandidate,
    NailProcessingError,
    NailSearchResult,
    PhotoEmbeddings,
    ReadyCatalog,
    SearchRequest,
)
from .nail_image_processor import NailImageProcessor
from .nail_matching import match_photos
from .nail_ports import NailCatalogPort, NailEmbeddingPort
from .replenishment_contracts import SnapshotSearchRequest, SnapshotSearchResult
from .replenishment_ports import SnapshotCatalogPort


class NailSearchService:
    def __init__(
        self,
        catalog: NailCatalogPort | SnapshotCatalogPort,
        processor: NailImageProcessor,
        embedding: NailEmbeddingPort,
        *,
        catalog_backend="legacy",
    ):
        if catalog_backend not in ("legacy", "snapshot"):
            raise NailProcessingError("INVALID_REQUEST")
        self.catalog_backend = catalog_backend
        self.catalog = catalog
        self.processor = processor
        self.embedding = embedding

    def execute_snapshot(self, request):
        if self.catalog_backend != "snapshot" or not isinstance(request, SnapshotSearchRequest):
            raise NailProcessingError("INVALID_REQUEST")
        binding = request.binding
        if self.catalog.read_snapshot_profile(binding.descriptor) != binding.profile:
            raise NailProcessingError("PROFILE_MISMATCH")
        groups = iter(self.catalog.read_snapshot(binding.descriptor))
        try:
            first = next(groups, None)
            if first is None:
                raise NailProcessingError("INDEX_EMPTY")
            profile = EmbeddingProfile(tuple((m[0], m[2]) for m in binding.profile.models))
            status, candidates, skipped = self._rank(
                request.photos, chain((first,), groups), profile, binding.max_solver_states
            )
            return SnapshotSearchResult(binding.descriptor, status, candidates, skipped)
        finally:
            close = getattr(groups, "close", None)
            if close is not None:
                close()

    def execute(self, photo, representation_id, verified_runtime):
        return self.execute_many(SearchRequest((photo,), representation_id, verified_runtime))

    def execute_many(self, request):
        if self.catalog_backend != "legacy" or not isinstance(request, SearchRequest):
            raise NailProcessingError("INVALID_REQUEST")
        runtime = request.verified_runtime
        ready = self.catalog.read_ready(request.representation_id)
        if (
            not isinstance(ready, ReadyCatalog)
            or ready.representation_id != request.representation_id
            or ready.representation_fingerprint != runtime.representation_fingerprint
            or ready.embedding_profile != runtime.embedding_profile
        ):
            raise NailProcessingError("PROFILE_MISMATCH")
        if not ready.has_ok_photos:
            raise NailProcessingError("INDEX_EMPTY")
        groups = iter(self.catalog.iter_photo_groups(request.representation_id))
        try:
            first = next(groups, None)
            if first is None:
                raise NailProcessingError("INDEX_EMPTY")
            status, candidates, skipped = self._rank(
                request.photos,
                chain((first,), groups),
                runtime.embedding_profile,
                runtime.max_solver_states,
            )
            return NailSearchResult(
                request.representation_id,
                status,
                candidates,
                skipped,
                ready.representation_fingerprint,
            )
        finally:
            close = getattr(groups, "close", None)
            if close is not None:
                close()

    def _rank(self, photos, groups, profile, max_solver_states):
        query = []
        skipped = []
        for photo in photos:
            processed = self.processor.process(photo)
            if processed.status == "NO_NAILS":
                skipped.append(photo.photo_ordinal)
                continue
            crops = tuple(region.rgb_crop for region in processed.regions)
            vectors = tuple(
                (key, self.embedding.encode(key, crops, profile)) for key, _ in MODEL_DIMENSIONS
            )
            query.append(
                PhotoEmbeddings(
                    photo.photo_ordinal,
                    photo.input_sha256,
                    tuple(region.ordinal for region in processed.regions),
                    vectors,
                )
            )
        if not query:
            return "NEED_MORE_PHOTOS", (), tuple(skipped)
        top = []
        previous = None
        for product in groups:
            if (
                not isinstance(product, CatalogProduct)
                or not product.photos
                or (previous is not None and product.product_record_id <= previous)
            ):
                raise NailProcessingError("INVALID_OUTPUT")
            previous = product.product_record_id
            best = None
            for catalog_photo in product.photos:
                for query_photo in query:
                    match = match_photos(query_photo, catalog_photo, max_solver_states)
                    order = (
                        -match.score,
                        query_photo.photo_ordinal,
                        catalog_photo.embeddings.photo_ordinal,
                    )
                    if best is None or order < best[0]:
                        best = (order, match)
            top.append(NailCandidate(product.product_record_id, best[1]))
            top.sort(key=lambda candidate: (-candidate.match.score, candidate.product_record_id))
            del top[10:]
        return "OK", tuple(top), tuple(skipped)


def validate_nail_commit(expected, current, response_inputs, pinned_id, response_id):
    if (
        expected != current
        or response_inputs != expected
        or (pinned_id is not None and pinned_id != response_id)
    ):
        raise NailProcessingError("SESSION_CONFLICT")


def validate_nail_finalization(current, served, status):
    if current != served or status != "OK":
        raise NailProcessingError("STALE_RESULT")
