"""Real lazy SDK/PostgreSQL/HTTP ports; preparation never imports model SDKs."""

from importlib import import_module
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

from product_search.infrastructure.nail_build_runner import (
    BuildStop,
    GuardedEmbedding,
    GuardedLocalization,
    ManifestImageStore,
    OwnedTarget,
    admitted_provider,
    run_admitted_build,
)
from product_search.infrastructure.nail_image_store import NailImageStore
from product_search.infrastructure.nail_ml_adapters import (
    ClientSettings,
    HttpNailLocalizationAdapter,
    NailEmbeddingAdapter,
)
from product_search.infrastructure.nail_query_runner import NailQueryRunner
from product_search.infrastructure.nail_repository import PostgresNailCatalog
from product_search.infrastructure.nail_runtime import FileLease
from product_search.infrastructure.nail_wire import WireLimits
from product_search.search.model_manifest import ModelManifestError, read_manifest, verify_manifest
from product_search.search.nail_catalog_build import NailCatalogBuildService
from product_search.search.nail_contracts import (
    DecodeProfile,
    EmbeddingProfile,
    LocalizationProfile,
    SearchProfile,
)
from product_search.search.nail_image_processor import NailImageProcessor
from product_search.search.nail_service import NailSearchService

MODEL_PINS = (
    (
        "openclip_b32",
        "1a25a446712ba5ee05982a381eed697ef9b435cf",
        "7daa2142c71b4c9b0ec0555361845dc78fbb0dbce6bed64ca784ae853404d67d",
        512,
    ),
    (
        "dinov2_b14",
        "f9e44c814b77203eaa57a6bdbbd535f21ede1415",
        "ecb704699963bfe8bb17f8defd3792daa26cf0da822032b796f6f5a40d606783",
        768,
    ),
    (
        "siglip2_b16_224",
        "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2",
        "45f047affe3c7c58e6789db142ae73b40096a0207f1417e3f976d3a9d15969e9",
        768,
    ),
)


def native_factories(model_root, models, *, permit=None, importer=None, verifier=None):
    actual = tuple((m.model_key, m.revision, m.manifest_sha256, m.dimension) for m in models)
    if actual != MODEL_PINS:
        raise BuildStop("MODEL_IDENTITY_MISMATCH")
    root = Path(model_root)
    importer = importer or import_module

    def verify_snapshot(path, expected_sha):
        try:
            manifest = read_manifest(path)
            if manifest.sha256 != expected_sha:
                raise BuildStop("MODEL_IDENTITY_MISMATCH")
            verify_manifest(path, manifest)
        except (ModelManifestError, OSError) as error:
            raise BuildStop("MODEL_SNAPSHOT_INVALID") from error

    verifier = verifier or verify_snapshot
    factories = {}
    for key, revision, sha, dim in MODEL_PINS:

        def load(key=key, revision=revision, sha=sha, dim=dim):
            if permit is None or permit() is not True:
                raise BuildStop("NATIVE_RUN_NOT_ADMITTED")
            verifier(root / key, sha)
            if key == "openclip_b32":
                module = importer("product_search.search.openclip_provider")
                return module.OpenClipImageProvider(revision, root / key, device="mps")
            module = importer("product_search.search.transformers_provider")
            return module.TransformersImageProvider(key, revision, root / key, dim, device="mps")

        factories[key] = load
    return MappingProxyType(factories)


