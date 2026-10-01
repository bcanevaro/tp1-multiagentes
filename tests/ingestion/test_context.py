"""VC-010: contexto de cada tabla del PDF sintético contra la verdad."""

from __future__ import annotations

import pytest

from tests.ingestion.conftest import Extraction
from tests.ingestion.test_extract import TRUTH_TABLES

FIELDS = {
    "caption": "caption",
    "section_title": "section_title",
    "paragraph_before": "paragraph_before",
    "footnotes": "footnote",
    "paragraph_after": "paragraph_after",
}


@pytest.mark.parametrize("index", range(len(TRUTH_TABLES)), ids=[t["key"] for t in TRUTH_TABLES])
def test_vc010_context_matches_truth(sample: Extraction, index: int) -> None:
    ctx = sample.context(sample.tables[index])
    truth = TRUTH_TABLES[index]
    for attr, key in FIELDS.items():
        assert getattr(ctx, attr) == truth[key], attr


def test_context_prompt_text_skips_empty_fields(sample: Extraction) -> None:
    text = sample.context(sample.tables[0]).as_prompt_text()
    assert text.startswith("Título de la sección: 1. Finanzas públicas")
    assert "Texto posterior" not in text  # vacío para el Cuadro 1


def test_indec_context_has_source_note(indec: Extraction) -> None:
    ctx = indec.context(indec.tables[8])  # Cuadro 9
    assert ctx.section_title.startswith("3.5 Origen de las exportaciones")
    assert "Fuente: INDEC" in ctx.footnotes
