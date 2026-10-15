"""Finite, private synthetic-test helpers. No existing database URL is accepted."""

import subprocess
import time


class HarnessError(RuntimeError):
    pass


class BoundedCommands:
    def __init__(self, end_at, *, clock=time.monotonic, execute=subprocess.run, failure_log=None):
        self.end_at = end_at
        self.clock = clock
        self.execute = execute
        self.failure_log = failure_log

    def run(self, argv):
        remaining = self.end_at - self.clock()
        if remaining <= 0:
            raise HarnessError("TEST_DEADLINE")
        try:
            result = self.execute(
                argv,
                timeout=min(10, remaining),
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise HarnessError("TEST_COMMAND_TIMEOUT") from None
        if result.returncode:
            if self.failure_log is not None:
                fd = os.open(self.failure_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "w") as stream:
                    stream.write(result.stdout + "\n" + result.stderr + "\n")
            raise HarnessError("TEST_COMMAND_FAILED")
        return result


IMAGE = "sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b"


def validate_container(info, marker):
    try:
        bindings = info["ports"]["5432/tcp"]
        port = int(bindings[0]["HostPort"])
        valid = (
            info["image"] == IMAGE
            and info["labels"].get("replenishment-b1") == marker
            and info["name"] == "/replenishment-b1-" + marker
            and info["memory"] == 536870912
            and info["cpus"] == 1000000000
            and info["pids"] == 128
            and info["running"] is True
            and len(info["mounts"]) == 1
            and info["mounts"][0]["Type"] == "tmpfs"
            and info["mounts"][0]["Destination"] == "/var/lib/postgresql/data"
            and len(bindings) == 1
            and bindings[0]["HostIp"] == "127.0.0.1"
            and 0 < port < 65536
        )
    except (KeyError, IndexError, TypeError, ValueError):
        valid = False
    if not valid:
        raise HarnessError("TEST_CONTAINER_MISMATCH")
    return port


import json
import os
import secrets
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg

INSPECT = """{"image":{{json .Image}},"labels":{{json .Config.Labels}},"name":{{json .Name}},"memory":{{json .HostConfig.Memory}},"cpus":{{json .HostConfig.NanoCpus}},"pids":{{json .HostConfig.PidsLimit}},"running":{{json .State.Running}},"mounts":{{json .Mounts}},"ports":{{json .NetworkSettings.Ports}}}"""


class SyntheticDatabase:
    def __init__(self, root, end_at):
        self.root = Path(root)
        self.end_at = end_at
        self.marker = uuid4().hex
        self.name = "replenishment-b1-" + self.marker
        self.commands = BoundedCommands(end_at, failure_log=self.root / "diagnostic.log")
        self.config = None
        self._admission_lease = None

    def _acquire_admission(self):
        from product_search.infrastructure.replenishment_supervisor import ModeLease
        from product_search.search.replenishment_contracts import ReplenishmentError

        root = Path("/private/tmp") / f"replenishment-b1-admission-{os.getuid()}"
        root.mkdir(mode=0o700, exist_ok=True)
        try:
            self._admission_lease = ModeLease(root)
        except ReplenishmentError:
            raise HarnessError("TEST_DB_BUSY") from None

    def _release_admission(self):
        if self._admission_lease is not None:
            self._admission_lease.close()
            self._admission_lease = None

    def docker(self, *args):
        return self.commands.run(["docker", "--context", "colima", *args]).stdout.strip()

    def verify(self):
        info = json.loads(self.docker("inspect", "--format", INSPECT, self.name))
        return validate_container(info, self.marker)

    def start(self):
        self._acquire_admission()
        # A crashed helper can leave a container after its OS descriptor closes.
        if self.docker(
            "container", "ls", "--all", "--filter", "label=replenishment-b1", "--format", "{{.ID}}"
        ):
            raise HarnessError("TEST_DB_BUSY")
        self.root.mkdir(mode=0o700)
        if self.root.is_symlink() or stat.S_IMODE(self.root.stat().st_mode) != 0o700:
            raise HarnessError("TEST_PRIVATE_ROOT")
        user = "b1_" + self.marker[:12]
        password = secrets.token_urlsafe(32)
        env_file = self.root / "postgres.env"
        fd = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(
                f"POSTGRES_USER={user}\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB={user}\n"
            )
        self.docker(
            "run",
            "--detach",
            "--name",
            self.name,
            "--label",
            "replenishment-b1=" + self.marker,
            "--pull=never",
            "--restart=no",
            "--memory=512m",
            "--cpus=1",
            "--pids-limit=128",
            "--mount",
            "type=tmpfs,destination=/var/lib/postgresql/data,tmpfs-size=268435456,tmpfs-mode=0700",
            "--publish",
            "127.0.0.1::5432",
            "--env-file",
            str(env_file),
            IMAGE,
        )
        port = self.verify()
        self.config = {
            "host": "127.0.0.1",
            "port": port,
            "user": user,
            "password": password,
            "dbname": user,
            "connect_timeout": 2,
            "options": "-c lock_timeout=2000 -c statement_timeout=5000",
        }
        ready_at = min(self.end_at, time.monotonic() + 10)
        while time.monotonic() + 2 < ready_at:
            try:
                with psycopg.connect(**self.config) as conn:
                    identity = conn.execute("SELECT current_database(),current_user").fetchone()
                    if identity != (user, user):
                        raise HarnessError("TEST_DB_IDENTITY")
                    if conn.execute(
                        "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
                    ).fetchone()[0]:
                        raise HarnessError("TEST_DB_NOT_EMPTY")
                    conn.execute("CREATE TABLE synthetic_owner_marker(marker text NOT NULL)")
                    conn.execute("INSERT INTO synthetic_owner_marker VALUES (%s)", (self.marker,))
                return
            except psycopg.OperationalError:
                time.sleep(0.1)
        raise HarnessError("TEST_DB_READINESS")

    @contextmanager
    def connect(self):
        if self.config is None or time.monotonic() + 2 >= self.end_at:
            raise HarnessError("TEST_DEADLINE")
        self.verify()
        with psycopg.connect(**self.config) as conn:
            if conn.execute("SELECT current_database(),current_user").fetchone() != (
                self.config["dbname"],
                self.config["user"],
            ):
                raise HarnessError("TEST_DB_IDENTITY")
            if conn.execute("SELECT marker FROM synthetic_owner_marker").fetchone() != (
                self.marker,
            ):
                raise HarnessError("TEST_DB_MARKER")
            yield conn

    def migrate(self, target="head", *, direction="upgrade"):
        if direction not in {"upgrade", "downgrade"}:
            raise HarnessError("INVALID_MIGRATION_DIRECTION")
        with self.connect():
            pass
        cfg = self.config
        env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "TMPDIR"}}
        env.update(
            PYTHONPATH="src:.",
            PYTHONDONTWRITEBYTECODE="1",
            MVP_POSTGRES_USER=cfg["user"],
            MVP_POSTGRES_PASSWORD=cfg["password"],
            MVP_POSTGRES_DB=cfg["dbname"],
            MVP_POSTGRES_PORT=str(cfg["port"]),
        )
        commands = BoundedCommands(
            self.end_at,
            failure_log=self.root / "diagnostic.log",
            execute=lambda argv, **kw: subprocess.run(argv, env=env, **kw),  # noqa: PLW1510 - check=False supplied by BoundedCommands
        )
        commands.run([sys.executable, "-B", "-m", "alembic", direction, target])

    def close(self):
        self.commands = BoundedCommands(time.monotonic() + 30)
        ids = self.docker(
            "container",
            "ls",
            "--all",
            "--filter",
            "label=replenishment-b1=" + self.marker,
            "--filter",
            "name=" + self.name,
            "--format",
            "{{.ID}}",
        ).splitlines()
        if len(ids) > 1:
            raise HarnessError("TEST_CLEANUP_UNCONFIRMED")
        if ids:
            self.verify()
            self.docker("rm", "--force", ids[0])
            if self.docker(
                "container",
                "ls",
                "--all",
                "--filter",
                "label=replenishment-b1=" + self.marker,
                "--format",
                "{{.ID}}",
            ):
                raise HarnessError("TEST_CLEANUP_UNCONFIRMED")
        (self.root / "postgres.env").unlink(missing_ok=True)
        self._release_admission()