def native_services(
    *,
    target_descriptor,
    target_sha256,
    model_root,
    models,
    source_root,
    source_names,
    artifact_root,
    query_root,
    runtime_root,
    base_url,
    extractor_fingerprint,
    representation_fingerprint,
    budget,
    permit=None,
    importer=None,
):
    target = OwnedTarget(target_descriptor, target_sha256)
    catalog = PostgresNailCatalog(target.connect)
    factories = native_factories(model_root, models, permit=permit, importer=importer)
    device = FileLease(runtime_root, "device.lock")
    embedding = GuardedEmbedding(
        NailEmbeddingAdapter(
            {key: admitted_provider(factory, budget, device) for key, factory in factories.items()}
        ),
        budget,
    )
    limits = WireLimits(2359296, 10, 41943040)
    guarded = GuardedLocalization(
        HttpNailLocalizationAdapter(ClientSettings(base_url, 1, 30, 300, 330, limits)), budget
    )

    class PermittedLocalization:
        def localize(self, *args):
            if permit is None or permit() is not True:
                raise BuildStop("NATIVE_RUN_NOT_ADMITTED")
            return guarded.localize(*args)

    localization = PermittedLocalization()
    decode = DecodeProfile(20971520, 2359296)
    local_profile = LocalizationProfile(extractor_fingerprint)
    source = ManifestImageStore(
        source_root, source_names, NailImageStore(artifact_root, max_manifest_bytes=8388608)
    )
    query_images = NailImageStore(query_root, max_manifest_bytes=8388608)
    build_processor = NailImageProcessor(source, localization, decode, local_profile, 10)
    query_processor = NailImageProcessor(query_images, localization, decode, local_profile, 10)
    build = NailCatalogBuildService(catalog, build_processor, embedding, source)

    class ReadOnlyCatalog:
        def read_ready(self, *args, **kwargs):
            return catalog.read_ready(*args, **kwargs)

        def iter_photo_groups(self, *args, **kwargs):
            return catalog.iter_photo_groups(*args, **kwargs)

    readonly_catalog = ReadOnlyCatalog()
    search = NailSearchService(readonly_catalog, query_processor, embedding)
    profile = SearchProfile(
        representation_fingerprint,
        EmbeddingProfile(tuple((m.model_key, m.revision) for m in models)),
        16384,
    )

    def execute_build(identity, inventory, *, input_check=None, runtime_check=None):
        if permit is None or permit() is not True:
            raise BuildStop("NATIVE_RUN_NOT_ADMITTED")
        if input_check is None or runtime_check is None:
            raise BuildStop("ACTUAL_PRECHECKS_REQUIRED")

        def target_check():
            with target.connect():
                return True

        return run_admitted_build(
            build,
            identity,
            inventory,
            profile,
            target_check=target_check,
            input_check=input_check,
            runtime_check=runtime_check,
            coordinator=FileLease(runtime_root, "coordinator.lock"),
        )

    class AdmittedBuild:
        def execute(self, identity, inventory, runtime=None, **checks):
            if runtime is not None and runtime != profile:
                raise BuildStop("PROFILE_MISMATCH")
            return execute_build(identity, inventory, **checks)

    return SimpleNamespace(
        execute_build=execute_build,
        target=target,
        catalog=readonly_catalog,
        build=AdmittedBuild(),
        search=search,
        source_images=source,
        query_images=query_images,
        embedding=embedding,
        localization=localization,
        factories=factories,
        runtime=profile,
        query_runner=lambda context_factory: NailQueryRunner(
            search, query_images, context_factory, query_root, runtime_root, decode.max_source_bytes
        ),
    )


def ready_query_context(ports, representation_id, corpus_version_id):
    from product_search.infrastructure.nail_query_runner import NailExecutionContext
    from product_search.search.nail_contracts import NailProcessingError

    if (
        not isinstance(representation_id, str)
        or not representation_id
        or type(corpus_version_id) is not int
        or corpus_version_id < 1
    ):
        raise NailProcessingError("PROFILE_MISMATCH")
    profile = ports.runtime

    def context(requested):
        if requested is not None and requested != representation_id:
            raise NailProcessingError("PROFILE_MISMATCH")
        with ports.target.connect() as conn:
            row = conn.execute(
                "SELECT corpus_version_id,fingerprint,status FROM search_representations WHERE id=%s",
                (representation_id,),
            ).fetchone()
        if row is None or row[2] != "READY":
            raise NailProcessingError("INDEX_NOT_READY")
        if row[0] != corpus_version_id or row[1] != profile.representation_fingerprint:
            raise NailProcessingError("PROFILE_MISMATCH")
        return NailExecutionContext(representation_id, corpus_version_id, profile)

    return context
