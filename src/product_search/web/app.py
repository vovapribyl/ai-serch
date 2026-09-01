from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from product_search.core.image_storage import ImageStorage

DatabaseProbe = Callable[[], bool]


def create_app(database_probe: DatabaseProbe, image_storage: ImageStorage) -> FastAPI:
    app = FastAPI(title="Product Search MVP", docs_url=None, redoc_url=None)
    app.state.image_storage = image_storage

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            database_ready = database_probe()
        except Exception as error:
            raise HTTPException(
                status_code=503, detail="База данных временно недоступна."
            ) from error
        if not database_ready:
            raise HTTPException(status_code=503, detail="База данных временно недоступна.")
        return {"status": "ok", "database": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def upload_screen() -> str:
        return """<!doctype html>
<html lang=\"ru\"><head><meta charset=\"utf-8\"><title>Поиск товара — MVP</title></head>
<body><main><h1>Поиск ранее рассмотренного товара</h1>
<p>Gate 1: экран готов. Поиск и загрузка данных появятся на следующих этапах.</p>
<label>Фотография товара <input type=\"file\" accept=\"image/*\" disabled></label>
<button disabled>Найти</button></main></body></html>"""

    return app
