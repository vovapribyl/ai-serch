import hashlib
from types import SimpleNamespace

import pytest
from PIL import Image

from product_search.infrastructure.nail_build_runner import (
    AdmissionBudget,
    BuildStop,
    ManifestImageStore,
    run_admitted_build,
)
from product_search.search.nail_contracts import DecodeProfile, PhotoInput


def test_manifest_source_is_read_only_and_preserves_white_alpha(tmp_path):
    path = tmp_path / "legacy.png"
    Image.new("RGBA", (2, 1), (255, 0, 0, 0)).save(path)
    path.chmod(0o644)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    before = path.stat()
    photo = PhotoInput(1, "a" * 32, sha)
    store = ManifestImageStore(tmp_path, {photo.source_ref: path.name}, object())
    rgb = store.read_rgb(photo, DecodeProfile(1000, 2))
    assert rgb.pixels == b"\xff" * 6
    assert path.stat().st_mode == before.st_mode
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha


@pytest.mark.parametrize("fault", ["hash", "pixels", "symlink", "escape"])
def test_invalid_source_never_decodes_as_valid(tmp_path, fault):
    path = tmp_path / "source.png"
    Image.new("RGB", (2, 1), "red").save(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    name = path.name
    if fault == "symlink":
        (tmp_path / "link").symlink_to(path)
        name = "link"
    if fault == "escape":
        name = "../source.png"
    photo = PhotoInput(1, "a" * 32, "b" * 64 if fault == "hash" else sha)
    store = ManifestImageStore(tmp_path, {photo.source_ref: name}, object())
    with pytest.raises((BuildStop, ValueError)):
        store.read_rgb(photo, DecodeProfile(1000, 1 if fault == "pixels" else 2))


def test_budget_stop_is_sticky_even_when_resource_sample_recovers():
    safe = [False]
    gate = AdmissionBudget(2, 10, lambda: safe[0], lambda: 0)
    with pytest.raises(BuildStop):
        gate.admit()
    safe[0] = True
    with pytest.raises(BuildStop):
        gate.admit()


@pytest.mark.parametrize("fault", ["limit", "timeout"])
def test_terminal_gate_denies_all_later_admissions(fault):
    now = [0]
    gate = AdmissionBudget(1, 10, lambda: True, lambda: now[0])
    gate.admit()
    if fault == "timeout":
        now[0] = 11
    with pytest.raises(BuildStop):
        gate.admit()
    now[0] = 0
    with pytest.raises(BuildStop):
        gate.admit()


class Lease:
    def __init__(self):
        self.held = False

    def try_acquire(self):
        self.held = True
        return True

    def release(self):
        self.held = False


@pytest.mark.parametrize("bad", ["target", "inputs", "runtime"])
def test_failed_verification_does_not_create_building_or_hold_lease(bad):
    events = []
    service = SimpleNamespace(execute=lambda *args, **kwargs: events.append("BUILDING"))
    lease = Lease()
    checks = {name: (lambda name=name: name != bad) for name in ("target", "inputs", "runtime")}
    with pytest.raises(BuildStop):
        run_admitted_build(
            service,
            None,
            (),
            None,
            target_check=checks["target"],
            input_check=checks["inputs"],
            runtime_check=checks["runtime"],
            coordinator=lease,
        )
    assert events == []
    assert not lease.held


def test_admitted_runner_never_publishes_and_releases_after_owned_worker_exit():
    lease = Lease()

    class Service:
        def execute(self, *args, **kwargs):
            assert lease.held
            raise SystemExit(17)

        def publish(self, *args):
            pytest.fail("Build runner must never publish")

    with pytest.raises(SystemExit):
        run_admitted_build(
            Service(),
            None,
            (),
            None,
            target_check=lambda: True,
            input_check=lambda: True,
            runtime_check=lambda: True,
            coordinator=lease,
        )
    assert not lease.held


def test_wrong_target_descriptor_denies_connection_before_sql(tmp_path, monkeypatch):
    import json

    from product_search.infrastructure.nail_build_runner import OwnedTarget

    path = tmp_path / "descriptor.json"
    data = {
        "marker": "owned",
        "container_id": "container",
        "image": "image",
        "volume": "volume",
        "config": {
            "host": "127.0.0.1",
            "port": 12345,
            "user": "owned",
            "dbname": "owned",
            "password": "test-only",
            "connect_timeout": 1,
        },
    }
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    import psycopg

    sql_calls = []

    def forbidden_connect(**config):
        sql_calls.append("SQL")
        raise AssertionError("Wrong container marker must be rejected before SQL")

    monkeypatch.setattr(psycopg, "connect", forbidden_connect)
    container = {
        "Id": "container",
        "Image": "image",
        "State": {"Running": True},
        "Config": {"Labels": {"candidate-i-g5-owner": "other"}},
        "Mounts": [{"Type": "volume", "Name": "volume", "Destination": "/var/lib/postgresql/data"}],
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "12345"}]}},
    }
    volume = {"Labels": {"candidate-i-g5-owner": "owned"}}
    target = OwnedTarget(
        path, expected, inspect=lambda kind, identity: volume if kind == "volume" else container
    )
    with pytest.raises(BuildStop):
        target.connect()
    data["config"]["dbname"] = "other"
    path.write_text(json.dumps(data))
    with pytest.raises(BuildStop):
        target.connect()
    assert sql_calls == []


