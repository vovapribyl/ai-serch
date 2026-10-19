"""SAM counts and cleanup ordering, without numpy/torch/model calls."""

import json

import pytest

from product_search.infrastructure.replenishment_load_diagnostics import (
    LoadDiagnostics,
    cache_cleanup_enabled,
)
from product_search.search.replenishment_contracts import ReplenishmentError


class ShapeOnly:
    def __init__(self, *shape):
        self.shape = shape

    def __iter__(self):
        raise AssertionError("must not read pixels or coordinates")


def recorder(tmp_path):
    tmp_path.chmod(0o700)
    return LoadDiagnostics(tmp_path / "events.jsonl", sample=dict, max_bytes=65536)


def rows(tmp_path):
    return [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("keywords", [False, True])
def test_sam_records_counts_and_shapes_without_payload_and_preserves_call(tmp_path, keywords):
    log = recorder(tmp_path)
    instance = object()
    images = [ShapeOnly(574, 556, 3), ShapeOnly(100, 200, 3)]
    boxes = [ShapeOnly(17, 4), ShapeOnly(0, 4)]
    result = object()

    def predict(got_instance, images_rgb, xyxy):
        assert got_instance is instance and images_rgb is images and xyxy is boxes
        return result

    wrapped = log.wrap_sam(predict)
    try:
        value = (
            wrapped(instance, images_rgb=images, xyxy=boxes)
            if keywords
            else wrapped(instance, images, boxes)
        )
        assert value is result
    finally:
        log.close()
    events = rows(tmp_path)
    summary = next(e["sam_input"] for e in events if e["step"] == "sam.input")
    assert summary == {
        "known": True,
        "image_count": 2,
        "box_count": 17,
        "images": [
            {"height": 574, "width": 556, "channels": 3, "boxes": 17},
            {"height": 100, "width": 200, "channels": 3, "boxes": 0},
        ],
    }
    assert [(e["step"], e["phase"]) for e in events] == [
        ("sam.input", "before"),
        ("sam.predict", "before"),
        ("sam.predict", "after"),
    ]
    assert all(e["call"] == 1 for e in events)


@pytest.mark.parametrize("fail_cache,fail_sam", [(False, False), (True, False), (False, True)])
def test_pre_sam_cleanup_orders_calls_and_preserves_errors(tmp_path, fail_cache, fail_sam):
    log = recorder(tmp_path)
    calls = []
    error = RuntimeError("private error")

    def cleanup():
        calls.append("cache")
        if fail_cache:
            raise error

    def predict(*args):
        calls.append("sam")
        if fail_sam:
            raise error
        return 42

    wrapped = log.wrap_sam(predict, before_sam=cleanup)
    try:
        if fail_cache or fail_sam:
            with pytest.raises(RuntimeError) as caught:
                wrapped(object(), [ShapeOnly(1, 2, 3)], [ShapeOnly(11, 4)])
            assert caught.value is error
        else:
            assert wrapped(object(), [ShapeOnly(1, 2, 3)], [ShapeOnly(11, 4)]) == 42
    finally:
        log.close()
    assert calls == (["cache"] if fail_cache else ["cache", "sam"])
    events = rows(tmp_path)
    assert [e["step"] for e in events][:3] == [
        "sam.input",
        "mps.pre_sam_cache",
        "mps.pre_sam_cache",
    ]
    assert events[2]["phase"] == ("error" if fail_cache else "after")
    assert "private error" not in (tmp_path / "events.jsonl").read_text()


@pytest.mark.parametrize(
    "images,boxes",
    [
        ([], []),
        ([ShapeOnly(1, 2, 3)], []),
        ([ShapeOnly(1, 2, 3)] * 17, [ShapeOnly(1, 4)] * 17),
        ([ShapeOnly(1, 2, 3)], [ShapeOnly(4, 5)]),
        ([ShapeOnly(True, 2, 3)], [ShapeOnly(1, 4)]),
    ],
)
def test_unknown_or_oversize_shape_metadata_does_not_change_prediction(tmp_path, images, boxes):
    log = recorder(tmp_path)
    try:
        assert log.wrap_sam(lambda *a: "unchanged")(object(), images, boxes) == "unchanged"
    finally:
        log.close()
    assert rows(tmp_path)[0]["sam_input"] == {"known": False}
    assert (tmp_path / "events.status.json").exists()
    assert json.loads((tmp_path / "events.status.json").read_text())["incomplete"] is True


def test_pre_sam_flag_is_default_off_and_does_not_replace_post_photo_cleanup():
    assert cache_cleanup_enabled({}, before_sam=True) is False
    binding = {
        "load_diagnostics": True,
        "empty_cache_after_photo": True,
        "empty_cache_before_sam": True,
    }
    assert cache_cleanup_enabled(binding, before_sam=True) is True
    assert cache_cleanup_enabled(binding) is True


@pytest.mark.parametrize(
    "binding",
    [
        {"empty_cache_before_sam": True},
        {"empty_cache_before_sam": True, "load_diagnostics": True},
        {
            "empty_cache_before_sam": "true",
            "load_diagnostics": True,
            "empty_cache_after_photo": True,
        },
    ],
)
def test_pre_sam_cleanup_refuses_invalid_or_missing_prerequisites(binding):
    with pytest.raises(ReplenishmentError, match="RUNTIME_MISMATCH"):
        cache_cleanup_enabled(binding)


@pytest.mark.parametrize("diagnostics,cleanup", [(object(), None), (None, lambda: None)])
def test_native_pre_sam_option_refuses_missing_measurements_or_callback(diagnostics, cleanup):
    from product_search.infrastructure.replenishment_worker_entry import _serve_localization

    with pytest.raises(ReplenishmentError, match="RUNTIME_MISMATCH"):
        _serve_localization(
            {},
            object(),
            {
                "load_diagnostics": True,
                "empty_cache_after_photo": True,
                "empty_cache_before_sam": True,
            },
            object(),
            object(),
            diagnostics=diagnostics,
            cache_cleanup=cleanup,
        )
