"""Los valores esperados de las preguntas sobre INDEC (eval/questions.yaml) salen de las tablas
extraídas del PDF real: si la extracción cambia y deja de reproducirlos, este test lo detecta."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

from agents.ingestion.normalize import normalize_table
from tests.ingestion.conftest import Extraction

QUESTIONS = {
    q["id"]: q
    for q in yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "eval" / "questions.yaml").read_text(
            encoding="utf-8"
        )
    )["questions"]
}


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 0.005 * abs(b) if b else abs(a) <= 0.01


def _expected(qid: str) -> float:
    value: float = QUESTIONS[qid]["expected_values"][0]["value"]
    return value


def _cuadro(indec: Extraction, number: int) -> pd.DataFrame:
    for table in indec.tables:
        if indec.context(table).caption.startswith(f"Cuadro {number}."):
            df, _, _ = normalize_table(table, indec.loaded)
            return df
    raise AssertionError(f"No se extrajo el Cuadro {number}")


def _col(df: pd.DataFrame, *parts: str) -> str:
    matches = [c for c in df.columns if all(p in c for p in parts)]
    assert len(matches) == 1, (parts, list(df.columns))
    return matches[0]


def _row(df: pd.DataFrame, label: str) -> pd.Series[Any]:
    mask = df.apply(lambda r: any(str(v).strip() == label for v in r.values), axis=1)
    rows = df[mask]
    assert len(rows) >= 1, label
    return rows.iloc[0]


def test_ind01_santa_fe_share(indec: Extraction) -> None:
    df = _cuadro(indec, 10)
    total = _col(df, "Total")
    share = _row(df, "Santa Fe")[total] / _row(df, "Total")[total] * 100
    assert _close(_expected("ind-01"), share)


def test_ind02_average_monthly_balance(indec: Extraction) -> None:
    df = _cuadro(indec, 1)
    saldo = _col(df, "Saldo", "2026")
    months = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto"]
    values = [_row(df, m)[saldo] for m in months]
    assert _close(_expected("ind-02"), sum(values) / len(values))
    accumulated = _row(df, "Acumulado hasta agosto")[saldo]
    assert _close(_expected("ind-02"), accumulated / 8)


def test_ind03_automotive_share(indec: Extraction) -> None:
    auto = _cuadro(indec, 7)
    total = _cuadro(indec, 1)
    exports_auto = _row(auto, "Exportaciones")[_col(auto, "Agosto", "2026")]
    exports_total = _row(total, "Agosto")[_col(total, "Exportaciones", "2026")]
    assert _close(_expected("ind-03"), exports_auto / exports_total * 100)


def test_ind04_september_2026_is_missing(indec: Extraction) -> None:
    df = _cuadro(indec, 1)
    september = _row(df, "Septiembre")
    assert pd.isna(september[_col(df, "Exportaciones", "2026")])
    assert not pd.isna(september[_col(df, "Exportaciones", "2025")])


def test_ind05_patagonia_only_has_2026(indec: Extraction) -> None:
    df = _cuadro(indec, 9)
    assert _close(_expected("ind-05"), _row(df, "Patagonia")[_col(df, "Total")])
    assert not any("2025" in c for c in df.columns)


@pytest.mark.parametrize("qid", ["ind-01", "ind-02", "ind-03", "ind-04", "ind-05"])
def test_indec_questions_point_to_the_real_pdf(qid: str) -> None:
    assert QUESTIONS[qid]["doc"] == "indec_ica.pdf"