def test_each_provider_load_and_each_crop_has_an_admission_and_releases_device():
    from product_search.infrastructure.nail_build_runner import admitted_provider

    calls = []
    provider = SimpleNamespace(
        model_key="openclip_b32",
        revision="r",
        embedding_dim=512,
        encode_image=lambda image: calls.append("encode") or (1.0,),
    )
    gate = AdmissionBudget(3, 10, lambda: True, lambda: 0)
    lease = Lease()
    factory = admitted_provider(lambda: calls.append("load") or provider, gate, lease)
    wrapped = factory()
    wrapped.encode_image(None)
    wrapped.encode_image(None)
    assert calls == ["load", "encode", "encode"]
    assert gate.used == 3 and not lease.held
    with pytest.raises(BuildStop):
        wrapped.encode_image(None)
    assert calls == ["load", "encode", "encode"] and not lease.held


def test_sdk_translation_cannot_turn_terminal_stop_into_a_recoverable_photo_error():
    from product_search.infrastructure.nail_build_runner import GuardedEmbedding, admitted_provider
    from product_search.infrastructure.nail_ml_adapters import NailEmbeddingAdapter
    from product_search.search.nail_contracts import EmbeddingProfile, RgbImage

    calls = []
    provider = SimpleNamespace(
        model_key="openclip_b32",
        revision="r",
        embedding_dim=512,
        encode_image=lambda image: calls.append("encode") or (1.0,) + (0.0,) * 511,
    )
    gate = AdmissionBudget(1, 10, lambda: True, lambda: 0)
    lease = Lease()
    port = GuardedEmbedding(
        NailEmbeddingAdapter(
            {
                "openclip_b32": admitted_provider(
                    lambda: calls.append("load") or provider, gate, lease
                )
            }
        ),
        gate,
    )
    profile = EmbeddingProfile(
        (("openclip_b32", "r"), ("dinov2_b14", "r"), ("siglip2_b16_224", "r"))
    )
    for _ in range(2):
        with pytest.raises(BuildStop):
            port.encode("openclip_b32", (RgbImage(1, 1, b"abc"),), profile)
    assert calls == ["load"] and not lease.held


@pytest.mark.parametrize("fault", ["budget", "error"])
def test_i_admission_is_counted_once_and_terminal_error_denies_next_photo(fault):
    from product_search.infrastructure.nail_build_runner import GuardedLocalization
    from product_search.search.nail_contracts import NailLocalization, NailProcessingError

    calls = []

    def localize(*args):
        calls.append("I")
        if fault == "error":
            raise NailProcessingError("MODEL_ERROR")
        return NailLocalization("NO_NAILS", ())

    gate = AdmissionBudget(1, 10, lambda: True, lambda: 0)
    port = GuardedLocalization(SimpleNamespace(localize=localize), gate)
    if fault == "error":
        with pytest.raises(BuildStop):
            port.localize(None, None)
    else:
        assert port.localize(None, None).status == "NO_NAILS"
    with pytest.raises(BuildStop):
        port.localize(None, None)
    assert calls == ["I"] and gate.used == 1


