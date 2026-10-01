"""Iteración 2: el set de preguntas cumple la consigna §9.2 y sus valores esperados son exactos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import sample_data as sd

QUESTIONS: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "eval" / "questions.yaml").read_text(encoding="utf-8")
)["questions"]
BY_ID = {q["id"]: q for q in QUESTIONS}
STATUSES = {"answered", "partial", "cannot_answer"}


def test_schema() -> None:
    assert len(QUESTIONS) >= 8
    assert len(BY_ID) == len(QUESTIONS)  # ids únicos
    for q in QUESTIONS:
        assert q["expected_status"] in STATUSES
        assert q["question"].strip() and q["doc"].endswith(".pdf")
        if q["expected_status"] == "cannot_answer":
            assert q["expected_values"] == [] and q["expected_missing"]
        else:
            assert q["expected_values"]
            for v in q["expected_values"]:
                assert ("value" in v) != ("values" in v) and v["unit"]
        if q["expected_status"] == "partial":
            assert q["expected_missing"]


def test_covers_assignment_minimums() -> None:
    multitable = [q for q in QUESTIONS if len(q["tables"]) >= 2]
    unrelated = [
        q for q in QUESTIONS if q["expected_status"] == "cannot_answer" and not q["tables"]
    ]
    related_missing = [
        q for q in QUESTIONS if q["expected_status"] in {"cannot_answer", "partial"} and q["tables"]
    ]
    assert len(multitable) >= 2
    assert len(unrelated) >= 1
    assert len(related_missing) >= 1
    kinds = " ".join(q["kind"] for q in QUESTIONS)
    for case in ("falta un período", "falta una entidad", "valor de comparación", "datos externos"):
        assert case in kinds


def _expected(qid: str) -> dict[str, Any]:
    values: dict[str, Any] = BY_ID[qid]["expected_values"][0]
    return values


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 0.005 * abs(b) if b else abs(a) <= 0.01


def test_syn01_average_yoy_growth() -> None:
    inc = sd.FINANCE["Ingresos totales"]
    growth = [(inc[i] / inc[i - 1] - 1) * 100 for i in range(1, len(inc))]
    assert _close(_expected("syn-01")["value"], sum(growth) / len(growth))


def test_syn02_rd_share_by_year() -> None:
    expected = _expected("syn-02")["values"]
    for year, rd, total in zip(
        sd.YEARS_FINANCE, sd.FINANCE["Gasto en ciencia y tecnología"], sd.FINANCE["Gastos totales"],
        strict=True,
    ):
        assert _close(expected[str(year)], rd / total * 100)


def test_syn04_max_unemployment() -> None:
    rates_2023 = {d: v[2] for d, v in sd.UNEMPLOYMENT.items()}
    top = max(rates_2023, key=lambda d: rates_2023[d] or 0.0)
    assert top in _expected("syn-04")["label"]
    assert _expected("syn-04")["value"] == rates_2023[top]


def test_syn05_soy_per_capita() -> None:
    expected = _expected("syn-05")["values"]
    for dep in sd.DEPARTMENTS:
        tonnes = sd.PRODUCTION[dep]["Soja"][1] * 1000
        assert _close(expected[dep], tonnes / sd.POPULATION[dep])


def test_syn06_population_weighted_unemployment() -> None:
    pop = sd.POPULATION
    rates = {d: sd.UNEMPLOYMENT[d][2] or 0.0 for d in sd.DEPARTMENTS}
    weighted = sum(rates[d] * pop[d] for d in sd.DEPARTMENTS) / sum(pop.values())
    assert _close(_expected("syn-06")["value"], weighted)


def test_syn08_exports_2023_in_millions() -> None:
    total = sum(sd.export_total(2023, m) for m in range(12)) / 1000
    assert _close(_expected("syn-08")["value"], total)


@pytest.mark.parametrize(
    ("qid", "evidence"),
    [
        ("syn-03", lambda: 2024 not in sd.YEARS_FINANCE),
        ("syn-11", lambda: "Río Seco" not in sd.DEPARTMENTS),
        ("syn-04", lambda: "Provincia" not in sd.UNEMPLOYMENT and "Total" not in sd.UNEMPLOYMENT),
    ],
)
def test_missing_data_is_really_missing(qid: str, evidence: Any) -> None:
    assert evidence(), qid
