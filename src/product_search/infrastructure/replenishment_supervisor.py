"""Local mode lease and owned process supervisor. No model imports."""

import fcntl
import math
import os
import signal
import stat
import subprocess
import time
from contextlib import contextmanager
from threading import Condition

from product_search.search.replenishment_contracts import (
    ExecutionPackage,
    Ownership,
    ReplenishmentError,
    ResourceObservation,
)


class ModeLease:
    """Close references, never LOCK_UN an open description shared with children."""

    def __init__(self, root):
        self.fd = -1
        directory_fd = -1
        try:
            directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(directory_fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ReplenishmentError("UNSAFE_RUNTIME")
            self.fd = os.open(
                "mode.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=directory_fd,
            )
            info = os.fstat(self.fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise ReplenishmentError("UNSAFE_RUNTIME")
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ReplenishmentError("BUSY") from None
        except OSError:
            self.close()
            raise ReplenishmentError("UNSAFE_RUNTIME") from None
        except BaseException:
            self.close()
            raise
        finally:
            if directory_fd >= 0:
                os.close(directory_fd)

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Supervisor:
    """One mode descriptor survives SEARCH/DRAINING/BUILD transitions.

    Callbacks are bounded adapters: quiesce stops only owned handles; issue_owner
    commits a fresh epoch; authorize_search verifies recovery and search identity.
    """

    def __init__(self, root, *, issue_owner, observe, quiesce, clock=time.monotonic):
        self.lease = ModeLease(root)
        self.await_resources = None
        self.issue_owner = issue_owner
        self.observe = observe
        self.quiesce = quiesce
        self.clock = clock
        self._commands = Condition()
        self._mode = "RECOVERY_REQUIRED"
        self._permits = 0
        self.owner = None

    @property
    def mode(self):
        with self._commands:
            return self._mode

    def _accept_owner(self, owner):
        if (
            not isinstance(owner, Ownership)
            or not owner.run_ref
            or not owner.owner_token
            or type(owner.epoch) is not int
            or owner.epoch <= 0
            or (self.owner is not None and owner.epoch <= self.owner.epoch)
        ):
            raise ReplenishmentError("INVALID_OWNERSHIP")
        self.owner = owner

    def _cleanup_arguments(self, end_at, stop_grace, kill_wait):
        if (
            any(
                type(v) not in (int, float) or not math.isfinite(v)
                for v in (end_at, stop_grace, kill_wait)
            )
            or stop_grace <= 0
            or kill_wait <= 0
        ):
            raise ReplenishmentError("INVALID_PACKAGE")
        if self.clock() >= end_at:
            raise ReplenishmentError("DEADLINE")

    def activate_search(self, authorize, *, end_at, stop_grace, kill_wait):
        self._cleanup_arguments(end_at, stop_grace, kill_wait)
        with self._commands:
            if self._permits or self._mode in {"SEARCH", "DRAINING", "CLOSED"}:
                raise ReplenishmentError("BUSY")
            self._mode = "DRAINING"
        try:
            if not self.quiesce(end_at, stop_grace, kill_wait):
                raise ReplenishmentError("RECOVERY_REQUIRED")
            with self._commands:
                # Authorization adapter also confirms recovery and fresh search identity.
                self._accept_owner(authorize())
                if self.clock() >= end_at:
                    raise ReplenishmentError("DEADLINE")
                self._mode = "SEARCH"
        except BaseException:
            with self._commands:
                self._mode = "RECOVERY_REQUIRED"
            raise

    @contextmanager
    def query_permit(self):
        with self._commands:
            if self._mode != "SEARCH":
                raise ReplenishmentError("TEMPORARILY_UNAVAILABLE")
            self._permits += 1
            owner = self.owner
        try:
            yield owner
        finally:
            with self._commands:
                self._permits -= 1
                self._commands.notify_all()

    def _require_resources(self, package):
        observation = self.observe()
        try:
            valid = (
                isinstance(observation, ResourceObservation)
                and observation.status == "OK"
                and type(observation.observed_at) in (int, float)
                and math.isfinite(observation.observed_at)
                and 0
                <= self.clock() - observation.observed_at
                <= package.observation_max_age_seconds
            )
        except (OverflowError, TypeError):
            valid = False
        if not valid:
            raise ReplenishmentError("RESOURCE_STOP")

    def begin_build(self, package, *, end_at=None):
        if not isinstance(package, ExecutionPackage):
            raise ReplenishmentError("INVALID_PACKAGE")
        now = self.clock()
        if end_at is None:
            end_at = now + package.overall_seconds
        if (
            type(end_at) not in (int, float)
            or not math.isfinite(end_at)
            or not now < end_at <= now + package.overall_seconds
        ):
            raise ReplenishmentError("INVALID_PACKAGE")
        work_end = end_at - package.cleanup_reserve_seconds
        with self._commands:
            if self._mode != "SEARCH" and not (
                self._mode == "RECOVERY_REQUIRED"
                and package.scope in {"RESUME", "RETRY_PHOTO", "RETRY_PUBLICATION"}
            ):
                raise ReplenishmentError("BUSY")
            self._mode = "DRAINING"
        try:
            with self._commands:
                while self._permits:
                    remaining = work_end - self.clock()
                    if remaining <= 0:
                        raise ReplenishmentError("DEADLINE")
                    self._commands.wait(min(remaining, 0.05))
            if not self.quiesce(end_at, package.stop_grace_seconds, package.kill_wait_seconds):
                raise ReplenishmentError("RECOVERY_REQUIRED")
            if self.await_resources is not None:
                self.await_resources(package, end_at, package.http_seconds)
            self._require_resources(package)
            with self._commands:
                if self.clock() + package.db_seconds >= work_end:
                    raise ReplenishmentError("DEADLINE")
                self._accept_owner(self.issue_owner("BUILD", package))
                if self.clock() >= work_end:
                    raise ReplenishmentError("DEADLINE")
                self._mode = "BUILD"
                self._build_package = package
                self._build_end_at = end_at
                self._child_admissions = 0
                return self.owner
        except BaseException:
            with self._commands:
                self._mode = "RECOVERY_REQUIRED"
            raise

    def require_recovery(self):
        with self._commands:
            if self._mode != "CLOSED":
                self._mode = "RECOVERY_REQUIRED"

    def launch_build_child(self, registry, argv, package):
        with self._commands:
            if self._mode != "BUILD":
                raise ReplenishmentError("BUSY")
            if registry.lease is not self.lease or package != self._build_package:
                raise ReplenishmentError("INVALID_PACKAGE")
            try:
                self._require_resources(package)
                work_end = self._build_end_at - package.cleanup_reserve_seconds
                if self.clock() + package.http_seconds >= work_end:
                    raise ReplenishmentError("DEADLINE")
                if self._child_admissions >= package.max_admissions:
                    raise ReplenishmentError("ADMISSION_LIMIT")
                self._child_admissions += 1
                return registry.launch(argv, self.owner, work_end)
            except BaseException:
                self._mode = "RECOVERY_REQUIRED"
                raise

    def close(self, *, end_at, stop_grace, kill_wait):
        self._cleanup_arguments(end_at, stop_grace, kill_wait)
        with self._commands:
            if self._mode == "CLOSED":
                return
            if self._permits or self._mode == "DRAINING":
                raise ReplenishmentError("BUSY")
            self._mode = "DRAINING"
        if not self.quiesce(end_at, stop_grace, kill_wait):
            with self._commands:
                self._mode = "RECOVERY_REQUIRED"
            raise ReplenishmentError("RECOVERY_REQUIRED")
        with self._commands:
            self.lease.close()
            self._mode = "CLOSED"


class OwnedProcesses:
    def __init__(self, lease, *, validate_argv, max_children, clock=time.monotonic, extra_fds=()):
        if type(extra_fds) is not tuple or len(set(extra_fds)) != len(extra_fds):
            raise ReplenishmentError("INVALID_WORKER")
        for descriptor in extra_fds:
            if type(descriptor) is not int or descriptor < 0 or descriptor == lease.fd:
                raise ReplenishmentError("INVALID_WORKER")
            try:
                info = os.fstat(descriptor)
            except OSError:
                raise ReplenishmentError("INVALID_WORKER") from None
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
                raise ReplenishmentError("INVALID_WORKER")
        self.extra_fds = extra_fds
        self.lease = lease
        self.validate_argv = validate_argv
        self.max_children = max_children
        self.clock = clock
        self._children = []

    def launch(self, argv, owner, end_at):
        if type(end_at) not in (int, float) or not math.isfinite(end_at):
            raise ReplenishmentError("INVALID_PACKAGE")
        if (
            type(argv) is not tuple
            or not argv
            or any(type(v) is not str or not v for v in argv)
            or not self.validate_argv(argv)
        ):
            raise ReplenishmentError("INVALID_WORKER")
        if (
            not isinstance(owner, Ownership)
            or not owner.owner_token
            or type(owner.epoch) is not int
            or owner.epoch <= 0
        ):
            raise ReplenishmentError("INVALID_OWNERSHIP")
        if self.clock() >= end_at:
            raise ReplenishmentError("DEADLINE")
        if len(self._children) >= self.max_children or self.lease.fd < 0:
            raise ReplenishmentError("BUSY")
        child = subprocess.Popen(
            argv,
            shell=False,
            start_new_session=True,
            pass_fds=(self.lease.fd, *self.extra_fds),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._children.append((child, owner))
        return child

    @staticmethod
    def _group_exists(child):
        try:
            os.killpg(child.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # XNU can return EPERM while a group contains only exiting/zombie
            # members. Visibility is unknown: keep waiting for ESRCH, bounded
            # by the existing stop deadline; never treat denial as absence.
            return True

    def _finished(self):
        return all(
            child.poll() is not None and not self._group_exists(child)
            for child, _ in self._children
        )

    def _signal_live_leaders(self, sig):
        for child, _ in self._children:
            # A reaped leader cannot prove that a newly observed PGID is ours.
            # Keep admission closed for orphan/unknown groups; never adopt a PID.
            if child.poll() is None:
                try:
                    os.killpg(child.pid, sig)
                except ProcessLookupError:
                    pass

    def _wait_until(self, end_at):
        while self.clock() < end_at:
            if self._finished():
                return True
            time.sleep(min(0.01, max(0, end_at - self.clock())))
        return self._finished()

    def stop(self, end_at, stop_grace, kill_wait):
        if self._finished():
            self._children.clear()
            return True
        if self.clock() >= end_at:
            return False
        self._signal_live_leaders(signal.SIGTERM)
        if not self._wait_until(min(end_at, self.clock() + stop_grace)):
            self._signal_live_leaders(signal.SIGKILL)
            if not self._wait_until(min(end_at, self.clock() + kill_wait)):
                return False
        self._children.clear()
        return True
