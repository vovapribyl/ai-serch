"""Bounded generated-only two-process probe; no database or corpus access."""

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import platform
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from product_search.infrastructure.nail_ml_adapters import (
    ClientSettings,
    HttpNailLocalizationAdapter,
    NailEmbeddingAdapter,
)
from product_search.infrastructure.nail_runtime import FileLease
from product_search.infrastructure.nail_wire import WireLimits
from product_search.search.nail_contracts import (
    DecodeProfile,
    EmbeddingProfile,
    LocalizationProfile,
    NailProcessingError,
    PhotoInput,
    RgbImage,
)
from product_search.search.nail_image_processor import NailImageProcessor
from services.candidate_i.bootstrap import installed_inventory
from tests.support.candidate_i_resource_metrics import sample_mps
from tests.support.candidate_i_scenario_probe import backend_embedding, encode_all_crops, real_crops


def generated_image():
    image = Image.new("RGB", (256, 256), color=(245, 245, 245))
    draw = ImageDraw.Draw(image)
    for offset in range(5):
        x = 48 + offset * 30
        draw.rounded_rectangle((x, 88, x + 20, 152), radius=10, fill=(180, 40, 80))
    return RgbImage(*image.size, image.tobytes())


def resource_violation(pressure, i_rss, backend_rss, profile, swapout_delta):
    policy = profile.get("resource_policy", "strict_no_warning_no_swap_v1")
    if policy not in {"strict_no_warning_no_swap_v1", "scenario_suitability_v1"}:
        raise ValueError("unknown resource policy")
    pressure_failure = pressure not in ({1, 2} if policy == "scenario_suitability_v1" else {1})
    swap_failure = swapout_delta < 0 or (policy != "scenario_suitability_v1" and swapout_delta != 0)
    return (
        pressure_failure
        or swap_failure
        or i_rss > profile["i_rss_bytes"]
        or backend_rss > profile["backend_rss_bytes"]
        or i_rss + backend_rss > profile["combined_rss_bytes"]
    )


