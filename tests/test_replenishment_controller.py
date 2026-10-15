"""Stage events are observable side effects of orchestration, not a fake's own API."""

import pytest

from product_search.search.corpus_replenishment import ReplenishmentController
from product_search.search.replenishment_contracts import (
    CheckpointReceipt,
    Ownership,
    PhotoOutcome,
    PhotoProcessingError,
    ReplenishmentError,
    StageAttempt,
    StageOutput,
)
from tests.test_replenishment_boundaries import Clock
from tests.test_replenishment_contracts import package
from tests.test_replenishment_rules import photo


class Progress:
    def __init__(self, queue, events):
        self.queue = queue
        self.events = events
        self.outcomes = {p.photo_ref: p.outcome for p in queue}
        self.checkpoints = {}

    def begin_attempt(self, photo, stage, model, owner):
        assert owner == Ownership("run-1", "token-1", 1)
        return StageAttempt(
            f"{photo.photo_ref}/{stage}/{model}",
            photo.photo_ref,
            stage,
            model,
            "f" * 64,
            photo.revision_ref,
            photo.head_version,
            photo.revision_version,
            1,
        )

    def commit_checkpoint(self, attempt, output, owner):
        self.events.append(("commit", attempt.photo_ref, attempt.stage_key, attempt.model_key))
        self.checkpoints[attempt.attempt_ref] = output
        return CheckpointReceipt(attempt.attempt_ref, output.manifest_sha)

    def fail_attempt(self, attempt, owner):
        self.events.append(
            ("attempt-error", attempt.photo_ref, attempt.stage_key, attempt.model_key)
        )

    def finish_photo(self, photo, outcome, owner):
        self.events.append(("finish", photo.photo_ref, outcome))
        self.outcomes[photo.photo_ref] = outcome

    def revision_outcomes(self, revision_ref):
        return tuple(
            self.outcomes[p.photo_ref] for p in self.queue if p.revision_ref == revision_ref
        )


class Artifacts:
    def __init__(self, events):
        self.events = events
        self.fail = False

    def verify(self, attempt, output, package):
        self.events.append(("verify", attempt.photo_ref, attempt.stage_key, attempt.model_key))
        if self.fail:
            raise ReplenishmentError("STORE_UNAVAILABLE")


class Workers:
    def __init__(self, events, progress):
        self.events = events
        self.progress = progress
        self.current = None
        self.no_nails = set()
        self.fail = set()
        self.exit_confirmed = True

    def open_stage(self, stage, model, owner, package, end_at):
        assert self.current is None, "ML stages overlapped"
        self.current = (stage, model)
        self.events.append(("open", stage, model))

    def process(self, photo, attempt, owner, end_at):
        self.events.append(("process", photo.photo_ref, *self.current))
        if attempt.stage_key == "embedding":
            assert f"{photo.photo_ref}/localization/" in self.progress.checkpoints
        if (photo.photo_ref, *self.current) in self.fail:
            raise PhotoProcessingError("known bad photo")
        return StageOutput(
            "opaque-artifact", "a" * 64, 0 if photo.photo_ref in self.no_nails else 1
        )

    def close_stage(self, owner, end_at):
        self.events.append(("close", *self.current))
        self.current = None
        return self.exit_confirmed


def setup(queue):
    events = []
    progress = Progress(queue, events)
    artifacts = Artifacts(events)
    workers = Workers(events, progress)
    controller = ReplenishmentController(progress, artifacts, workers, Clock(10))
    return controller, progress, artifacts, workers, events


def run(controller, queue, **changes):
    return controller.run(
        queue, package(max_admissions=100, **changes), Ownership("run-1", "token-1", 1)
    )


