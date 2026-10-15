"""Experiment checks; run explicitly with the reviewed frozen runtime on PYTHONPATH."""

import hashlib
import itertools
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.compare_nail_models import (
    capture_queries,
    model_combinations,
    pair_matrices,
    rank_combinations,
    score_matrices,
)


def test_exactly_seven_nonempty_combinations_with_baseline_first():
    combinations = model_combinations()
    assert combinations[0] == ("openclip_b32", "dinov2_b14", "siglip2_b16_224")
    assert len(combinations) == len(set(combinations)) == 7
    assert {frozenset(c) for c in combinations} == {
        frozenset(c) for n in (1, 2, 3) for c in itertools.combinations(combinations[0], n)
    }


def test_exclusion_recomputes_assignment_instead_of_reusing_baseline_pairs():
    matrices = {
        "openclip_b32": ((0.9, 0.1), (0.1, 0.9)),
        "dinov2_b14": ((0.9, 0.1), (0.1, 0.9)),
        "siglip2_b16_224": ((0.1, 0.8), (0.8, 0.1)),
    }
    assert score_matrices(matrices, tuple(matrices), 100)[0] == (1, 2)
    pairs, score = score_matrices(matrices, ("siglip2_b16_224",), 100)
    assert pairs == (2, 1)
    assert score == pytest.approx(0.8)


def test_unmatched_query_regions_keep_zero_and_original_denominator():
    pairs, score = score_matrices({"a": ((0.2,), (0.9,))}, ("a",), 100)
    assert pairs == (None, 1)
    assert score == pytest.approx(0.45)


def test_pairwise_mean_uses_selected_model_count_and_lexicographic_tie():
    pairs, score = score_matrices({"a": ((0.8, 0.8),), "b": ((0.2, 0.2),)}, ("a", "b"), 100)
    assert pairs == (1,)
    assert score == math.fsum((0.8, 0.2)) / 2


@pytest.mark.parametrize("keys", [(), ("a", "a"), ("unknown",)])
def test_invalid_model_selection_is_rejected(keys):
    with pytest.raises(ValueError):
        score_matrices({"a": ((0.5,),)}, keys, 100)


def test_malformed_matrix_is_rejected_before_mean_can_hide_it():
    with pytest.raises(ValueError):
        score_matrices({"a": ((1.1,),), "b": ((0.0,),)}, ("a", "b"), 100)


def test_baseline_matches_existing_core_on_real_dimension_synthetic_vectors():
    from product_search.search.nail_contracts import MODEL_DIMENSIONS, CatalogPhoto, PhotoEmbeddings
    from product_search.search.nail_matching import match_photos

    vectors = tuple(
        (key, ((1.0,) + (0.0,) * (dim - 1), (0.0, 1.0) + (0.0,) * (dim - 2)))
        for key, dim in MODEL_DIMENSIONS
    )
    query = PhotoEmbeddings(1, "a" * 64, (1, 2), vectors)
    catalog = CatalogPhoto("photo", PhotoEmbeddings(1, "b" * 64, (1, 2), vectors))
    pairs, score = score_matrices(pair_matrices(query, catalog, 100), model_combinations()[0], 100)
    reference = match_photos(query, catalog, 100)
    assert pairs == reference.pairs
    assert score == reference.score == 1.0


