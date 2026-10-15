"""Lazy bridge from the HTTP core DTOs to the existing LangSAM adapter."""

from collections.abc import Callable
from importlib import import_module as _import_module
from pathlib import Path

from PIL import Image

from experiments.nail_localization.config import FrozenConfig
from experiments.nail_localization.langsam_adapter import LangSAMAdapter, LazyLangSAMClient
from experiments.nail_localization.roi_localizer import TwoPassRoiLocalizer
from product_search.search.nail_contracts import (
    BinaryMask,
    LocalizationProfile,
    LocalizedRegion,
    NailLocalization,
    NailProcessingError,
    RgbImage,
)


class CandidateIBinding:
    """Keep model imports lazy and translate the established experiment contract."""

    def __init__(
        self,
        *,
        config: FrozenConfig,
        expected_extractor_fingerprint: str,
        gdino_snapshot_path: Path,
        sam_checkpoint_path: Path,
        gdino_allowed_files: frozenset[str],
        import_module: Callable[[str], object] = _import_module,
    ) -> None:
        if not isinstance(config, FrozenConfig):
            raise TypeError("frozen config required")
        LocalizationProfile(expected_extractor_fingerprint)
        if (
            config.data.get("device") != "mps"
            or config.data.get("mps_operator_fallback_enabled") is not False
        ):
            raise NailProcessingError("PROFILE_MISMATCH")
        self._config = config
        self._expected_fingerprint = expected_extractor_fingerprint

        def initialize_runtime():
            torch = import_module("torch")
            torch.set_default_dtype(torch.float32)
            options = config.data["deterministic"]
            torch.manual_seed(options["seed"])
            torch.use_deterministic_algorithms(options["deterministic_algorithms"])

        self._client = LazyLangSAMClient(
            device="mps",
            gdino_snapshot_path=gdino_snapshot_path,
            sam_checkpoint_path=sam_checkpoint_path,
            gdino_allowed_files=gdino_allowed_files,
            initialize_runtime=initialize_runtime if "deterministic" in config.data else None,
            import_module=import_module,
        )
        self._adapter = LangSAMAdapter(self._client)
        if "packaging_roi" in config.data.get("postprocessing", {}):
            self._adapter = TwoPassRoiLocalizer(self._adapter)

    def __call__(self, image: RgbImage, profile: LocalizationProfile) -> NailLocalization:
        if profile.extractor_fingerprint != self._expected_fingerprint:
            raise NailProcessingError("PROFILE_MISMATCH")
        pil_image = Image.frombytes("RGB", (image.width, image.height), image.pixels)
        result = self._adapter.localize(pil_image, self._config)
        if result.status == "SUCCESS":
            regions = tuple(
                LocalizedRegion(
                    ordinal=index,
                    label=detection.label,
                    confidence=detection.confidence,
                    detector_box_xyxy=detection.box_xyxy,
                    mask=BinaryMask(
                        detection.mask.width,
                        detection.mask.height,
                        detection.mask.pixels,
                    ),
                )
                for index, detection in enumerate(result.detections, start=1)
            )
            return NailLocalization("OK", regions)
        if result.status == "LOCALIZATION_FAILED" and result.error_code == "DETECTOR_NO_MATCH":
            return NailLocalization("NO_NAILS", ())
        if result.error_code == "INVALID_MODEL_OUTPUT":
            raise NailProcessingError("INVALID_OUTPUT")
        raise NailProcessingError(result.error_code or "MODEL_ERROR")