def test_stages_are_sequential_and_checkpoints_precede_success():
    queue = (photo(0), photo(1))
    controller, progress, _, _, events = setup(queue)
    result = run(controller, queue)
    assert result.reason == "COMPLETED"
    assert result.ready_revision_refs == ("revision-1",)
    assert list(progress.outcomes.values()) == [PhotoOutcome.OK, PhotoOutcome.OK]
    assert [e for e in events if e[0] == "open"] == [
        ("open", "localization", ""),
        ("open", "embedding", "openclip_b32"),
        ("open", "embedding", "dinov2_b14"),
        ("open", "embedding", "siglip2_b16_224"),
    ]
    for p in queue:
        last_commit = events.index(("commit", p.photo_ref, "embedding", "siglip2_b16_224"))
        assert last_commit < events.index(("finish", p.photo_ref, PhotoOutcome.OK))
    for i, e in enumerate(events):
        if e[0] == "commit":
            assert events[i - 1] == ("verify", *e[1:])
    for i, e in enumerate(events):
        if e[0] == "open" and e[1] == "embedding":
            assert events[i - 1][0] == "close"


def test_no_nails_and_photo_errors_skip_encoders_and_other_photo_continues():
    queue = (photo(0), photo(1), photo(2))
    controller, progress, _, workers, events = setup(queue)
    workers.no_nails.add("photo-0")
    workers.fail.add(("photo-1", "localization", ""))
    result = run(controller, queue)
    assert result.outcomes == (
        ("photo-0", PhotoOutcome.NO_NAILS),
        ("photo-1", PhotoOutcome.ERROR),
        ("photo-2", PhotoOutcome.OK),
    )
    assert [e[1] for e in events if e[0] == "process" and e[2] == "embedding"] == ["photo-2"] * 3
    assert len(progress.checkpoints) == 5
    assert ("attempt-error", "photo-1", "localization", "") in events


def test_seven_selected_photos_do_not_publish_or_start_another_batch():
    queue = tuple(photo(i) for i in range(7))
    controller, progress, _, _, events = setup(queue)
    result = run(controller, queue)
    assert result.selected_photo_refs == tuple(f"photo-{i}" for i in range(5))
    assert result.ready_revision_refs == ()
    assert progress.outcomes["photo-5"] == PhotoOutcome.PENDING
    assert progress.outcomes["photo-6"] == PhotoOutcome.PENDING
    assert len([e for e in events if e[0] == "open"]) == 4


def test_global_store_failure_stops_run_without_marking_photo_success():
    queue = (photo(0), photo(1))
    controller, progress, artifacts, _, events = setup(queue)
    artifacts.fail = True
    with pytest.raises(ReplenishmentError, match="STORE_UNAVAILABLE"):
        run(controller, queue)
    assert not progress.checkpoints
    assert list(progress.outcomes.values()) == [PhotoOutcome.PENDING] * 2
    assert events[-1] == ("close", "localization", "")


def test_unconfirmed_worker_exit_blocks_next_model():
    queue = (photo(0),)
    controller, _, _, workers, events = setup(queue)
    workers.exit_confirmed = False
    with pytest.raises(ReplenishmentError, match="RECOVERY_REQUIRED"):
        run(controller, queue)
    assert [e for e in events if e[0] == "open"] == [("open", "localization", "")]


def test_publication_only_package_cannot_start_ml_processing():
    queue = (photo(0),)
    controller, _, _, _, events = setup(queue)
    with pytest.raises(ReplenishmentError, match="INVALID_SCOPE"):
        run(controller, queue, scope="RETRY_PUBLICATION")
    assert events == []


def test_lost_checkpoint_confirmation_prevents_next_stage():
    queue = (photo(0),)
    controller, progress, _, _, events = setup(queue)
    original = progress.commit_checkpoint

    def lost_receipt(attempt, output, owner):
        original(attempt, output, owner)

    progress.commit_checkpoint = lost_receipt
    with pytest.raises(ReplenishmentError, match="CHECKPOINT_UNKNOWN"):
        run(controller, queue)
    assert progress.outcomes["photo-0"] == PhotoOutcome.PENDING
    assert events[-1] == ("close", "localization", "")
    assert len([e for e in events if e[0] == "open"]) == 1


