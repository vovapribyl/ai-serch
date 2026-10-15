from dataclasses import dataclass
from pathlib import Path

from product_search.infrastructure.nail_runtime import validate_runtime_root
from product_search.infrastructure.nail_wire import WireLimits
from product_search.search.nail_contracts import LocalizationProfile


@dataclass(frozen=True)
class ServiceSettings:
    extractor_fingerprint: str
    limits: WireLimits
    runtime_root: Path

    def __post_init__(self) -> None:
        LocalizationProfile(self.extractor_fingerprint)
        if not isinstance(self.limits, WireLimits):
            raise TypeError("Explicit wire limits required")
        validate_runtime_root(self.runtime_root)
