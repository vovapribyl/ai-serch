"""B1 warning/recovery wiring; fake clocks and owned temporary DB, no real ML."""

from dataclasses import asdict, replace

import pytest

from product_search.infrastructure.replenishment_cli import OwnerDispatcher
from product_search.search.replenishment_contracts import ReplenishmentError, ResourceObservation
from tests.test_replenishment_flow import command
from tests.test_replenishment_flow import flow as flow  # noqa: PLC0414 -- pytest fixture
from tests.test_replenishment_postgres_integration import (
    db as db,  # noqa: PLC0414 -- pytest fixture
)


def test_warning_waits_for_stable_resources_before_any_warmup(flow):
    app, pkg, products, clock, events, _ = flow
    clock.value = 0
    app.supervisor.observe = lambda: ResourceObservation(
        "WARNING" if clock.value < 5 else "OK", clock.value
    )
    polls = []

    def poll(cutoff):
        polls.append(clock.value)
        clock.value += 1

    app.poll_resources = poll
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "OK" and len(polls) == 35
    assert events and clock.value == 35


def test_warning_times_out_without_ml_or_publication(flow, db):
    app, pkg, products, clock, events, _ = flow
    clock.value = 0
    pkg = replace(pkg, overall_seconds=600)
    app.supervisor.observe = lambda: ResourceObservation("WARNING", clock.value)

    def poll(cutoff):
        clock.value += 1

    app.poll_resources = poll
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "STOPPED" and answer["reason"] == "WAIT_TIMEOUT"
    assert clock.value == 300 and events == [] and app.supervisor.mode == "RECOVERY_REQUIRED"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 0


def test_critical_after_processing_blocks_publication_and_search_restart(flow, db):
    app, pkg, products, clock, events, _ = flow
    original = app.worker_factory

    def workers(*args):
        worker = original(*args)
        close = worker.close_stage

        def after_close(owner, end):
            result = close(owner, end)
            if sum(e[0] == "close" for e in events) == 4:
                app.supervisor.observe = lambda: ResourceObservation("CRITICAL", clock.monotonic())
            return result

        worker.close_stage = after_close
        return worker

    app.worker_factory = workers
    answer = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    assert answer["status"] == "STOPPED" and answer["reason"] == "RESOURCE_STOP"
    assert app.supervisor.mode == "RECOVERY_REQUIRED"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM revision_publications").fetchone()[0] == 0


def replacement(app, events):
    from product_search.infrastructure.replenishment_application import (
        LocalReplenishmentApplication,
    )
    from tests.test_replenishment_flow import FakeWorkers

    new = LocalReplenishmentApplication(
        app.artifacts.root.parent / "runtime",
        app.repository_factory,
        app.profile,
        app.artifacts,
        lambda *args: FakeWorkers(app.artifacts, new, app.clock, events),
        app.clock,
        authorize_build=app.authorize_build,
        authorize_search=app.authorize_search,
        observe=app.supervisor.observe,
        quiesce=lambda *args: True,
        summary_reader=app.summary_reader,
    )
    return new


def test_ready_snapshot_survives_restart_without_automatic_ml(flow, db):
    app, pkg, products, clock, events, _ = flow
    first = OwnerDispatcher(app, role="OWNER").handle(command(pkg, products))
    snapshot = first["summary"]["publications"][0]["snapshot_ref"]
    app.supervisor.close(end_at=clock.monotonic() + 5, stop_grace=1, kill_wait=1)
    events.clear()
    new = replacement(app, events)
    try:
        assert new.supervisor.mode == "RECOVERY_REQUIRED"
        with (
            pytest.raises(ReplenishmentError, match="TEMPORARILY_UNAVAILABLE"),
            new.supervisor.query_permit(),
        ):
            pytest.fail("startup query")
        new.initialize_search(pkg)
        assert new.supervisor.mode == "SEARCH" and events == []
        with db.connect() as conn:
            assert (
                conn.execute("SELECT snapshot_id::text FROM active_catalog_snapshots").fetchone()[0]
                == snapshot
            )
            assert conn.execute("SELECT state FROM product_revisions").fetchone()[0] == "READY"
        answer = OwnerDispatcher(new, role="OWNER").handle(
            {
                "schema_version": 1,
                "action": "resume",
                "run": first["summary"]["run_ref"],
                "package": asdict(replace(pkg, scope="RESUME")),
            }
        )
        assert answer["status"] == "OK" and events == []
    finally:
        new.supervisor.close(end_at=clock.monotonic() + 5, stop_grace=1, kill_wait=1)


def test_live_inherited_child_blocks_successor_without_touching_foreign_process(flow):
    import sys

    from tests.test_replenishment_lifecycle import owned_group

    app, _, _, _, events, _ = flow
    lease = app.supervisor.lease
    code = (
        "import os,sys,time; os.fstat(int(sys.argv[1])); print('READY',flush=True); time.sleep(10)"
    )
    with owned_group(
        [sys.executable, "-c", code, str(lease.fd)],
        pass_fds=(lease.fd,),
        stdout=__import__("subprocess").PIPE,
        text=True,
    ) as child:
        assert child.stdout.readline().strip() == "READY"
        with owned_group([sys.executable, "-c", "import time; time.sleep(10)"]) as foreign:
            lease.close()
            with pytest.raises(ReplenishmentError, match="BUSY"):
                replacement(app, events)
            assert child.poll() is None and foreign.poll() is None
