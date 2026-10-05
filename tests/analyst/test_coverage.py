"""VC-034, VC-034b, VC-034c, VC-048: chequeos determinísticos de cobertura (FR-024, FR-024b)."""

from __future__ import annotations

import pandas as pd
import pytest

from agents.analyst.coverage import apply_deterministic_checks
from agents.analyst.schemas import Candidate
from tests.analyst.fakes import (
    FINANCE_ID,
    UNEMPLOYMENT_ID,
    WAGES_ID,
    _col,
    _meta,
    cover,
    sub,
    synthetic_tables,
)


def candidates() -> list[Candidate]:
    return [
        Candidate(table_id=m.table_id, score=0.9, metadata=m, preview_markdown="")
        for m, _ in synthetic_tables()
    ]


def test_vc034_missing_year_uncovers_and_names_related_range() -> None:
    q = sub("q1", "Ingresos totales en 2024", periods=["2024"])
    [result] = apply_deterministic_checks([q], [cover("q1", [FINANCE_ID], ["2024"])], candidates())
    assert not result.covered
    assert "2024" in result.missing
    assert "2019" in result.related_table and "2023" in result.related_table


def test_missing_entity_uncovers() -> None:
    q = sub("q1", "Desempleo en Río Seco", entities=["Río Seco"], periods=["2023"])
    [result] = apply_deterministic_checks(
        [q], [cover("q1", [UNEMPLOYMENT_ID], ["2023"])], candidates()
    )
    assert not result.covered and "Río Seco" in result.missing


def test_vc034b_normalized_entity_and_year_inside_column_name() -> None:
    df = pd.DataFrame({"Provincia": ["Cordoba", "Santa Fe"], "Año 2023": [1.0, 2.0]})
    meta = _meta(
        "x-t01",
        "Producción provincial",
        [_col("Provincia"), _col("Año 2023", "t", "conteo")],
        df,
        1,
    )
    cand = [Candidate(table_id="x-t01", score=1.0, metadata=meta, preview_markdown="")]
    q = sub("q1", "Producción de Córdoba en 2023", periods=["2023"], entities=["Córdoba"])
    [result] = apply_deterministic_checks([q], [cover("q1", ["x-t01"], ["Año 2023"])], cand)
    assert result.covered


def test_vc034c_real_wage_with_unknown_money_column_is_not_covered() -> None:
    q = sub("q1", "¿Cuánto creció el salario real de la industria entre 2021 y 2023?")
    [result] = apply_deterministic_checks(
        [q], [cover("q1", [WAGES_ID], ["Sector", "2021", "2023"])], candidates()
    )
    assert not result.covered
    assert "nominales o reales" in result.missing  # VC-048: el motivo describe la ambigüedad


def test_vc034c_same_column_without_real_nominal_stays_covered() -> None:
    q = sub("q1", "¿Cuánto creció el salario de la industria entre 2021 y 2023?")
    [result] = apply_deterministic_checks(
        [q], [cover("q1", [WAGES_ID], ["Sector", "2021", "2023"])], candidates()
    )
    assert result.covered


def test_vc034c_identifier_column_with_unknown_unit_stays_covered() -> None:
    df = pd.DataFrame({"Año": [2021.0, 2022.0], "Ventas": [10.0, 12.0]})
    meta = _meta(
        "x-t02",
        "Ventas anuales",
        [_col("Año", "desconocida", "unknown"), _col("Ventas", "unidades vendidas", "conteo")],
        df,
        1,
    )
    cand = [Candidate(table_id="x-t02", score=1.0, metadata=meta, preview_markdown="")]
    q = sub("q1", "¿Cuánto crecieron las ventas?")
    [result] = apply_deterministic_checks([q], [cover("q1", ["x-t02"], ["Año", "Ventas"])], cand)
    assert result.covered


def test_unknown_unit_on_value_column_uncovers_unless_justified() -> None:
    df = pd.DataFrame({"Región": ["A", "B"], "Valor": [1.0, 3.0]})
    meta = _meta(
        "x-t03",
        "Indicador regional",
        [_col("Región"), _col("Valor", "desconocida", "unknown")],
        df,
        1,
    )
    cand = [Candidate(table_id="x-t03", score=1.0, metadata=meta, preview_markdown="")]
    q = sub("q1", "¿Cuántas veces el valor de B supera al de A?")
    [plain] = apply_deterministic_checks([q], [cover("q1", ["x-t03"], ["Valor"])], cand)
    assert not plain.covered and "unidad desconocida" in plain.missing
    justified = cover("q1", ["x-t03"], ["Valor"]).model_copy(
        update={"ambiguity_ok": "Es un cociente entre valores de la misma columna."}
    )
    [ok] = apply_deterministic_checks([q], [justified], cand)
    assert ok.covered


def test_unknown_table_ids_are_dropped_and_missing_subquestions_added() -> None:
    q1, q2 = sub("q1", "uno"), sub("q2", "dos")
    result = apply_deterministic_checks([q1, q2], [cover("q1", ["no-existe"], [])], candidates())
    assert [r.subquestion_id for r in result] == ["q1", "q2"]
    assert not result[0].covered and result[0].table_ids == []
    assert not result[1].covered


# --- Casos encontrados en la corrida real (syn-02, syn-04, syn-08) ---


