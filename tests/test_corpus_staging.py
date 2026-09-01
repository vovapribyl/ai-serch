from __future__ import annotations

from pathlib import Path

import pytest

from product_search.corpus.staging import CorpusStagingError, stage_products
from product_search.corpus.xlsx_reader import ParsedProduct


def product(product_id: str, image: bytes = b"image") -> ParsedProduct:
    return ParsedProduct(
        product_id=product_id,
        source_row=6,
        category="Накладные ногти",
        primary_image=image,
    )


def test_stages_every_accepted_image_before_activation(tmp_path: Path) -> None:
    stage = stage_products([product("101"), product("102")], tmp_path)

    assert stage.directory.parent == tmp_path / "staging"
    assert [item.product_id for item in stage.products] == ["101", "102"]
    assert [item.image_path.read_bytes() for item in stage.products] == [b"image", b"image"]


def test_cleans_partial_stage_when_an_image_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_write(path: Path, content: bytes) -> None:
        if path.name == "102.bin":
            raise OSError("disk error")
        path.write_bytes(content)

    monkeypatch.setattr("product_search.corpus.staging._write_image", broken_write)

    with pytest.raises(CorpusStagingError, match="staging"):
        stage_products([product("101"), product("102")], tmp_path)

    assert not list((tmp_path / "staging").glob("*"))
