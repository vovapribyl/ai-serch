"""Test-only disposable DB owner. Never accepts an existing DB URL."""

import json
import os
import secrets
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg

IMAGE = "sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b"
PYTHON = "/Users/v.pribylovskiy/Documents/ChatGPT/Ai/.venv/bin/python"
BASE = "0008_gate4_multiphoto_v3"


@contextmanager
def disposable_database(private_root):
    marker = uuid4().hex
    name = "candidate-i-g3-" + marker[:12]
    user = "g3_" + marker[:12]
    password = secrets.token_urlsafe(32)
    private_root.chmod(0o700)
    env_file = private_root / "postgres.env"
    fd = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"POSTGRES_USER={user}\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB={user}\n")
    container = None

    def docker(*args):
        result = subprocess.run(
            ["docker", "--context", "colima", *args], capture_output=True, text=True, check=False
        )
        if result.returncode:
            raise RuntimeError("Owned synthetic Docker operation failed")
        return result.stdout.strip()

    try:
        container = docker(
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            f"candidate-i-g3={marker}",
            "--pull=never",
            "--restart=no",
            "--memory=512m",
            "--cpus=1",
            "--mount",
            "type=tmpfs,destination=/var/lib/postgresql/data,tmpfs-size=268435456,tmpfs-mode=0700",
            "--publish",
            "127.0.0.1::5432",
            "--env-file",
            str(env_file),
            IMAGE,
        )
        assert (
            json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", container)).get(
                "candidate-i-g3"
            )
            == marker
        )
        assert docker("inspect", "--format", "{{.Image}}", container) == IMAGE
        assert all(
            m["Type"] == "tmpfs"
            for m in json.loads(docker("inspect", "--format", "{{json .Mounts}}", container))
        )
        binding = json.loads(
            docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", container)
        )["5432/tcp"][0]
        assert binding["HostIp"] == "127.0.0.1"
        config = {
            "host": "127.0.0.1",
            "port": int(binding["HostPort"]),
            "user": user,
            "password": password,
            "dbname": user,
            "connect_timeout": 2,
        }
        for attempt in range(50):
            try:
                conn = psycopg.connect(**config)
                break
            except psycopg.OperationalError:
                if attempt == 49:
                    raise RuntimeError("Owned synthetic database readiness timeout") from None
                time.sleep(0.2)
        with conn, conn.cursor() as cursor:
            cursor.execute("SELECT current_database(),current_user")
            assert cursor.fetchone() == (user, user)
            cursor.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'")
            assert cursor.fetchone()[0] == 0
            cursor.execute("CREATE TABLE synthetic_owner_marker (marker text NOT NULL)")
            cursor.execute("INSERT INTO synthetic_owner_marker VALUES (%s)", (marker,))
        yield config, marker
    finally:
        if container:
            assert (
                json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", container)).get(
                    "candidate-i-g3"
                )
                == marker
            )
            docker("rm", "--force", container)
        env_file.unlink(missing_ok=True)


def migrate(config, marker, action, target):
    with psycopg.connect(**config) as conn:
        assert conn.execute("SELECT current_database(),current_user").fetchone() == (
            config["dbname"],
            config["user"],
        )
        assert conn.execute("SELECT marker FROM synthetic_owner_marker").fetchone() == (marker,)
    root = Path(__file__).resolve().parents[2]
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("MVP_POSTGRES_")
    }
    environment.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=f"{root}:{root}/src:{root}/.superpowers/sdd/plan/g3-test-deps",
        MVP_POSTGRES_USER=config["user"],
        MVP_POSTGRES_PASSWORD=config["password"],
        MVP_POSTGRES_DB=config["dbname"],
        MVP_POSTGRES_PORT=str(config["port"]),
    )
    result = subprocess.run(
        [PYTHON, "-B", "-m", "alembic", action, target],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result
