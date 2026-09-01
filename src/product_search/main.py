from __future__ import annotations

from pathlib import Path

import uvicorn

from product_search.core.settings import Settings
from product_search.infrastructure.database import create_database_engine, database_is_available
from product_search.infrastructure.image_storage import LocalTemporaryImageStorage
from product_search.web.app import create_app


def build_application(settings: Settings):
    """Собирает web-приложение с локальными инфраструктурными адаптерами."""
    engine = create_database_engine(settings.database_url)
    image_storage = LocalTemporaryImageStorage(settings.data_dir / "temporary-queries")
    return create_app(lambda: database_is_available(engine), image_storage)


def main() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    settings = Settings.from_environment(repository_root=repository_root)
    application = build_application(settings)
    uvicorn.run(application, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
