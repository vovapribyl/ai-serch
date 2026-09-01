from __future__ import annotations

import os
from urllib.parse import quote


def database_url_from_environment() -> str:
    """Собирает единый URL БД из локального секретного окружения."""
    password = os.environ.get("MVP_POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Задайте MVP_POSTGRES_PASSWORD во внешнем runtime-env файле.")
    user = os.environ.get("MVP_POSTGRES_USER", "mvp")
    database = os.environ.get("MVP_POSTGRES_DB", "mvp")
    port = os.environ.get("MVP_POSTGRES_PORT", "54329")
    return (
        "postgresql+psycopg://"
        f"{quote(user, safe='')}:{quote(password, safe='')}@127.0.0.1:{quote(port, safe='')}/{quote(database, safe='')}"
    )
