"""VC-002b, VC-003, VC-004, VC-007, VC-008, VC-008b, VC-009, VC-009b, VC-009c, VC-009d."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from agents.ingestion.extract import flatten_header, is_data_number, split_header
from agents.ingestion.normalize import normalize_table
from tests.ingestion.conftest import ROOT, Extraction

TRUTH: dict[str, Any] = json.loads(
    (ROOT / "tests" / "fixtures" / "sample_truth.json").read_text(encoding="utf-8")
)
TRUTH_TABLES = TRUTH["tables"]


def test_sample_has_one_table_per_truth_table(sample: Extraction) -> None:
    assert len(sample.tables) == len(TRUTH_TABLES)
    assert [t.pages for t in sample.tables] == [t["pages"] for t in TRUTH_TABLES]


@pytest.mark.parametrize("index", range(len(TRUTH_TABLES)), ids=[t["key"] for t in TRUTH_TABLES])
def test_vc003_vc004_shapes_columns_and_values(sample: Extraction, index: int) -> None:
    truth = TRUTH_TABLES[index]
    df, _, warnings = normalize_table(sample.tables[index], sample.loaded)
    assert df.shape == (truth["n_rows"], truth["n_cols"])
    assert list(df.columns) == truth["columns"]
    assert warnings == []
    for got_row, exp_row in zip(df.itertuples(index=False), truth["values"], strict=True):
        for got, exp in zip(got_row, exp_row, strict=True):
            if exp is None:
                assert isinstance(got, float) and math.isnan(got)
            elif isinstance(exp, str):
                assert got == exp
            else:
                assert got == pytest.approx(exp)


def test_vc004_two_level_header(sample: Extraction) -> None:
    produccion = sample.tables[3]
    assert produccion.columns == [
        "Departamento", "Soja | 2022", "Soja | 2023", "Maíz | 2022", "Maíz | 2023",
    ]  # fmt: skip
    assert len(set(produccion.columns)) == len(produccion.columns)


def test_vc009d_horizontal_rules_only_table(sample: Extraction) -> None:
    salarios = sample.tables[2]
    assert salarios.strategy == "hrules"
    assert (len(salarios.rows), salarios.n_cols) == (4, 4)


def test_vc007_multipage_table_is_merged(sample: Extraction) -> None:
    exportaciones = sample.tables[-1]
    assert exportaciones.pages == [2, 3]
    assert len(exportaciones.rows) == 24
    assert all(row[0] != "Año" for row in exportaciones.rows)  # sin el encabezado repetido
    assert [t.page for t in sample.raw if t.page >= 2 and t.n_cols == 6] == [2, 3]  # venía partida


def test_continuation_without_header_is_merged(edge: dict[str, Extraction]) -> None:
    (table,) = edge["continuacion_sin_encabezado.pdf"].tables
    assert table.pages == [1, 2]
    assert len(table.rows) == 60
    assert table.columns == ["Mes", "Valor", "Variación"]


def test_vc008_different_column_counts_are_not_merged(edge: dict[str, Extraction]) -> None:
    tables = edge["columnas_distintas.pdf"].tables
    assert [(t.pages, t.n_cols) for t in tables] == [([1], 3), ([2], 4)]


def test_vc002b_text_only_pdf_has_no_tables(edge: dict[str, Extraction]) -> None:
    assert edge["solo_texto.pdf"].tables == []


def test_vc009_image_table_is_reported_and_text_table_kept(edge: dict[str, Extraction]) -> None:
    result = edge["tabla_imagen_y_texto.pdf"]
    assert len(result.tables) == 1
    assert [w.code for w in result.warnings] == ["image_region"]
    assert "Página 1" in result.warnings[0].message


def test_vc009b_small_logo_is_not_reported(edge: dict[str, Extraction]) -> None:
    result = edge["logo_y_tabla.pdf"]
    assert len(result.tables) == 1
    assert result.warnings == []


def test_empty_table_is_skipped_with_warning(edge: dict[str, Extraction]) -> None:
    result = edge["tabla_vacia.pdf"]
    assert result.tables == []
    assert [w.code for w in result.warnings] == ["empty_table"]


# --- PDF real de INDEC ---------------------------------------------------------------


def test_vc009c_indec_numbered_tables_are_found(indec: Extraction) -> None:
    pages = [t.pages for t in indec.tables]
    assert pages == [[7], [7], [13], [22], [24], [25], [27], [28], [29], [30], [35]]
    captions = [indec.context(t).caption for t in indec.tables[:10]]
    for n, caption in enumerate(captions, start=1):
        assert caption.startswith(f"Cuadro {n}.")


def test_vc009c_indec_charts_and_infographics_are_discarded(indec: Extraction) -> None:
    chart_pages = {1, 4, 5, 6, 10, 11, 14, 15, 16, 17, 18, 19, 20}
    assert not any(t.page in chart_pages for t in indec.tables)
    discarded = {w.page for w in indec.warnings if w.code == "not_a_table"}
    assert {5, 6, 14, 15, 16, 17, 18} <= discarded


def test_vc008b_indec_consecutive_tables_are_not_merged(indec: Extraction) -> None:
    cuadro9, cuadro10 = indec.tables[8], indec.tables[9]
    assert (cuadro9.pages, cuadro10.pages) == ([29], [30])
    assert cuadro9.columns == cuadro10.columns  # misma estructura: la regla del epígrafe decide


def test_indec_dash_is_zero_and_units_in_header(indec: Extraction) -> None:
    cuadro9 = indec.tables[8]
    df, notes, _ = normalize_table(cuadro9, indec.loaded)
    assert "Total | Millones de USD" in df.columns
    assert any("cero absoluto" in n for n in notes)
    caba = df[df["Provincias"] == "Ciudad Autónoma de Buenos Aires"].iloc[0]
    assert caba["Productos primarios (PP) | Millones de USD"] == 0.0  # "-" en el PDF
    assert caba["Total | Millones de USD"] == 17.0


# --- Unidades de bajo nivel ----------------------------------------------------------


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("1.234,5", True), ("(7.670,2)", True), ("12,5 %", True), ("$ 98.320", True),
     ("2023", False), ("Norte", False), ("", False), (None, False), ("-2,6", True)],
)  # fmt: skip
def test_is_data_number(cell: str | None, expected: bool) -> None:
    assert is_data_number(cell) is expected


def test_split_header_detects_year_headers_and_headerless_rows() -> None:
    rows: list[list[str | None]] = [["Concepto", "2019"], ["Ingresos", "1.234,5"]]
    assert split_header(rows) == ([["Concepto", "2019"]], [["Ingresos", "1.234,5"]])
    headerless: list[list[str | None]] = [["Mes 31", "2.110,0"], ["Mes 32", "2.147,0"]]
    assert split_header(headerless) == ([], headerless)


def test_flatten_header_with_spanned_units_row() -> None:
    header: list[list[str | None]] = [
        ["Región", "Total", "Primarios"],
        ["", "Millones de USD", None],
    ]
    assert flatten_header(header, 3) == [
        "Región", "Total | Millones de USD", "Primarios | Millones de USD",
    ]  # fmt: skip
    assert flatten_header([["A", "A", ""]], 3) == ["A", "A (2)", "columna_3"]
