"""VC-038: validación de la salida de una ejecución (FR-028) y contrato CodeResult (§7.5)."""

from __future__ import annotations

import pytest

from services.sandbox.result import ExecutionResult, parse_code_result, validate_execution

VALID = (
    '{"results": [{"subquestion_id": "q1", "value": 12.5, "unit": "%"}],'
    ' "conversions": ["miles -> millones"]}'
)


def _exec(stdout: str = VALID, **kw: object) -> ExecutionResult:
    base: dict[str, object] = {
        "stderr": "",
        "exit_code": 0,
        "duration_s": 0.1,
        "backend": "subprocess",
    }
    base.update(kw)
    return ExecutionResult(stdout=stdout, **base)  # type: ignore[arg-type]


def test_valid_output_is_parsed() -> None:
    result, error = validate_execution(_exec("cálculo intermedio\n" + VALID + "\n\n"))
    assert error is None and result is not None
    assert result.results[0].value == 12.5
    assert result.conversions == ["miles -> millones"]


def test_labeled_values_and_missing() -> None:
    out = (
        '{"results": [{"subquestion_id": "q1", "value": [{"label": "2019", "value": 1.13}]}],'
        ' "missing": [{"subquestion_id": "q2", "reason": "no hay 2024"}]}'
    )
    result = parse_code_result(out)
    assert result.missing[0].reason == "no hay 2024"


@pytest.mark.parametrize(
    ("execution", "fragment"),
    [
        (
            _exec(exit_code=1, stderr="Traceback ...\nKeyError: 'Poblacion'"),
            "KeyError: 'Poblacion'",
        ),
        (_exec(exit_code=None, timed_out=True), "timeout"),
        (_exec(""), "no imprimió nada"),
        (_exec("resultado = 3"), "no es JSON"),
        (_exec('{"results": [{"value": 3}]}'), "contrato CodeResult"),
        (_exec('{"results": [{"subquestion_id": "q1", "value": NaN}]}'), "NaN o infinito"),
        (_exec(exit_code=None, rejected="import de 'os' no permitido"), "filtro de seguridad"),
    ],
    ids=["exit", "timeout", "vacio", "no-json", "contrato", "nan", "rechazado"],
)
def test_vc038_invalid_executions(execution: ExecutionResult, fragment: str) -> None:
    result, error = validate_execution(execution)
    assert result is None
    assert error is not None and fragment in error
