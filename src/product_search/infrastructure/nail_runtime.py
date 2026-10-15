"""Concrete single-owner POSIX leases for the selected local Mac profile."""

import fcntl
import os
import stat
from pathlib import Path


def validate_runtime_root(root: Path) -> Path:
    root = Path(root)
    try:
        details = root.lstat()
    except OSError:
        raise ValueError("Existing private runtime root required") from None
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != 0o700
    ):
        raise ValueError("Existing private runtime root required")
    return root.resolve()


class FileLease:
    def __init__(self, root: Path, name: str):
        self.root = validate_runtime_root(root)
        if name not in ("device.lock", "coordinator.lock"):
            raise ValueError("Unknown resource lease")
        self.name = name
        self._fd: int | None = None

    def try_acquire(self) -> bool:
        if self._fd is not None:
            return True
        directory = fd = None
        try:
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            details = os.fstat(directory)
            if details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700:
                raise ValueError("Unsafe runtime root")
            fd = os.open(self.name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            details = os.fstat(fd)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_nlink != 1
            ):
                raise ValueError("Unsafe lease file")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            self._fd, fd = fd, None
            return True
        except OSError:
            raise ValueError("Unsafe or unavailable lease file") from None
        finally:
            if fd is not None:
                os.close(fd)
            if directory is not None:
                os.close(directory)

    def release(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
