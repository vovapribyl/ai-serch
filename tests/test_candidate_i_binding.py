from __future__ import annotations

from pathlib import Path

import pytest

from experiments.nail_localization.config import FrozenConfig
from product_search.search.nail_contracts import (
    LocalizationProfile,
    NailProcessingError,
    RgbImage,
)
from services.candidate_i.binding import CandidateIBinding

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


def frozen_config() -> FrozenConfig:
    return FrozenConfig(
        data={
            "prompt": {"text": "press-on nails"},
            "thresholds": {"box": 0.25, "text": 0.2, "mask": 0.5},
            "device": "mps",
            "mps_operator_fallback_enabled": False,
        },
        config_fingerprint="sha256:" + "1" * 64,
        dependency_lock_fingerprint="sha256:" + "2" * 64,
    )


def model_paths(tmp_path: Path) -> tuple[Path, Path]:
    gdino = tmp_path / "gdino"
    gdino.mkdir()
    for name in GDINO_FILES:
        (gdino / name).write_bytes(b"synthetic")
    sam = tmp_path / "sam2.1_hiera_small.pt"
    sam.write_bytes(b"synthetic")
    return gdino, sam


def test_binding_is_lazy_and_passes_external_allowlisted_paths(tmp_path: Path) -> None:
    gdino, sam = model_paths(tmp_path)
    calls: list[tuple[str, object]] = []

    class FakeLangSAM:
        def __init__(self, **kwargs: object) -> None:
            calls.append(("init", kwargs))

        def predict(self, **kwargs: object) -> list[dict[str, object]]:
            calls.append(("predict", kwargs))
            return [
                {
                    "boxes": [[0.0, 0.0, 2.0, 2.0]],
                    "masks": [[[1, 0], [0, 1]]],
                    "scores": [0.9],
                    "labels": ["nail"],
                }
            ]

    def fake_import(name: str) -> object:
        calls.append(("import", name))
        return type("Module", (), {"LangSAM": FakeLangSAM})

    binding = CandidateIBinding(
        config=frozen_config(),
        expected_extractor_fingerprint="a" * 64,
        gdino_snapshot_path=gdino,
        sam_checkpoint_path=sam,
        gdino_allowed_files=GDINO_FILES,
        import_module=fake_import,
    )

    assert calls == []
    result = binding(RgbImage(2, 2, b"\x00\x00\x00" * 4), LocalizationProfile("a" * 64))

    assert result.status == "OK"
    assert result.regions[0].ordinal == 1
    assert result.regions[0].mask.pixels == b"\xff\x00\x00\xff"
    assert calls[0] == ("import", "lang_sam")
    assert calls[1][0] == "init"
    assert calls[1][1]["gdino_model_ckpt_path"] == str(gdino)
    assert calls[1][1]["sam_ckpt_path"] == str(sam)


def test_profile_mismatch_is_rejected_before_model_import(tmp_path: Path) -> None:
    gdino, sam = model_paths(tmp_path)
    imported: list[str] = []
    binding = CandidateIBinding(
        config=frozen_config(),
        expected_extractor_fingerprint="a" * 64,
        gdino_snapshot_path=gdino,
        sam_checkpoint_path=sam,
        gdino_allowed_files=GDINO_FILES,
        import_module=lambda name: imported.append(name),
    )

    with pytest.raises(NailProcessingError, match="PROFILE_MISMATCH"):
        binding(RgbImage(1, 1, b"\x00\x00\x00"), LocalizationProfile("b" * 64))

    assert imported == []


def test_empty_detector_maps_to_no_nails(tmp_path: Path) -> None:
    gdino, sam = model_paths(tmp_path)

    class FakeLangSAM:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def predict(self, **kwargs: object) -> list[dict[str, object]]:
            del kwargs
            return [{"boxes": [], "masks": [], "scores": [], "labels": []}]

    binding = CandidateIBinding(
        config=frozen_config(),
        expected_extractor_fingerprint="a" * 64,
        gdino_snapshot_path=gdino,
        sam_checkpoint_path=sam,
        gdino_allowed_files=GDINO_FILES,
        import_module=lambda name: type("Module", (), {"LangSAM": FakeLangSAM}),
    )

    result = binding(RgbImage(1, 1, b"\x00\x00\x00"), LocalizationProfile("a" * 64))

    assert result.status == "NO_NAILS"
    assert result.regions == ()


