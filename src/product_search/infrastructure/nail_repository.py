"""PostgreSQL adapter for plain application-owned catalog/build data."""

import json
import re
from contextlib import contextmanager
from itertools import groupby
from uuid import uuid4

import psycopg

from product_search.search.nail_contracts import (
    MODEL_DIMENSIONS,
    BuildSummary,
    CatalogPhoto,
    CatalogProduct,
    EmbeddingProfile,
    NailProcessingError,
    PhotoEmbeddings,
    ReadyCatalog,
)
from product_search.search.nail_matching import quantize_vector


class PostgresNailCatalog:
    def __init__(self, connection_factory):
        self.connection_factory = connection_factory

    @contextmanager
    def _connection(self):
        try:
            with self.connection_factory() as conn:
                yield conn
        except psycopg.Error:
            raise NailProcessingError("RESOURCE_ERROR", reason="CATALOG_FAILURE") from None

    @staticmethod
    def _mutable(conn, representation_id):
        row = conn.execute(
            "SELECT status FROM search_representations WHERE id=%s FOR UPDATE", (representation_id,)
        ).fetchone()
        if not row or row[0] != "BUILDING":
            raise NailProcessingError("INDEX_NOT_READY")

    def begin_build(self, identity, inventory):
        if type(inventory) is not tuple or not inventory:
            raise NailProcessingError("INVALID_OUTPUT")
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO search_representations VALUES (%s,%s,%s,'BUILDING',%s::jsonb,%s,now(),now())",
                (
                    identity.representation_id,
                    identity.corpus_version_id,
                    identity.fingerprint,
                    json.dumps(dict(identity.profile)),
                    identity.inventory_sha256,
                ),
            )
            for model in identity.models:
                conn.execute(
                    "INSERT INTO representation_models VALUES (%s,%s,%s,%s,%s)",
                    (
                        identity.representation_id,
                        model.model_key,
                        model.revision,
                        model.manifest_sha256,
                        model.dimension,
                    ),
                )
            for item in inventory:
                conn.execute(
                    "INSERT INTO catalog_photos(id,representation_id,product_record_id,ordinal,input_sha256,source_locator,status) VALUES (%s,%s,%s,%s,%s,%s,'PENDING')",
                    (
                        item.catalog_photo_id,
                        identity.representation_id,
                        item.product_record_id,
                        item.photo.photo_ordinal,
                        item.photo.input_sha256,
                        item.photo.source_ref,
                    ),
                )

    def write_photo_outcome(self, outcome):
        with self._connection() as conn:
            self._mutable(conn, outcome.representation_id)
            stored = conn.execute(
                "SELECT ordinal,input_sha256,status FROM catalog_photos WHERE id=%s AND representation_id=%s",
                (outcome.catalog_photo_id, outcome.representation_id),
            ).fetchone()
            if not stored or stored[2] != "PENDING":
                raise NailProcessingError("INVALID_OUTPUT")
            if outcome.photo is None:
                if (
                    not outcome.error_code
                    or outcome.error_code == "DETECTOR_NO_MATCH"
                    or outcome.embeddings is not None
                    or outcome.artifacts
                ):
                    raise NailProcessingError("INVALID_OUTPUT")
                conn.execute(
                    "UPDATE catalog_photos SET status='ERROR',error_code=%s WHERE id=%s",
                    (outcome.error_code, outcome.catalog_photo_id),
                )
                return
            photo = outcome.photo
            if (photo.photo_ordinal, photo.input_sha256) != (stored[0], stored[1]):
                raise NailProcessingError("PROFILE_MISMATCH")
            if photo.status == "NO_NAILS":
                if (
                    outcome.embeddings is not None
                    or outcome.artifacts
                    or outcome.error_code != "DETECTOR_NO_MATCH"
                ):
                    raise NailProcessingError("INVALID_OUTPUT")
                conn.execute(
                    "UPDATE catalog_photos SET status='NO_NAILS',error_code='DETECTOR_NO_MATCH' WHERE id=%s",
                    (outcome.catalog_photo_id,),
                )
                return
            embeddings = outcome.embeddings
            if (
                embeddings is None
                or outcome.error_code is not None
                or (embeddings.photo_ordinal, embeddings.input_sha256)
                != (photo.photo_ordinal, photo.input_sha256)
                or embeddings.region_ordinals != tuple(r.ordinal for r in photo.regions)
                or tuple(a.ordinal for a in outcome.artifacts) != embeddings.region_ordinals
            ):
                raise NailProcessingError("INVALID_OUTPUT")
            for region, artifact in zip(photo.regions, outcome.artifacts):
                if (
                    not all(
                        isinstance(ref, str) and re.fullmatch("[0-9a-f]{32}", ref)
                        for ref in (artifact.mask_ref, artifact.crop_ref)
                    )
                    or not isinstance(artifact.crop_sha256, str)
                    or not re.fullmatch("[0-9a-f]{64}", artifact.crop_sha256)
                ):
                    raise NailProcessingError("INVALID_OUTPUT")
                region_id = uuid4()
                conn.execute(
                    "INSERT INTO nail_regions VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)",
                    (
                        region_id,
                        outcome.representation_id,
                        outcome.catalog_photo_id,
                        region.ordinal,
                        json.dumps(region.detector_box_xyxy),
                        json.dumps(region.crop_box_xyxy),
                        artifact.mask_ref,
                        artifact.crop_ref,
                        artifact.crop_sha256,
                    ),
                )
                for (key, rows), (_, dimension) in zip(embeddings.vectors, MODEL_DIMENSIONS):
                    vector = quantize_vector(rows[region.ordinal - 1], dimension)
                    literal = "[" + ",".join(str(v) for v in vector) + "]"
                    conn.execute(
                        "INSERT INTO nail_embeddings VALUES (%s,%s,%s,%s,%s::vector)",
                        (outcome.representation_id, region_id, key, dimension, literal),
                    )
            conn.execute(
                "UPDATE catalog_photos SET status='OK',error_code=NULL WHERE id=%s",
                (outcome.catalog_photo_id,),
            )

    @staticmethod
    def _summary(conn, representation_id):
        row = conn.execute(
            "SELECT status FROM search_representations WHERE id=%s", (representation_id,)
        ).fetchone()
        if not row:
            raise NailProcessingError("INDEX_NOT_READY")
        total, ok, no_nails, error, pending = conn.execute(
            "SELECT count(*),count(*) FILTER(WHERE status='OK'),count(*) FILTER(WHERE status='NO_NAILS'),count(*) FILTER(WHERE status='ERROR'),count(*) FILTER(WHERE status='PENDING') FROM catalog_photos WHERE representation_id=%s",
            (representation_id,),
        ).fetchone()
        models = conn.execute(
            "SELECT count(*) FROM representation_models WHERE representation_id=%s",
            (representation_id,),
        ).fetchone()[0]
        incomplete = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM catalog_photos p WHERE p.representation_id=%s AND p.status='OK' AND NOT EXISTS(SELECT 1 FROM nail_regions r WHERE r.catalog_photo_id=p.id)) OR EXISTS(SELECT 1 FROM nail_regions r WHERE r.representation_id=%s AND (SELECT count(*) FROM nail_embeddings e WHERE e.region_id=r.id)<>3)",
            (representation_id, representation_id),
        ).fetchone()[0]
        uncovered = tuple(
            row[0]
            for row in conn.execute(
                "SELECT product_record_id FROM catalog_photos WHERE representation_id=%s GROUP BY product_record_id HAVING NOT bool_or(status='OK') ORDER BY product_record_id",
                (representation_id,),
            )
        )
        return BuildSummary(
            representation_id,
            row[0],
            total,
            ok,
            no_nails,
            error,
            pending,
            ok > 0 and error == 0 and pending == 0 and models == 3 and not incomplete,
            uncovered,
        )

    def read_build_summary(self, representation_id):
        with self._connection() as conn:
            return self._summary(conn, representation_id)

    def publish(self, representation_id, expected_active_id):
        with self._connection() as conn:
            self._mutable(conn, representation_id)
            if not self._summary(conn, representation_id).complete:
                raise NailProcessingError("INDEX_NOT_READY")
            conn.execute(
                "UPDATE search_representations SET status='READY',updated_at=now() WHERE id=%s",
                (representation_id,),
            )
            if expected_active_id is None:
                row = conn.execute(
                    "INSERT INTO search_active_representations VALUES ('nail-search-v1',%s) ON CONFLICT(mode) DO NOTHING RETURNING representation_id",
                    (representation_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "UPDATE search_active_representations SET representation_id=%s WHERE mode='nail-search-v1' AND representation_id=%s RETURNING representation_id",
                    (representation_id, expected_active_id),
                ).fetchone()
            if row is None:
                raise NailProcessingError("ACTIVE_CONFLICT")
            return True

    def read_ready(self, representation_id):
        with self._connection() as conn:
            row = conn.execute(
                "SELECT status,fingerprint FROM search_representations WHERE id=%s",
                (representation_id,),
            ).fetchone()
            if not row or row[0] != "READY":
                raise NailProcessingError("INDEX_NOT_READY")
            models = dict(
                conn.execute(
                    "SELECT model_key,revision FROM representation_models WHERE representation_id=%s",
                    (representation_id,),
                ).fetchall()
            )
            if set(models) != set(dict(MODEL_DIMENSIONS)):
                raise NailProcessingError("PROFILE_MISMATCH")
            profile = EmbeddingProfile(tuple((key, models[key]) for key, _ in MODEL_DIMENSIONS))
            has_ok = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM catalog_photos WHERE representation_id=%s AND status='OK')",
                (representation_id,),
            ).fetchone()[0]
            return ReadyCatalog(representation_id, row[1], profile, has_ok)

    def iter_photo_groups(self, representation_id):
        self.read_ready(representation_id)
        with self._connection() as conn, conn.cursor(name="nail_photo_groups") as cursor:
            cursor.execute(
                """SELECT p.product_record_id,p.id,p.ordinal,p.input_sha256,r.ordinal,e.model_key,e.embedding::text FROM catalog_photos p JOIN nail_regions r ON r.catalog_photo_id=p.id AND r.representation_id=p.representation_id JOIN nail_embeddings e ON e.region_id=r.id AND e.representation_id=r.representation_id WHERE p.representation_id=%s AND p.status='OK' ORDER BY p.product_record_id,p.ordinal,r.ordinal,CASE e.model_key WHEN 'openclip_b32' THEN 0 WHEN 'dinov2_b14' THEN 1 ELSE 2 END""",
                (representation_id,),
            )
            for product_id, product_rows in groupby(cursor, key=lambda row: row[0]):
                photos = []
                for photo_id, photo_rows in groupby(product_rows, key=lambda row: row[1]):
                    rows = list(photo_rows)
                    ordinals = tuple(sorted({row[4] for row in rows}))
                    vectors = tuple(
                        (key, tuple(tuple(json.loads(row[6])) for row in rows if row[5] == key))
                        for key, _ in MODEL_DIMENSIONS
                    )
                    photos.append(
                        CatalogPhoto(
                            str(photo_id),
                            PhotoEmbeddings(rows[0][2], rows[0][3], ordinals, vectors),
                        )
                    )
                yield CatalogProduct(product_id, tuple(photos))

    def read_build_identity(self, representation_id):
        from product_search.search.nail_contracts import BuildIdentity, ModelIdentity

        with self._connection() as conn:
            row = conn.execute(
                "SELECT corpus_version_id,fingerprint,inventory_sha256,profile FROM search_representations WHERE id=%s",
                (representation_id,),
            ).fetchone()
            if not row:
                raise NailProcessingError("INDEX_NOT_READY")
            models = {
                r[0]: ModelIdentity(*r)
                for r in conn.execute(
                    "SELECT model_key,revision,manifest_sha256,dimension FROM representation_models WHERE representation_id=%s",
                    (representation_id,),
                )
            }
            if set(models) != set(dict(MODEL_DIMENSIONS)):
                raise NailProcessingError("PROFILE_MISMATCH")
            return BuildIdentity(
                representation_id,
                row[0],
                row[1],
                row[2],
                tuple(sorted(row[3].items())),
                tuple(models[key] for key, _ in MODEL_DIMENSIONS),
            )

    def read_photo_states(self, representation_id):
        from product_search.search.nail_contracts import (
            BuildPhoto,
            PhotoInput,
            RegionArtifacts,
            StoredPhotoState,
        )

        with self._connection() as conn:
            photos = conn.execute(
                "SELECT id,product_record_id,ordinal,source_locator,input_sha256,status,error_code FROM catalog_photos WHERE representation_id=%s ORDER BY product_record_id,ordinal",
                (representation_id,),
            ).fetchall()
            states = []
            for photo_id, product_id, ordinal, ref, checksum, status, error in photos:
                artifacts = tuple(
                    RegionArtifacts(*row)
                    for row in conn.execute(
                        "SELECT ordinal,mask_locator,crop_locator,crop_sha256 FROM nail_regions WHERE catalog_photo_id=%s ORDER BY ordinal",
                        (photo_id,),
                    )
                )
                states.append(
                    StoredPhotoState(
                        BuildPhoto(str(photo_id), product_id, PhotoInput(ordinal, ref, checksum)),
                        status,
                        error,
                        artifacts,
                    )
                )
            return tuple(states)
