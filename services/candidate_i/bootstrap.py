"""Verified local-only service assembly."""

import json
import os
import platform
import re
from importlib import metadata
from pathlib import Path

from experiments.nail_localization.config import freeze_config
from product_search.infrastructure.nail_wire import WireLimits
from product_search.search.nail_contracts import NailProcessingError
from services.candidate_i.app import create_app
from services.candidate_i.binding import CandidateIBinding
from services.candidate_i.readiness import VerifiedReadiness
from services.candidate_i.settings import ServiceSettings

CODE_FILES = (
    "services/candidate_i/app.py",
    "services/candidate_i/settings.py",
    "services/candidate_i/binding.py",
    "services/candidate_i/readiness.py",
    "services/candidate_i/bootstrap.py",
    "experiments/nail_localization/config.py",
    "experiments/nail_localization/contracts.py",
    "experiments/nail_localization/langsam_adapter.py",
    "experiments/nail_localization/roi.py",
    "experiments/nail_localization/roi_localizer.py",
    "src/product_search/search/nail_contracts.py",
    "src/product_search/infrastructure/nail_wire.py",
    "src/product_search/infrastructure/nail_runtime.py",
)
GDINO_FILES = frozenset(
    {
        "config.json",
        "model.safetensors",
        "preprocessor_config.json",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    }
)


def installed_inventory():
    return sorted(
        re.sub("[-_.]+", "-", item.metadata["Name"]).lower() + "==" + item.version
        for item in metadata.distributions()
    )


def installed_vcs():
    return {
        name: json.loads(metadata.distribution(name).read_text("direct_url.json"))["vcs_info"][
            "commit_id"
        ]
        for name in ("lang-sam", "sam-2")
    }


def assemble_service(
    manifest,
    files,
    *,
    runtime_root,
    gdino_snapshot_path,
    sam_checkpoint_path,
    diagnostic_root=None,
    observe_inventory=installed_inventory,
    observe_vcs=installed_vcs,
):
    """Bind settings, config, model paths and code to one externally pinned identity."""
    try:
        files = dict(files)
        root = Path(__file__).resolve().parents[2]
        required = {"code/" + relative: root / relative for relative in CODE_FILES}
        if diagnostic_root is not None:
            relative = "services/candidate_i/region_diagnostics.py"
            required["code/" + relative] = root / relative
        required.update({"model/gdino/" + name: gdino_snapshot_path / name for name in GDINO_FILES})
        required["model/sam"] = sam_checkpoint_path
        if any(files.get(name) != path for name, path in required.items()):
            raise ValueError("paths must match the imported code and fixed model manifests")
        config = freeze_config(
            json.loads(files["config"].read_text()), lock_bytes=files["lock"].read_bytes()
        )
        profile = json.loads(files["runtime_profile"].read_text())

        def actual_runtime():
            return {
                "python": platform.python_version(),
                "machine": platform.machine(),
                "device": config.data["device"],
                "dtype": profile["dtype"],
                "operator_fallback": os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK"),
            }

        ready = VerifiedReadiness(
            manifest,
            files,
            observe_inventory=observe_inventory,
            observe_vcs=observe_vcs,
            observe_runtime=actual_runtime,
        )
        if not ready() or config.data["python_version"] != platform.python_version():
            raise ValueError("runtime identity mismatch")
        installed = set(observe_inventory())
        if any(
            name + "==" + version not in installed
            for name, version in config.data["dependencies"].items()
        ):
            raise ValueError("frozen config dependencies mismatch")
        settings = ServiceSettings(
            ready.extractor_fingerprint,
            WireLimits(
                profile["max_decoded_pixels"],
                profile["max_region_count"],
                profile["max_response_bytes"],
            ),
            runtime_root,
        )
        binding = CandidateIBinding(
            config=config,
            expected_extractor_fingerprint=ready.extractor_fingerprint,
            gdino_snapshot_path=gdino_snapshot_path,
            sam_checkpoint_path=sam_checkpoint_path,
            gdino_allowed_files=GDINO_FILES,
        )
        recorder = None
        if diagnostic_root is not None:
            from services.candidate_i.region_diagnostics import ObservedBinding, RegionDiagnostics

            recorder = RegionDiagnostics(diagnostic_root)
            binding = ObservedBinding(binding, recorder)
        app = create_app(settings, binding, ready_check=ready)
        app.state.localization_diagnostics = recorder
        return app
    except Exception:  # noqa: BLE001 - bootstrap errors cannot expose private state.
        raise NailProcessingError("MODEL_NOT_READY") from None
