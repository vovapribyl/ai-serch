"""B1 vertical fake flow with real PostgreSQL receipts and private files/IPC."""

import json
import time
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from product_search.infrastructure.replenishment_application import LocalReplenishmentApplication
from product_search.infrastructure.replenishment_artifacts import CheckpointFiles
from product_search.infrastructure.replenishment_cli import OwnerDispatcher
from product_search.infrastructure.replenishment_repository import PostgresReplenishment
from product_search.search.nail_contracts import MODEL_DIMENSIONS
from product_search.search.replenishment_contracts import (
    PhotoProcessingError,
    ReplenishmentError,
    ResourceObservation,
)
from product_search.web.app import create_app
from tests.test_replenishment_artifacts import png
from tests.test_replenishment_postgres_integration import (
    db as db,  # noqa: PLC0414 -- pytest fixture
)
from tests.test_replenishment_postgres_integration import (
    fixture_inventory,
    profile_payload,
    repository,
)


class Clock:
    def __init__(self):
        self.value = None

    def monotonic(self):
        return time.monotonic() if self.value is None else self.value


class FakeWorkers:
    def __init__(self, files, app, clock, events, *, fail=False, expire=False):
        self.files, self.app, self.clock, self.events = files, app, clock, events
        self.fail, self.expire = fail, expire

    def open_stage(self, stage, model, owner, pkg, end):
        self.pkg = pkg
        self.events.append(("open", stage, model))
        assert self.app.supervisor.mode == "BUILD"
        with (
            pytest.raises(ReplenishmentError, match="TEMPORARILY_UNAVAILABLE"),
            self.app.supervisor.query_permit(),
        ):
            pytest.fail("search during build")
        web = create_app(
            lambda: True, object(), search_available=lambda: self.app.supervisor.mode == "SEARCH"
        )
        assert TestClient(web).get("/").status_code == 503

    def process(self, photo, attempt, owner, end):
        if self.fail == "all" or (self.fail and photo == self.app.queue[0]):
            raise PhotoProcessingError("synthetic")
        if attempt.stage_key == "localization":
            files = {"crop-1.png": png("RGB"), "mask-1.png": png("L")}
        else:
            dim = dict(MODEL_DIMENSIONS)[attempt.model_key]
            files = {
                "vectors.json": json.dumps(
                    {
                        "model_key": attempt.model_key,
                        "vectors": [{"ordinal": 1, "values": [0.25] * dim}],
                    }
                ).encode()
            }
        output = self.files.write_staging(attempt, self.pkg, 1, files)
        if self.expire:
            self.clock.value = 58.0
        return output

    def close_stage(self, owner, end):
        self.events.append(("close", owner.run_ref))
        return True


@pytest.fixture
def flow(db, tmp_path):
    db.migrate()
    with db.connect() as conn:
        products = fixture_inventory(conn, 2)
    template = repository(db, products)
    pkg = type(template.package)(
        **{**asdict(template.package), "max_vector_bytes": 20000, "max_wire_bytes": 8000}
    )
    tmp_path.chmod(0o700)
    root = tmp_path / "runtime"
    root.mkdir(mode=0o700)
    files_root = tmp_path / "files"
    files_root.mkdir(mode=0o700)
    files = CheckpointFiles(files_root)
    clock = Clock()
    events = []
    workers = {}

    def repo_factory(p, end):
        return PostgresReplenishment(db.connect, p, end, clock=clock.monotonic)

    def reader(run, mode):
        read = PostgresReplenishment(db.connect, pkg, db.end_at, clock=time.monotonic)
        return read.read_summary(run, search_state=mode)

    app = LocalReplenishmentApplication(
        root,
        repo_factory,
        profile_payload(),
        files,
        lambda *args: FakeWorkers(files, app, clock, events, **workers),
        clock,
        authorize_build=lambda p: True,
        authorize_search=lambda p: True,
        observe=lambda: ResourceObservation("OK", clock.monotonic()),
        quiesce=lambda *args: True,
        summary_reader=reader,
    )
    app.initialize_search(pkg)
    try:
        yield app, pkg, products, clock, events, workers
    finally:
        if hasattr(app, "supervisor"):
            app.supervisor.close(end_at=clock.monotonic() + 5, stop_grace=1, kill_wait=1)


def command(pkg, products):
    return {
        "schema_version": 1,
        "action": "start",
        "package": asdict(pkg),
        "inventory": [{**asdict(p), "photos": [asdict(f) for f in p.photos]} for p in products],
    }


def test_start_stages_publish_saved_summary_and_return_search(flow, db):
    app, pkg, products, _clock, events, _ = flow
    dispatcher = OwnerDispatcher(app, role="OWNER")
    answer = dispatcher.handle(command(pkg, products))
    assert answer["status"] == "OK"
    summary = answer["summary"]
    assert summary["status"] == "COMPLETED" and summary["search_state"] == "SEARCH"
    assert [outcome for _, outcome in summary["outcomes"]] == ["OK", "OK"]
    assert summary["publications"][0]["state"] == "SUCCEEDED"
    assert [e[1:] for e in events if e[0] == "open"] == [
        ("localization", ""),
        ("embedding", "openclip_b32"),
        ("embedding", "dinov2_b14"),
        ("embedding", "siglip2_b16_224"),
    ]
    assert sum(e[0] == "close" for e in events) == 4
    assert (
        dispatcher.handle({"schema_version": 1, "action": "status", "run": summary["run_ref"]})[
            "summary"
        ]
        == summary
    )
    with app.supervisor.query_permit():
        pass
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM revision_vectors").fetchone()[0] == 6


