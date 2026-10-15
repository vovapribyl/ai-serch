from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import file_digest, sha256
from pathlib import Path


class ModelManifestError(ValueError):
    """Локальный snapshot модели неполный, изменён или небезопасен."""


@dataclass(frozen=True)
class ManifestEntry:
    relative_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelManifest:
    entries: tuple[ManifestEntry, ...]

    @property
    def sha256(self) -> str:
        content = "".join(
            f"{item.relative_path}\t{item.size}\t{item.sha256}\n" for item in self.entries
        )
        return sha256(content.encode()).hexdigest()


def build_manifest(root: Path) -> ModelManifest:
    root = _safe_root(root)
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ModelManifestError("Snapshot модели не может содержать symlink.")
        if path.is_file() and path.name != "manifest.json":
            entries.append(
                ManifestEntry(path.relative_to(root).as_posix(), path.stat().st_size, _digest(path))
            )
    if not entries:
        raise ModelManifestError("Snapshot модели не содержит файлов.")
    return ModelManifest(tuple(entries))


def verify_manifest(root: Path, expected: ModelManifest) -> ModelManifest:
    actual = build_manifest(root)
    if actual != expected:
        raise ModelManifestError("Manifest snapshot модели не совпадает.")
    return actual


def write_manifest(root: Path, manifest: ModelManifest) -> None:
    path = _safe_root(root) / "manifest.json"
    path.write_text(
        json.dumps(
            {"entries": [entry.__dict__ for entry in manifest.entries], "sha256": manifest.sha256},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def read_manifest(root: Path) -> ModelManifest:
    path = _safe_root(root) / "manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = ModelManifest(tuple(ManifestEntry(**entry) for entry in payload["entries"]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ModelManifestError("Saved manifest модели недоступен или повреждён.") from error
    if payload.get("sha256") != manifest.sha256:
        raise ModelManifestError("Saved manifest имеет неверный digest.")
    return manifest


def _safe_root(root: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ModelManifestError("Корень snapshot модели должен быть обычным каталогом.")
    return root.resolve(strict=True)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()
