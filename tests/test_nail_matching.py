import itertools
import math
import random

import pytest

from product_search.search.nail_contracts import CatalogPhoto, NailProcessingError, PhotoEmbeddings
from product_search.search.nail_matching import assignment, match_photos, prepare_vector


@pytest.mark.parametrize(
    "matrix,want",
    [
        (((0.9, 0.8), (0.85, 0.1)), (2, 1)),
        (((0.9, 0.1, 0.2), (0.1, 0.8, 0.2)), (1, 2)),
        (((0.9, 0.1), (0.1, 0.8), (0.2, 0.2)), (1, 2, None)),
        (((0.0, 0.0), (0.0, 0.0), (0.0, 0.0)), (1, 2, None)),
        (((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)), (1, 2)),
    ],
)
def test_optimal_not_greedy_and_stable_ties(matrix, want):
    assert assignment(matrix, 10000) == want


def oracle(matrix):
    n, m = len(matrix), len(matrix[0])
    options = []
    for rows in itertools.combinations(range(n), min(n, m)):
        for columns in itertools.permutations(range(m), len(rows)):
            pairs = [None] * n
            for i, j in zip(rows, columns):
                pairs[i] = j + 1
            score = sum(matrix[i][j - 1] for i, j in enumerate(pairs) if j is not None)
            options.append((-score, tuple(m + 1 if j is None else j for j in pairs), tuple(pairs)))
    return min(options)[2]


def test_independent_exhaustive_small_matrix_oracle():
    rng = random.Random(23)
    for n in range(1, 5):
        for m in range(1, 5):
            for _ in range(8):
                # Dyadic exact values exercise ties without oracle summation ambiguity.
                matrix = tuple(tuple(rng.randrange(9) / 8 for _ in range(m)) for _ in range(n))
                assert assignment(matrix, 10000) == oracle(matrix)


@pytest.mark.parametrize(
    "matrix,budget",
    [
        ((), 100),
        (((0.5,),), 0),
        (((math.nan,),), 100),
        (((0.5,), (0.5, 0.5)), 100),
        (((0.5,) * 10,) * 10, 100),
    ],
)
def test_invalid_or_over_budget_has_no_truncation(matrix, budget):
    with pytest.raises(NailProcessingError):
        assignment(matrix, budget)


def vectors(rows):
    return tuple(
        (key, tuple(tuple(row) + (0.0,) * (dim - len(row)) for row in rows))
        for key, dim in [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)]
    )


def test_cosine_scale_and_missing_zero_diagnostics():
    q = PhotoEmbeddings(1, "a" * 64, (1, 2, 3), vectors(((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0))))
    c = CatalogPhoto(
        "photo", PhotoEmbeddings(1, "b" * 64, (1, 2), vectors(((1.0, 0.0), (0.0, 1.0))))
    )
    result = match_photos(q, c, 1000)
    assert result is not None
    assert result.pairs == (1, 2, None)
    assert result.score == pytest.approx(2 / 3, abs=1e-12)
    assert all(
        score == pytest.approx(2 / 3, abs=1e-12) for _, score in result.per_model_pair_scores
    )


def test_three_model_mean_uses_one_shared_assignment():
    vq = list(vectors(((1.0, 0.0),)))
    vc = list(vectors(((1.0, 0.0),)))
    key, rows = vc[-1]
    vc[-1] = (key, (tuple(-x for x in rows[0]),))
    q = PhotoEmbeddings(1, "a" * 64, (1,), tuple(vq))
    c = CatalogPhoto("p", PhotoEmbeddings(1, "b" * 64, (1,), tuple(vc)))
    result = match_photos(q, c, 100)
    assert result is not None
    assert result.score == pytest.approx(2 / 3, abs=1e-12)
    assert dict(result.per_model_pair_scores) == {
        "openclip_b32": 1.0,
        "dinov2_b14": 1.0,
        "siglip2_b16_224": 0.0,
    }


@pytest.mark.parametrize(
    "values",
    [(0.0, 0.0), (math.inf, 1.0), (math.nan, 1.0), (1e100, 1.0), (1e-100, 0.0), (True, 1.0)],
)
def test_numeric_boundary_rejects_invalid_vectors(values):
    with pytest.raises(NailProcessingError):
        prepare_vector(values, 2)


def test_float32_before_float64_cosine():
    result = prepare_vector((0.1, 0.2), 2)
    assert result == pytest.approx((1 / math.sqrt(5), 2 / math.sqrt(5)), abs=1e-12)
    assert result != (0.1, 0.2)


def test_solver_budget_rejected_before_numeric_matrix_allocation(monkeypatch):
    import product_search.search.nail_matching as matching

    rows = ((1.0, 0.0),) * 10
    q = PhotoEmbeddings(1, "a" * 64, tuple(range(1, 11)), vectors(rows))
    c = CatalogPhoto("p", PhotoEmbeddings(1, "b" * 64, tuple(range(1, 11)), vectors(rows)))

    def forbidden(*args):
        raise AssertionError("numeric allocation must not start")

    monkeypatch.setattr(matching, "prepare_vector", forbidden)
    with pytest.raises(NailProcessingError, match="RESOURCE_LIMIT"):
        matching.match_photos(q, c, 100)
