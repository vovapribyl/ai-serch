"""External admission/executor/clock/files; core remains plain and synchronous."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from types import SimpleNamespace

from product_search.search.nail_contracts import (
    NailProcessingError,
    PhotoInput,
    SearchProfile,
    SearchRequest,
)

from .nail_runtime import FileLease, validate_runtime_root


@dataclass(frozen=True)
class NailExecutionContext:
    representation_id: str
    corpus_version_id: int
    verified_runtime: SearchProfile


class NailQueryRunner:
    search_mode = "nail-search-v1"

    def __init__(
        self, service, images, context_factory, input_root, runtime_root, source_bytes_limit
    ):
        if type(source_bytes_limit) is not int or source_bytes_limit <= 0:
            raise NailProcessingError("RESOURCE_LIMIT")
        self.service, self.images, self.context_factory = service, images, context_factory
        self.input_root = validate_runtime_root(input_root)
        self.runtime_root = validate_runtime_root(runtime_root)
        self.source_bytes_limit = source_bytes_limit
        self._admission = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nail-query")

    def start(self, paths, *, representation_id=None, expected_checksums=None):
        if not self._admission.acquire(blocking=False):
            raise NailProcessingError("BUSY")
        try:
            future = self._executor.submit(
                self._execute, tuple(paths), representation_id, expected_checksums
            )
        except RuntimeError:
            self._admission.release()
            raise NailProcessingError("MODEL_NOT_READY") from None
        # Cancellation before execution owns no native work; running work releases in finally.
        future.add_done_callback(lambda f: self._admission.release() if f.cancelled() else None)
        return future

    def _execute(self, paths, representation_id, expected_checksums):
        refs = []
        lease = FileLease(self.runtime_root, "coordinator.lock")
        started = monotonic()
        try:
            if not lease.try_acquire():
                raise NailProcessingError("BUSY")
            context = self.context_factory(representation_id)
            if (
                not isinstance(context, NailExecutionContext)
                or not isinstance(context.verified_runtime, SearchProfile)
                or type(context.corpus_version_id) is not int
                or context.corpus_version_id < 1
                or (
                    representation_id is not None and context.representation_id != representation_id
                )
            ):
                raise NailProcessingError("PROFILE_MISMATCH")
            if not 1 <= len(paths) <= 4 or (
                expected_checksums is not None and len(expected_checksums) != len(paths)
            ):
                raise NailProcessingError("INVALID_REQUEST")
            photos = []
            for ordinal, path in enumerate(paths, 1):
                ref, checksum = self.images.import_source(
                    self.input_root, path, self.source_bytes_limit
                )
                refs.append(ref)
                if expected_checksums is not None and checksum != expected_checksums[ordinal - 1]:
                    raise NailProcessingError("PROFILE_MISMATCH")
                photos.append(PhotoInput(ordinal, ref, checksum))
            result = self.service.execute_many(
                SearchRequest(tuple(photos), context.representation_id, context.verified_runtime)
            )
            candidates = []
            diagnostics = []
            for rank, candidate in enumerate(result.candidates, 1):
                match = candidate.match
                candidates.append(
                    {
                        "candidate_id": candidate.product_record_id,
                        "rank": rank,
                        "score": match.score,
                        "score_kind": result.score_kind,
                        "display_photo_ordinal": match.query_photo_ordinal,
                    }
                )
                diagnostics.append(
                    {
                        "candidate_id": candidate.product_record_id,
                        "rank": rank,
                        "score": match.score,
                        "query_photo_ordinal": match.query_photo_ordinal,
                        "catalog_photo_id": match.catalog_photo_id,
                        "pairs": list(match.pairs),
                        "missing_regions": [i for i, j in enumerate(match.pairs, 1) if j is None],
                        "per_model_pair_scores": dict(match.per_model_pair_scores),
                    }
                )
            revisions = dict(context.verified_runtime.embedding_profile.revisions)
            payload = {
                "schema_version": 1,
                "fingerprint": result.representation_fingerprint,
                "input_photos": [
                    {
                        "ordinal": p.photo_ordinal,
                        "sha256": p.input_sha256,
                        "status": "NO_NAILS"
                        if p.photo_ordinal in result.skipped_photo_ordinals
                        else "OK",
                    }
                    for p in photos
                ],
                "model_revisions": revisions,
                "profile": {
                    "score_kind": result.score_kind,
                    "max_solver_states": context.verified_runtime.max_solver_states,
                },
                "candidates": diagnostics,
            }
            return SimpleNamespace(
                status=result.status,
                candidates=candidates,
                corpus_version_id=context.corpus_version_id,
                representation_id=result.representation_id,
                representation_fingerprint=result.representation_fingerprint,
                model_keys=list(revisions),
                model_revisions=revisions,
                search_mode=self.search_mode,
                score_kind=result.score_kind,
                search_payload=payload,
                search_duration_ms=int((monotonic() - started) * 1000),
            )
        finally:
            try:
                if refs:
                    self.images.cleanup(tuple(refs))
            finally:
                lease.release()
                self._admission.release()

    def close(self):
        self._executor.shutdown(wait=True, cancel_futures=False)
