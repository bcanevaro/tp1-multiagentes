"""Decisión del estado de la respuesta (BR-010, FR-030, FR-022)."""

from __future__ import annotations

from agents.analyst.schemas import (
    AnalystError,
    MissingInfo,
    Status,
    SubQuestion,
    SubquestionCoverage,
)
from services.sandbox.result import CodeResult

NO_TABLES_REASON = "No hay tablas indexadas"
NO_SUBQUESTIONS_REASON = "La pregunta no pide ningún dato que se pueda calcular con tablas"
EXECUTION_FAILED_REASON = "No se pudo calcular: el código generado falló en todos los intentos"


def decide_status(
    subquestions: list[SubQuestion],
    coverage: list[SubquestionCoverage],
    code_result: CodeResult | None,
    error: AnalystError | None,
) -> tuple[Status, list[MissingInfo]]:
    """Una subpregunta está resuelta si está cubierta Y el código devolvió un valor para ella.

    answered: todas resueltas; partial: algunas; cannot_answer: ninguna (o error de ejecución).
    """
    texts = {s.id: s.text for s in subquestions}
    if not subquestions:
        return "cannot_answer", [
            MissingInfo(subquestion_id="q1", text="", reason=NO_SUBQUESTIONS_REASON)
        ]
    if error == "no_tables_indexed":
        return "cannot_answer", [
            MissingInfo(subquestion_id=s.id, text=s.text, reason=NO_TABLES_REASON)
            for s in subquestions
        ] or [MissingInfo(subquestion_id="q1", text="", reason=NO_TABLES_REASON)]

    by_sub = {c.subquestion_id: c for c in coverage}
    results = {r.subquestion_id for r in code_result.results} if code_result else set()
    code_missing = {m.subquestion_id: m.reason for m in code_result.missing} if code_result else {}

    resolved: list[str] = []
    missing: list[MissingInfo] = []
    for sub in subquestions:
        cov = by_sub.get(sub.id)
        if cov is not None and cov.covered and sub.id in results and error is None:
            resolved.append(sub.id)
            continue
        if cov is None or not cov.covered:
            reason = (cov.missing if cov else "") or "No hay datos en las tablas indexadas"
            related = cov.related_table if cov else ""
        elif error == "execution_failed":
            reason, related = EXECUTION_FAILED_REASON, ""
        else:
            reason = code_missing.get(sub.id) or "El cálculo no devolvió un resultado"
            related = ""
        missing.append(
            MissingInfo(
                subquestion_id=sub.id, text=texts[sub.id], reason=reason, related_table=related
            )
        )

    if error == "execution_failed" or not resolved:
        status: Status = "cannot_answer"
    elif len(resolved) == len(subquestions):
        status = "answered"
    else:
        status = "partial"
    return status, missing
