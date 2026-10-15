"""Native B1 tests: only synthetic processes and private temporary leases."""

import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest

from product_search.infrastructure.replenishment_supervisor import ModeLease
from product_search.search.replenishment_contracts import ReplenishmentError


@pytest.fixture(autouse=True)
def bounded_case():
    previous = signal.signal(
        signal.SIGALRM, lambda *args: (_ for _ in ()).throw(TimeoutError("B1_CASE_DEADLINE"))
    )
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@pytest.fixture
def root(tmp_path):
    tmp_path.chmod(0o700)
    return tmp_path


def test_second_lease_is_rejected_until_first_is_closed(root):
    first = ModeLease(root)
    try:
        with pytest.raises(ReplenishmentError, match="BUSY"):
            second = ModeLease(root)
            second.close()
    finally:
        first.close()
    with ModeLease(root):
        pass


def test_shared_runtime_root_is_refused(root):
    root.chmod(0o755)
    with pytest.raises(ReplenishmentError, match="UNSAFE_RUNTIME"):
        ModeLease(root)


def test_symlink_lockfile_is_refused(root):
    target = root / "unrelated"
    target.write_bytes(b"protected")
    (root / "mode.lock").symlink_to(target)
    with pytest.raises(ReplenishmentError, match="UNSAFE_RUNTIME"):
        ModeLease(root)
    assert target.read_bytes() == b"protected"


@contextmanager
def owned_group(argv, **kwargs):
    child = subprocess.Popen(argv, start_new_session=True, **kwargs)
    try:
        yield child
    finally:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)


def test_exec_child_retains_mode_lease_when_parent_closes_its_reference(root):
    lease = ModeLease(root)
    code = (
        "import os,sys,time; os.fstat(int(sys.argv[1])); print('READY',flush=True); time.sleep(10)"
    )
    try:
        with owned_group(
            [sys.executable, "-c", code, str(lease.fd)],
            pass_fds=(lease.fd,),
            stdout=subprocess.PIPE,
            text=True,
        ) as child:
            assert child.stdout.readline().strip() == "READY"
            lease.close()
            with pytest.raises(ReplenishmentError, match="BUSY"):
                ModeLease(root)
        with ModeLease(root):
            pass
    finally:
        lease.close()


def test_parent_death_does_not_allow_a_second_mode_while_child_lives(root):
    code = """
import os,subprocess,sys
from product_search.infrastructure.replenishment_supervisor import ModeLease
lease=ModeLease(sys.argv[1])
child=subprocess.Popen([sys.executable,'-c',
    "import os,sys,time; os.fstat(int(sys.argv[1])); print('READY',flush=True); time.sleep(10)",
    str(lease.fd)],pass_fds=(lease.fd,),stdout=subprocess.PIPE,text=True)
assert child.stdout.readline().strip()=='READY'
os._exit(0)
"""
    with owned_group([sys.executable, "-c", code, str(root)]) as parent:
        assert parent.wait(timeout=3) == 0
        with pytest.raises(ReplenishmentError, match="BUSY"):
            ModeLease(root)
    end_at = time.monotonic() + 3
    while True:
        try:
            lease = ModeLease(root)
            break
        except ReplenishmentError as error:
            assert str(error) == "BUSY"
            if time.monotonic() >= end_at:
                raise TimeoutError("CHILD_LEASE_NOT_RELEASED") from None
            time.sleep(0.01)
    lease.close()


from threading import Event, Thread

from product_search.infrastructure.replenishment_supervisor import Supervisor
from product_search.search.replenishment_contracts import Ownership, ResourceObservation
from tests.test_replenishment_contracts import package


