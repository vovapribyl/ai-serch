"""Synthetic fixture worker only: no corpus paths or native SDK factories."""

import hashlib
import json
import os
import platform
import re
import sys
import time
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import httpx

from product_search.infrastructure.nail_build_composition import (
    ObservationGate,
    RecordingBudget,
    RuntimeVerifier,
    compose_build,
    publish_private_json,
    read_private_json,
)
from product_search.infrastructure.nail_build_runner import AdmissionBudget, BuildStop, OwnedTarget
from product_search.infrastructure.nail_image_store import NailImageStore
from product_search.infrastructure.nail_ml_adapters import (
    ClientSettings,
    HttpNailLocalizationAdapter,
)
from product_search.infrastructure.nail_runtime import FileLease
from product_search.infrastructure.nail_wire import WireLimits
from product_search.search.nail_contracts import (
    MODEL_DIMENSIONS,
    BinaryMask,
    BuildIdentity,
    BuildPhoto,
    BuildSummary,
    DecodeProfile,
    EmbeddingProfile,
    LocalizationProfile,
    LocalizedRegion,
    ModelIdentity,
    NailLocalization,
    PhotoInput,
    SearchProfile,
    StoredPhotoState,
)
from services.candidate_i.app import create_app
from services.candidate_i.settings import ServiceSettings


