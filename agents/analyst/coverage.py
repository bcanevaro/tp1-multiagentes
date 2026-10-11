"""Chequeos determinísticos de cobertura (FR-024, FR-024b, FR-024c).

Solo pueden quitar cobertura, nunca agregarla.
"""

from __future__ import annotations

import re
import unicodedata

from agents.analyst.schemas import Candidate, SubQuestion, SubquestionCoverage

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
UNKNOWN_UNIT = "desconocida"


def normalize(text: str) -> str:
    """Minúsculas, sin tildes ni espacios extremos."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()


_MONTHS = {
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "setiembre", "octubre", "noviembre", "diciembre",
}  # fmt: skip

# Palabras que nombran el alcance del documento, no una fila: no se buscan como entidad.
GENERIC_ENTITIES = {
    "provincia", "la provincia", "pais", "el pais", "nacion", "nacional", "provincial",
    "total", "region", "regiones", "departamento", "departamentos", "sector", "sectores",
}  # fmt: skip


def _haystack(tables: list[Candidate], with_text: bool = False) -> list[str]:
    """Textos donde buscar períodos y entidades. `with_text` agrega descripción, notas y título
    de sección (solo para entidades: un año suelto en la descripción no prueba que haya datos)."""
    items: list[str] = []
    for t in tables:
        m = t.metadata
        items += m.row_headers + m.entities_covered + m.periods_covered
        items += [c.name for c in m.columns]
        items += [m.name, m.caption]
        if with_text:
            items += [m.description, m.notes, m.source.section_title]
    return [normalize(i) for i in items if i]


def is_checkable_period(period: str) -> bool:
    """Un período se verifica solo si es concreto: tiene un número (2023, T1 2023) o es un mes.
    "cada año" o "todos los años disponibles" no se pueden buscar en la tabla."""
    n = normalize(period)
    return bool(re.search(r"\d", n)) or any(re.search(rf"\b{m}\b", n) for m in _MONTHS)


# Palabras que no identifican una entidad: artículos/preposiciones y sustantivos genéricos que
# el plan a veces mete en una entidad ("dato nacional", "a nivel nacional", "valor total").
_ENTITY_STOPWORDS = {
    "de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "en", "a", "al", "por", "para",
    "con", "su", "sus",
    "dato", "datos", "valor", "valores", "cifra", "cifras", "nivel", "numero", "cantidad",
}  # fmt: skip
_GENERIC_WORDS = {w for w in GENERIC_ENTITIES if " " not in w}


def _entity_tokens(entity: str) -> list[str]:
    """Palabras que identifican la entidad ("IPC nivel general nacional" -> ipc, nivel, general)."""
    words = re.findall(r"\w+", normalize(entity))
    return [w for w in words if w not in _ENTITY_STOPWORDS and w not in _GENERIC_WORDS]


def is_checkable_entity(entity: str) -> bool:
    return normalize(entity) not in GENERIC_ENTITIES and bool(_entity_tokens(entity))


def _entity_present(entity: str, haystack: list[str]) -> bool:
    """La entidad está si aparece como frase o si cada palabra que la identifica aparece en
    alguna parte de las tablas. El plan a veces junta en una "entidad" la fila, la columna y el
    alcance ("IPC nivel general nacional"), que en la tabla están separados: fila "Nivel
    general", columna "Nacional", "IPC" en el nombre. Sigue sin estar si falta una palabra
    propia ("Río Seco" cuando ninguna tabla dice "Seco")."""
    if _present(entity, haystack):
        return True
    return all(
        any(re.search(rf"\b{re.escape(w)}\b", item) for item in haystack)
        for w in _entity_tokens(entity)
    )


def _present(term: str, haystack: list[str]) -> bool:
    needle = normalize(term)
    if not needle:
        return True
    if _YEAR_RE.match(needle):  # un año está si aparece dentro de algún elemento
        return any(needle in item for item in haystack)
    return any(needle == item or re.search(rf"\b{re.escape(needle)}\b", item) for item in haystack)


_YEAR_TOKEN_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def _period_present(period: str, haystack: list[str]) -> bool:
    """Un período compuesto ("enero 2026", "2026 hasta agosto", "acumulado a agosto de 2026")
    está presente si cada año y cada mes que nombra aparece en alguna parte de las tablas: en
    las tablas reales el mes suele ser una fila y el año, una columna o el epígrafe."""
    n = normalize(period)
    years = _YEAR_TOKEN_RE.findall(n)
    found = sorted(
        (m.start(), name) for name in _MONTHS for m in [re.search(rf"\b{name}\b", n)] if m
    )
    months = [name for _, name in found]
    if not years and not months:
        return _present(period, haystack)
    if len(months) >= 2 and months[0] == "enero" and _year_to_date_present(months[-1], haystack):
        months = months[
            1:
        ]  # "enero-agosto" = "acumulado hasta agosto": el acumulado empieza en enero
    return all(any(y in item for item in haystack) for y in years) and all(
        any(re.search(rf"\b{m}\b", item) for item in haystack) for m in months
    )


def _year_to_date_present(last_month: str, haystack: list[str]) -> bool:
    """¿Alguna tabla informa el acumulado del año hasta `last_month`? ("acumulado hasta agosto",
    "acumulado a agosto de 2026", "enero-agosto"…)."""
    pattern = rf"\b(acumulad\w*|hasta)\b.*\b{last_month}\b"
    return any(re.search(pattern, item) for item in haystack)


def _describe(tables: list[Candidate]) -> str:
    parts = []
    for t in tables:
        m = t.metadata
        periods = ", ".join(m.periods_covered) or "períodos no indicados"
        parts.append(f"la tabla «{m.name}» cubre {periods}")
    return "; ".join(parts)


def check_periods_and_entities(
    sub: SubQuestion, cov: SubquestionCoverage, tables: list[Candidate]
) -> SubquestionCoverage:
    """FR-024: si la subpregunta nombra períodos o entidades que no están en las tablas, no está
    cubierta."""
    if not cov.covered:
        return cov
    haystack, text_haystack = _haystack(tables), _haystack(tables, with_text=True)
    absent = [p for p in sub.periods if is_checkable_period(p) and not _period_present(p, haystack)]
    absent += [
        e for e in sub.entities if is_checkable_entity(e) and not _entity_present(e, text_haystack)
    ]
    if not absent:
        return cov
    kind = "el período" if all(a in sub.periods for a in absent) else "la entidad"
    if any(a in sub.periods for a in absent) and any(a in sub.entities for a in absent):
        kind = "los datos"
    return cov.model_copy(
        update={
            "covered": False,
            "missing": f"Falta {kind} {', '.join(absent)}",
            "related_table": cov.related_table or _describe(tables).capitalize(),
        }
    )


_IDENTIFIER_COLUMNS = {"ano", "anio", "year", "periodo", "mes", "fecha", "trimestre"}
_MONEY_RE = re.compile(r"(\$|peso|dolar|usd|us\$|euro|€)")
_REAL_NOMINAL_RE = re.compile(
    r"\b(real(es)?|nominal(es)?|inflaci[oó]n|constantes?|corrientes?|poder adquisitivo|deflact)"
)


def _is_identifier(name: str) -> bool:
    """Columnas cuyos valores identifican la fila (Año, Mes…): su unidad no afecta ningún cálculo.

    Una columna *llamada* "2023" (tabla ancha) no es identificadora: contiene los valores.
    """
    return normalize(name) in _IDENTIFIER_COLUMNS


def check_units(
    sub: SubQuestion, cov: SubquestionCoverage, tables: list[Candidate]
) -> SubquestionCoverage:
    """FR-024b (BR-014): la subpregunta deja de estar cubierta si una columna usada
    (a) tiene unidad "desconocida" (salvo columnas identificadoras como Año o Mes), o
    (b) es un monto con `value_type = unknown` y la pregunta depende de nominal vs. real
        (menciona real, nominal, inflación, constantes, corrientes, poder adquisitivo).
    No aplica si el LLM justificó en `ambiguity_ok` que la ambigüedad no cambia el resultado.
    """
    if not cov.covered or cov.ambiguity_ok.strip():
        return cov
    used = set(cov.columns_used)
    asks_real_nominal = bool(_REAL_NOMINAL_RE.search(normalize(sub.text)))
    ambiguous: list[str] = []
    for t in tables:
        for col in t.metadata.columns:
            if col.name not in used or col.dtype != "float64" or _is_identifier(col.name):
                continue
            unit = col.unit.strip().lower()
            if unit == UNKNOWN_UNIT:
                ambiguous.append(f"«{col.name}» de «{t.metadata.name}» (unidad desconocida)")
            elif (
                col.value_type == "unknown"
                and _MONEY_RE.search(normalize(unit))
                and asks_real_nominal
            ):
                ambiguous.append(
                    f"«{col.name}» de «{t.metadata.name}» (el documento no indica si los "
                    "montos son nominales o reales)"
                )
    if not ambiguous:
        return cov
    return cov.model_copy(
        update={
            "covered": False,
            "missing": "El significado o la unidad de una columna necesaria no es claro: "
            + "; ".join(ambiguous),
        }
    )


_REFERENCE_RE = re.compile(
    r"\b(promedio|media)s? (provincial|nacional|regional|general|del pais|de la provincia"
    r"|de la region|de la nacion|total)\b"
)
_EXPLICIT_CALC_RE = re.compile(
    r"\b(ponderad[oa]|promedio simple|calculad[oa]|promedio de l[oa]s)\b"
)
# Filas que informan un valor de referencia ("Total", "Promedio", "Provincia", "País"…) y
# columnas "Promedio"/"Media"/"Total".
_REFERENCE_ROW_RE = re.compile(
    r"^(total|promedio|media)\b|^(provincia|toda la provincia|nacional|pais|total pais|argentina)$"
)
_REFERENCE_COLUMN_RE = re.compile(r"\b(promedio|media|total)\b")


def check_reference_value(
    sub: SubQuestion, cov: SubquestionCoverage, tables: list[Candidate]
) -> SubquestionCoverage:
    """FR-024c (BR-013): si la subpregunta compara contra un valor de referencia ("promedio
    provincial", "media nacional"…), alguna tabla usada tiene que informarlo como fila o columna
    (Promedio, Total, Provincia…). No se acepta calcularlo con las filas, salvo que la pregunta
    diga cómo (ponderado, promedio simple, promedio de los departamentos…)."""
    if not cov.covered:
        return cov
    text = normalize(sub.text)
    match = _REFERENCE_RE.search(text)
    if match is None or _EXPLICIT_CALC_RE.search(text):
        return cov
    rows = [normalize(h) for t in tables for h in t.metadata.row_headers]
    columns = [normalize(c.name) for t in tables for c in t.metadata.columns]
    if any(_REFERENCE_ROW_RE.search(r) for r in rows) or any(
        _REFERENCE_COLUMN_RE.search(c) for c in columns
    ):
        return cov
    return cov.model_copy(
        update={
            "covered": False,
            "missing": f"Ninguna tabla informa el {match.group(0)}; no se reemplaza por un "
            "promedio calculado con las filas de la tabla",
        }
    )


def apply_deterministic_checks(
    subquestions: list[SubQuestion],
    coverage: list[SubquestionCoverage],
    candidates: list[Candidate],
) -> list[SubquestionCoverage]:
    """Aplica FR-024, FR-024b y FR-024c a la cobertura que propuso el LLM.

    También descarta `table_id` que no estén entre las candidatas y completa subpreguntas que el
    LLM no devolvió (como no cubiertas).
    """
    by_id = {c.table_id: c for c in candidates}
    by_sub = {c.subquestion_id: c for c in coverage}
    result: list[SubquestionCoverage] = []
    for sub in subquestions:
        cov = by_sub.get(sub.id) or SubquestionCoverage(
            subquestion_id=sub.id, covered=False, table_ids=[], columns_used=[],
            missing="No se encontró una tabla que la responda", related_table="",
        )  # fmt: skip
        known = [t for t in cov.table_ids if t in by_id]
        cov = cov.model_copy(update={"table_ids": known})
        if cov.covered and not known:
            cov = cov.model_copy(
                update={"covered": False, "missing": "No hay una tabla indexada con estos datos"}
            )
        tables = [by_id[t] for t in known]
        cov = check_periods_and_entities(sub, cov, tables)
        cov = check_units(sub, cov, tables)
        cov = check_reference_value(sub, cov, tables)
        result.append(cov)
    return result
