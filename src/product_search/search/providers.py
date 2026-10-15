from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from PIL import Image


class EmbeddingProviderError(ValueError):
    """Модель вернула вектор, непригодный для сохранения или поиска."""


class EmbeddingProvider(Protocol):
    model_key: str
    revision: str
    embedding_dim: int

    def encode_image(self, image: Image.Image.Image) -> Sequence[float]: ...


def normalize_embedding(values: Sequence[float], *, expected_dim: int) -> tuple[float, ...]:
    """Проверяет и L2-нормализует полный выход одного model provider."""
    if expected_dim <= 0 or len(values) != expected_dim:
        raise EmbeddingProviderError("Embedding имеет недопустимую размерность.")
    vector = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingProviderError("Embedding содержит не конечное число.")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise EmbeddingProviderError("Embedding не может быть нулевым.")
    return tuple(value / norm for value in vector)
