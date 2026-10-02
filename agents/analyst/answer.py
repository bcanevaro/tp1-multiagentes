"""Formato de resultados y texto determinístico de `cannot_answer` (FR-032, FR-033, BR-015)."""

from __future__ import annotations

import math

from agents.analyst.schemas import MissingInfo, UsedTable
from services.sandbox.result import CodeResult, ResultItem


def fmt_number(value: float) -> str:
    """Formato argentino: `1234567.891` → `1.234.567,89`; valores chicos con más decimales."""
    if math.isnan(value) or math.isinf(value):
        return str(value)
    decimals = 2 if abs(value) >= 1 or value == 0 else 4
    text = f"{abs(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return f"-{text}" if value < 0 else text


def fmt_with_unit(value: float, unit: str) -> str:
    number = fmt_number(value)
    if not unit:
        return number
    return f"{number} %" if unit.strip() == "%" else f"{number} {unit}"


def format_item(item: ResultItem) -> str:
    label = f"{item.label}: " if item.label else ""
    if isinstance(item.value, list):
        values = "; ".join(f"{v.label}: {fmt_with_unit(v.value, item.unit)}" for v in item.value)
        return f"[{item.subquestion_id}] {label}{values}"
    return f"[{item.subquestion_id}] {label}{fmt_with_unit(item.value, item.unit)}"


def format_results(result: CodeResult | None) -> str:
    if result is None or not result.results:
        return "(sin resultados)"
    return "\n".join(f"- {format_item(item)}" for item in result.results)


def format_tables(tables: list[UsedTable]) -> str:
    return "\n".join(
        f"- «{t.name}» ({t.pdf_name}, página{'s' if len(t.pages) > 1 else ''} "
        f"{', '.join(map(str, t.pages))})"
        for t in tables
    )


def format_missing(missing: list[MissingInfo]) -> str:
    lines = []
    for m in missing:
        text = f"- {m.text or m.subquestion_id}: {m.reason}"
        if m.related_table:
            text += f" ({m.related_table})"
        lines.append(text)
    return "\n".join(lines)


def cannot_answer_text(missing: list[MissingInfo]) -> str:
    """Respuesta de `cannot_answer` armada sin LLM: no contiene resultados calculados (BR-015)."""
    return (
        f"No puedo responder esta pregunta con las tablas indexadas.\n\n{format_missing(missing)}"
    )
