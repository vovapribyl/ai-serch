import hashlib
import json
from pathlib import Path

import pytest

from product_search.infrastructure.nail_build_runner import BuildStop


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True))
    path.chmod(0o600)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def job_fixture(tmp_path):
    code = tmp_path / "code.py"
    code.write_text("pass\n")
    return save(
        tmp_path / "job.json",
        {
            "schema_version": 1,
            "mode": "native",
            "files": {"input": save(tmp_path / "input.json", {"count": 674})},
            "code": [{"path": str(code), "sha256": hashlib.sha256(code.read_bytes()).hexdigest()}],
        },
    )


@pytest.mark.parametrize("changed", ["job", "code", "metadata", "permissions"])
def test_changed_or_nonprivate_job_cannot_reach_worker(tmp_path, changed):
    from product_search.infrastructure.nail_native_job import load_job

    ref = job_fixture(tmp_path)
    if changed == "job":
        Path(ref["path"]).write_text("{}")
    if changed == "code":
        (tmp_path / "code.py").write_text("changed")
    if changed == "metadata":
        (tmp_path / "input.json").write_text("{}")
    if changed == "permissions":
        Path(ref["path"]).chmod(0o644)
    with pytest.raises(BuildStop):
        load_job(ref["path"], ref["sha256"])


@pytest.mark.parametrize(
    "status,job,expiry",
    [
        ("PENDING_OWNER_APPROVAL", "a" * 64, 200),
        ("APPROVED_BY_OWNER", "b" * 64, 200),
        ("APPROVED_BY_OWNER", "a" * 64, 99),
    ],
)
def test_unapproved_changed_or_expired_permit_denies_execution(tmp_path, status, job, expiry):
    from product_search.infrastructure.nail_native_job import execution_allowed

    ref = save(
        tmp_path / "permit.json",
        {
            "status": status,
            "action": "BUILD_ONCE_NO_PUBLISH",
            "job_sha256": job,
            "expires_at": expiry,
        },
    )
    assert execution_allowed(ref, "a" * 64, now=100) is False


def test_valid_permit_is_bound_to_one_attempt_even_after_failure(tmp_path):
    from product_search.infrastructure.nail_native_job import claim_execution, execution_allowed

    ref = save(
        tmp_path / "permit.json",
        {
            "status": "APPROVED_BY_OWNER",
            "action": "BUILD_ONCE_NO_PUBLISH",
            "job_sha256": "a" * 64,
            "expires_at": 200,
        },
    )
    assert execution_allowed(ref, "a" * 64, now=100) is True
    claim_execution(tmp_path, ref, "a" * 64, now=100)
    with pytest.raises(BuildStop):
        claim_execution(tmp_path, ref, "a" * 64, now=101)


