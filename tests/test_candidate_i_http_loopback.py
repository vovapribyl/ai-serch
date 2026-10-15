import os
import socket
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep

import httpx
import pytest

from product_search.infrastructure.nail_ml_adapters import (
    ClientSettings,
    HttpNailLocalizationAdapter,
)
from product_search.infrastructure.nail_wire import WireLimits
from product_search.search.nail_contracts import LocalizationProfile, RgbImage


@pytest.fixture
def fake_server(tmp_path):
    root = Path(__file__).parents[1]
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    with (tmp_path / "server.log").open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                str(root / "tests/support/candidate_i_fake_server.py"),
                "--fd",
                str(sock.fileno()),
                "--runtime-root",
                str(runtime),
            ],
            cwd=root,
            pass_fds=(sock.fileno(),),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=log,
            stderr=log,
        )
        sock.close()
        try:
            deadline = monotonic() + 5
            with httpx.Client(trust_env=False, timeout=0.2) as probe:
                while True:
                    assert process.poll() is None, "Synthetic server exited before readiness"
                    try:
                        if probe.get(url + "/health/ready").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    assert monotonic() < deadline, "Synthetic server did not become ready"
                    sleep(0.01)
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    assert not any(p.suffix in (".png", ".jpg", ".json") for p in runtime.rglob("*"))


def test_real_http_round_trip_with_fake_model_and_repeated_owned_client(fake_server):
    settings = ClientSettings(fake_server, 1, 1, 1, 3, WireLimits(4096, 10, 1024 * 1024))
    client = HttpNailLocalizationAdapter(settings)
    profile = LocalizationProfile("a" * 64)
    result = client.localize(RgbImage(2, 1, b"\x12\x34\x56" * 2), profile)
    assert result.status == "OK"
    assert result.regions[0].mask.pixels == b"\xff\xff"
    assert result.regions[0].detector_box_xyxy == (0, 0, 2, 1)
    assert client.localize(RgbImage(1, 1, b"\0\0\0"), profile).status == "NO_NAILS"
    assert client.localize(RgbImage(1, 1, b"\x01\x02\x03"), profile).status == "OK"
