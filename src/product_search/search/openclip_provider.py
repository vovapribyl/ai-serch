from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import open_clip
import torch
from PIL import Image

from product_search.search.model_manifest import read_manifest, verify_manifest
from product_search.search.providers import normalize_embedding

OPENCLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
OPENCLIP_STD = (0.26862954, 0.26130258, 0.27577711)


class OpenClipImageProvider:
    model_key = "openclip_b32"
    embedding_dim: int

    def __init__(
        self,
        revision: str,
        model_path: Path,
        embedding_dim: int = 512,
        *,
        loader: Callable[..., object] = open_clip.create_model_and_transforms,
        device: str = "cpu",
    ) -> None:
        self.revision = revision
        self.embedding_dim = embedding_dim
        manifest = read_manifest(model_path)
        verify_manifest(model_path, manifest)
        weights = model_path / "open_clip_model.safetensors"
        if not weights.is_file() or weights.is_symlink():
            raise ValueError("OpenCLIP safetensors artifact is unavailable.")
        model, _, preprocess = loader(
            "ViT-B-32",
            pretrained=str(weights),
            device="cpu",
            weights_only=True,
            image_mean=OPENCLIP_MEAN,
            image_std=OPENCLIP_STD,
        )
        self._device = device
        self._model = model.visual
        del model  # Release unused text weights before copying the image branch to MPS.
        self._model = self._model.to(device).eval()
        self._preprocess = preprocess

    def encode_image(self, image: Image.Image) -> tuple[float, ...]:
        tensor = self._preprocess(image.convert("RGB")).unsqueeze(0).to(self._device)
        with torch.inference_mode():
            vector = self._model(tensor)
        return normalize_embedding(
            vector.squeeze(0).detach().cpu().tolist(), expected_dim=self.embedding_dim
        )