def fake_runtime():
    packages = sorted(
        re.sub("[-_.]+", "-", d.metadata["Name"]).lower() + "==" + d.version
        for d in metadata.distributions()
    )
    return {
        "mode": "fake",
        "extractor_fingerprint": "a" * 64,
        "backend_inventory_sha256": hashlib.sha256(
            json.dumps(packages, separators=(",", ":")).encode()
        ).hexdigest(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "device": "fake",
        "dtype": "float32",
        "operator_fallback": os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") is not None,
        "models": [[key, "fake-" + key + "-v1", "b" * 64, dim] for key, dim in MODEL_DIMENSIONS],
    }


class SyntheticCatalog:
    def __init__(self, root):
        self.root, self.states, self.outcomes = root, (), {}
        self.budget = None

    def summary(self):
        statuses = [
            self.outcomes.get(state.item.catalog_photo_id, "PENDING") for state in self.states
        ]
        ok, no, error, pending = (statuses.count(s) for s in ("OK", "NO_NAILS", "ERROR", "PENDING"))
        uncovered = tuple(
            sorted(
                state.item.product_record_id
                for state in self.states
                if self.outcomes.get(state.item.catalog_photo_id) != "OK"
            )
        )
        return BuildSummary(
            "synthetic",
            "BUILDING",
            len(statuses),
            ok,
            no,
            error,
            pending,
            ok > 0 and error == pending == 0,
            uncovered,
        )

    def checkpoint(self):
        summary = self.summary()
        publish_private_json(
            self.root / "checkpoint.json",
            {
                "mode": "fake",
                "status": "BUILDING",
                "total": summary.total_photos,
                "ok": summary.ok_photos,
                "no_nails": summary.no_nails_photos,
                "error": summary.error_photos,
                "pending": summary.pending_photos,
                "admissions": self.budget.used if self.budget else 0,
                "published": False,
            },
        )

    def begin_build(self, identity, inventory):
        self.identity = identity
        self.states = tuple(StoredPhotoState(item, "PENDING", None, ()) for item in inventory)
        self.checkpoint()

    def read_photo_states(self, representation_id):
        return self.states

    def write_photo_outcome(self, outcome):
        if outcome.embeddings is not None:
            for key, rows in outcome.embeddings.vectors:
                for vector in rows:
                    assert len(vector) == dict(MODEL_DIMENSIONS)[key]
                    assert abs(sum(v * v for v in vector) - 1) < 1e-5
        self.outcomes[outcome.catalog_photo_id] = outcome.photo.status if outcome.photo else "ERROR"
        self.checkpoint()

    def read_build_summary(self, representation_id):
        return self.summary()


def worker(job_path, sha):
    blob = Path(job_path).read_bytes()
    if hashlib.sha256(blob).hexdigest() != sha:
        raise BuildStop("JOB_CHANGED")
    job = json.loads(blob)
    if job["mode"] != "fake":
        raise BuildStop("FAKE_WORKER_ONLY")
    root = Path(job_path).parent
    publish_private_json(root / "worker-pid.json", {"pid": os.getpid(), "parent": os.getppid()})
    for entry in job["code"]:
        if hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise BuildStop("CODE_CHANGED")
    # No code path accepts source locators: inputs are this fresh fixture namespace only.
    names = job["inputs"]
    images = NailImageStore(root / "inputs")
    derivatives = NailImageStore(root / "artifacts", max_manifest_bytes=8388608)

    class Sources:
        def read_rgb(self, *args):
            return images.read_rgb(*args)

        def write_region_artifacts(self, *args):
            return derivatives.write_region_artifacts(*args)

        def cleanup(self, *args):
            return derivatives.cleanup(*args)

    store = Sources()
    while not (root / "observation.json").exists():
        time.sleep(0.01)

    def allowed():
        try:
            value = read_private_json(root / "observation.json")
            if value["stop_reason"] is not None:
                return False
            gate = ObservationGate(job["limits"], time.monotonic)
            gate.update(value["sample"], value["observed_at"])
            return gate.allowed()
        except Exception:  # noqa: BLE001 -- observation never grants permission on failure.
            return False

    budget = RecordingBudget(
        AdmissionBudget(8, time.monotonic() + job["limits"]["wall_s"], allowed, time.monotonic),
        lambda count: publish_private_json(
            root / "admissions.json", {"reserved": count, "before_sdk": True}
        ),
    )
    catalog = SyntheticCatalog(root)
    catalog.budget = budget
    models = tuple(ModelIdentity(*row) for row in job["runtime"]["models"])
    identity = BuildIdentity(
        job["representation_id"],
        1,
        job["representation_fingerprint"],
        job["inventory_sha256"],
        (("crop_profile", "mask_bbox_white_v1"), ("scope", "synthetic-composition")),
        models,
    )
    inventory = tuple(
        BuildPhoto(item["catalog_photo_id"], i + 1, PhotoInput(1, item["ref"], item["sha256"]))
        for i, item in enumerate(names)
    )
    runtime = SearchProfile(
        identity.fingerprint,
        EmbeddingProfile(tuple((m.model_key, m.revision) for m in models)),
        16384,
    )
    leases = Path(root / "runtime")

    def binding(image, profile):
        if image.pixels[0] == 0:
            return NailLocalization("NO_NAILS", ())
        return NailLocalization(
            "OK",
            (
                LocalizedRegion(
                    1,
                    "nail",
                    0.99,
                    (0.0, 0.0, float(image.width), float(image.height)),
                    BinaryMask(image.width, image.height, b"\xff" * (image.width * image.height)),
                ),
            ),
        )

    app = create_app(
        ServiceSettings("a" * 64, WireLimits(2359296, 10, 41943040), leases),
        binding,
        ready_check=lambda: True,
    )
    localization = HttpNailLocalizationAdapter(
        ClientSettings("http://127.0.0.1:1", 1, 30, 300, 330, WireLimits(2359296, 10, 41943040)),
        transport=httpx.ASGITransport(app=app),
    )
    factories = {}
    for key, rev, manifest, dim in fake_runtime()["models"]:

        def load(key=key, rev=rev, dim=dim):
            def encode(image):
                if job["fault"] == "provider_error":
                    raise RuntimeError("SYNTHETIC_PROVIDER_ERROR")
                if job["fault"] == "wall":
                    time.sleep(30)
                return (1.0,) + (0.0,) * (dim - 1)

            return SimpleNamespace(
                model_key=key, revision=rev, embedding_dim=dim, encode_image=encode
            )

        factories[key] = load
    target = OwnedTarget(job["target"]["path"], job["target"]["sha256"])

    def target_ok():
        with target.connect():
            return True

    decode = DecodeProfile(20971520, 2359296)

    def input_ok():
        return allowed() and all(
            isinstance(store.read_rgb(item.photo, decode), object) for item in inventory
        )

    verifier = RuntimeVerifier(job["runtime"], fake_runtime)
    execute = compose_build(
        catalog=catalog,
        images=store,
        localization=localization,
        factories=factories,
        identity=identity,
        inventory=inventory,
        runtime=runtime,
        localization_profile=LocalizationProfile("a" * 64),
        decode_profile=decode,
        max_regions=10,
        budget=budget,
        device=FileLease(leases, "device.lock"),
        coordinator=FileLease(leases, "coordinator.lock"),
        target_check=target_ok,
        input_check=input_ok,
        runtime_check=verifier.verify,
    )
    try:
        summary = execute()
        result = {
            "outcome": "PASS" if summary.complete else "INCOMPLETE",
            "admissions": budget.used,
            "ok": summary.ok_photos,
            "no_nails": summary.no_nails_photos,
            "pending": summary.pending_photos,
            "published": False,
            "mode": "fake",
            "sdk_imported": any(k == "torch" or k.startswith("transformers") for k in sys.modules),
        }
    except BuildStop:
        catalog.checkpoint()
        result = {
            "outcome": "STOP",
            "admissions": budget.used,
            "mode": "fake",
            "published": False,
            "sdk_imported": any(k == "torch" or k.startswith("transformers") for k in sys.modules),
        }
    publish_private_json(root / "result.json", result)
    publish_private_json(root / "worker-done.json", {"done": True})
    return 0 if result["outcome"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(worker(sys.argv[1], sys.argv[2]))