def capture_fixture(tmp_path, count=3):
    from product_search.search.nail_contracts import MODEL_DIMENSIONS

    items = []
    for number in range(1, count + 1):
        path = tmp_path / f"query-{number}.png"
        path.write_bytes(b"synthetic")
        path.chmod(0o600)
        items.append(
            {
                "query_number": number,
                "input_path": str(path),
                "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "outcome": "SAME_PRODUCT",
            }
        )
    path = tmp_path / "queries.json"
    path.write_text(json.dumps({"queries": items}))
    path.chmod(0o600)
    job = {
        "files": {
            "ablation_queries": {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        },
        "build": {"fingerprint": "a" * 64},
    }
    calls = []

    class Images:
        def import_source(self, root, path, limit):
            calls.append("import")
            return "a" * 32, hashlib.sha256(path.read_bytes()).hexdigest()

        def cleanup(self, refs):
            calls.append("cleanup")

    class Processor:
        def process(self, photo):
            calls.append("localize")
            return SimpleNamespace(
                status="OK",
                input_sha256=photo.input_sha256,
                regions=(SimpleNamespace(ordinal=1, rgb_crop=None),),
            )

    class Embedding:
        def encode(self, key, crops, profile):
            calls.append(key)
            dim = dict(MODEL_DIMENSIONS)[key]
            return ((1.0,) + (0.0,) * (dim - 1),)

    ports = SimpleNamespace(
        query_images=Images(),
        search=SimpleNamespace(processor=Processor()),
        embedding=Embedding(),
        runtime=SimpleNamespace(embedding_profile=None),
    )
    return job, ports, calls


def test_capture_three_queries_once_and_retain_complete_vectors(tmp_path):
    job, ports, calls = capture_fixture(tmp_path)
    capture_queries(job, ports, tmp_path)
    assert calls.count("localize") == 3
    assert calls.count("cleanup") == 3
    assert len(list(tmp_path.glob("query-vectors-*.json"))) == 3
    for number in (1, 2, 3):
        data = json.loads((tmp_path / f"query-vectors-{number}.json").read_text())
        assert len(data["vectors"]) == 3


def test_changed_query_rejected_before_localization(tmp_path):
    from product_search.infrastructure.nail_build_runner import BuildStop

    job, ports, calls = capture_fixture(tmp_path)
    (tmp_path / "query-1.png").write_bytes(b"changed")
    with pytest.raises(BuildStop, match="PINNED_FILE_CHANGED"):
        capture_queries(job, ports, tmp_path)
    assert "localize" not in calls
    assert calls == []


def test_all_products_ranked_with_same_product_id_tie_break():
    from product_search.search.nail_contracts import (
        MODEL_DIMENSIONS,
        CatalogPhoto,
        CatalogProduct,
        PhotoEmbeddings,
    )

    vectors = tuple((key, ((1.0,) + (0.0,) * (dim - 1),)) for key, dim in MODEL_DIMENSIONS)
    query = PhotoEmbeddings(1, "a" * 64, (1,), vectors)
    products = tuple(
        CatalogProduct(pid, (CatalogPhoto(str(pid), PhotoEmbeddings(1, "b" * 64, (1,), vectors)),))
        for pid in (3, 1, 2)
    )
    ranked = rank_combinations(query, products, 100)
    assert len(ranked) == 7
    for rows in ranked.values():
        assert [row[1] for row in rows] == [1, 2, 3]
        assert [row[0] for row in rows] == [1.0] * 3


def test_capture_seven_queries_including_absent_goods(tmp_path):
    job, ports, calls = capture_fixture(tmp_path, 7)
    ref = job["files"]["ablation_queries"]
    path = Path(ref["path"])
    data = json.loads(path.read_text())
    for item in data["queries"][:4]:
        item["outcome"] = "NOT_IN_CORPUS"
    path.write_text(json.dumps(data))
    ref["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    job["ablation_query_count"] = 7
    capture_queries(job, ports, tmp_path)
    captures = sorted(tmp_path.glob("query-vectors-*.json"))
    assert len(captures) == 7
    assert all(len(json.loads(p.read_text())["vectors"]) == 3 for p in captures)
    assert calls.count("cleanup") == 7


@pytest.mark.parametrize("declared,count", [(2, 3), (8, 8), (True, 1)])
def test_capture_rejects_count_outside_frozen_scope_before_processing(tmp_path, declared, count):
    job, ports, calls = capture_fixture(tmp_path, count)
    job["ablation_query_count"] = declared
    with pytest.raises(ValueError):
        capture_queries(job, ports, tmp_path)
    assert calls == []
