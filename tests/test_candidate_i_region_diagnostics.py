"""Opt-in artifacts capture rejected regions without changing HTTP or model results."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from product_search.search.nail_contracts import BinaryMask, LocalizedRegion, NailLocalization
from services.candidate_i.app import create_app
from services.candidate_i.settings import ServiceSettings
from tests.test_candidate_i_http_service import FP, LIMITS, image_png, multipart


def many_regions(number):
    def binding(image, profile):
        return NailLocalization(
            "OK",
            tuple(
                LocalizedRegion(
                    ordinal,
                    "nail",
                    0.9,
                    (0, 0, image.width, image.height),
                    BinaryMask(image.width, image.height, b"\xff" * image.width * image.height),
                )
                for ordinal in range(1, number + 1)
            ),
        )

    return binding


@pytest.mark.parametrize("number,http_status", [(10, 200), (20, 503), (33, 503)])
def test_capture_precedes_http_limit_and_preserves_all_model_regions(tmp_path, number, http_status):
    from services.candidate_i.region_diagnostics import ObservedBinding, RegionDiagnostics

    tmp_path.chmod(0o700)
    directory = tmp_path / "diagnostics"
    directory.mkdir(mode=0o700)
    recorder = RegionDiagnostics(directory)
    model = many_regions(number)
    wrapped = ObservedBinding(model, recorder)
    application = create_app(
        ServiceSettings(FP, LIMITS, tmp_path), wrapped, ready_check=lambda: True
    )
    payload = image_png(size=(16, 16))
    with TestClient(application) as client:
        response = client.post(
            "/v1/localizations", files=multipart(payload, {"width": 16, "height": 16})
        )
    assert response.status_code == http_status
    if http_status == 503:
        assert response.json()["code"] == "REGION_COUNT_LIMIT"
    snapshot = next(directory.glob("*/diagnostic.json"))
    data = json.loads(snapshot.read_text())
    assert data["total_regions"] == number
    assert data["saved_region_count"] == min(number, 32)
    assert data["status"] == ("PARTIAL" if number == 33 else "COMPLETE")
    assert data["truncated"] == (number == 33)
    assert data["extractor_fingerprint"] == FP
    assert data["rgb_sha256"] == hashlib.sha256(bytes((18, 52, 86)) * 16 * 16).hexdigest()
    assert data["regions"][0]["detector_box_xyxy"] == [0, 0, 16, 16]
    assert [x["ordinal"] for x in data["regions"]] == list(range(1, min(number, 32) + 1))
    for row in data["regions"]:
        with Image.open(snapshot.parent / row["mask_file"]) as image:
            assert image.size == (16, 16)
    with Image.open(snapshot.parent / data["overview_file"]) as image:
        assert image.size == (16, 16)
    assert all(f.stat().st_mode & 0o777 == 0o600 for f in snapshot.parent.iterdir())


def test_byte_budget_marks_partial_and_never_overruns_total(tmp_path):
    from product_search.search.nail_contracts import LocalizationProfile, RgbImage
    from services.candidate_i.region_diagnostics import ObservedBinding, RegionDiagnostics

    tmp_path.chmod(0o700)
    recorder = RegionDiagnostics(tmp_path, max_bytes=4096)
    image = RgbImage(16, 16, bytes((18, 52, 86)) * 16 * 16)
    model = many_regions(20)
    expected = model(image, LocalizationProfile(FP))
    wrapped = ObservedBinding(lambda *args: expected, recorder)
    assert wrapped(image, LocalizationProfile(FP)) is expected
    snapshot = next(tmp_path.glob("*/diagnostic.json"))
    data = json.loads(snapshot.read_text())
    assert data["status"] == "PARTIAL" and data["total_regions"] == 20
    assert "byte_limit" in data["truncation_reasons"]
    assert sum(f.stat().st_size for f in snapshot.parent.iterdir()) <= 4096
    # This is a one-snapshot probe, not an unbounded collection on repeated requests.
    wrapped(image, LocalizationProfile(FP))
    assert len(list(tmp_path.iterdir())) == 1


def test_save_error_does_not_replace_original_http_failure(tmp_path, monkeypatch):
    from services.candidate_i.region_diagnostics import ObservedBinding, RegionDiagnostics

    tmp_path.chmod(0o700)
    directory = tmp_path / "diagnostics"
    directory.mkdir(mode=0o700)
    recorder = RegionDiagnostics(directory)
    payload = image_png()
    application = create_app(
        ServiceSettings(FP, LIMITS, tmp_path),
        ObservedBinding(many_regions(20), recorder),
        ready_check=lambda: True,
    )
    monkeypatch.setattr(
        Image.Image, "save", lambda *a, **kw: (_ for _ in ()).throw(OSError("secret path"))
    )
    with TestClient(application) as client:
        response = client.post("/v1/localizations", files=multipart(payload))
    assert response.status_code == 503 and response.json()["code"] == "REGION_COUNT_LIMIT"
    assert recorder.last_status["status"] == "FAILED"
    assert "secret path" not in next(directory.glob("*/diagnostic.json")).read_text()


def test_default_off_creates_no_diagnostic_artifacts(tmp_path):
    tmp_path.chmod(0o700)
    application = create_app(
        ServiceSettings(FP, LIMITS, tmp_path), many_regions(20), ready_check=lambda: True
    )
    with TestClient(application) as client:
        response = client.post("/v1/localizations", files=multipart())
    assert response.status_code == 503 and response.json()["code"] == "REGION_COUNT_LIMIT"
    assert not list(tmp_path.glob("*/diagnostic.json"))


def test_diagnostic_failure_does_not_change_invalid_model_output(tmp_path):
    from services.candidate_i.region_diagnostics import ObservedBinding, RegionDiagnostics

    tmp_path.chmod(0o700)
    application = create_app(
        ServiceSettings(FP, LIMITS, tmp_path),
        ObservedBinding(lambda *a: object(), RegionDiagnostics(tmp_path)),
        ready_check=lambda: True,
    )
    with TestClient(application) as client:
        response = client.post("/v1/localizations", files=multipart())
    assert response.status_code == 500 and response.json()["code"] == "INVALID_MODEL_OUTPUT"


def test_mid_png_byte_limit_discards_partial_images(tmp_path):
    from product_search.search.nail_contracts import LocalizationProfile, RgbImage
    from services.candidate_i.region_diagnostics import ObservedBinding, RegionDiagnostics

    tmp_path.chmod(0o700)
    recorder = RegionDiagnostics(tmp_path, max_bytes=16450)
    image = RgbImage(16, 16, bytes((18, 52, 86)) * 16 * 16)
    ObservedBinding(many_regions(20), recorder)(image, LocalizationProfile(FP))
    folder = next(tmp_path.iterdir())
    data = json.loads((folder / "diagnostic.json").read_text())
    assert data["status"] == "PARTIAL" and data["saved_region_count"] == 0
    assert {f.name for f in folder.iterdir()} == {"diagnostic.json"}
    assert sum(f.stat().st_size for f in folder.iterdir()) <= 16450


def test_manifest_publication_failure_is_explicit_without_partial_json(tmp_path, monkeypatch):
    import os

    from product_search.search.nail_contracts import LocalizationProfile, RgbImage
    from services.candidate_i.region_diagnostics import ObservedBinding, RegionDiagnostics

    tmp_path.chmod(0o700)
    recorder = RegionDiagnostics(tmp_path)
    monkeypatch.setattr(
        os,
        "replace",
        lambda *a: (_ for _ in ()).throw(OSError("secret disk path")),
    )
    image = RgbImage(16, 16, bytes((18, 52, 86)) * 16 * 16)
    model = many_regions(20)
    result = model(image, LocalizationProfile(FP))
    assert ObservedBinding(lambda *a: result, recorder)(image, LocalizationProfile(FP)) is result
    assert recorder.last_status["status"] == "FAILED"
    folder = next(tmp_path.iterdir())
    assert not (folder / "diagnostic.json").exists()
    assert not list(folder.glob(".control-*"))
