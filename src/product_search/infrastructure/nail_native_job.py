"""Pinned native job gates. Importing this module never imports model SDKs."""

import hashlib
import json
import math
import os
import stat
import time
from pathlib import Path

from product_search.infrastructure.nail_build_composition import read_private_json
from product_search.infrastructure.nail_build_runner import BuildStop


def read_pinned(ref, *, private=True):
    path = Path(ref["path"])
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise BuildStop("UNSAFE_PINNED_PATH")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_size > 8388608
            or (private and stat.S_IMODE(before.st_mode) != 0o600)
        ):
            raise BuildStop("UNSAFE_PINNED_FILE")
        blob = stream.read(8388609)
        after = os.fstat(stream.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise BuildStop("PINNED_FILE_CHANGED")
    if hashlib.sha256(blob).hexdigest() != ref["sha256"]:
        raise BuildStop("PINNED_FILE_CHANGED")
    return blob


def load_job(path, sha):
    try:
        job = json.loads(read_pinned({"path": str(path), "sha256": sha}))
        if job["schema_version"] != 1 or job["mode"] != "native" or not job["code"]:
            raise BuildStop("INVALID_NATIVE_JOB")
        for ref in job["code"]:
            read_pinned(ref, private=False)
        for ref in job["files"].values():
            read_pinned(ref)
        return job
    except (OSError, ValueError, KeyError, TypeError):
        raise BuildStop("INVALID_NATIVE_JOB") from None


def execution_allowed(ref, job_sha, *, now):
    try:
        value = json.loads(read_pinned(ref))
        expiry = value["expires_at"]
        return (
            value["status"] == "APPROVED_BY_OWNER"
            and value["action"] == "BUILD_ONCE_NO_PUBLISH"
            and value["job_sha256"] == job_sha
            and type(expiry) in (int, float)
            and math.isfinite(expiry)
            and now < expiry
        )
    except (OSError, ValueError, KeyError, TypeError, BuildStop):
        return False


def claim_execution(root, ref, job_sha, *, now, run_root=None):
    from product_search.infrastructure.nail_runtime import validate_runtime_root

    root = validate_runtime_root(Path(root))
    if not execution_allowed(ref, job_sha, now=now):
        raise BuildStop("NATIVE_EXECUTION_NOT_AUTHORIZED")
    try:
        fd = os.open(
            root / "execution.claim", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "w") as stream:
            json.dump(
                {
                    "job_sha256": job_sha,
                    "claimed_at": now,
                    "owner_pid": os.getpid(),
                    "run_root": str(run_root) if run_root is not None else None,
                },
                stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        raise BuildStop("EXECUTION_WINDOW_ALREADY_CONSUMED") from None


def guard_i_application(app, *, check, allowed):
    from starlette.responses import JSONResponse

    @app.middleware("http")
    async def admitted(request, call_next):
        if request.method == "GET" and request.url.path == "/health/ready":
            return await call_next(request)
        if (
            check
            or request.method != "POST"
            or request.url.path != "/v1/localizations"
            or allowed() is not True
        ):
            return JSONResponse({"code": "NATIVE_EXECUTION_NOT_AUTHORIZED"}, status_code=403)
        return await call_next(request)

    return app


class CurrentObservation:
    def __init__(self, root, limits):
        from product_search.infrastructure.nail_build_composition import ObservationGate

        self.root, self.gate = Path(root), ObservationGate(limits, time.monotonic)

    def allowed(self):
        try:
            value = read_private_json(self.root / "observation.json", allow_replaced=True)
            if value["stop_reason"] is not None:
                self.gate.invalidate()
            else:
                self.gate.update(value["sample"], value["observed_at"])
        except (OSError, KeyError, TypeError, BuildStop):
            self.gate.invalidate()
        return self.gate.allowed()


def backend_runtime(job, extractor_fingerprint):
    import platform
    import re
    from importlib import metadata

    from product_search.search.model_manifest import read_manifest, verify_manifest

    packages = sorted(
        re.sub("[-_.]+", "-", d.metadata["Name"]).lower() + "==" + d.version
        for d in metadata.distributions()
    )
    models = []
    for key, revision, expected, dim in job["runtime"]["models"]:
        root = Path(job["model_root"]) / key
        manifest = read_manifest(root)
        verify_manifest(root, manifest)
        models.append([key, revision, manifest.sha256, dim])
    return {
        "mode": "native",
        "extractor_fingerprint": extractor_fingerprint,
        "backend_inventory_sha256": hashlib.sha256(
            json.dumps(packages, separators=(",", ":")).encode()
        ).hexdigest(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "device": "mps",
        "dtype": "float32",
        "operator_fallback": os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") is not None,
        "models": models,
    }


def target_precheck(target, job):
    with target.connect() as conn:
        conn.rollback()
        conn.execute("SET TRANSACTION READ ONLY")
        head = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        parents = conn.execute(
            "SELECT id FROM product_records WHERE corpus_version_id=%s ORDER BY id",
            (job["build"]["corpus_version_id"],),
        ).fetchall()
        exists = conn.execute(
            "SELECT count(*) FROM search_representations WHERE id=%s",
            (job["build"]["representation_id"],),
        ).fetchone()[0]
    expected = sorted(
        item["product_record_id"]
        for item in json.loads(read_pinned(job["files"]["inventory"]))["items"]
    )
    parent_ids = [row[0] for row in parents]
    parent_sha = hashlib.sha256(json.dumps(parent_ids, separators=(",", ":")).encode()).hexdigest()
    if (
        head != ("0009_nail_search_v1",)
        or exists
        or len(parent_ids) != job["source_parent_count"]
        or parent_sha != job["source_parent_ids_sha256"]
        or len(expected) != job["input_count"]
        or len(set(expected)) != len(expected)
        or not set(expected).issubset(parent_ids)
    ):
        raise BuildStop("TARGET_PRECHECK_FAILED")
    return True


def safe_target_counts(target, job):
    with target.connect() as conn:
        conn.rollback()
        conn.execute("SET TRANSACTION READ ONLY")
        status = conn.execute(
            "SELECT status FROM search_representations WHERE id=%s",
            (job["build"]["representation_id"],),
        ).fetchone()
        rows = conn.execute(
            "SELECT status,count(*) FROM catalog_photos WHERE representation_id=%s GROUP BY status",
            (job["build"]["representation_id"],),
        ).fetchall()
        regions = conn.execute(
            "SELECT count(*) FROM nail_regions WHERE representation_id=%s",
            (job["build"]["representation_id"],),
        ).fetchone()[0]
        vectors = conn.execute(
            "SELECT count(*) FROM nail_embeddings WHERE representation_id=%s",
            (job["build"]["representation_id"],),
        ).fetchone()[0]
        pointers = conn.execute("SELECT count(*) FROM search_active_representations").fetchone()[0]
    return {
        "representation_status": status[0] if status else "NOT_CREATED",
        "photo_counts": dict(rows),
        "regions": regions,
        "vectors": vectors,
        "active_pointer_count": pointers,
    }


def consume_worker_claim(job_root, run_root, job_sha, parent_pid):
    from product_search.infrastructure.nail_runtime import validate_runtime_root

    job_root, run_root = (
        validate_runtime_root(Path(job_root)),
        validate_runtime_root(Path(run_root)),
    )
    claim = read_private_json(job_root / "execution.claim")
    if (
        claim.get("job_sha256") != job_sha
        or claim.get("owner_pid") != parent_pid
        or claim.get("run_root") != str(run_root)
    ):
        raise BuildStop("WORKER_CLAIM_MISMATCH")
    try:
        fd = os.open(
            job_root / "worker-started.claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "w") as stream:
            json.dump(
                {"job_sha256": job_sha, "run_root": str(run_root), "pid": os.getpid()}, stream
            )
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        raise BuildStop("WORKER_ATTEMPT_ALREADY_CONSUMED") from None


def validate_input_scope(job, inventory):
    count = job["input_count"]
    if (
        type(count) is not int
        or not 1 <= count <= 674
        or type(inventory) is not tuple
        or len(inventory) != count
        or job["max_admissions"] != count * 31 + 3
        or len({i.catalog_photo_id for i in inventory}) != count
        or len({(i.product_record_id, i.photo.photo_ordinal) for i in inventory}) != count
        or inventory
        != tuple(sorted(inventory, key=lambda i: (i.product_record_id, i.photo.photo_ordinal)))
    ):
        raise BuildStop("INVENTORY_SCOPE_CHANGED")
    return True


def select_distinct_inputs(items, count):
    if type(count) is not int or count < 1:
        raise BuildStop("INVALID_TEST_COUNT")
    unique = {}
    for item in sorted(items, key=lambda i: (i["product_record_id"], i["photo"]["photo_ordinal"])):
        unique.setdefault(item["photo"]["input_sha256"], item)
    if len(unique) < count:
        raise BuildStop("INSUFFICIENT_DISTINCT_INPUTS")
    hashes = sorted(
        unique,
        key=lambda sha: hashlib.sha256(("candidate-i-corpus100-v1\0" + sha).encode()).hexdigest(),
    )
    return tuple(
        sorted(
            (unique[sha] for sha in hashes[:count]),
            key=lambda i: (i["product_record_id"], i["photo"]["photo_ordinal"]),
        )
    )
