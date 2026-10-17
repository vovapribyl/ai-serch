"""Private probe export, separate from catalog activation and SQL recovery."""

import os
from pathlib import Path

from product_search.infrastructure.nail_build_composition import publish_private_json
from product_search.infrastructure.nail_runtime import validate_runtime_root


def export_before_verification(connection, destination, profile, verify):
    """Preserve partial outcomes/vectors even when the batch verification raises."""
    destination = Path(destination)
    validate_runtime_root(destination.parent)
    vectors = connection.execute(
        "SELECT CAST(revision_photo_id AS TEXT),region_ordinal,model_key,"
        "CAST(vector AS TEXT) FROM revision_vectors "
        "ORDER BY revision_photo_id,region_ordinal,model_key"
    ).fetchall()
    regions = connection.execute(
        "SELECT CAST(revision_photo_id AS TEXT),region_ordinal,mask_ref,crop_ref,crop_sha "
        "FROM revision_regions ORDER BY revision_photo_id,region_ordinal"
    ).fetchall()
    columns = connection.execute("SELECT * FROM revision_regions WHERE false").description
    photos = connection.execute(
        "SELECT CAST(p.id AS TEXT),r.product_record_id,p.ordinal,p.input_sha "
        "FROM revision_photos p JOIN product_revisions r ON r.id=p.revision_id "
        "ORDER BY r.product_record_id,p.ordinal"
    ).fetchall()
    outcomes = connection.execute(
        "SELECT CAST(p.id AS TEXT),r.product_record_id,p.outcome "
        "FROM revision_photos p JOIN product_revisions r ON r.id=p.revision_id "
        "ORDER BY r.product_record_id,p.ordinal"
    ).fetchall()
    publish_private_json(
        destination,
        {
            "vectors": vectors,
            "region_columns": [column[0] for column in columns],
            "regions": regions,
            "photos": photos,
            "photo_outcomes": outcomes,
            "profile": profile,
            "source": "owned diagnostic export; includes incomplete photos; no working cutover",
        },
    )
    directory = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return verify()
