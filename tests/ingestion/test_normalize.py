"""VC-005, VC-005b, VC-006, VC-006b: normalización de celdas."""

from __future__ import annotations

import math

import pytest

from agents.ingestion.extract import RawTable
from agents.ingestion.normalize import normalize_table, parse_number
from agents.ingestion.pdf_loader import LoadedPdf


def _loaded(*, zero_dash: bool = False, decimal_comma: bool = True) -> LoadedPdf:
    return LoadedPdf("d", "x.pdf", [], zero_dash, decimal_comma, 10.0)


def _column(values: list[str], **kw: bool) -> tuple[list[object], list[str]]:
    table = RawTable(
        pages=[1],
        bbox=(0, 0, 1, 1),
        last_bbox=(0, 0, 1, 1),
        header_rows=[["Fila", "Valor"]],
        rows=[[f"r{i}", v] for i, v in enumerate(values)],
        strategy="lines",
    )
    df, notes, _ = normalize_table(table, _loaded(**kw))
    return df["Valor"].tolist(), notes


def _same(got: list[object], expected: list[float | None]) -> bool:
    return all(
        (e is None and isinstance(g, float) and math.isnan(g)) or g == pytest.approx(e)
        for g, e in zip(got, expected, strict=True)
    )


def test_vc005_missing_markers_are_nan_not_zero() -> None:
    got, notes = _column(["", "-", "—", "s/d", "12"])
    assert _same(got, [None, None, None, None, 12.0])
    assert any("dato faltante" in n for n in notes)


def test_vc005b_dash_follows_document_convention() -> None:
    got, notes = _column(["-", "12"], zero_dash=True)
    assert _same(got, [0.0, 12.0])
    assert any("cero absoluto" in n for n in notes)
    got, _ = _column(["-", "12"], zero_dash=False)
    assert _same(got, [None, 12.0])
    got, notes = _column(["///", "...", "1.234*"])
    assert _same(got, [None, None, 1234.0])
    assert any("provisorios" in n for n in notes)


def test_vc006_comma_decimal_column() -> None:
    got, _ = _column(["1.234,56", "(1.500)", "12,5%", "$ 3.000"])
    assert _same(got, [1234.56, -1500.0, 12.5, 3000.0])


def test_vc006_dot_decimal_column() -> None:
    got, _ = _column(["1,234.56", "(1,500)", "US$ 1,000.50"], decimal_comma=True)
    assert _same(got, [1234.56, -1500.0, 1000.5])


def test_vc006b_mostly_text_column_stays_text() -> None:
    got, _ = _column(["Norte", "Sur", "12"])
    assert got == ["Norte", "Sur", "12"]


def test_ambiguous_thousands_use_document_format() -> None:
    assert _same(_column(["612.450", "97.820"], decimal_comma=True)[0], [612450.0, 97820.0])
    assert _same(_column(["612.450", "97.820"], decimal_comma=False)[0], [612.45, 97.82])


@pytest.mark.parametrize(
    ("text", "comma", "expected"),
    [("1.854.320,6", True, 1854320.6), ("-2,6", True, -2.6), ("(48.454,7)", True, -48454.7),
     ("7,1 %", True, 7.1), ("abc", True, None), ("1,234.5", True, None),
     ("1,234.5", False, 1234.5)],
)  # fmt: skip
def test_parse_number(text: str, comma: bool, expected: float | None) -> None:
    assert parse_number(text, comma) == (None if expected is None else pytest.approx(expected))
