"""Lo que ven los LLM del Analista sobre cada tabla candidata."""

from __future__ import annotations

from agents.analyst.prompts import SELECT_SYSTEM, describe_table
from tests.analyst.fakes import synthetic_tables


def test_table_description_includes_pdf_caption() -> None:
    """El epígrafe original distingue tablas con nombres parecidos ("respecto al mes anterior"
    vs. "respecto a diciembre"); antes el selector solo veía el nombre que inventó el LLM."""
    meta, _ = synthetic_tables()[0]
    meta = meta.model_copy(update={"caption": "Cuadro 2. Variaciones respecto a diciembre de 2025"})
    text = describe_table(meta, "")
    assert "Epígrafe en el PDF: Cuadro 2. Variaciones respecto a diciembre de 2025" in text


def test_table_description_without_caption_has_no_empty_line() -> None:
    meta, _ = synthetic_tables()[0]
    assert "Epígrafe" not in describe_table(meta.model_copy(update={"caption": ""}), "")


def test_select_prompt_asks_for_denominator_tables_and_period_equivalences() -> None:
    assert "denominador" in SELECT_SYSTEM
    assert "acumulado hasta" in SELECT_SYSTEM and "respecto a diciembre" in SELECT_SYSTEM
