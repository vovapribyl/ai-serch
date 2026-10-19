"""Private source-linked deferrals for the explicitly selected region-limit bypass."""

import json
import os
from functools import wraps
from pathlib import Path

from product_search.infrastructure.nail_build_composition import publish_private_json
from product_search.infrastructure.nail_runtime import validate_runtime_root
from product_search.search.replenishment_contracts import PhotoProcessingError, ReplenishmentError

DEFERRED_LIST_MAX_BYTES = 2 * 1024**2


def _publish(path, payload):
    # One bounded owner writes; no automatic queue, rotation or loss of old rows.
    if len(json.dumps(payload).encode()) > DEFERRED_LIST_MAX_BYTES:
        raise ValueError("Deferred list size limit")
    publish_private_json(path, payload)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _source_identity(inventory, selected):
    photos = [(p["product_record_id"], f) for p in inventory["products"] for f in p["photos"]]
    matches = [
        (i, product, f)
        for i, (product, f) in enumerate(photos)
        if (f["ordinal"], f["source_ref"], f["input_sha"])
        == (selected.ordinal, selected.source_ref, selected.input_sha)
    ]
    if len(matches) != 1:
        raise ValueError("Ambiguous source identity")
    index, product, source = matches[0]
    records = inventory.get("source_records")
    if records is None:
        return product, source["source_ref"], source["source_ref"]
    if len(records) != len(photos):
        raise ValueError("Missing original source mapping")
    original = records[index]
    if original["input_sha256"] != selected.input_sha:
        raise ValueError("Original source hash mismatch")
    item = original["source_item"]
    return item["product_record_id"], item["catalog_photo_id"], original["source_ref"]


class DeferredPhotos:
    """One private append-only list shared by batches of the same host."""

    def __init__(self, root, inventory):
        self.path = validate_runtime_root(Path(root)) / "deferred-photos.json"
        self.inventory = inventory
        self.payload = {"schema_version": 1, "photos": []}
        try:
            # Each package owns a fresh directory. Never overwrite a previous run's list.
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            _publish(self.path, self.payload)
        except Exception:  # noqa: BLE001 -- a missing durable list must stop this campaign.
            raise ReplenishmentError("DEFERRED_PHOTOS_UNAVAILABLE") from None

    def attach(self, workers, repository):
        process = workers.process

        @wraps(process)
        def observed(photo, attempt, owner, end_at):
            try:
                return process(photo, attempt, owner, end_at)
            except PhotoProcessingError as error:
                if str(error) != "REGION_COUNT_LIMIT" or attempt.stage_key != "localization":
                    raise ReplenishmentError("PHOTO_NOT_DEFERRED") from None
                try:
                    source = repository.read_stage_source(attempt, owner)
                    product, source_id, source_ref = _source_identity(self.inventory, source)
                    record = {
                        "product_record_id": product,
                        "source_photo_id": source_id,
                        "source_ref": source_ref,
                        "input_sha": source.input_sha,
                        "runtime_source_ref": source.source_ref,
                        "photo_ref": photo.photo_ref,
                        "run_ref": owner.run_ref,
                        "attempt_ref": attempt.attempt_ref,
                        "reason": "REGION_COUNT_LIMIT",
                    }
                    candidate = {**self.payload, "photos": [*self.payload["photos"], record]}
                    _publish(self.path, candidate)
                    self.payload["photos"].append(record)
                except Exception:  # noqa: BLE001 -- a missing durable list must stop this campaign.
                    raise ReplenishmentError("DEFERRED_PHOTOS_UNAVAILABLE") from None
                raise

        workers.process = observed
        return self.path


def batch_summary(snapshot, deferred):
    """Verify terminal outcomes; a matching source-linked limit record permits ERROR."""
    try:
        if deferred["schema_version"] != 1:
            raise ValueError
        photos = {r[0]: (r[1], r[3]) for r in snapshot["photos"]}
        outcomes = {r[0]: (r[1], r[2]) for r in snapshot["photo_outcomes"]}
        if (
            len(photos) != len(snapshot["photos"])
            or len(outcomes) != len(snapshot["photo_outcomes"])
            or photos.keys() != outcomes.keys()
        ):
            raise ValueError
        rows = deferred["photos"]
        saved = {r["photo_ref"]: r for r in rows}
        if len(saved) != len(rows) or not saved.keys() <= photos.keys():
            raise ValueError
        result = {
            "ready": 0,
            "deferred": 0,
            "no_nails": 0,
            "other_errors": 0,
            "pending": 0,
            "total": len(photos),
        }
        for key, (product, outcome) in outcomes.items():
            if product != photos[key][0]:
                raise ValueError
            row = saved.get(key)
            if row is not None and (
                outcome != "ERROR"
                or row["reason"] != "REGION_COUNT_LIMIT"
                or row["input_sha"] != photos[key][1]
            ):
                raise ValueError
            if outcome == "OK":
                result["ready"] += 1
            elif outcome == "NO_NAILS":
                result["no_nails"] += 1
            elif outcome == "ERROR":
                result["deferred" if row is not None else "other_errors"] += 1
            elif outcome in {"PENDING", "RUNNING"}:
                result["pending"] += 1
            else:
                raise ValueError
        if result["other_errors"] or result["pending"]:
            raise ReplenishmentError("PHOTO_NOT_DEFERRED")
        return result
    except ReplenishmentError:
        raise
    except (KeyError, TypeError, ValueError, IndexError):
        raise ReplenishmentError("INVALID_DEFERRED_EXPORT") from None


def export_deferred_batch(connection, destination, profile, deferred_path):
    """Outer runners use this instead of all-OK: export first, then account for skips."""
    from product_search.infrastructure.replenishment_cli import private_json
    from product_search.infrastructure.replenishment_diagnostic_export import (
        export_before_verification,
        read_catalog_export,
    )

    return export_before_verification(
        connection,
        destination,
        profile,
        lambda: batch_summary(
            read_catalog_export(destination),
            private_json(deferred_path, max_bytes=DEFERRED_LIST_MAX_BYTES),
        ),
    )


def main(argv=None):
    """Read-only terminal summary; never launches models, SQL or automatic retries."""
    import argparse

    from product_search.infrastructure.replenishment_cli import private_json
    from product_search.infrastructure.replenishment_diagnostic_export import read_catalog_export

    parser = argparse.ArgumentParser(description="Сводка готовых и отложенных фото")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--deferred", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        summary = batch_summary(
            read_catalog_export(args.catalog),
            private_json(args.deferred, max_bytes=DEFERRED_LIST_MAX_BYTES),
        )
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "REFUSED"}))
        return 1
    print(
        json.dumps(
            {"status": "PASS", **summary, "deferred_photos_path": str(args.deferred.resolve())}
        )
    )
    return 0