def test_mutated_preparation_bundle_is_denied_before_target_access(tmp_path):
    from product_search.infrastructure.nail_build_runner import verify_preparation

    p = tmp_path / "bundle.json"
    p.write_text("{}")
    p.chmod(0o600)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    p.write_text('{"target": "changed"}')
    with pytest.raises(BuildStop):
        verify_preparation(p, sha)


@pytest.mark.parametrize("known", [True, False])
def test_localization_stop_keeps_safe_wire_code_but_not_private_details(known):
    from product_search.infrastructure.nail_build_runner import GuardedLocalization
    from product_search.search.nail_contracts import NailProcessingError

    class Adapter:
        def localize(self, *args):
            raise NailProcessingError(
                "RESOURCE_LIMIT" if known else "private-path-must-not-be-published",
                reason="private-cause-message",
            )

    budget = AdmissionBudget(1, 10, lambda: True, lambda: 0)
    with pytest.raises(BuildStop) as caught:
        GuardedLocalization(Adapter(), budget).localize(None, None)
    assert budget.stopped and budget.used == 1
    assert getattr(caught.value, "cause_type", None) == "NailProcessingError"
    assert getattr(caught.value, "cause_code", None) == ("RESOURCE_LIMIT" if known else None)
    assert "private-cause-message" not in str(caught.value)


def test_native_cli_failure_reports_safe_cause_code(monkeypatch, capsys):
    from scripts import run_nail_native_build

    error = BuildStop("LOCALIZATION_STOP")
    error.cause_code = "RESOURCE_LIMIT"
    error.cause_type = "NailProcessingError"

    def fail(*args):
        raise error

    monkeypatch.setattr(run_nail_native_build, "load_job", fail)
    assert run_nail_native_build.main(["--job", "unused", "--job-sha256", "a" * 64, "--check"]) == 3
    result = __import__("json").loads(capsys.readouterr().out)
    assert (
        result.get("cause_code") == "RESOURCE_LIMIT"
        and result.get("cause_type") == "NailProcessingError"
    )


@pytest.mark.parametrize("code", ["REGION_COUNT_LIMIT", "RESPONSE_SIZE_LIMIT"])
def test_photo_result_limit_does_not_deny_next_localization(code):
    from product_search.infrastructure.nail_build_runner import GuardedLocalization
    from product_search.search.nail_contracts import NailLocalization, NailProcessingError

    calls = []
    def localize(*args):
        calls.append(1)
        if len(calls) == 1:
            raise NailProcessingError(code)
        return NailLocalization("NO_NAILS", ())
    budget = AdmissionBudget(2, 10, lambda: True, lambda: 0)
    port = GuardedLocalization(SimpleNamespace(localize=localize), budget)
    with pytest.raises(NailProcessingError) as caught:
        port.localize(None, None)
    assert caught.value.code == code and not budget.stopped
    assert port.localize(None, None).status == "NO_NAILS"
    assert budget.used == 2


@pytest.mark.parametrize("code", ["RESOURCE_ERROR", "MODEL_ERROR", "PROFILE_MISMATCH", "UNKNOWN"])
def test_non_photo_limit_failure_remains_terminal(code):
    from product_search.infrastructure.nail_build_runner import GuardedLocalization
    from product_search.search.nail_contracts import NailProcessingError
    def localize(*args):
        raise NailProcessingError(code)
    budget = AdmissionBudget(2, 10, lambda: True, lambda: 0)
    port = GuardedLocalization(SimpleNamespace(localize=localize), budget)
    with pytest.raises(BuildStop):
        port.localize(None, None)
    assert budget.stopped
    with pytest.raises(BuildStop):
        port.localize(None, None)
    assert budget.used == 1
