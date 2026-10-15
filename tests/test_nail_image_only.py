"""Model-free regression: keep the exact image branch, never move the text parent."""

import importlib.util
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from product_search.search.model_manifest import build_manifest, write_manifest


class Tensor:
    def unsqueeze(self, _):
        return self

    def to(self, _):
        return self

    def squeeze(self, _):
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return [3.0, 4.0]


class Vision:
    def __init__(self, kind):
        self.kind = kind
        self.devices = []
        self.evaluated = False

    def to(self, device):
        self.devices.append(device)
        return self

    def eval(self):
        self.evaluated = True
        return self

    def __call__(self, *args, **kwargs):
        assert self.evaluated
        return Tensor() if self.kind == "openclip" else SimpleNamespace(pooler_output=Tensor())


def load_module(monkeypatch, name, loader):
    import sys

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext))
    monkeypatch.setitem(
        sys.modules, "open_clip", SimpleNamespace(create_model_and_transforms=loader)
    )
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoModel=SimpleNamespace(from_pretrained=loader),
            AutoImageProcessor=SimpleNamespace(
                from_pretrained=lambda *a, **k: lambda **kw: {"pixel_values": Tensor()}
            ),
        ),
    )
    path = Path(__file__).parents[1] / "src/product_search/search" / (name + ".py")
    spec = importlib.util.spec_from_file_location("model_free_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("kind", ["openclip", "siglip", "dino"])
def test_only_original_image_branch_is_retained_and_moved(monkeypatch, tmp_path, kind):
    import gc
    import weakref

    vision = Vision("openclip" if kind == "openclip" else "transformers")
    parent_refs = []
    calls = []

    class Parent:
        def __init__(self):
            if kind == "openclip":
                self.visual = vision
            else:
                self.vision_model = vision
            self.unused_text = object()

        def to(self, device):
            calls.append(("parent_transfer", device))
            return self

        def eval(self):
            return self

        def encode_image(self, tensor, normalize=False):
            return self.visual(tensor)

    def loader(*args, **kwargs):
        calls.append(kwargs)
        model = vision if kind == "dino" else Parent()
        if kind != "dino":
            parent_refs.append(weakref.ref(model))
        return (model, None, lambda im: Tensor()) if kind == "openclip" else model

    if kind == "openclip":
        (tmp_path / "open_clip_model.safetensors").write_bytes(b"fixture")
        write_manifest(tmp_path, build_manifest(tmp_path))
        module = load_module(monkeypatch, "openclip_provider", loader)
        provider = module.OpenClipImageProvider(
            "revision", tmp_path, 2, loader=loader, device="mps"
        )
    else:
        module = load_module(monkeypatch, "transformers_provider", loader)
        provider = module.TransformersImageProvider(
            kind,
            "revision",
            tmp_path,
            2,
            processor_loader=lambda *a, **k: lambda **kw: {"pixel_values": Tensor()},
            model_loader=loader,
            device="mps",
        )
    gc.collect()
    assert all(ref() is None for ref in parent_refs)
    assert provider._model is vision
    assert vision.devices == ["mps"]
    assert vision.evaluated
    assert not any(isinstance(call, tuple) for call in calls)
    if kind == "openclip":
        assert calls[0]["device"] == "cpu"
    assert provider.encode_image(Image.new("RGB", (1, 1))) == (0.6, 0.8)
