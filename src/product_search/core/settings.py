from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from product_search.core.database_url import database_url_from_environment
from product_search.core.runtime_safety import is_loopback_host, validate_runtime_directory


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_url: str
    data_dir: Path
    repository_root: Path

    @classmethod
    def from_environment(cls, *, repository_root: Path) -> Settings:
        host = os.environ.get("MVP_HOST", "127.0.0.1")
        if not is_loopback_host(host):
            raise ValueError("MVP_HOST должен быть loopback-адресом: 127.0.0.1 или ::1.")

        raw_data_dir = os.environ.get("MVP_DATA_DIR")
        if not raw_data_dir:
            raise ValueError("Задайте абсолютный MVP_DATA_DIR вне репозитория.")
        data_dir = validate_runtime_directory(Path(raw_data_dir), repository_root=repository_root)

        return cls(
            host=host,
            port=int(os.environ.get("MVP_PORT", "8000")),
            database_url=database_url_from_environment(),
            data_dir=data_dir,
            repository_root=repository_root.resolve(),
        )
