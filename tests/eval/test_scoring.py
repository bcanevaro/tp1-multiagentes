"""Corrección según BR-030 (eval/scoring.py)."""

from __future__ import annotations

from typing import Any

import pytest

from eval.scoring import close, expected_text, score
from services.sandbox.result import CodeResult, LabeledValue, ResultItem


def q(status: str, *values: dict[str, Any], missing: str = "") -> dict[str, Any]:
    return {
        "expected_status": status,
        "expected_values": list(values),
        "expected_missing": missing,
    }


def res(*items: ResultItem) -> CodeResult:
    return CodeResult(results=list(items))


def item(value: float | list[LabeledValue], label: str = "", sid: str = "q1") -> ResultItem:
    return ResultItem(subquestion_id=sid, value=value, unit="%", label=label)


@pytest.mark.parametrize(
    ("obtained", "expected", "ok"),
    [
        (84.8792, 84.8792, True),
        (85.30, 84.8792, True),  # 0,496 %
        (85.31, 84.8792, False),  # 0,508 %
        (-1500.0, -1500.0, True),
        (0.009, 0.0, True),  # esperado 0: tolerancia absoluta 0,01
        (0.011, 0.0, False),
        (-0.01, 0.0, True),
    ],
)
def test_br030_tolerances(obtained: float, expected: float, ok: bool) -> None:
    assert close(obtained, expected) is ok


def test_scalar_value_found_in_any_subquestion() -> None:
    question = q("answered", {"label": "x", "value": 9.8, "unit": "%"})
    assert score(question, "answered", res(item(1.0), item(9.81, sid="q2"))).correct
    assert score(question, "answered", res(item([LabeledValue(label="Norte", value=9.8)]))).correct
    wrong = score(question, "answered", res(item(9.9)))
    assert not wrong.correct and wrong.status_ok and wrong.details


def test_per_category_values_need_label_and_value() -> None:
    question = q(
        "answered",
        {"label": "Proporción", "unit": "%", "values": {"2019": 1.1311, "Valle Alto": 2.0282}},
    )
    as_list = res(
        item(
            [LabeledValue(label="2019", value=1.131), LabeledValue(label="valle alto", value=2.03)]
        )
    )
    assert score(question, "answered", as_list).correct
    as_items = res(item(1.1311, label="Año 2019"), item(2.0282, label="Valle Alto", sid="q2"))
    assert score(question, "answered", as_items).correct
    swapped = res(
        item(
            [
                LabeledValue(label="2019", value=2.0282),
                LabeledValue(label="Valle Alto", value=1.1311),
            ]
        )
    )
    assert not score(question, "answered", swapped).correct
    # la etiqueta tiene que coincidir como palabra: "2019" no coincide con "20190"
    assert not score(question, "answered", res(item(1.1311, label="20190"))).correct


def test_status_must_match() -> None:
    question = q("answered", {"label": "x", "value": 1.0, "unit": ""})
    s = score(question, "partial", res(item(1.0)))
    assert s.values_ok and not s.status_ok and not s.correct


def test_cannot_answer_only_checks_status() -> None:
    question = q("cannot_answer", missing="falta 2024")
    assert score(question, "cannot_answer", None).correct
    assert not score(question, "answered", res(item(3.0))).correct


def test_partial_checks_values_of_answered_part() -> None:
    question = q("partial", {"label": "Norte", "value": 9.8, "unit": "%"}, missing="promedio")
    assert score(question, "partial", res(item(9.8, label="Norte"))).correct
    assert not score(question, "partial", None).correct


def test_expected_text_uses_argentine_format() -> None:
    question = q(
        "partial",
        {"label": "Total", "value": 956.6873, "unit": "millones de US$"},
        missing="sin dato de 2025",
    )
    assert expected_text(question) == "Total: 956,69 millones de US$ · Falta: sin dato de 2025"
