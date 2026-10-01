"""Iteración 2: cada PDF de caso borde tiene la propiedad que dice cubrir."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from scripts.make_test_fixtures import FIXTURES


def _image_area_ratios(page: pymupdf.Page) -> list[float]:
    area = page.rect.get_area()
    return [r.get_area() / area for img in page.get_images() for r in page.get_image_rects(img[0])]


def test_all_fixtures_generated(edge_pdfs: dict[str, Path]) -> None:
    assert set(edge_pdfs) == set(FIXTURES)
    assert all(p.exists() for p in edge_pdfs.values())


def test_image_only_pdf_has_no_text(edge_pdfs: dict[str, Path]) -> None:
    with pymupdf.open(edge_pdfs["solo_imagen.pdf"]) as doc:
        assert all(not p.get_text().strip() for p in doc)
        assert _image_area_ratios(doc[0])[0] >= 0.10


def test_text_only_pdf_has_no_tables(edge_pdfs: dict[str, Path]) -> None:
    with pymupdf.open(edge_pdfs["solo_texto.pdf"]) as doc:
        assert doc[0].get_text().strip()
        assert all(not p.find_tables().tables for p in doc)


def test_big_image_and_small_logo(edge_pdfs: dict[str, Path]) -> None:
    with pymupdf.open(edge_pdfs["tabla_imagen_y_texto.pdf"]) as doc:
        assert max(_image_area_ratios(doc[0])) >= 0.10
    with pymupdf.open(edge_pdfs["logo_y_tabla.pdf"]) as doc:
        assert max(_image_area_ratios(doc[0])) < 0.10


def test_unopenable_files(edge_pdfs: dict[str, Path]) -> None:
    with pymupdf.open(edge_pdfs["protegido.pdf"]) as doc:
        assert doc.needs_pass
    with pytest.raises(pymupdf.FileDataError):
        pymupdf.open(edge_pdfs["no_es_pdf.pdf"])


@pytest.mark.parametrize(
    ("name", "cols_p1", "cols_p2"),
    [("columnas_distintas.pdf", 3, 4), ("continuacion_sin_encabezado.pdf", 3, 3)],
)
def test_tables_on_consecutive_pages(
    edge_pdfs: dict[str, Path], name: str, cols_p1: int, cols_p2: int
) -> None:
    with pymupdf.open(edge_pdfs[name]) as doc:
        assert doc.page_count == 2
        last_p1 = doc[0].find_tables().tables[-1]
        first_p2 = doc[1].find_tables().tables[0]
        assert (last_p1.col_count, first_p2.col_count) == (cols_p1, cols_p2)
        assert first_p2.bbox[1] < 100  # empieza al tope de la página 2


def test_continuation_does_not_repeat_header(edge_pdfs: dict[str, Path]) -> None:
    with pymupdf.open(edge_pdfs["continuacion_sin_encabezado.pdf"]) as doc:
        first_row_p2 = doc[1].find_tables().tables[0].extract()[0]
        assert first_row_p2[0] != "Mes"
