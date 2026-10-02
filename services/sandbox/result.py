"""Resultado de una ejecución y contrato `CodeResult` (spec §7.5, FR-028)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

BackendName = Literal["docker", "subprocess"]


@dataclass(frozen=True)
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int | None  # None si no llegó a ejecutarse (rechazado) o se cortó por timeout
    duration_s: float
    backend: BackendName
    timed_out: bool = False
    rejected: str | None = None  # motivo del filtro estático (FR-053)


class LabeledValue(BaseModel):
    label: str
    value: float


class ResultItem(BaseModel):
    subquestion_id: str
    value: float | list[LabeledValue]
    unit: str = ""
    label: str = ""


class MissingItem(BaseModel):
    subquestion_id: str
    reason: str


class CodeResult(BaseModel):
    """Lo que el código generado imprime como última línea de stdout (una línea JSON)."""

    results: list[ResultItem] = Field(default_factory=list)
    missing: list[MissingItem] = Field(default_factory=list)
    conversions: list[str] = Field(default_factory=list)


def _numbers(item: ResultItem) -> list[float]:
    if isinstance(item.value, list):
        return [v.value for v in item.value]
    return [item.value]


def parse_code_result(stdout: str) -> CodeResult:
    """Interpreta la última línea no vacía de stdout. Lanza `ValueError` con el motivo."""
    lines = [line for line in stdout.strip().splitlines() if line.strip()]
    if not lines:
        raise ValueError("el programa no imprimió nada; la última línea debe ser un JSON")
    last = lines[-1].strip()
    try:
        data = json.loads(last)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"la última línea de stdout no es JSON válido ({exc.msg}): {last[:200]}"
        ) from exc
    try:
        result = CodeResult.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
        raise ValueError(f"el JSON no cumple el contrato CodeResult: {details}") from exc
    for item in result.results:
        if any(not math.isfinite(v) for v in _numbers(item)):
            raise ValueError(
                f"el resultado de {item.subquestion_id} contiene NaN o infinito; revisá datos "
                "faltantes o divisiones por cero"
            )
    return result


def validate_execution(execution: ExecutionResult) -> tuple[CodeResult | None, str | None]:
    """Valida una ejecución (FR-028). Devuelve (resultado, None) o (None, motivo de invalidez)."""
    if execution.rejected:
        return None, f"código rechazado por el filtro de seguridad: {execution.rejected}"
    if execution.timed_out:
        return None, "timeout: el programa superó el tiempo máximo de ejecución"
    if execution.exit_code != 0:
        tail = execution.stderr.strip()[-1500:] or "(sin stderr)"
        return None, f"el programa terminó con código {execution.exit_code}:\n{tail}"
    try:
        return parse_code_result(execution.stdout), None
    except ValueError as exc:
        return None, str(exc)
