from types import SimpleNamespace

import pytest

from product_search.infrastructure.nail_build_runner import BuildStop
from product_search.infrastructure.nail_native_bindings import native_factories, native_services
from product_search.search.nail_contracts import ModelIdentity

MODELS = (
    ModelIdentity(
        "openclip_b32",
        "1a25a446712ba5ee05982a381eed697ef9b435cf",
        "7daa2142c71b4c9b0ec0555361845dc78fbb0dbce6bed64ca784ae853404d67d",
        512,
    ),
    ModelIdentity(
        "dinov2_b14",
        "f9e44c814b77203eaa57a6bdbbd535f21ede1415",
        "ecb704699963bfe8bb17f8defd3792daa26cf0da822032b796f6f5a40d606783",
        768,
    ),
    ModelIdentity(
        "siglip2_b16_224",
        "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2",
        "45f047affe3c7c58e6789db142ae73b40096a0207f1417e3f976d3a9d15969e9",
        768,
    ),
)


def test_native_factory_creation_has_no_sdk_import_and_default_permit_denies_load(tmp_path):
    imports = []
    factories = native_factories(tmp_path, MODELS, importer=lambda name: imports.append(name))
    assert set(factories) == {"openclip_b32", "dinov2_b14", "siglip2_b16_224"} and imports == []
    for factory in factories.values():
        with pytest.raises(BuildStop):
            factory()
    assert imports == []


@pytest.mark.parametrize("key", ["openclip_b32", "dinov2_b14", "siglip2_b16_224"])
def test_admitted_factory_uses_pinned_revision_local_root_dimensions_and_mps(tmp_path, key):
    calls = []

    def construct(*args, **kwargs):
        calls.append((args, kwargs))
        return "loaded-test-double"

    def importer(name):
        return SimpleNamespace(OpenClipImageProvider=construct, TransformersImageProvider=construct)

    factories = native_factories(
        tmp_path, MODELS, permit=lambda: True, importer=importer, verifier=lambda *args: None
    )
    assert calls == []
    assert factories[key]() == "loaded-test-double"
    args, kwargs = calls[0]
    assert kwargs["device"] == "mps"
    model = next(m for m in MODELS if m.model_key == key)
    if key == "openclip_b32":
        assert args == (model.revision, tmp_path / key)
    else:
        assert args == (key, model.revision, tmp_path / key, 768)


def test_unknown_or_changed_model_identity_is_denied_before_import(tmp_path):
    imports = []
    with pytest.raises(BuildStop):
        native_factories(tmp_path, MODELS[:-1], importer=lambda name: imports.append(name))
    assert imports == []


def test_native_build_and_query_use_real_adapters_without_sdk_or_sql_side_effects(tmp_path):
    imports = []
    for name in ("source", "artifacts", "queries", "runtime"):
        (tmp_path / name).mkdir(mode=0o700)
    ports = native_services(
        target_descriptor=tmp_path / "not-read-in-constructor.json",
        target_sha256="a" * 64,
        model_root=tmp_path / "models",
        models=MODELS,
        source_root=tmp_path / "source",
        source_names={},
        artifact_root=tmp_path / "artifacts",
        query_root=tmp_path / "queries",
        runtime_root=tmp_path / "runtime",
        base_url="http://127.0.0.1:12345",
        extractor_fingerprint="b" * 64,
        representation_fingerprint="c" * 64,
        budget=SimpleNamespace(stopped=False, admit=lambda: None),
        permit=lambda: False,
        importer=lambda name: imports.append(name),
    )
    assert ports.catalog.__class__.__name__ == "ReadOnlyCatalog"
    assert ports.build.__class__.__name__ == "AdmittedBuild"
    assert ports.search.__class__.__name__ == "NailSearchService"
    assert ports.query_images.__class__.__name__ == "NailImageStore"
    assert imports == []


def test_closed_permit_prevents_i_http_request_and_admission(tmp_path, monkeypatch):
    from product_search.infrastructure.nail_ml_adapters import HttpNailLocalizationAdapter

    for name in ("source", "artifacts", "queries", "runtime"):
        (tmp_path / name).mkdir(mode=0o700)
    calls = []
    monkeypatch.setattr(HttpNailLocalizationAdapter, "localize", lambda *args: calls.append("POST"))
    ports = native_services(
        target_descriptor=tmp_path / "unused.json",
        target_sha256="a" * 64,
        model_root=tmp_path / "models",
        models=MODELS,
        source_root=tmp_path / "source",
        source_names={},
        artifact_root=tmp_path / "artifacts",
        query_root=tmp_path / "queries",
        runtime_root=tmp_path / "runtime",
        base_url="http://127.0.0.1:12345",
        extractor_fingerprint="b" * 64,
        representation_fingerprint="c" * 64,
        budget=SimpleNamespace(stopped=False, admit=lambda: calls.append("ADMIT")),
        permit=lambda: False,
    )
    with pytest.raises(BuildStop):
        ports.localization.localize(None, None)
    assert calls == []


