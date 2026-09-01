from __future__ import annotations

import ipaddress
import os
import stat
from pathlib import Path


class UnsafeRuntimeDirectoryError(ValueError):
    """Рабочий каталог не соответствует правилам локального контура."""


def is_loopback_host(host: str) -> bool:
    """Разрешает приложение только на loopback-интерфейсе."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_runtime_directory(
    directory: Path, *, repository_root: Path, expected_uid: int | None = None
) -> Path:
    """Проверяет, что локальные рабочие файлы не попадут в репозиторий или другим пользователям."""
    expanded_directory = directory.expanduser()
    if not expanded_directory.is_absolute():
        raise UnsafeRuntimeDirectoryError("Рабочий каталог должен быть задан абсолютным путём.")
    resolved_directory = expanded_directory.resolve()
    resolved_repository = repository_root.expanduser().resolve()

    if resolved_directory == resolved_repository or resolved_repository in resolved_directory.parents:
        raise UnsafeRuntimeDirectoryError("Рабочий каталог не может находиться внутри репозитория.")

    resolved_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    details = resolved_directory.stat()
    mode = stat.S_IMODE(details.st_mode)
    if mode & 0o077:
        raise UnsafeRuntimeDirectoryError(
            "У рабочего каталога небезопасные права: доступ группы и других пользователей запрещён."
        )
    owner_uid = os.geteuid() if expected_uid is None else expected_uid
    if details.st_uid != owner_uid:
        raise UnsafeRuntimeDirectoryError(
            "Рабочий каталог должен принадлежать учётной записи, запускающей MVP."
        )
    return resolved_directory