def test_photo_error_is_saved_without_losing_successful_photo(flow):
    app, pkg, products, _, _, workers = flow
    workers["fail"] = True
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "OK"
    assert [o for _, o in answer["summary"]["outcomes"]] == ["ERROR", "OK"]
    assert answer["summary"]["publications"][0]["state"] == "SUCCEEDED"


def test_controller_and_drain_use_the_same_deadline(flow, db):
    app, pkg, products, clock, _, workers = flow
    clock.value = 0.0

    def drain(*args):
        clock.value = 10.0
        return True

    app.supervisor.quiesce = drain
    workers["expire"] = True
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "STOPPED" and answer["reason"] == "DEADLINE"
    assert app.supervisor.mode == "RECOVERY_REQUIRED"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT status FROM replenishment_runs WHERE id=%s", (answer["summary"]["run_ref"],)
            ).fetchone()[0]
            == "EXPIRED"
        )


def test_denied_build_never_opens_worker(flow):
    app, pkg, products, _, events, _ = flow
    app.authorize_build = lambda p: False
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "REFUSED" and answer["reason"] == "INVALID_SCOPE"
    assert app.supervisor.mode == "SEARCH" and events == []


def test_success_summary_reports_no_remaining_stages(flow):
    app, pkg, products, _, _, _ = flow
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["summary"]["remaining_stages"] == []


def test_rejected_second_start_cannot_replace_repository_of_active_build(flow):
    app, pkg, products, _, _, _ = flow
    original = app.worker_factory

    class Workers:
        def __init__(self, inner):
            self.inner = inner
            self.once = False

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def open_stage(self, *args):
            self.inner.open_stage(*args)
            if not self.once:
                self.once = True
                other = {**asdict(pkg), "code_sha": "f" * 64}
                with pytest.raises(ReplenishmentError, match="BUSY"):
                    app.start(other, command(pkg, products)["inventory"])
                assert app.supervisor.mode == "BUILD"

    app.worker_factory = lambda *args: Workers(original(*args))
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "OK"


def test_private_socket_routes_cli_start_and_saved_status(flow):
    import io
    import threading

    from product_search.infrastructure.replenishment_cli import (
        PrivateCommandServer,
        UnixCommandClient,
        main,
    )

    app, pkg, products, _, _, _ = flow
    root = app.artifacts.root.parent / "runtime"
    pkgfile = root / "package.json"
    pkgfile.write_text(json.dumps(asdict(pkg)))
    pkgfile.chmod(0o600)
    inventory = root / "inventory.json"
    inventory.write_text(json.dumps(command(pkg, products)["inventory"]))
    inventory.chmod(0o600)
    server = PrivateCommandServer(
        root,
        app.supervisor.lease,
        OwnerDispatcher(app, role="OWNER").handle,
        timeout_seconds=3,
        max_bytes=65536,
    )
    client = UnixCommandClient(root, timeout_seconds=3, max_bytes=65536)
    errors = []

    def serve():
        try:
            server.serve_once()
        except OSError as error:
            errors.append(error)

    try:
        thread = threading.Thread(target=serve)
        thread.start()
        out = io.StringIO()
        try:
            assert (
                main(
                    ["start", "--execution-package", str(pkgfile), "--inventory", str(inventory)],
                    client=client.send,
                    stdout=out,
                    stderr=io.StringIO(),
                )
                == 0
            )
        finally:
            thread.join(4)
        assert not thread.is_alive() and not errors
        summary = json.loads(out.getvalue())["summary"]
        assert summary["status"] == "COMPLETED" and summary["search_state"] == "SEARCH"
        thread = threading.Thread(target=serve)
        thread.start()
        status = io.StringIO()
        try:
            assert (
                main(
                    ["status", "--run", summary["run_ref"]],
                    client=client.send,
                    stdout=status,
                    stderr=io.StringIO(),
                )
                == 0
            )
        finally:
            thread.join(4)
        assert not thread.is_alive() and not errors
        assert json.loads(status.getvalue())["summary"] == summary
    finally:
        server.close()


def test_all_failed_photos_mark_product_not_publishable(flow, db):
    app, pkg, products, _, _, workers = flow
    workers["fail"] = "all"
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "OK" and answer["summary"]["publications"] == []
    with db.connect() as conn:
        assert (
            conn.execute("SELECT state FROM product_revisions").fetchone()[0] == "NOT_PUBLISHABLE"
        )


def test_unconfirmed_exit_persists_failure_and_keeps_search_closed(flow, db):
    app, pkg, products, _, _, _ = flow
    original = app.worker_factory

    def workers(*args):
        work = original(*args)
        work.close_stage = lambda *args: False
        return work

    app.worker_factory = workers
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "STOPPED" and answer["reason"] == "RECOVERY_REQUIRED"
    assert app.supervisor.mode == "RECOVERY_REQUIRED"
    with db.connect() as conn:
        assert (
            conn.execute("SELECT status FROM replenishment_runs WHERE epoch=2").fetchone()[0]
            == "FAILED"
        )


def test_input_identity_is_verified_before_mode_or_database_mutation(flow, db):
    app, pkg, products, _, events, _ = flow
    wrong = command(pkg, products)
    wrong["inventory"][0]["photos"][0]["input_sha"] = "f" * 64
    answer = OwnerDispatcher(app, role="OWNER").handle(wrong)
    assert answer["status"] == "REFUSED" and answer["reason"] == "INPUT_MISMATCH"
    assert app.supervisor.mode == "SEARCH" and events == []
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM replenishment_runs").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM processing_profiles").fetchone()[0] == 0
