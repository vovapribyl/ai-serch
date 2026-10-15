import hashlib
from concurrent.futures import Future
from threading import Event

import pytest

from product_search.infrastructure.nail_query_runner import NailExecutionContext, NailQueryRunner
from product_search.search.nail_contracts import (
    EmbeddingProfile,
    NailCandidate,
    NailProcessingError,
    NailSearchResult,
    PairMatch,
    SearchProfile,
)

PROFILE = SearchProfile(
    "a" * 64,
    EmbeddingProfile((("openclip_b32", "r1"), ("dinov2_b14", "r2"), ("siglip2_b16_224", "r3"))),
    10000,
)


class Service:
    def __init__(self, entered=None, finish=None):
        self.entered, self.finish = entered, finish

    def execute_many(self, request):
        if self.entered:
            self.entered.set()
            assert self.finish.wait(timeout=5)
        match = PairMatch(
            1,
            "catalog-photo",
            (1,),
            tuple((key, 0.8) for key, _ in PROFILE.embedding_profile.revisions),
            0.8,
        )
        return NailSearchResult(
            request.representation_id,
            "OK",
            (NailCandidate(2, match),),
            (),
            PROFILE.representation_fingerprint,
        )


class Images:
    def __init__(self):
        self.cleaned = ()

    def import_source(self, root, path, limit):
        data = path.read_bytes()
        return "b" * 32, hashlib.sha256(data).hexdigest()

    def cleanup(self, refs):
        self.cleaned = refs


@pytest.fixture
def runner_parts(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir(mode=0o700)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    path = inputs / "fake.png"
    path.write_bytes(b"synthetic")
    path.chmod(0o600)
    return inputs, runtime, path


def test_runner_translates_plain_result_and_releases_owned_inputs(runner_parts):
    inputs, runtime, path = runner_parts
    images = Images()
    runner = NailQueryRunner(
        Service(),
        images,
        lambda pinned: NailExecutionContext(pinned or "rep", 1, PROFILE),
        inputs,
        runtime,
        1000,
    )
    try:
        future = runner.start(
            [path], expected_checksums=(hashlib.sha256(path.read_bytes()).hexdigest(),)
        )
        assert isinstance(future, Future)
        result = future.result(timeout=5)
        assert result.candidates[0]["candidate_id"] == 2
        assert result.candidates[0]["score"] == 0.8 and "rrf_score" not in result.candidates[0]
        assert result.search_payload["schema_version"] == 1
        assert (
            result.search_payload["input_photos"][0]["sha256"]
            == hashlib.sha256(b"synthetic").hexdigest()
        )
        assert images.cleaned == ("b" * 32,)
    finally:
        runner.close()


def test_admission_and_cancel_never_release_running_worker_early(runner_parts):
    inputs, runtime, path = runner_parts
    entered, finish = Event(), Event()
    runner = NailQueryRunner(
        Service(entered, finish),
        Images(),
        lambda pinned: NailExecutionContext("rep", 1, PROFILE),
        inputs,
        runtime,
        1000,
    )
    try:
        future = runner.start([path])
        assert isinstance(future, Future)
        assert entered.wait(timeout=5)
        assert future.cancel() is False
        with pytest.raises(NailProcessingError, match="BUSY"):
            runner.start([path])
        finish.set()
        assert future.result(timeout=5).status == "OK"
    finally:
        finish.set()
        runner.close()


def test_pinned_representation_or_changed_source_rejected_before_service(runner_parts):
    inputs, runtime, path = runner_parts
    runner = NailQueryRunner(
        Service(),
        Images(),
        lambda pinned: NailExecutionContext("other", 1, PROFILE),
        inputs,
        runtime,
        1000,
    )
    try:
        future = runner.start([path], representation_id="rep")
        assert isinstance(future, Future)
        with pytest.raises(NailProcessingError, match="PROFILE_MISMATCH"):
            future.result(timeout=5)
        future = runner.start([path], expected_checksums=("c" * 64,))
        assert isinstance(future, Future)
        with pytest.raises(NailProcessingError, match="PROFILE_MISMATCH"):
            future.result(timeout=5)
    finally:
        runner.close()
