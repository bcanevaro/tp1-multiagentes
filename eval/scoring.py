"""Corrección de una respuesta del Analista según BR-030.

Una respuesta es correcta si el estado obtenido es igual al esperado y, para `answered` y
`partial`, cada valor numérico esperado aparece entre los resultados del código con tolerancia
relativa de 0,5 % (absoluta de 0,01 si el esperado es 0).

Cómo se buscan los valores (D-035):
- Un esperado con `value` (un número) es correcto si algún número obtenido, de cualquier
  subpregunta, coincide.
- Un esperado con `values` (un número por categoría) exige, para cada categoría, un número
  obtenido cuya etiqueta contenga la de la categoría (sin tildes ni mayúsculas) y que coincida.
  Sirve tanto si el código devolvió una lista por categoría como si devolvió un resultado por
  categoría con la etiqueta en `label`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from services.sandbox.result import CodeResult

REL_TOL = 0.005
ABS_TOL = 0.01


def close(obtained: float, expected: float) -> bool:
    if expected == 0:
        return abs(obtained) <= ABS_TOL
    return abs(obtained - expected) <= REL_TOL * abs(expected)


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", plain).strip()


def obtained_pool(result: CodeResult | None) -> list[tuple[str, float]]:
    """Todos los números obtenidos con su etiqueta (la del ítem y la de la categoría)."""
    pool: list[tuple[str, float]] = []
    if result is None:
        return pool
    for item in result.results:
        if isinstance(item.value, list):
            for lv in item.value:
                pool.append((_norm(f"{lv.label} {item.label}"), lv.value))
        else:
            pool.append((_norm(item.label), item.value))
    return pool


@dataclass
class Score:
    status_ok: bool
    values_ok: bool
    correct: bool
    details: list[str] = field(default_factory=list)  # qué valor esperado no se encontró


def _label_match(expected_label: str, obtained_label: str) -> bool:
    exp = _norm(expected_label)
    return bool(re.search(rf"(^|\W){re.escape(exp)}(\W|$)", obtained_label))


def score(question: dict[str, Any], status: str, result: CodeResult | None) -> Score:
    status_ok = status == question["expected_status"]
    details: list[str] = []
    if question["expected_status"] in ("answered", "partial"):
        pool = obtained_pool(result)
        for expected in question.get("expected_values", []):
            if "value" in expected:
                if not any(close(v, float(expected["value"])) for _, v in pool):
                    details.append(f"falta {expected['label']} = {expected['value']}")
            else:
                for label, value in expected["values"].items():
                    if not any(
                        _label_match(str(label), lab) and close(v, float(value)) for lab, v in pool
                    ):
                        details.append(f"falta {expected['label']} [{label}] = {value}")
    values_ok = not details
    return Score(status_ok, values_ok, status_ok and values_ok, details)


def expected_text(question: dict[str, Any]) -> str:
    """Respuesta esperada en una línea, con formato argentino."""
    from agents.analyst.answer import fmt_with_unit

    parts: list[str] = []
    for exp in question.get("expected_values", []):
        if "value" in exp:
            parts.append(f"{exp['label']}: {fmt_with_unit(float(exp['value']), exp['unit'])}")
        else:
            values = "; ".join(
                f"{k}: {fmt_with_unit(float(v), exp['unit'])}" for k, v in exp["values"].items()
            )
            parts.append(f"{exp['label']}: {values}")
    if question.get("expected_missing"):
        parts.append(f"Falta: {question['expected_missing']}")
    return " · ".join(parts)