def supervisor(root, **changes):
    issued = []

    def issue(mode, pkg):
        owner = Ownership("run-test", f"token-{len(issued) + 1}", len(issued) + 1)
        issued.append((mode, owner))
        return owner

    values = {
        "issue_owner": issue,
        "observe": lambda: ResourceObservation("OK", time.monotonic()),
        "quiesce": lambda *args: True,
    }
    late_quiesce = changes.pop("quiesce", None)
    values.update(changes)
    service = Supervisor(root, **values)
    service.activate_search(
        lambda: issue("SEARCH", None), end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3
    )
    if late_quiesce is not None:
        service.quiesce = late_quiesce
    return service, issued


def test_drain_closes_new_query_admission_atomically_and_retains_mode_lock(root):
    service, issued = supervisor(root)
    entered = Event()
    release = Event()
    failures = []

    def query():
        with service.query_permit():
            entered.set()
            assert release.wait(2)

    def build():
        try:
            service.begin_build(package())
        except (AssertionError, ReplenishmentError, TimeoutError) as error:
            failures.append(error)

    query_thread = Thread(target=query)
    build_thread = Thread(target=build)
    try:
        query_thread.start()
        assert entered.wait(2)
        build_thread.start()
        end_at = time.monotonic() + 2
        while service.mode != "DRAINING" and time.monotonic() < end_at:
            time.sleep(0.005)
        assert service.mode == "DRAINING"
        with (
            pytest.raises(ReplenishmentError, match="TEMPORARILY_UNAVAILABLE"),
            service.query_permit(),
        ):
            pass
        with pytest.raises(ReplenishmentError, match="BUSY"):
            ModeLease(root)
        release.set()
        query_thread.join(2)
        build_thread.join(2)
        assert not query_thread.is_alive() and not build_thread.is_alive()
        assert failures == []
        assert service.mode == "BUILD"
        assert [mode for mode, _ in issued] == ["SEARCH", "BUILD"]
    finally:
        release.set()
        if query_thread.ident is not None:
            query_thread.join(2)
        if build_thread.ident is not None:
            build_thread.join(2)
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)


def test_drain_timeout_does_not_issue_build_epoch(root):
    service, issued = supervisor(root)
    tiny = package(
        overall_seconds=0.08,
        cleanup_reserve_seconds=0.01,
        stop_grace_seconds=0.001,
        kill_wait_seconds=0.001,
        http_seconds=0.005,
        db_seconds=0.005,
    )
    try:
        with service.query_permit(), pytest.raises(ReplenishmentError, match="DEADLINE"):
            service.begin_build(tiny)
        assert [m for m, _ in issued] == ["SEARCH"]
        assert service.mode == "RECOVERY_REQUIRED"
    finally:
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)


@pytest.mark.parametrize("status", ["WARNING", "CRITICAL", "UNKNOWN", "STALE"])
def test_unsafe_resource_signal_refuses_build(root, status):
    service, issued = supervisor(
        root, observe=lambda: ResourceObservation(status, time.monotonic())
    )
    try:
        with pytest.raises(ReplenishmentError, match="RESOURCE_STOP"):
            service.begin_build(package())
        assert service.mode == "RECOVERY_REQUIRED"
        assert [m for m, _ in issued] == ["SEARCH"]
    finally:
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)


def test_unconfirmed_search_worker_exit_blocks_build(root):
    service, issued = supervisor(root, quiesce=lambda *args: False)
    try:
        with pytest.raises(ReplenishmentError, match="RECOVERY_REQUIRED"):
            service.begin_build(package())
        assert [m for m, _ in issued] == ["SEARCH"]
    finally:
        service.quiesce = lambda *args: True
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)


def test_db_epoch_failure_keeps_admission_closed(root):
    service, _ = supervisor(root)
    service.issue_owner = lambda *args: (_ for _ in ()).throw(ReplenishmentError("DB_ERROR"))
    try:
        with pytest.raises(ReplenishmentError, match="DB_ERROR"):
            service.begin_build(package())
        assert service.mode == "RECOVERY_REQUIRED"
        with (
            pytest.raises(ReplenishmentError, match="TEMPORARILY_UNAVAILABLE"),
            service.query_permit(),
        ):
            pass
    finally:
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)