def test_non_concrete_period_is_not_checked() -> None:
    """syn-02: el plan anotó "todos los años disponibles" como período."""
    q = sub("q1", "Proporción en cada año", periods=["todos los años disponibles", "cada año"])
    [result] = apply_deterministic_checks(
        [q], [cover("q1", [FINANCE_ID], ["Concepto", "2019"])], candidates()
    )
    assert result.covered


def test_month_names_are_checked() -> None:
    q = sub("q1", "Desempleo en marzo de 2023", periods=["marzo"])
    [result] = apply_deterministic_checks(
        [q], [cover("q1", [UNEMPLOYMENT_ID], ["2023"])], candidates()
    )
    assert not result.covered and "marzo" in result.missing


def test_document_scope_entity_is_ignored() -> None:
    """syn-08: el plan anotó "provincia" como entidad."""
    q = sub(
        "q1",
        "Exportaciones de la provincia en 2023",
        periods=["2023"],
        entities=["provincia", "la provincia"],
    )
    [result] = apply_deterministic_checks([q], [cover("q1", [FINANCE_ID], ["2023"])], candidates())
    assert result.covered


def test_entity_found_in_description_counts() -> None:
    meta, _ = synthetic_tables()[0]
    meta = meta.model_copy(update={"description": "Finanzas de la provincia de San Aurelio."})
    cand = [Candidate(table_id=meta.table_id, score=1.0, metadata=meta, preview_markdown="")]
    q = sub("q1", "Ingresos de San Aurelio en 2023", periods=["2023"], entities=["San Aurelio"])
    [result] = apply_deterministic_checks([q], [cover("q1", [FINANCE_ID], ["2023"])], cand)
    assert result.covered


def test_vc047_reference_average_not_in_table_uncovers() -> None:
    """syn-04 / BR-013: "promedio provincial" sin fila de total o promedio → no cubierta."""
    q1 = sub("q1", "Departamento con la tasa de desempleo más alta en 2023", periods=["2023"])
    q2 = sub(
        "q2", "Diferencia entre la tasa más alta y el promedio provincial en 2023", periods=["2023"]
    )
    cov = [cover("q1", [UNEMPLOYMENT_ID], ["2023"]), cover("q2", [UNEMPLOYMENT_ID], ["2023"])]
    r1, r2 = apply_deterministic_checks([q1, q2], cov, candidates())
    assert r1.covered and not r2.covered
    assert "promedio provincial" in r2.missing


def test_reference_average_reported_by_table_or_explicit_calculation_stays_covered() -> None:
    df = pd.DataFrame({"Región": ["Norte", "Sur", "Total del país"], "2023": [9.8, 6.1, 7.7]})
    meta = _meta(
        "x-t04", "Desempleo por región", [_col("Región"), _col("2023", "%", "porcentaje")], df, 1
    )
    cand = [Candidate(table_id="x-t04", score=1.0, metadata=meta, preview_markdown="")]
    q = sub("q1", "¿Por cuánto superó Norte al promedio nacional?", entities=["Norte"])
    [result] = apply_deterministic_checks([q], [cover("q1", ["x-t04"], ["2023"])], cand)
    assert result.covered
    q = sub("q1", "¿Por cuánto superó Norte al promedio provincial ponderado por población?")
    [result] = apply_deterministic_checks(
        [q], [cover("q1", [UNEMPLOYMENT_ID], ["2023"])], candidates()
    )
    assert result.covered


def indec_like() -> list[Candidate]:
    """Como el Cuadro 1 de INDEC: meses en las filas y el año en columnas y epígrafe."""
    df = pd.DataFrame(
        {
            "Período": ["Acumulado hasta agosto", "Enero", "Febrero", "Agosto", "Septiembre"],
            "Saldo | 2026 | Millones de USD": [18249.0, 2189.0, 797.0, 2187.0, float("nan")],
            "Saldo | 2025 | Millones de USD": [5109.0, 162.0, 275.0, 1440.0, 937.0],
        }
    )
    meta = _meta(
        "ica-t01",
        "Intercambio comercial argentino",
        [
            _col("Período"),
            _col("Saldo | 2026 | Millones de USD", "millones de USD", "nominal"),
            _col("Saldo | 2025 | Millones de USD", "millones de USD", "nominal"),
        ],
        df,
        7,
    ).model_copy(update={"caption": "Cuadro 1. Intercambio comercial. Enero-agosto de 2026"})
    return [Candidate(table_id="ica-t01", score=1.0, metadata=meta, preview_markdown="")]


@pytest.mark.parametrize(
    "periods",
    [
        ["2026 hasta agosto"],  # ind-01 en la primera corrida real
        ["enero 2026", "febrero 2026", "agosto de 2026"],  # ind-02
        ["acumulado hasta agosto de 2026"],
    ],
)
def test_composite_periods_split_into_month_and_year(periods: list[str]) -> None:
    q = sub("q1", "Saldo comercial", periods=periods)
    [result] = apply_deterministic_checks(
        [q], [cover("q1", ["ica-t01"], ["Período"])], indec_like()
    )
    assert result.covered, result.missing


@pytest.mark.parametrize("periods", [["marzo de 2026"], ["agosto 2024"], ["2027"]])
def test_composite_period_with_absent_month_or_year_is_uncovered(periods: list[str]) -> None:
    q = sub("q1", "Saldo comercial", periods=periods)
    [result] = apply_deterministic_checks(
        [q], [cover("q1", ["ica-t01"], ["Período"])], indec_like()
    )
    assert not result.covered and periods[0] in result.missing
