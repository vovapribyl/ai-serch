from contextlib import nullcontext
from pathlib import Path

from fastapi.testclient import TestClient

from product_search.core.settings import Settings
from product_search.infrastructure.image_storage import LocalTemporaryImageStorage
from product_search.main import build_application
from product_search.web.app import create_app


class StubImageStorage:
    def temporary_file(self, original_name: str):
        return nullcontext(Path(original_name))


def test_health_reports_database_available() -> None:
    client = TestClient(create_app(lambda: True, StubImageStorage()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_unavailable_without_internal_error() -> None:
    def unavailable_database() -> bool:
        raise RuntimeError("database driver is offline")

    client = TestClient(
        create_app(unavailable_database, StubImageStorage()), raise_server_exceptions=False
    )

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "База данных временно недоступна."}


def test_empty_upload_screen_has_no_search_logic() -> None:
    client = TestClient(create_app(lambda: True, StubImageStorage()))

    response = client.get("/")

    assert response.status_code == 200
    assert "Поиск ранее рассмотренного товара" in response.text
    assert "type=\"file\"" in response.text
    assert response.text.count("disabled") == 2


def test_application_composes_local_image_storage(tmp_path: Path) -> None:
    settings = Settings(
        host="127.0.0.1",
        port=8000,
        database_url="postgresql+psycopg://user:password@127.0.0.1:54329/mvp",
        data_dir=tmp_path,
        repository_root=Path.cwd(),
    )

    app = build_application(settings)

    assert isinstance(app.state.image_storage, LocalTemporaryImageStorage)