def test_close_during_drain_cannot_release_mode_lease(root):
    entered = Event()
    leave = Event()

    def quiesce(*args):
        if entered.is_set():
            return True
        entered.set()
        assert leave.wait(2)
        return True

    service, _ = supervisor(root)
    service.quiesce = quiesce
    failures = []

    def build():
        try:
            service.begin_build(package())
        except (AssertionError, ReplenishmentError, TimeoutError) as error:
            failures.append(error)

    thread = Thread(target=build)
    try:
        thread.start()
        assert entered.wait(2)
        with pytest.raises(ReplenishmentError, match="BUSY"):
            service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)
        with pytest.raises(ReplenishmentError, match="BUSY"):
            ModeLease(root)
    finally:
        leave.set()
        thread.join(2)
        service.quiesce = lambda *args: True
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)
    assert failures == []


def test_unconfirmed_teardown_retains_parent_mode_lease(root):
    service, _ = supervisor(root)
    service.quiesce = lambda *args: False
    try:
        with pytest.raises(ReplenishmentError, match="RECOVERY_REQUIRED"):
            service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)
        with pytest.raises(ReplenishmentError, match="BUSY"):
            ModeLease(root)
    finally:
        service.quiesce = lambda *args: True
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)


from product_search.infrastructure.replenishment_supervisor import OwnedProcesses


def test_owned_process_teardown_does_not_touch_unregistered_group(root):
    lease = ModeLease(root)
    registry = OwnedProcesses(
        lease, validate_argv=lambda argv: argv[0] == sys.executable, max_children=10
    )
    command = (sys.executable, "-c", "import time; time.sleep(10)")
    with owned_group(command) as unrelated:
        try:
            child = registry.launch(command, Ownership("run-1", "token-1", 1), time.monotonic() + 5)
            assert child is not None
            assert child.poll() is None
            assert registry.stop(time.monotonic() + 5, 2, 3) is True
            assert child.poll() is not None
            assert unrelated.poll() is None
        finally:
            registry.stop(time.monotonic() + 5, 2, 3)
            lease.close()


def test_unverified_argv_cannot_start_a_child(root):
    with ModeLease(root) as lease:
        registry = OwnedProcesses(lease, validate_argv=lambda argv: False, max_children=10)
        with pytest.raises(ReplenishmentError, match="INVALID_WORKER"):
            registry.launch(
                (sys.executable, "-c", "raise SystemExit(0)"),
                Ownership("run-1", "token-1", 1),
                time.monotonic() + 5,
            )


@pytest.mark.parametrize("deadline", [float("nan"), float("inf"), None, True])
def test_invalid_deadline_cannot_launch_a_worker(root, deadline):
    with ModeLease(root) as lease:
        registry = OwnedProcesses(lease, validate_argv=lambda argv: True, max_children=10)
        try:
            with pytest.raises(ReplenishmentError, match="INVALID_PACKAGE"):
                registry.launch(
                    (sys.executable, "-c", "import time; time.sleep(10)"),
                    Ownership("run-1", "token-1", 1),
                    deadline,
                )
        finally:
            registry.stop(time.monotonic() + 5, 2, 3)


def test_term_ignoring_owned_worker_is_killed_within_budget(root):
    ready = root / "ready"
    code = "import os,sys,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); fd=os.open(sys.argv[1],os.O_CREAT|os.O_WRONLY,0o600); os.close(fd); time.sleep(10)"
    with ModeLease(root) as lease:
        registry = OwnedProcesses(lease, validate_argv=lambda argv: True, max_children=10)
        try:
            child = registry.launch(
                (sys.executable, "-c", code, str(ready)),
                Ownership("run-1", "token-1", 1),
                time.monotonic() + 5,
            )
            end_at = time.monotonic() + 2
            while not ready.exists() and time.monotonic() < end_at:
                time.sleep(0.005)
            assert ready.exists()
            assert registry.stop(time.monotonic() + 1, 0.05, 0.2)
            assert child.returncode == -signal.SIGKILL
        finally:
            registry.stop(time.monotonic() + 5, 2, 3)