def test_model_free_i_server_exposes_readiness_but_never_calls_post_binding(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from services.candidate_i.health_entry import health_application

    calls = []
    app = FastAPI()

    @app.get("/health/ready")
    def ready():
        return {"ready": True}

    @app.post("/v1/localizations")
    def predict():
        calls.append("SDK")
        return {}

    assembly = {
        "manifest": {},
        "files": {},
        "runtime_root": str(tmp_path),
        "gdino_snapshot_path": str(tmp_path),
        "sam_checkpoint_path": str(tmp_path / "dummy"),
    }
    guarded = health_application(assembly, factory=lambda *args, **kwargs: app)
    with TestClient(guarded) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.post("/v1/localizations").status_code == 403
    assert calls == []


def test_native_execute_default_does_not_begin_build_or_allocate_sdk(tmp_path):
    imports = []
    writes = []
    for name in ("source", "artifacts", "queries", "runtime"):
        (tmp_path / name).mkdir(mode=0o700)
    ports = native_services(
        target_descriptor=tmp_path / "unused.json",
        target_sha256="a" * 64,
        model_root=tmp_path / "models",
        models=MODELS,
        source_root=tmp_path / "source",
        source_names={},
        artifact_root=tmp_path / "artifacts",
        query_root=tmp_path / "queries",
        runtime_root=tmp_path / "runtime",
        base_url="http://127.0.0.1:12345",
        extractor_fingerprint="b" * 64,
        representation_fingerprint="c" * 64,
        budget=SimpleNamespace(stopped=False, admit=lambda: imports.append("ADMIT")),
        permit=lambda: False,
    )
    ports.build.execute = lambda *args, **kwargs: writes.append("BUILDING")
    with pytest.raises(BuildStop):
        ports.execute_build(None, ())
    assert writes == [] and imports == []


@pytest.mark.parametrize("status", ["BUILDING", "READY"])
def test_query_context_checks_pinned_id_corpus_fingerprint_and_ready_before_inputs(status):
    from contextlib import contextmanager

    from product_search.infrastructure.nail_native_bindings import ready_query_context
    from product_search.search.nail_contracts import (
        EmbeddingProfile,
        NailProcessingError,
        SearchProfile,
    )

    runtime = SearchProfile(
        "c" * 64, EmbeddingProfile(tuple((m.model_key, m.revision) for m in MODELS)), 16384
    )

    @contextmanager
    def connect():
        yield SimpleNamespace(
            execute=lambda *args: SimpleNamespace(fetchone=lambda: (4, "c" * 64, status))
        )

    ports = SimpleNamespace(target=SimpleNamespace(connect=connect), runtime=runtime)
    context = ready_query_context(ports, "pinned-rep", 4)
    if status == "BUILDING":
        with pytest.raises(NailProcessingError):
            context(None)
    else:
        value = context(None)
        assert value.representation_id == "pinned-rep" and value.corpus_version_id == 4
    with pytest.raises(NailProcessingError):
        context("different-rep")


def test_direct_core_build_catalog_and_publish_paths_cannot_bypass_closed_entry(
    tmp_path, monkeypatch
):
    from product_search.infrastructure.nail_repository import PostgresNailCatalog
    from product_search.search.nail_contracts import BuildIdentity, BuildPhoto, PhotoInput

    writes = []
    monkeypatch.setattr(PostgresNailCatalog, "begin_build", lambda *args: writes.append("BUILDING"))
    for name in ("source", "artifacts", "queries", "runtime"):
        (tmp_path / name).mkdir(mode=0o700)
    ports = native_services(
        target_descriptor=tmp_path / "unused.json",
        target_sha256="a" * 64,
        model_root=tmp_path / "models",
        models=MODELS,
        source_root=tmp_path / "source",
        source_names={},
        artifact_root=tmp_path / "artifacts",
        query_root=tmp_path / "queries",
        runtime_root=tmp_path / "runtime",
        base_url="http://127.0.0.1:12345",
        extractor_fingerprint="b" * 64,
        representation_fingerprint="c" * 64,
        budget=SimpleNamespace(stopped=False, admit=lambda: None),
        permit=lambda: False,
    )
    identity = BuildIdentity(
        "fake-representation",
        1,
        "c" * 64,
        "d" * 64,
        (("crop_profile", "mask_bbox_white_v1"),),
        MODELS,
    )
    items = (BuildPhoto("fake-photo", 1, PhotoInput(1, "e" * 32, "f" * 64)),)
    with pytest.raises((BuildStop, AttributeError)):
        ports.build.execute(identity, items, ports.runtime)
    assert writes == []
    assert not hasattr(ports.catalog, "begin_build") and not hasattr(ports.catalog, "publish")
    assert not hasattr(ports.build, "publish") and not hasattr(ports.search.catalog, "publish")


def test_changed_local_model_manifest_is_rejected_before_sdk_import(tmp_path):
    imports = []
    factories = native_factories(
        tmp_path, MODELS, permit=lambda: True, importer=lambda name: imports.append(name)
    )
    with pytest.raises(BuildStop):
        factories["openclip_b32"]()
    assert imports == []
