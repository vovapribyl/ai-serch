"""Build policy with plain ports; publication is a separate explicit operation."""

from .nail_contracts import MODEL_DIMENSIONS, BuildPhotoResult, NailProcessingError, PhotoEmbeddings
from .nail_image_processor import NailImageProcessor
from .nail_ports import NailCatalogPort, NailEmbeddingPort, NailImageStorePort


class NailCatalogBuildService:
    def __init__(
        self,
        catalog: NailCatalogPort,
        processor: NailImageProcessor,
        embedding: NailEmbeddingPort,
        images: NailImageStorePort,
    ):
        self.catalog, self.processor, self.embedding, self.images = (
            catalog,
            processor,
            embedding,
            images,
        )

    def execute(self, identity, inventory, verified_runtime, *, resume=False):
        revisions = tuple((model.model_key, model.revision) for model in identity.models)
        if (
            identity.fingerprint != verified_runtime.representation_fingerprint
            or revisions != verified_runtime.embedding_profile.revisions
            or dict(identity.profile).get("crop_profile") != "mask_bbox_white_v1"
        ):
            raise NailProcessingError("PROFILE_MISMATCH")
        if (
            type(inventory) is not tuple
            or not inventory
            or len({item.catalog_photo_id for item in inventory}) != len(inventory)
            or len({(item.product_record_id, item.photo.photo_ordinal) for item in inventory})
            != len(inventory)
        ):
            raise NailProcessingError("INVALID_OUTPUT")
        if inventory != tuple(
            sorted(inventory, key=lambda item: (item.product_record_id, item.photo.photo_ordinal))
        ):
            raise NailProcessingError("INVALID_OUTPUT", reason="INVENTORY_ORDER")
        if resume:
            if self.catalog.read_build_identity(identity.representation_id) != identity:
                raise NailProcessingError("PROFILE_MISMATCH")
        else:
            self.catalog.begin_build(identity, inventory)
        states = self.catalog.read_photo_states(identity.representation_id)
        if tuple(state.item for state in states) != inventory:
            raise NailProcessingError("PROFILE_MISMATCH")
        if any(state.status == "ERROR" for state in states):
            raise NailProcessingError("INVALID_OUTPUT", reason="EXPLICIT_BUILD_RETRY_REQUIRED")
        build_id = identity.representation_id.replace("-", "")
        if resume:
            reachable = tuple(
                ref
                for state in states
                for artifact in state.artifacts
                for ref in (artifact.mask_ref, artifact.crop_ref)
            )
            self.images.cleanup_orphans(build_id, reachable)
        for state in states:
            item = state.item
            if state.status in ("OK", "NO_NAILS"):
                self.images.read_rgb(item.photo, self.processor.decode_profile)
                if state.status == "OK":
                    self.images.verify_artifacts(
                        build_id, state.artifacts, self.processor.decode_profile
                    )
                continue
            if state.status != "PENDING":
                raise NailProcessingError("INVALID_OUTPUT")
            artifacts = ()
            try:
                photo = self.processor.process(item.photo)
                if photo.status == "NO_NAILS":
                    outcome = BuildPhotoResult(
                        identity.representation_id,
                        item.catalog_photo_id,
                        photo,
                        None,
                        (),
                        "DETECTOR_NO_MATCH",
                    )
                else:
                    crops = tuple(region.rgb_crop for region in photo.regions)
                    vectors = tuple(
                        (key, self.embedding.encode(key, crops, verified_runtime.embedding_profile))
                        for key, _ in MODEL_DIMENSIONS
                    )
                    embeddings = PhotoEmbeddings(
                        photo.photo_ordinal,
                        photo.input_sha256,
                        tuple(region.ordinal for region in photo.regions),
                        vectors,
                    )
                    artifacts = self.images.write_region_artifacts(build_id, photo)
                    outcome = BuildPhotoResult(
                        identity.representation_id,
                        item.catalog_photo_id,
                        photo,
                        embeddings,
                        artifacts,
                    )
                self.catalog.write_photo_outcome(outcome)
            except NailProcessingError as error:
                if artifacts:
                    self.images.cleanup(
                        tuple(
                            ref
                            for artifact in artifacts
                            for ref in (artifact.mask_ref, artifact.crop_ref)
                        )
                    )
                self.catalog.write_photo_outcome(
                    BuildPhotoResult(
                        identity.representation_id,
                        item.catalog_photo_id,
                        None,
                        None,
                        (),
                        error.code,
                    )
                )
        return self.catalog.read_build_summary(identity.representation_id)

    def publish(self, representation_id, expected_active_id, *, coverage_accepted=False):
        summary = self.catalog.read_build_summary(representation_id)
        if not summary.complete:
            raise NailProcessingError("INDEX_NOT_READY")
        if summary.uncovered_product_ids and not coverage_accepted:
            raise NailProcessingError("COVERAGE_NOT_ACCEPTED")
        return self.catalog.publish(representation_id, expected_active_id)
