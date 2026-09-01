from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from product_search.core.database_url import database_url_from_environment


def test_database_url_uses_single_secret_environment_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MVP_POSTGRES_PASSWORD", "secret with spaces")
    monkeypatch.setenv("MVP_POSTGRES_USER", "local_user")
    monkeypatch.setenv("MVP_POSTGRES_DB", "local_db")
    monkeypatch.setenv("MVP_POSTGRES_PORT", "54330")

    url = database_url_from_environment()

    assert "secret%20with%20spaces" in url
    assert make_url(url).password == "secret with spaces"


def test_database_url_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MVP_POSTGRES_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="MVP_POSTGRES_PASSWORD"):
        database_url_from_environment()


def test_compose_application_and_alembic_use_environment_contract() -> None:
    repository_root = Path(__file__).parents[1]
    compose = (repository_root / "docker-compose.yml").read_text(encoding="utf-8")
    alembic_env = (repository_root / "migrations" / "env.py").read_text(encoding="utf-8")
    settings = (repository_root / "src" / "product_search" / "core" / "settings.py").read_text(
        encoding="utf-8"
    )

    assert "POSTGRES_PASSWORD: ${MVP_POSTGRES_PASSWORD" in compose
    assert "mvp/mvp" not in compose
    assert "MVP_POSTGRES_HOST" not in compose
    assert "database_url_from_environment()" in alembic_env
    assert "database_url_from_environment()" in settings