def test_admission_budget_stops_work_and_preserves_pending_photo():
    queue = (photo(0),)
    controller, progress, _, _, events = setup(queue)
    result = controller.run(queue, package(max_admissions=1), Ownership("run-1", "token-1", 1))
    assert result.reason == "ADMISSION_LIMIT"
    assert result.outcomes == (("photo-0", PhotoOutcome.PENDING),)
    assert progress.checkpoints == {}
    assert events == [("open", "localization", ""), ("close", "localization", "")]


def test_no_work_does_not_open_a_worker():
    controller, _, _, _, events = setup(())
    assert run(controller, ()).selected_photo_refs == ()
    assert events == []


def test_deadline_during_stage_stops_next_photo_and_always_closes_worker():
    queue = (photo(0), photo(1))
    controller, progress, _, workers, events = setup(queue)
    original = workers.process

    def advance_clock(*args):
        result = original(*args)
        controller.clock.now = 70
        return result

    workers.process = advance_clock
    result = run(controller, queue)
    assert result.reason == "DEADLINE"
    assert len(progress.checkpoints) == 0
    assert events[-1] == ("close", "localization", "")
    assert not any(e[0] == "process" and e[1] == "photo-1" for e in events)


@pytest.mark.parametrize(
    "owner",
    [
        None,
        Ownership("", "token-1", 1),
        Ownership("run-1", "", 1),
        Ownership("run-1", "token-1", 0),
    ],
)
def test_missing_ownership_is_rejected_before_any_work(owner):
    queue = (photo(0),)
    controller, _, _, _, events = setup(queue)
    with pytest.raises(ReplenishmentError, match="INVALID_OWNERSHIP"):
        controller.run(queue, package(), owner)
    assert events == []


def test_result_after_deadline_is_not_committed():
    queue = (photo(0),)
    controller, progress, _, workers, _ = setup(queue)
    original = workers.process

    def late_result(*args):
        output = original(*args)
        controller.clock.now = 70
        return output

    workers.process = late_result
    result = run(controller, queue)
    assert result.reason == "DEADLINE"
    assert progress.checkpoints == {}
    assert progress.outcomes["photo-0"] == PhotoOutcome.PENDING


def test_attempt_for_another_photo_is_rejected_before_worker_process():
    queue = (photo(0),)
    controller, progress, _, _, events = setup(queue)
    progress.begin_attempt = lambda *args: StageAttempt(
        "attempt-wrong", "other-photo", "localization", "", "f" * 64, "revision-1", 1, 1, 1
    )
    with pytest.raises(ReplenishmentError, match="ATTEMPT_MISMATCH"):
        run(controller, queue)
    assert not any(e[0] == "process" for e in events)
    assert progress.checkpoints == {}


@pytest.mark.parametrize(
    "changes",
    [
        {"head_version": 2},
        {"revision_version": 2},
        {"expected_version": 0},
        {"revision_ref": "other-revision"},
    ],
)
def test_attempt_versions_must_match_current_work_before_worker_call(changes):
    from dataclasses import replace

    queue = (photo(0),)
    controller, progress, _, _, events = setup(queue)
    original = progress.begin_attempt
    progress.begin_attempt = lambda *args: replace(original(*args), **changes)
    with pytest.raises(ReplenishmentError, match="ATTEMPT_MISMATCH"):
        run(controller, queue)
    assert not any(e[0] == "process" for e in events)


def test_deadline_never_starts_a_final_read_of_revision_outcomes():
    queue = (photo(0),)
    controller, progress, _, workers, _ = setup(queue)
    original = workers.process

    def expired(*args):
        output = original(*args)
        controller.clock.now = 70
        return output

    workers.process = expired
    progress.revision_outcomes = lambda _: pytest.fail("DB read after deadline")
    result = run(controller, queue)
    assert result.reason == "DEADLINE" and result.ready_revision_refs == ()
