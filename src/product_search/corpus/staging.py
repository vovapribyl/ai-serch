from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from product_search.corpus.xlsx_reader import ParsedProduct


class CorpusStagingError(RuntimeError):
    """Не удалось подготовить полный набор файлов для новой версии корпуса."""


class CorpusStagingCleanupError(CorpusStagingError):
    """Staging не удалось удалить после ошибки записи."""


@dataclass(frozen=True)
class StagedProduct:
    product_id: str
    source_row: int
    category: str
    image_path: Path
    image_sha256: str
    image_format: str


@dataclass(frozen=True)
class CorpusStage:
    directory: Path
    products: tuple[StagedProduct, ...]


def stage_products(
    products: list[ParsedProduct], data_dir: Path, operation_id: str | None = None
) -> CorpusStage:
    staging_root = data_dir / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    stage_directory = staging_root / (operation_id or uuid.uuid4().hex)
    if stage_directory.exists():
        raise CorpusStagingError("Для операции уже существует staging-каталог.")
    stage_directory.mkdir()
    staged_products: list[StagedProduct] = []
    try:
        for product in products:
            image_path = stage_directory / f"{product.product_id}.bin"
            _write_image(image_path, product.primary_image)
            staged_products.append(
                StagedProduct(
                    product_id=product.product_id,
                    source_row=product.source_row,
                    category=product.category,
                    image_path=image_path,
                    image_sha256=sha256(product.primary_image).hexdigest(),
                    image_format=_image_format(product.primary_image),
                )
            )
    except OSError as error:
        try:
            shutil.rmtree(stage_directory)
        except OSError as cleanup_error:
            raise CorpusStagingCleanupError(
                "Не удалось удалить неполный staging-каталог."
            ) from cleanup_error
        raise CorpusStagingError("Не удалось записать все изображения в staging.") from error
    return CorpusStage(stage_directory, tuple(staged_products))


def discard_stage(stage: CorpusStage) -> None:
    if stage.directory.exists():
        shutil.rmtree(stage.directory)


def _write_image(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def _image_format(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if content.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    return "UNKNOWN"
