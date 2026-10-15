from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

from product_search.search.providers import normalize_embedding


class TransformersImageProvider:
    """Offline image embedding provider for a local Transformers snapshot."""

    def __init__(
        self,
        model_key: str,
        revision: str,
        model_path: str | Path,
        embedding_dim: int,
        processor_loader: Callable[..., object] = AutoImageProcessor.from_pretrained,
        model_loader: Callable[..., object] = AutoModel.from_pretrained,
        device: str = "cpu",
    ) -> None:
        self.model_key = model_key
        self.revision = revision
        self.embedding_dim = embedding_dim
        self._device = device
        self._processor = processor_loader(str(model_path), local_files_only=True)
        model = model_loader(str(model_path), local_files_only=True)
        self._model = getattr(model, "vision_model", model)
        del model  # Retain DINO or the original SigLIP vision branch, without its text parent.
        self._model = self._model.to(device).eval()

    def encode_image(self, image: Image.Image) -> tuple[float, ...]:
        inputs = self._processor(images=image.convert("RGB"), return_tensors="pt")
        inputs = {name: value.to(self._device) for name, value in inputs.items()}
        with torch.inference_mode():
            output = self._model(**inputs)
        vector = getattr(output, "pooler_output", None)
        if vector is None:
            vector = output.last_hidden_state.mean(dim=1)
        return normalize_embedding(
            vector.squeeze(0).detach().cpu().tolist(), expected_dim=self.embedding_dim
        )
