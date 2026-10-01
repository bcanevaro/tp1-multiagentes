"""VC-001, VC-002, VC-002c: carga del PDF."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agents.ingestion.pdf_loader import NoTextLayerError, PdfOpenError, compute_doc_id, read_pdf
from tests.ingestion.conftest import INDEC, SAMPLE, Extraction


def test_vc001_loads_text_of_every_page(sample: Extraction) -> None:
    assert sample.loaded.page_count == 3
    assert all(p.has_text and p.blocks for p in sample.loaded.pages)


def test_vc002_image_only_pdf_has_no_text_layer(edge_pdfs: dict[str, Path]) -> None:
    with pytest.raises(NoTextLayerError, match="no tiene capa de texto"):
        read_pdf(edge_pdfs["solo_imagen.pdf"])


@pytest.mark.parametrize(
    ("name", "reason"), [("no_es_pdf.pdf", "no es un PDF"), ("protegido.pdf", "contraseña")]
)
def test_vc002c_unopenable_files(edge_pdfs: dict[str, Path], name: str, reason: str) -> None:
    with pytest.raises(PdfOpenError, match=reason) as err:
        read_pdf(edge_pdfs[name])
    assert str(err.value).startswith("No se pudo abrir el PDF:")


def test_doc_id_is_content_hash() -> None:
    data = SAMPLE.read_bytes()
    assert compute_doc_id(data) == hashlib.sha256(data).hexdigest()[:16]
    doc, loaded = read_pdf(data, name="otro_nombre.pdf")
    doc.close()
    assert loaded.doc_id == compute_doc_id(data)  # no depende del nombre del archivo


def test_document_conventions(sample: Extraction, indec: Extraction) -> None:
    assert sample.loaded.decimal_comma and indec.loaded.decimal_comma
    assert not sample.loaded.zero_dash
    assert indec.loaded.zero_dash  # "- Cero absoluto" en los signos convencionales
    assert INDEC.exists()
