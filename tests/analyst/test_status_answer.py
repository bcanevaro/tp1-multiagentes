"""VC-041 (tabla de decisión de BR-010), VC-049 y formato de números de la respuesta."""

from __future__ import annotations

import re

import pytest

from agents.analyst.answer import cannot_answer_text, fmt_number, fmt_with_unit, format_results
from agents.analyst.schemas import SubquestionCoverage
from agents.analyst.status import EXECUTION_FAILED_REASON, NO_TABLES_REASON, decide_status
from services.sandbox.result import CodeResult, LabeledValue, MissingItem, ResultItem
from tests.analyst.fakes import cover, sub

SUBS = [sub("q1", "primera"), sub("q2", "segunda")]
BOTH = [cover("q1", ["t"], ["a"]), cover("q2", ["t"], ["b"])]


def result(*ids: str) -> CodeResult:
    return CodeResult(results=[ResultItem(subquestion_id=i, value=1.0, unit="") for i in ids])


@pytest.mark.parametrize(
    ("coverage", "code_result", "expected"),
    [
        (BOTH, result("q1", "q2"), "answered"),
        (BOTH, result("q1"), "partial"),
        (
            [BOTH[0], cover("q2", [], [], covered=False, missing="Falta 2024")],
            result("q1"),
            "partial",
        ),
        (BOTH, result(), "cannot_answer"),
        ([cover("q1", [], [], False), cover("q2", [], [], False)], None, "cannot_answer"),
    ],
)
def test_vc041_decision_table(
    coverage: list[SubquestionCoverage], code_result: CodeResult | None, expected: str
) -> None:
    status, missing = decide_status(SUBS, coverage, code_result, None)
    assert status == expected
    assert len(missing) == 2 - len(code_result.results if code_result else [])


def test_partial_reasons_come_from_coverage_and_code() -> None:
    coverage = [BOTH[0], cover("q2", [], [], covered=False, missing="Falta el período 2024")]
    _, missing = decide_status(SUBS, coverage, result("q1"), None)
    assert [m.reason for m in missing] == ["Falta el período 2024"]
    code_missing = CodeResult(
        results=[], missing=[MissingItem(subquestion_id="q1", reason="sin fila")]
    )
    _, missing = decide_status(SUBS[:1], BOTH[:1], code_missing, None)
    assert missing[0].reason == "sin fila"


def test_errors_force_cannot_answer() -> None:
    status, missing = decide_status(SUBS, BOTH, result("q1", "q2"), "execution_failed")
    assert status == "cannot_answer" and {m.reason for m in missing} == {EXECUTION_FAILED_REASON}
    status, missing = decide_status(SUBS, [], None, "no_tables_indexed")
    assert status == "cannot_answer" and missing[0].reason == NO_TABLES_REASON
    status, missing = decide_status([], [], None, None)
    assert status == "cannot_answer" and missing


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (1234567.891, "1.234.567,89"),
        (84.8792, "84,88"),
        (1.0, "1"),
        (-1500.0, "-1.500"),
        (0.0, "0"),
        (0.12345, "0,1235"),
        (956.6873, "956,69"),
    ],
)
def test_argentine_number_format(value: float, text: str) -> None:
    assert fmt_number(value) == text


def test_units_and_per_category_results() -> None:
    assert fmt_with_unit(7.4926, "%") == "7,49 %"
    assert fmt_with_unit(956.6873, "millones de US$") == "956,69 millones de US$"
    res = CodeResult(
        results=[
            ResultItem(
                subquestion_id="q1",
                unit="%",
                label="Proporción",
                value=[
                    LabeledValue(label="2019", value=1.1311),
                    LabeledValue(label="2020", value=1.0707),
                ],
            )
        ]
    )
    assert format_results(res) == "- [q1] Proporción: 2019: 1,13 %; 2020: 1,07 %"


def test_vc049_cannot_answer_text_has_no_computed_numbers() -> None:
    _, missing = decide_status(
        SUBS,
        [
            cover("q1", [], [], False, "No hay tipo de cambio"),
            cover("q2", [], [], False, "No hay datos"),
        ],
        None,
        None,
    )
    text = cannot_answer_text(missing)
    assert text.startswith("No puedo responder")
    assert not re.search(r"\d", text)