def test_invalid_allowlist_becomes_sanitized_model_error(tmp_path: Path) -> None:
    gdino, sam = model_paths(tmp_path)
    (gdino / "unexpected.bin").write_bytes(b"synthetic")
    binding = CandidateIBinding(
        config=frozen_config(),
        expected_extractor_fingerprint="a" * 64,
        gdino_snapshot_path=gdino,
        sam_checkpoint_path=sam,
        gdino_allowed_files=GDINO_FILES,
        import_module=lambda name: (_ for _ in ()).throw(AssertionError(name)),
    )

    with pytest.raises(NailProcessingError, match="MODEL_ERROR"):
        binding(RgbImage(1, 1, b"\x00\x00\x00"), LocalizationProfile("a" * 64))


def test_binding_rejects_cpu_or_mps_fallback_profile(tmp_path: Path) -> None:
    gdino, sam = model_paths(tmp_path)
    for device, fallback in (("cpu", False), ("mps", True)):
        config = frozen_config()
        body = dict(config.data)
        body.update(device=device, mps_operator_fallback_enabled=fallback)
        with pytest.raises(NailProcessingError, match="PROFILE_MISMATCH"):
            CandidateIBinding(
                config=FrozenConfig(
                    body, config.config_fingerprint, config.dependency_lock_fingerprint
                ),
                expected_extractor_fingerprint="a" * 64,
                gdino_snapshot_path=gdino,
                sam_checkpoint_path=sam,
                gdino_allowed_files=GDINO_FILES,
                import_module=lambda name: name,
            )


def test_binding_honors_frozen_candidate_i_large_box_filter(tmp_path: Path) -> None:
    gdino, sam = model_paths(tmp_path)
    base = frozen_config()
    body = dict(base.data)
    body["postprocessing"] = {
        "max_detection_box_area_ratio": 0.3,
        "packaging_roi": {
            "min_parent_area_ratio": 0.1,
            "max_parent_area_ratio": 0.5,
            "padding_ratio": 0.1,
            "min_aspect_ratio": 0.9,
            "max_aspect_ratio": 1.25,
        },
    }

    class FakeLangSAM:
        def __init__(self, **kwargs):
            pass

        def predict(self, **kwargs):
            return [
                {
                    "boxes": [[0, 0, 2, 2]],
                    "masks": [[[1, 1], [1, 1]]],
                    "scores": [0.9],
                    "labels": ["nail"],
                }
            ]

    binding = CandidateIBinding(
        config=FrozenConfig(body, base.config_fingerprint, base.dependency_lock_fingerprint),
        expected_extractor_fingerprint="a" * 64,
        gdino_snapshot_path=gdino,
        sam_checkpoint_path=sam,
        gdino_allowed_files=GDINO_FILES,
        import_module=lambda name: type("Module", (), {"LangSAM": FakeLangSAM}),
    )
    result = binding(RgbImage(2, 2, b"\0" * 12), LocalizationProfile("a" * 64))
    assert result.status == "NO_NAILS"
    assert result.regions == ()


def test_frozen_torch_options_are_applied_before_loading_once(tmp_path):
    gdino, sam = model_paths(tmp_path)
    base = frozen_config()
    body = dict(base.data)
    body["deterministic"] = {"seed": 7, "deterministic_algorithms": True}
    state = {}

    class Torch:
        float32 = "float32"

        @staticmethod
        def set_default_dtype(value):
            state["dtype"] = value

        @staticmethod
        def manual_seed(value):
            state["seed"] = value

        @staticmethod
        def use_deterministic_algorithms(value):
            state["deterministic"] = value

    class FakeLangSAM:
        def __init__(self, **kwargs):
            assert state == {"dtype": "float32", "seed": 7, "deterministic": True}

        def predict(self, **kwargs):
            return [{"boxes": [], "masks": [], "scores": [], "labels": []}]

    def importer(name):
        if name == "torch":
            return Torch
        return type("Module", (), {"LangSAM": FakeLangSAM})

    binding = CandidateIBinding(
        config=FrozenConfig(body, base.config_fingerprint, base.dependency_lock_fingerprint),
        expected_extractor_fingerprint="a" * 64,
        gdino_snapshot_path=gdino, sam_checkpoint_path=sam, gdino_allowed_files=GDINO_FILES,
        import_module=importer,
    )
    assert state == {}
    result = binding(RgbImage(1, 1, b"\0" * 3), LocalizationProfile("a" * 64))
    assert result.status == "NO_NAILS"
    state["seed"] = 8
    assert binding(RgbImage(1, 1, b"\0" * 3), LocalizationProfile("a" * 64)).status == "NO_NAILS"
    assert state["seed"] == 8