def test_build_epoch_is_issued_after_owned_search_workers_have_exited(root):
    service, _ = supervisor(root)
    registry = OwnedProcesses(service.lease, validate_argv=lambda argv: True, max_children=10)
    command = (sys.executable, "-c", "import time; time.sleep(10)")
    child = registry.launch(command, service.owner, time.monotonic() + 5)
    service.quiesce = registry.stop
    previous = service.issue_owner

    def issue(mode, pkg):
        assert child.poll() is not None
        return previous(mode, pkg)

    service.issue_owner = issue
    try:
        owner = service.begin_build(package())
        assert owner.epoch == 2
        assert service.mode == "BUILD"
    finally:
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)


def test_build_child_requires_build_mode_and_fresh_resources(root):
    service, _ = supervisor(root)
    registry = OwnedProcesses(service.lease, validate_argv=lambda argv: True, max_children=10)
    service.quiesce = registry.stop
    command = (sys.executable, "-c", "import time; time.sleep(10)")
    pkg = package()
    try:
        with pytest.raises(ReplenishmentError, match="BUSY"):
            service.launch_build_child(registry, command, pkg)
        service.begin_build(pkg)
        service.observe = lambda: ResourceObservation("CRITICAL", time.monotonic())
        with pytest.raises(ReplenishmentError, match="RESOURCE_STOP"):
            service.launch_build_child(registry, command, pkg)
        assert service.mode == "RECOVERY_REQUIRED"
    finally:
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)


def test_build_child_uses_existing_mode_descriptor_and_owner(root):
    service, _ = supervisor(root)
    registry = OwnedProcesses(service.lease, validate_argv=lambda argv: True, max_children=10)
    service.quiesce = registry.stop
    pkg = package()
    try:
        owner = service.begin_build(pkg)
        child = service.launch_build_child(
            registry, (sys.executable, "-c", "import time; time.sleep(10)"), pkg
        )
        assert child is not None and child.poll() is None
        with pytest.raises(ReplenishmentError, match="BUSY"):
            ModeLease(root)
        assert owner.epoch == 2
    finally:
        service.close(end_at=time.monotonic() + 5, stop_grace=2, kill_wait=3)


def test_unrepresentable_resource_timestamp_is_a_controlled_stop(root):
    service, issued = supervisor(root, observe=lambda: ResourceObservation('OK', 10**400))
    try:
        with pytest.raises(ReplenishmentError, match='RESOURCE_STOP'):
            service.begin_build(package())
        assert service.mode == 'RECOVERY_REQUIRED'
        assert [mode for mode, _ in issued] == ['SEARCH']
    finally:
        service.close(end_at=time.monotonic()+5, stop_grace=2, kill_wait=3)


def test_owned_child_inherits_auxiliary_coordinator_descriptor(root):

    from product_search.infrastructure.replenishment_supervisor import OwnedProcesses
    from product_search.search.replenishment_contracts import Ownership
    coordinator_root = root / 'coordinator'
    coordinator_root.mkdir(mode=0o700)
    with ModeLease(root) as mode, ModeLease(coordinator_root) as coordinator:
        marker = root / 'ready'
        code = 'import os,sys,time; os.fstat(int(sys.argv[1])); open(sys.argv[2],"w").write("ready"); time.sleep(10)'
        argv = (sys.executable, '-c', code, str(coordinator.fd), str(marker))
        registry = OwnedProcesses(mode, validate_argv=lambda x: x == argv, max_children=1, extra_fds=(coordinator.fd,))
        try:
            child = registry.launch(argv, Ownership('run', 'token', 1), time.monotonic() + 10)
            end = time.monotonic() + 2
            while not marker.exists() and child.poll() is None and time.monotonic() < end:
                time.sleep(0.01)
            assert marker.read_text() == 'ready'
        finally:
            assert registry.stop(time.monotonic() + 5, 2, 3)
