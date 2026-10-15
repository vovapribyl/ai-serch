"""Pure scoring and exact subset assignment, with explicit finite work budget."""

import math
import struct

from .nail_contracts import MODEL_DIMENSIONS, NailProcessingError, PairMatch, _number


def quantize_vector(values, dimension):
    if len(values) != dimension or not all(_number(v) for v in values):
        raise NailProcessingError("INVALID_EMBEDDING")
    try:
        vector = tuple(struct.unpack("!f", struct.pack("!f", v))[0] for v in values)
    except (OverflowError, struct.error):
        raise NailProcessingError("INVALID_EMBEDDING") from None
    if not all(math.isfinite(v) for v in vector):
        raise NailProcessingError("INVALID_EMBEDDING")
    if not any(vector):
        raise NailProcessingError("INVALID_EMBEDDING")
    return vector


def prepare_vector(values, dimension):
    vector = quantize_vector(values, dimension)
    norm = math.hypot(*vector)
    return tuple(v / norm for v in vector)


def _admit(n, m, max_states):
    if not n or not m:
        raise NailProcessingError("INVALID_EMBEDDING")
    small, large = min(n, m), max(n, m)
    if (
        type(max_states) is not int
        or max_states <= 0
        or small > max_states.bit_length()
        or (large + 1) * (1 << small) > max_states
    ):
        raise NailProcessingError("RESOURCE_LIMIT")


def assignment(scores, max_states):
    n = len(scores)
    m = len(scores[0]) if n else 0
    if (
        not n
        or not m
        or any(
            len(row) != m or any(not _number(v) or not 0 <= v <= 1 for v in row) for row in scores
        )
    ):
        raise NailProcessingError("INVALID_EMBEDDING")
    _admit(n, m, max_states)
    small, large = min(n, m), max(n, m)
    # ponytail: exponential in the smaller set; explicit budget rejects before allocation.
    states = {0: (0.0, (None,) * n)}

    def keep(target, mask, total, pairs):
        old = target.get(mask)
        key = lambda p: tuple(m + 1 if j is None else j for j in p)
        if old is None or total > old[0] or (total == old[0] and key(pairs) < key(old[1])):
            target[mask] = (total, pairs)

    for index in range(large):
        following = dict(states)
        for mask, (total, pairs) in states.items():
            for bit in range(small):
                if mask & (1 << bit):
                    continue
                row, column = (bit, index) if n <= m else (index, bit)
                updated = list(pairs)
                updated[row] = column + 1
                keep(following, mask | (1 << bit), total + scores[row][column], tuple(updated))
        states = following
    return states[(1 << small) - 1][1]


def match_photos(query, catalog, max_states):
    other = catalog.embeddings
    _admit(len(query.region_ordinals), len(other.region_ordinals), max_states)

    def normalized(photo):
        if (
            photo.region_ordinals != tuple(range(1, len(photo.region_ordinals) + 1))
            or not photo.region_ordinals
            or type(photo.vectors) is not tuple
            or tuple(k for k, _ in photo.vectors) != tuple(k for k, _ in MODEL_DIMENSIONS)
        ):
            raise NailProcessingError("INVALID_EMBEDDING")
        result = []
        for (key, rows), (_, dim) in zip(photo.vectors, MODEL_DIMENSIONS):
            if len(rows) != len(photo.region_ordinals):
                raise NailProcessingError("INVALID_EMBEDDING")
            result.append((key, tuple(prepare_vector(row, dim) for row in rows)))
        return tuple(result)

    q, c = normalized(query), normalized(other)
    n, m = len(query.region_ordinals), len(other.region_ordinals)
    per_model = []
    for (_, qrows), (_, crows) in zip(q, c):
        per_model.append(
            tuple(
                tuple(
                    (max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(qrow, crow)))) + 1) / 2
                    for crow in crows
                )
                for qrow in qrows
            )
        )
    scores = tuple(
        tuple(math.fsum(matrix[i][j] for matrix in per_model) / 3 for j in range(m))
        for i in range(n)
    )
    pairs = assignment(scores, max_states)
    diagnostics = tuple(
        (key, math.fsum(matrix[i][j - 1] for i, j in enumerate(pairs) if j is not None) / n)
        for (key, _), matrix in zip(MODEL_DIMENSIONS, per_model)
    )
    score = math.fsum(scores[i][j - 1] for i, j in enumerate(pairs) if j is not None) / n
    return PairMatch(query.photo_ordinal, catalog.photo_id, pairs, diagnostics, score)