@pytest.mark.parametrize("check", [True, False])
def test_i_firewall_blocks_inference_before_binding_when_check_or_unpermitted(check):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from product_search.infrastructure.nail_native_job import guard_i_application

    called = []
    app = FastAPI()

    @app.get("/health/ready")
    def ready():
        return {"ready": True}

    @app.post("/v1/localizations")
    def infer():
        called.append("model")
        return {}

    with TestClient(guard_i_application(app, check=check, allowed=lambda: False)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.post("/v1/localizations").status_code == 403
    assert called == []


def test_cached_provider_cannot_encode_or_reserve_after_permit_expiry(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from product_search.infrastructure.nail_build_runner import admitted_provider
    from product_search.infrastructure.nail_runtime import FileLease
    from scripts.run_nail_native_build import create_budget

    monkeypatch.setattr("scripts.run_nail_native_build.time.time", lambda: 100)
    ref = save(
        tmp_path / "permit.json",
        {
            "status": "APPROVED_BY_OWNER",
            "action": "BUILD_ONCE_NO_PUBLISH",
            "job_sha256": "a" * 64,
            "expires_at": 200,
        },
    )
    args = SimpleNamespace(check=False, permit=ref["path"], permit_sha256=ref["sha256"])
    budget = create_budget(
        {"max_admissions": 8, "limits": {"wall_s": 60}},
        "a" * 64,
        args,
        SimpleNamespace(allowed=lambda: True),
        tmp_path,
    )
    encodes = []
    provider = admitted_provider(
        lambda: SimpleNamespace(
            model_key="test",
            revision="r",
            embedding_dim=1,
            encode_image=lambda image: encodes.append(image),
        ),
        budget,
        FileLease(tmp_path, "device.lock"),
    )()
    monkeypatch.setattr("scripts.run_nail_native_build.time.time", lambda: 201)
    with pytest.raises(BuildStop):
        provider.encode_image("must-not-encode")
    assert encodes == [] and budget.used == 1


@pytest.mark.parametrize("fault", ["wrong_root", "reentry"])
def test_worker_cannot_reenter_consumed_claim_or_change_root(tmp_path, fault):
    from product_search.infrastructure.nail_native_job import consume_worker_claim

    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    save(
        tmp_path / "execution.claim",
        {"job_sha256": "a" * 64, "owner_pid": 123, "run_root": str(run)},
    )
    if fault == "reentry":
        consume_worker_claim(tmp_path, run, "a" * 64, 123)
    with pytest.raises(BuildStop):
        consume_worker_claim(tmp_path, tmp_path if fault == "wrong_root" else run, "a" * 64, 123)


def test_supervisor_retains_each_storage_sample_for_build_report(tmp_path):
    import sys

    from product_search.infrastructure.nail_build_composition import supervise_owned
    from tests.support.candidate_i_probe_watchdog import run_owned_probe

    tmp_path.chmod(0o700)
    script = "import os,json,pathlib,time,sys; p=pathlib.Path(sys.argv[1])/'worker-pid.json'; fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,json.dumps({'pid':os.getpid(),'parent':os.getppid()}).encode()); os.close(fd); time.sleep(.3)"
    sample = {
        "pressure": 1,
        "i_rss": 10,
        "backend_rss": 10,
        "artifact_bytes": 3,
        "db_bytes": 4,
        "host_free": 1000,
        "vm_free": 900,
    }
    limits = {
        "i_rss_bytes": 100,
        "backend_rss_bytes": 100,
        "combined_rss_bytes": 200,
        "max_storage_bytes": 500,
        "min_free_bytes": 100,
        "freshness_s": 1,
        "wall_s": 2,
    }
    result = supervise_owned(
        [sys.executable, "-B", "-c", script, str(tmp_path)],
        tmp_path,
        limits,
        observe=lambda pid: sample,
        watchdog=run_owned_probe,
    )
    assert result["exit_code"] == 0
    rows = [
        json.loads(line) for line in (tmp_path / "supervisor-trace.jsonl").read_text().splitlines()
    ]
    assert rows and all(
        {"artifact_bytes", "db_bytes", "host_free", "vm_free"} <= row.keys() for row in rows
    )
    assert (
        rows[-1]["artifact_bytes"] == 3
        and rows[-1]["db_bytes"] == 4
        and rows[-1]["host_free"] == 1000
        and rows[-1]["vm_free"] == 900
    )


def test_atomic_observation_replacement_does_not_invalidate_open_private_snapshot(
    tmp_path, monkeypatch
):
    import os
    import time

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.nail_native_job import CurrentObservation

    sample = {
        "pressure": 1,
        "i_rss": 10,
        "backend_rss": 10,
        "artifact_bytes": 3,
        "db_bytes": 4,
        "host_free": 1000,
        "vm_free": 900,
    }
    limits = {
        "i_rss_bytes": 100,
        "backend_rss_bytes": 100,
        "combined_rss_bytes": 200,
        "max_storage_bytes": 500,
        "min_free_bytes": 100,
        "freshness_s": 1,
        "wall_s": 2,
    }
    value = {"sample": sample, "observed_at": time.monotonic(), "stop_reason": None}
    publish_private_json(tmp_path / "observation.json", value)
    actual_fstat = os.fstat
    replaced = False

    def replace_before_fstat(fd):
        nonlocal replaced
        if not replaced:
            replaced = True
            publish_private_json(tmp_path / "observation.json", value)
        return actual_fstat(fd)

    monkeypatch.setattr(os, "fstat", replace_before_fstat)
    assert CurrentObservation(tmp_path, limits).allowed() is True


@pytest.mark.parametrize("unsafe", ["hardlink", "symlink"])
def test_atomic_snapshot_option_still_rejects_aliases(tmp_path, unsafe):
    import os
    import time

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.nail_native_job import CurrentObservation

    sample = {
        "pressure": 1,
        "i_rss": 10,
        "backend_rss": 10,
        "artifact_bytes": 3,
        "db_bytes": 4,
        "host_free": 1000,
        "vm_free": 900,
    }
    limits = {
        "i_rss_bytes": 100,
        "backend_rss_bytes": 100,
        "combined_rss_bytes": 200,
        "max_storage_bytes": 500,
        "min_free_bytes": 100,
        "freshness_s": 1,
        "wall_s": 2,
    }
    path = tmp_path / "observation.json"
    publish_private_json(
        path, {"sample": sample, "observed_at": time.monotonic(), "stop_reason": None}
    )
    if unsafe == "hardlink":
        os.link(path, tmp_path / "alias")
    else:
        original = tmp_path / "original"
        path.rename(original)
        path.symlink_to(original)
    assert CurrentObservation(tmp_path, limits).allowed() is False


def test_subset_parent_precheck_accepts_selected_records_but_detects_parent_drift(tmp_path):
    import contextlib
    from types import SimpleNamespace

    from product_search.infrastructure.nail_native_job import target_precheck

    items = [{"product_record_id": i} for i in (2, 4)]
    ref = save(tmp_path / "inventory.json", {"items": items})
    parent_ids = [1, 2, 3, 4]
    job = {
        "files": {"inventory": ref},
        "input_count": 2,
        "source_parent_count": 4,
        "source_parent_ids_sha256": hashlib.sha256(
            json.dumps(parent_ids, separators=(",", ":")).encode()
        ).hexdigest(),
        "build": {
            "corpus_version_id": 1,
            "representation_id": "00000000-0000-0000-0000-000000000000",
        },
    }

    class Connection:
        def rollback(self):
            pass

        def execute(self, query, *args):
            return SimpleNamespace(
                fetchone=lambda: ("0009_nail_search_v1",) if "version_num" in query else (0,),
                fetchall=lambda: [(x,) for x in parent_ids],
            )

    @contextlib.contextmanager
    def connect():
        yield Connection()

    target = SimpleNamespace(connect=connect)
    assert target_precheck(target, job) is True
    parent_ids[:] = [1, 2, 3, 5]
    with pytest.raises(BuildStop):
        target_precheck(target, job)


def test_frozen_input_count_and_budget_accept100_and_reject_mismatch():
    from types import SimpleNamespace

    from product_search.infrastructure.nail_native_job import validate_input_scope

    items = tuple(
        SimpleNamespace(
            product_record_id=i, catalog_photo_id=str(i), photo=SimpleNamespace(photo_ordinal=1)
        )
        for i in range(1, 101)
    )
    assert validate_input_scope({"input_count": 100, "max_admissions": 3103}, items) is True
    with pytest.raises(BuildStop):
        validate_input_scope({"input_count": 100, "max_admissions": 3103}, items[:-1])
    with pytest.raises(BuildStop):
        validate_input_scope({"input_count": 100, "max_admissions": 20897}, items)


def test_selection_is_stable_and_keeps_unique_image_bytes():
    from product_search.infrastructure.nail_native_job import select_distinct_inputs

    items = [
        {"product_record_id": 1, "photo": {"photo_ordinal": 1, "input_sha256": "a" * 64}},
        {"product_record_id": 2, "photo": {"photo_ordinal": 1, "input_sha256": "a" * 64}},
        {"product_record_id": 3, "photo": {"photo_ordinal": 1, "input_sha256": "b" * 64}},
    ]
    chosen = select_distinct_inputs(items, 2)
    assert {i["product_record_id"] for i in chosen} == {1, 3}
    assert select_distinct_inputs(list(reversed(items)), 2) == chosen
    with pytest.raises(BuildStop):
        select_distinct_inputs(items, 3)
