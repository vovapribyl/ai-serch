"""Offline experiment; imports scoring from an explicitly supplied frozen runtime."""

import itertools
import math

from product_search.search.nail_contracts import MODEL_DIMENSIONS, NailProcessingError, _number
from product_search.search.nail_matching import _admit, assignment, prepare_vector


def model_combinations():
    keys = tuple(key for key, _ in MODEL_DIMENSIONS)
    return tuple(c for size in (3, 2, 1) for c in itertools.combinations(keys, size))


def score_matrices(matrices, keys, max_states):
    if not keys or len(set(keys)) != len(keys) or any(key not in matrices for key in keys):
        raise ValueError("invalid model selection")
    selected = [matrices[key] for key in keys]
    n = len(selected[0])
    m = len(selected[0][0]) if n else 0
    if (
        not n
        or not m
        or any(
            len(matrix) != n
            or any(
                len(row) != m or any(not _number(v) or not 0 <= v <= 1 for v in row)
                for row in matrix
            )
            for matrix in selected
        )
    ):
        raise ValueError("invalid pair matrices")
    scores = tuple(
        tuple(math.fsum(matrix[i][j] for matrix in selected) / len(keys) for j in range(m))
        for i in range(n)
    )
    pairs = assignment(scores, max_states)
    return pairs, math.fsum(scores[i][j - 1] for i, j in enumerate(pairs) if j is not None) / n


def pair_matrices(query, catalog, max_states):
    other = catalog.embeddings
    _admit(len(query.region_ordinals), len(other.region_ordinals), max_states)

    def normalize(photo):
        if (
            photo.region_ordinals != tuple(range(1, len(photo.region_ordinals) + 1))
            or not photo.region_ordinals
            or type(photo.vectors) is not tuple
            or tuple(key for key, _ in photo.vectors) != tuple(key for key, _ in MODEL_DIMENSIONS)
        ):
            raise NailProcessingError("INVALID_EMBEDDING")
        normalized = {}
        for (key, rows), (_, dimension) in zip(photo.vectors, MODEL_DIMENSIONS):
            if len(rows) != len(photo.region_ordinals):
                raise NailProcessingError("INVALID_EMBEDDING")
            normalized[key] = tuple(prepare_vector(row, dimension) for row in rows)
        return normalized

    q, c = normalize(query), normalize(other)
    return {
        key: tuple(
            tuple(
                (max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(qrow, crow)))) + 1) / 2
                for crow in c[key]
            )
            for qrow in q[key]
        )
        for key, _ in MODEL_DIMENSIONS
    }


def capture_queries(job, ports, output_root):
    import json
    from pathlib import Path

    from product_search.infrastructure.nail_build_composition import publish_private_json
    from product_search.infrastructure.nail_native_job import read_pinned
    from product_search.search.nail_contracts import PhotoEmbeddings, PhotoInput

    items = json.loads(read_pinned(job["files"]["ablation_queries"]))["queries"]
    count = job.get("ablation_query_count", 3)
    if (
        type(count) is not int
        or not 1 <= count <= 7
        or len(items) != count
        or [item["query_number"] for item in items] != list(range(1, count + 1))
        or any(item["outcome"] not in ("SAME_PRODUCT", "NOT_IN_CORPUS") for item in items)
    ):
        raise ValueError("confirmed queries must match the frozen count (1..7)")
    for item in items:
        path = Path(item["input_path"])
        read_pinned({"path": str(path), "sha256": item["input_sha256"]})
        refs = []
        try:
            ref, sha = ports.query_images.import_source(path.parent, path, 20971520)
            refs.append(ref)
            if sha != item["input_sha256"]:
                raise ValueError("query identity mismatch")
            photo = ports.search.processor.process(PhotoInput(1, ref, sha))
            if photo.status != "OK" or photo.input_sha256 != sha:
                raise ValueError("query incomplete")
            crops = tuple(region.rgb_crop for region in photo.regions)
            vectors = tuple(
                (key, ports.embedding.encode(key, crops, ports.runtime.embedding_profile))
                for key, _ in MODEL_DIMENSIONS
            )
            ordinals = tuple(region.ordinal for region in photo.regions)
            embedded = PhotoEmbeddings(1, sha, ordinals, vectors)
            # Reuse the core validation before persisting a complete result.
            from product_search.search.nail_contracts import CatalogPhoto

            pair_matrices(embedded, CatalogPhoto("validation", embedded), 16384)
            publish_private_json(
                output_root / f"query-vectors-{item['query_number']}.json",
                {
                    "input_sha256": sha,
                    "fingerprint": job["build"]["fingerprint"],
                    "region_ordinals": ordinals,
                    "vectors": vectors,
                },
            )
        finally:
            if refs:
                ports.query_images.cleanup(tuple(refs))


def rank_combinations(query, products, max_states):
    from product_search.search.nail_matching import match_photos

    combinations = model_combinations()
    ranked = {keys: [] for keys in combinations}
    for product in products:
        best = {}
        for photo in product.photos:
            matrices = pair_matrices(query, photo, max_states)
            baseline = match_photos(query, photo, max_states)
            for keys in combinations:
                pairs, score = score_matrices(matrices, keys, max_states)
                if keys == combinations[0] and (
                    pairs != baseline.pairs or abs(score - baseline.score) > 1e-12
                ):
                    raise ValueError("baseline parity failed")
                row = (score, product.product_record_id, pairs, photo.embeddings.photo_ordinal)
                if keys not in best or (-score, row[3]) < (-best[keys][0], best[keys][3]):
                    best[keys] = row
        if len(best) != 7:
            raise ValueError("incomplete catalog product")
        for keys in combinations:
            ranked[keys].append(best[keys])
    for rows in ranked.values():
        rows.sort(key=lambda row: (-row[0], row[1]))
    return ranked
