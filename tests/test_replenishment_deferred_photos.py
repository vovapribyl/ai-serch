"""Deferred source identities survive photo failure without ML, SQL or retries."""

import json
from types import SimpleNamespace

import pytest

from product_search.search.replenishment_contracts import (
    PhotoProcessingError,
    ReplenishmentError,
    SelectedPhoto,
)
from tests.test_replenishment_controller import run, setup
from tests.test_replenishment_rules import photo


def inventory():
    return {
        "products": [
            {
                "product_record_id": 1,
                "photos": [
                    {"ordinal": 1, "source_ref": "frozen.jpg", "input_sha": "a" * 64},
                ],
            }
        ],
        "source_records": [
            {
                "input_sha256": "a" * 64,
                "source_ref": "original.jpg",
                "source_item": {"product_record_id": 117, "catalog_photo_id": "original-photo-id"},
            }
        ],
    }


def wire(tmp_path, workers, source=None, inputs=None):
    from product_search.infrastructure.replenishment_deferred_photos import DeferredPhotos

    tmp_path.chmod(0o700)
    repository = SimpleNamespace(
        read_stage_source=lambda *args: source or SelectedPhoto(1, "frozen.jpg", "a" * 64, 100)
    )
    return DeferredPhotos(tmp_path, inputs or inventory()).attach(workers, repository)


def test_limit_photo_is_saved_before_failure_and_following_photo_completes(tmp_path):
    queue = tuple(photo(i) for i in range(3))
    controller, progress, _, workers, events = setup(queue)
    process = workers.process

    def fail_middle(p, attempt, owner, end):
        if p.photo_ref == "photo-1":
            raise PhotoProcessingError("REGION_COUNT_LIMIT")
        return process(p, attempt, owner, end)

    workers.process = fail_middle
    path = wire(tmp_path, workers)
    assert json.loads(path.read_text())["photos"] == []
    result = run(controller, queue)
    assert result.reason == "COMPLETED"
    assert list(progress.outcomes.values()) == ["OK", "ERROR", "OK"]
    row = json.loads(path.read_text())["photos"][0]
    assert row == {
        "product_record_id": 117,
        "source_photo_id": "original-photo-id",
        "source_ref": "original.jpg",
        "input_sha": "a" * 64,
        "runtime_source_ref": "frozen.jpg",
        "photo_ref": "photo-1",
        "run_ref": "run-1",
        "attempt_ref": "photo-1/localization/",
        "reason": "REGION_COUNT_LIMIT",
    }
    assert path.stat().st_mode & 0o777 == 0o600
    assert not any(e[:2] == ("process", "photo-1") and e[2] == "embedding" for e in events)
    assert ("process", "photo-2", "embedding", "siglip2_b16_224") in events


@pytest.mark.parametrize(
    "error", [PhotoProcessingError("MODEL_ERROR"), ReplenishmentError("RESOURCE_STOP")]
)
def test_other_errors_stop_and_are_not_deferred(tmp_path, error):
    controller, _, _, workers, _ = setup((photo(0), photo(1)))
    workers.process = lambda *args: (_ for _ in ()).throw(error)
    path = wire(tmp_path, workers)
    with pytest.raises(ReplenishmentError):
        run(controller, (photo(0), photo(1)))
    assert json.loads(path.read_text())["photos"] == []


def test_write_failure_stops_before_the_next_photo(tmp_path, monkeypatch):
    from product_search.infrastructure import replenishment_deferred_photos as module

    queue = (photo(0), photo(1))
    controller, _, _, workers, events = setup(queue)
    workers.process = lambda *args: (_ for _ in ()).throw(
        PhotoProcessingError("REGION_COUNT_LIMIT")
    )
    path = wire(tmp_path, workers)
    previous = path.read_bytes()
    monkeypatch.setattr(module, "publish_private_json", lambda *a: (_ for _ in ()).throw(OSError()))
    with pytest.raises(ReplenishmentError, match="DEFERRED_PHOTOS_UNAVAILABLE"):
        run(controller, queue)
    assert path.read_bytes() == previous
    assert not any(e[:2] == ("process", "photo-1") for e in events)


def test_source_mismatch_never_records_a_wrong_identity(tmp_path):
    controller, _, _, workers, _ = setup((photo(0),))
    workers.process = lambda *args: (_ for _ in ()).throw(
        PhotoProcessingError("REGION_COUNT_LIMIT")
    )
    path = wire(tmp_path, workers, source=SelectedPhoto(1, "other.jpg", "a" * 64, 100))
    with pytest.raises(ReplenishmentError, match="DEFERRED_PHOTOS_UNAVAILABLE"):
        run(controller, (photo(0),))
    assert json.loads(path.read_text())["photos"] == []


def test_batch_report_accepts_only_accounted_limit_errors(tmp_path):
    from product_search.infrastructure.replenishment_deferred_photos import batch_summary

    snapshot = {
        "photos": [["p1", 1, 1, "sha1"], ["p2", 2, 1, "sha2"]],
        "photo_outcomes": [["p1", 1, "OK"], ["p2", 2, "ERROR"]],
    }
    deferred = {
        "schema_version": 1,
        "photos": [{"photo_ref": "p2", "input_sha": "sha2", "reason": "REGION_COUNT_LIMIT"}],
    }
    assert batch_summary(snapshot, deferred) == {
        "ready": 1,
        "deferred": 1,
        "no_nails": 0,
        "other_errors": 0,
        "pending": 0,
        "total": 2,
    }
    with pytest.raises(ReplenishmentError, match="PHOTO_NOT_DEFERRED"):
        batch_summary(snapshot, {"schema_version": 1, "photos": []})
    deferred["photos"][0]["input_sha"] = "wrong"
    with pytest.raises(ReplenishmentError):
        batch_summary(snapshot, deferred)


