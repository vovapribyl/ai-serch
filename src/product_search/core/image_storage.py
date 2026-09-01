from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol


class ImageStorage(Protocol):
    """Контракт временного хранения загружаемого изображения."""

    def temporary_file(self, original_name: str) -> AbstractContextManager[Path]: ...
