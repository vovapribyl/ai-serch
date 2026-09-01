from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class TemporaryFileCleanupError(RuntimeError):
    """Временный файл нельзя было безопасно удалить."""


class LocalTemporaryImageStorage:
    """Временное файловое хранилище с очисткой при успехе и исключении."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextmanager
    def temporary_file(self, original_name: str) -> Iterator[Path]:
        suffix = Path(original_name).suffix
        session_dir = Path(tempfile.mkdtemp(prefix="query-", dir=self._root))
        file_path = session_dir / f"upload{suffix}"
        try:
            yield file_path
        finally:
            try:
                shutil.rmtree(session_dir)
            except OSError as error:
                raise TemporaryFileCleanupError(
                    f"Не удалось удалить временный query-каталог: {session_dir.name}"
                ) from error