def test_pending_and_duplicate_outcomes_do_not_pass_batch_verification():
    from product_search.infrastructure.replenishment_deferred_photos import batch_summary

    for outcomes in [[["p", 1, "PENDING"]], [["p", 1, "OK"], ["p", 1, "OK"]]]:
        with pytest.raises(ReplenishmentError):
            batch_summary(
                {"photos": [["p", 1, 1, "sha"]], "photo_outcomes": outcomes},
                {"schema_version": 1, "photos": []},
            )


def test_list_accumulates_across_batches_and_precedes_error_receipt(tmp_path):
    from product_search.infrastructure.replenishment_deferred_photos import DeferredPhotos

    tmp_path.chmod(0o700)
    deferred = DeferredPhotos(tmp_path, inventory())
    for index in range(2):
        queue = (photo(index),)
        controller, progress, _, workers, _ = setup(queue)
        workers.process = lambda *a: (_ for _ in ()).throw(
            PhotoProcessingError("REGION_COUNT_LIMIT")
        )
        deferred.attach(
            workers,
            SimpleNamespace(
                read_stage_source=lambda *a: SelectedPhoto(1, "frozen.jpg", "a" * 64, 100)
            ),
        )
        finish = progress.finish_photo

        def durable_before_receipt(p, outcome, owner, finish=finish):
            assert json.loads(deferred.path.read_text())["photos"][-1]["photo_ref"] == p.photo_ref
            finish(p, outcome, owner)

        progress.finish_photo = durable_before_receipt
        assert run(controller, queue).reason == "COMPLETED"
    assert len(json.loads(deferred.path.read_text())["photos"]) == 2
    before = deferred.path.read_bytes()
    with pytest.raises(ReplenishmentError):
        DeferredPhotos(tmp_path, inventory())
    assert deferred.path.read_bytes() == before


def test_oversized_record_stops_without_replacing_existing_list(tmp_path):
    controller, _, _, workers, _ = setup((photo(0),))
    workers.process = lambda *a: (_ for _ in ()).throw(PhotoProcessingError("REGION_COUNT_LIMIT"))
    inputs = inventory()
    inputs["source_records"][0]["source_ref"] = "x" * (2 * 1024**2)
    path = wire(tmp_path, workers, inputs=inputs)
    before = path.read_bytes()
    with pytest.raises(ReplenishmentError, match="DEFERRED_PHOTOS_UNAVAILABLE"):
        run(controller, (photo(0),))
    assert path.read_bytes() == before


def test_symlink_list_never_overwrites_another_file(tmp_path):
    from product_search.infrastructure.replenishment_deferred_photos import DeferredPhotos

    tmp_path.chmod(0o700)
    target = tmp_path / "other.json"
    target.write_text("preserve")
    (tmp_path / "deferred-photos.json").symlink_to(target)
    with pytest.raises(ReplenishmentError):
        DeferredPhotos(tmp_path, inventory())
    assert target.read_text() == "preserve"


def test_terminal_report_prints_counts_and_path_without_source_ids(tmp_path, capsys):
    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.replenishment_deferred_photos import main

    tmp_path.chmod(0o700)
    export = tmp_path / "export.json"
    deferred = tmp_path / "deferred-photos.json"
    publish_private_json(
        export,
        {
            "photos": [["private-photo", 1, 1, "sha"]],
            "photo_outcomes": [["private-photo", 1, "ERROR"]],
        },
    )
    publish_private_json(
        deferred,
        {
            "schema_version": 1,
            "photos": [
                {"photo_ref": "private-photo", "input_sha": "sha", "reason": "REGION_COUNT_LIMIT"}
            ],
        },
    )
    assert main(["--catalog", str(export), "--deferred", str(deferred)]) == 0
    output = capsys.readouterr().out
    assert "private-photo" not in output
    assert json.loads(output)["deferred_photos_path"] == str(deferred)
    assert json.loads(output)["deferred"] == 1
    publish_private_json(deferred, {"schema_version": 1, "photos": []})
    assert main(["--catalog", str(export), "--deferred", str(deferred)]) == 1


def test_partial_export_exists_before_rejecting_an_unaccounted_error(tmp_path, catalog):  # noqa: F811
    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.replenishment_deferred_photos import export_deferred_batch

    tmp_path.chmod(0o700)
    deferred = tmp_path / "deferred-photos.json"
    publish_private_json(deferred, {"schema_version": 1, "photos": []})
    export = tmp_path / "partial.json"
    with pytest.raises(ReplenishmentError, match="PHOTO_NOT_DEFERRED"):
        export_deferred_batch(catalog, export, {}, deferred)
    assert len(json.loads(export.read_text())["photos"]) == 3


from tests.test_replenishment_diagnostic_export import catalog  # noqa: F401