def require_resource_sample(first_sample, sampler, violations, *, timeout=5):
    assert first_sample.wait(timeout=timeout), "resource sampler not ready"
    assert sampler.is_alive(), "resource sampler stopped"
    assert not violations, violations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assembly", required=True)
    parser.add_argument("--i-python", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--started-at", type=float, required=True)
    parser.add_argument("--initial-model-calls", type=int, required=True)
    parser.add_argument("--swapouts-baseline", type=int, required=True)
    parser.add_argument("--cold-only", action="store_true")
    parser.add_argument("--mps-footprint", action="store_true")
    parser.add_argument("--control-fallback", action="store_true")
    parser.add_argument("--trace-label", default="20261008")
    parser.add_argument("--scenario-suitability", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.trace_label):
        parser.error("safe trace label required")
    if args.control_fallback and not (args.cold_only and args.mps_footprint):
        parser.error("control fallback requires cold-only and mps-footprint")
    if args.scenario_suitability and (
        args.cold_only or args.control_fallback or not args.mps_footprint
    ):
        parser.error("scenario requires full no-fallback mode with telemetry")
    if args.scenario_suitability and os.environ.get("CANDIDATE_I_OWNED_WATCHDOG") != "1":
        parser.error("scenario requires external owned-process watchdog")
    a = json.loads(Path(args.assembly).read_text())
    runtime = Path(a["runtime_root"])
    profile = json.loads(Path(a["files"]["runtime_profile"]).read_text())
    if (profile.get("resource_policy") == "scenario_suitability_v1") != args.scenario_suitability:
        parser.error("scenario policy and mode must match")
    if args.scenario_suitability and (
        profile["max_model_calls"] != 65
        or profile.get("scenario_rounds") != 2
        or profile["max_region_count"] != 10
        or args.initial_model_calls != 0
    ):
        parser.error("scenario requires frozen two-round budget")
    if args.scenario_suitability:
        backend_hash = hashlib.sha256(
            json.dumps(installed_inventory(), separators=(",", ":")).encode()
        ).hexdigest()
        if (
            backend_hash != profile.get("backend_inventory_sha256")
            or platform.python_version() != profile.get("backend_python")
            or platform.machine() != profile.get("backend_machine")
            or os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") is not None
        ):
            parser.error("actual backend identity must match before I launch")
    calls = args.initial_model_calls
    assert 0 <= calls <= profile["max_model_calls"]
    resources = {
        "i_rss_peak": 0,
        "backend_rss_peak": 0,
        "combined_rss_peak": 0,
        "pressure_levels": [],
        "samples": 0,
        "swapouts_delta": 0,
    }
    stop = threading.Event()
    backend_mps = {"status": "not_imported", "epoch": None}
    first_sample = threading.Event()
    violations = []
    timeline_path = runtime / f"host-footprint-{args.trace_label}.jsonl"
    trace = timeline_path.open("x") if args.mps_footprint else None
    if trace is not None:
        os.chmod(timeline_path, 0o600)

    def admit():
        nonlocal calls
        require_resource_sample(first_sample, sampler, violations)
        assert calls < profile["max_model_calls"]
        assert time.time() - args.started_at < profile["wall_clock_limit_s"]
        calls += 1
        print(
            json.dumps(
                {"event": "model_admission", "model_calls": calls, "epoch": time.time()},
                sort_keys=True,
            ),
            flush=True,
        )

    def rss(pid):
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=False
        )
        if result.returncode != 0 or not result.stdout.strip():
            if pid == process.pid and process.poll() is not None:
                return 0
            raise RuntimeError("RSS_OBSERVATION_FAILED")
        return int(result.stdout.strip()) * 1024

    def monitor_backend_mps():
        nonlocal backend_mps
        while not stop.is_set():
            try:
                value = sample_mps(sys.modules.get("torch"))
            except Exception as error:  # noqa: BLE001 - optional telemetry cannot block host guard.
                value = {"status": "unavailable", "error_type": type(error).__name__}
            backend_mps = {"epoch": time.time(), **value}
            stop.wait(0.25)

    def monitor(pid):
        vmmap_taken = False
        while not stop.is_set():
            try:
                i_rss, backend_rss = rss(pid), rss(os.getpid())
                pressure = int(
                    subprocess.check_output(
                        ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], text=True
                    ).strip()
                )
                resources["i_rss_peak"] = max(resources["i_rss_peak"], i_rss)
                resources["backend_rss_peak"] = max(resources["backend_rss_peak"], backend_rss)
                resources["combined_rss_peak"] = max(
                    resources["combined_rss_peak"], i_rss + backend_rss
                )
                resources["pressure_levels"].append(pressure)
                resources["samples"] += 1
                vm = subprocess.check_output(["vm_stat"], text=True)
                swapouts = int(re.search(r"Swapouts:\s+(\d+)\.", vm)[1])
                resources["swapouts_delta"] = swapouts - args.swapouts_baseline
                if resource_violation(
                    pressure, i_rss, backend_rss, profile, resources["swapouts_delta"]
                ):
                    violations.append("RESOURCE_CEILING")
                if trace is not None:
                    value = {
                        "epoch": time.time(),
                        "monotonic": time.monotonic(),
                        "i_rss": i_rss,
                        "controller_rss": backend_rss,
                        "pressure": pressure,
                        "swapouts_delta": resources["swapouts_delta"],
                        "backend_mps": backend_mps,
                    }
                    for field in (
                        "Pages free",
                        "Pages inactive",
                        "Pages wired down",
                        "Pages occupied by compressor",
                    ):
                        value[field] = int(re.search(re.escape(field) + r":\s+(\d+)\.", vm)[1])
                    trace.write(json.dumps(value, sort_keys=True) + "\n")
                    trace.flush()
                first_sample.set()
                if trace is not None and pressure != 1 and not vmmap_taken:
                    vmmap_taken = True
                    path = runtime / f"i-vmmap-warning-{args.trace_label}.txt"
                    try:
                        with path.open("xb") as output:
                            os.chmod(path, 0o600)
                            result = subprocess.run(
                                ["vmmap", "-summary", str(pid)],
                                stdout=output,
                                stderr=subprocess.STDOUT,
                                timeout=3,
                                check=False,
                            )
                        resources["vmmap_exit"] = result.returncode
                    except Exception as error:  # noqa: BLE001 - optional diagnostic.
                        resources["vmmap_error_type"] = type(error).__name__
            except Exception as error:  # noqa: BLE001 - failed resource observation fails the probe.
                violations.append(type(error).__name__)
                if trace is not None:
                    trace.write(
                        json.dumps(
                            {
                                "event": "resource_observation_error",
                                "error_type": type(error).__name__,
                                "epoch": time.time(),
                                "monotonic": time.monotonic(),
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    trace.flush()
            stop.wait(0.5)
        if trace is not None:
            trace.close()

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    root = Path(__file__).parents[2]
    env = {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
    env["CANDIDATE_I_TRACE_LABEL"] = args.trace_label
    if args.control_fallback:
        env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
    if args.mps_footprint:
        env["CANDIDATE_I_MPS_TRACE"] = "1"
    outcomes = {}
    coordinator = FileLease(runtime, "coordinator.lock")
    assert coordinator.try_acquire()
    server_name = (
        "candidate_i_control_server.py" if args.control_fallback else "candidate_i_real_server.py"
    )
    log_name = f"server-{args.trace_label}.log" if args.control_fallback else "server.log"
    if args.scenario_suitability:
        log_name = f"server-{args.trace_label}.log"
    with (runtime / log_name).open(
        "xb" if args.control_fallback or args.scenario_suitability else "wb"
    ) as log:
        process = subprocess.Popen(
            [
                args.i_python,
                "-B",
                str(root / "tests/support" / server_name),
                "--assembly",
                args.assembly,
                "--fd",
                str(sock.fileno()),
            ],
            cwd=root,
            env=env,
            pass_fds=(sock.fileno(),),
            stdout=log,
            stderr=log,
        )
        sock.close()
        sampler = threading.Thread(target=monitor, args=(process.pid,), daemon=True)
        backend_sampler = threading.Thread(target=monitor_backend_mps, daemon=True)
        backend_sampler.start()
        sampler.start()
        try:
            with httpx.Client(trust_env=False, timeout=profile["read_timeout_s"]) as probe:
                deadline = time.monotonic() + 20
                while True:
                    assert process.poll() is None, "I server exited"
                    try:
                        response = probe.get(url + "/health/ready")
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    assert time.monotonic() < deadline, "bootstrap deadline"
                    time.sleep(0.05)
                fingerprint = response.json()["extractor_fingerprint"]
                loc_profile = LocalizationProfile(fingerprint)
                limits = WireLimits(
                    profile["max_decoded_pixels"],
                    profile["max_region_count"],
                    profile["max_response_bytes"],
                )
                client = HttpNailLocalizationAdapter(
                    ClientSettings(
                        url,
                        profile["connect_timeout_s"],
                        profile["write_timeout_s"],
                        profile["read_timeout_s"],
                        profile["overall_timeout_s"],
                        limits,
                    )
                )
                image = generated_image()
                parent_device = FileLease(runtime, "device.lock")
                assert parent_device.try_acquire()
                try:
                    try:
                        client.localize(image, loc_profile)
                    except NailProcessingError as error:
                        assert error.code == "BUSY"
                    else:
                        raise AssertionError("shared device lease ignored")
                finally:
                    parent_device.release()
                outcomes["shared_device_busy"] = True
                t = time.monotonic()
                admit()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(client.localize, image, loc_profile)
                    while not future.done():
                        health = probe.get(url + "/health/ready").json()
                        if health.get("busy"):
                            outcomes["busy_observed"] = True
                            break
                    outcomes["concurrent_busy"] = "NOT_RUN_CONTROLLED_FAKE_TESTS_ONLY"
                    result = future.result(timeout=profile["overall_timeout_s"])
                durations = [round(time.monotonic() - t, 3)]
                outcomes.update(
                    cold_status=result.status,
                    cold_region_count=len(result.regions),
                    cold_seconds=durations[0],
                )
                if args.cold_only:
                    outcomes["probe_mode"] = "cold_only"
                    assert not violations, violations
                    return
                if args.scenario_suitability:
                    # Keep production provider caching across both rounds; measure real residency.
                    require_resource_sample(first_sample, sampler, violations)
                    embedding, revisions = backend_embedding(Path(args.models), admit)
                    rounds = []
                    outcomes["scenario_rounds"] = rounds
                    for round_index in range(profile["scenario_rounds"]):
                        if round_index:
                            admit()
                            t = time.monotonic()
                            result = client.localize(image, loc_profile)
                        localization_seconds = (
                            round(time.monotonic() - t, 3) if round_index else durations[0]
                        )
                        assert not violations, violations
                        crops = real_crops(image, result, loc_profile, profile)
                        round_summary = {
                            "round": round_index + 1,
                            "localization_status": result.status,
                            "region_count": len(crops),
                            "localization_seconds": localization_seconds,
                        }
                        rounds.append(round_summary)
                        lease = FileLease(runtime, "device.lock")
                        assert lease.try_acquire(), "I retained device lease after completed HTTP"
                        try:
                            round_summary["providers"] = encode_all_crops(
                                embedding, crops, EmbeddingProfile(revisions)
                            )
                        finally:
                            lease.release()
                        round_summary["resident_provider_count"] = len(embedding.providers)
                        round_summary["backend_mps_sample"] = backend_mps
                        assert not violations, violations
                    outcomes["probe_mode"] = "scenario_suitability"
                    outcomes["lifecycle_source"] = "real_http_result_all_regions"
                    return
                for _ in range(2):
                    admit()
                    t = time.monotonic()
                    result = client.localize(image, loc_profile)
                    durations.append(round(time.monotonic() - t, 3))
                outcomes.update(
                    i_status=result.status,
                    region_count=len(result.regions),
                    cold_warm_seconds=durations,
                    extractor_fingerprint=fingerprint,
                )
                if result.status == "OK":
                    assert len(result.regions) == 1, (
                        "single-region fixture required for remaining budget"
                    )

                    class GeneratedStore:
                        def read_rgb(self, photo, decode):
                            return image

                    class CompletedLocalization:
                        def localize(self, rgb, pinned):
                            assert rgb == image and pinned == loc_profile
                            return result

                    processor = NailImageProcessor(
                        GeneratedStore(),
                        CompletedLocalization(),
                        DecodeProfile(profile["max_source_bytes"], profile["max_decoded_pixels"]),
                        loc_profile,
                        profile["max_region_count"],
                    )
                    photo = processor.process(
                        PhotoInput(1, "a" * 32, hashlib.sha256(image.pixels).hexdigest())
                    )
                    crops = tuple(region.rgb_crop for region in photo.regions)
                    outcomes["crop_frame"] = [crops[0].width, crops[0].height]
                    outcomes["lifecycle_source"] = "real_http_result"
                else:
                    crops = (RgbImage(32, 64, b"\xb4\x28\x50" * (32 * 64)),)
                    outcomes["lifecycle_source"] = "independent_synthetic_provider_probe"
                from product_search.search.model_manifest import read_manifest, verify_manifest
                from product_search.search.openclip_provider import OpenClipImageProvider
                from product_search.search.transformers_provider import TransformersImageProvider

                model_root = Path(args.models)
                revisions = (
                    ("openclip_b32", "1a25a446712ba5ee05982a381eed697ef9b435cf"),
                    ("dinov2_b14", "f9e44c814b77203eaa57a6bdbbd535f21ede1415"),
                    ("siglip2_b16_224", "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"),
                )
                manifests = (
                    "7daa2142c71b4c9b0ec0555361845dc78fbb0dbce6bed64ca784ae853404d67d",
                    "ecb704699963bfe8bb17f8defd3792daa26cf0da822032b796f6f5a40d606783",
                    "45f047affe3c7c58e6789db142ae73b40096a0207f1417e3f976d3a9d15969e9",
                )
                for (key, _), expected in zip(revisions, manifests):
                    manifest = read_manifest(model_root / key)
                    assert verify_manifest(model_root / key, manifest).sha256 == expected
                embedding = NailEmbeddingAdapter(
                    {
                        "openclip_b32": lambda: OpenClipImageProvider(
                            revisions[0][1], model_root / revisions[0][0], device="mps"
                        ),
                        "dinov2_b14": lambda: TransformersImageProvider(
                            *revisions[1], model_root / revisions[1][0], 768, device="mps"
                        ),
                        "siglip2_b16_224": lambda: TransformersImageProvider(
                            *revisions[2], model_root / revisions[2][0], 768, device="mps"
                        ),
                    }
                )
                dimensions = []
                for key, dimension in (
                    ("openclip_b32", 512),
                    ("dinov2_b14", 768),
                    ("siglip2_b16_224", 768),
                ):
                    admit()
                    lease = FileLease(runtime, "device.lock")
                    assert lease.try_acquire(), "I retained device lease after completed HTTP"
                    try:
                        vectors = embedding.encode(key, crops, EmbeddingProfile(revisions))
                    finally:
                        lease.release()
                    assert len(vectors) == 1 and len(vectors[0]) == dimension
                    assert all(math.isfinite(value) for value in vectors[0])
                    assert abs(math.sqrt(sum(value * value for value in vectors[0])) - 1) < 1e-5
                    dimensions.append(dimension)
                outcomes["provider_dimensions"] = dimensions
                assert not violations, violations
        except BaseException as error:
            outcomes["failure_kind"] = type(error).__name__
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            stop.set()
            sampler.join(timeout=5)
            backend_sampler.join(timeout=1)
            coordinator.release()
            summary_resources = dict(resources)
            summary_resources["pressure_levels"] = sorted(set(resources["pressure_levels"]))
            print(
                json.dumps(
                    {
                        "event": "teardown",
                        "outcomes": outcomes,
                        "resources": summary_resources,
                        "violations": sorted(set(violations)),
                        "model_calls": calls,
                        "i_process_exited": process.poll() is not None,
                        "series_elapsed_seconds": round(time.time() - args.started_at, 2),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    for name in ("device.lock", "coordinator.lock"):
        lease = FileLease(runtime, name)
        assert lease.try_acquire()
        lease.release()
    resources["pressure_levels"] = sorted(set(resources["pressure_levels"]))
    outcomes.update(
        model_calls=calls,
        series_elapsed_seconds=round(time.time() - args.started_at, 2),
        resources=resources,
        cleanup=True,
        i_process_exited=True,
    )
    print(json.dumps(outcomes, sort_keys=True))


if __name__ == "__main__":
    main()
