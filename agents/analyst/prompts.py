"""Prompts del Agente Analista (FR-020, FR-023, FR-026, FR-032)."""

from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agents.analyst.schemas import Candidate, QueryPlan, SubQuestion
from agents.ingestion.schemas import TableMetadata
from services.sandbox.ast_guard import ALLOWED_MODULES

MAX_ROW_HEADERS_IN_PROMPT = 60

# --------------------------------------------------------------------------------------
# 1. Entender la consulta
# --------------------------------------------------------------------------------------

PLAN_SYSTEM = """\
Descomponés preguntas sobre tablas estadísticas en subpreguntas calculables.

- Cada subpregunta pide un resultado (un número o un número por categoría). Si la pregunta \
tiene varias partes ("¿qué región tuvo más desempleo y por cuánto superó al promedio?"), \
separalas: q1 = qué región y su valor; q2 = la diferencia con el promedio.
- `entities`: SOLO nombres propios que tienen que aparecer como fila o columna de los datos \
(regiones, provincias, productos, sectores con nombre). No pongas términos genéricos ni el \
alcance del documento ("la provincia", "el país", "departamentos", "sector público").
- `periods`: SOLO períodos concretos que la subpregunta nombra ("2023", "marzo de 2022"). Si \
dice "cada año", "todos los años" o no nombra ninguno, dejalo vacío.
- `search_queries`: de 1 a 4 búsquedas temáticas para encontrar las tablas (p. ej. "tasa de \
desempleo por departamento", "población por departamento"). Si la pregunta combina temas, una \
búsqueda por tema.
"""


def plan_messages(question: str) -> list[BaseMessage]:
    return [SystemMessage(PLAN_SYSTEM), HumanMessage(f"Pregunta: {question}")]


# --------------------------------------------------------------------------------------
# 2. Seleccionar tablas
# --------------------------------------------------------------------------------------

SELECT_SYSTEM = """\
Decidís qué tablas hacen falta para responder cada subpregunta y si los datos alcanzan. \
Solo se pueden usar los datos de las tablas candidatas: nada de conocimiento general, \
estimaciones ni fuentes externas.

Para cada subpregunta devolvé `covered`, `table_ids` (las necesarias, pueden ser varias), \
`columns_used` (nombres exactos), y si no está cubierta, `missing` (qué falta) y \
`related_table` (qué contiene la tabla más parecida, p. ej. "La tabla Ingresos por año cubre \
2019-2023").

Una subpregunta NO está cubierta cuando:
1. Falta un período o una entidad pedidos (no se interpola, no se extrapola, no se usa el año \
más cercano).
2. Hace falta una conversión que requiere datos externos: tipo de cambio entre monedas, ajuste \
por inflación (valores reales), o pasar a per cápita sin una tabla de población. Sí se permiten \
y no impiden la cobertura: cambio de escala (miles → millones), porcentaje ↔ fracción, y sumar \
los 12 meses de un año cuando están todos.
3. Falta un valor de comparación (p. ej. "el promedio nacional" o "provincial" cuando ninguna \
tabla lo informa como fila o columna, del tipo "Total" o "Promedio"). NO lo reemplaces por un \
promedio calculado de las filas (el promedio simple de departamentos no es el promedio \
provincial: no pondera por población), salvo que la pregunta diga explícitamente cómo \
calcularlo (p. ej. "promedio ponderado por población"). En ese caso la subpregunta que compara \
NO está cubierta, aunque otras partes sí lo estén.
4. El significado o la unidad de una columna necesaria no es claro y la elección cambia el \
resultado (p. ej. no se sabe si un monto es nominal o real y la pregunta pide valores reales).

Si una columna usada tiene unidad "desconocida" o tipo "unknown" pero eso no cambia el \
resultado (p. ej. una proporción entre valores de la misma columna), explicalo en \
`ambiguity_ok`.
"""


def describe_table(meta: TableMetadata, preview: str) -> str:
    columns = "\n".join(
        f"    - {c.name!r} ({'texto' if c.dtype == 'str' else 'número'}; unidad: "
        f"{c.unit or '-'}; escala: {c.scale}; tipo: {c.value_type}) — {c.description}"
        for c in meta.columns
    )
    rows = meta.row_headers[:MAX_ROW_HEADERS_IN_PROMPT]
    more = f" … (+{len(meta.row_headers) - len(rows)})" if len(meta.row_headers) > len(rows) else ""
    parts = [
        f"table_id: {meta.table_id}",
        f"Nombre: {meta.name}",
        f"Fuente: {meta.source.pdf_name}, página(s) {', '.join(map(str, meta.source.pages))}",
        f"Descripción: {meta.description}",
        f"Filas: {meta.n_rows}. Columnas:\n{columns}",
    ]
    if rows:
        parts.append(f"Encabezados de fila ({meta.row_header_column}): {', '.join(rows)}{more}")
    if meta.periods_covered:
        parts.append(f"Períodos: {', '.join(meta.periods_covered)}")
    if meta.entities_covered:
        parts.append(f"Entidades: {', '.join(meta.entities_covered)}")
    if meta.notes:
        parts.append(f"Notas: {meta.notes}")
    parts.append(f"Primeras filas:\n{preview}")
    return "\n".join(parts)


def _subquestions_text(subs: list[SubQuestion]) -> str:
    return "\n".join(
        f"- {s.id}: {s.text} (métricas: {', '.join(s.metrics) or '-'}; entidades: "
        f"{', '.join(s.entities) or '-'}; períodos: {', '.join(s.periods) or '-'}; "
        f"operación: {s.operation})"
        for s in subs
    )


def select_messages(
    question: str, plan: QueryPlan, candidates: list[Candidate]
) -> list[BaseMessage]:
    tables = "\n\n".join(
        f"### Candidata {i}\n{describe_table(c.metadata, c.preview_markdown)}"
        for i, c in enumerate(candidates, start=1)
    )
    human = (
        f"Pregunta: {question}\n\nSubpreguntas:\n{_subquestions_text(plan.subquestions)}\n\n"
        f"## Tablas candidatas\n\n{tables}"
    )
    return [SystemMessage(SELECT_SYSTEM), HumanMessage(human)]


# --------------------------------------------------------------------------------------
# 3. Generar código
# --------------------------------------------------------------------------------------

CODE_SYSTEM = f"""\
Escribís un programa Python que calcula la respuesta a partir de tablas ya cargadas en pandas.

Entorno:
- Ya existen `pd` (pandas) y `load_table(table_id)`, que devuelve la tabla como DataFrame. \
Usá SIEMPRE `load_table("<table_id>")`; no hay archivos ni rutas.
- Solo podés importar: {", ".join(sorted(ALLOWED_MODULES))}. No uses open, eval, exec, \
getattr, exit, quit, os, sys ni métodos que lean o escriban archivos (read_csv, to_csv…). Si \
falta un dato, no cortes el programa: registralo en "missing" y seguí hasta imprimir el JSON.
- Las columnas numéricas ya son float (sin "$", "%" ni separadores). Los porcentajes están en \
escala 0-100. Los faltantes son NaN. Usá los nombres de columna EXACTOS que se te dan.

El programa:
1. Calcula SOLO las subpreguntas listadas para calcular, solo con los datos de las tablas. Las \
partes de la pregunta que se te indiquen como "NO calcular" no aparecen en ningún resultado, \
tampoco como un valor extra dentro de otra subpregunta.
2. Si durante el cálculo falta un dato (un año o una fila que no está), NO lo estimes: \
agregalo a "missing" con el motivo. No calcules valores de referencia que la tabla no trae \
(p. ej. un promedio provincial a partir de los departamentos).
3. Termina imprimiendo, como ÚLTIMA línea, un único JSON:
   print(json.dumps({{"results": [...], "missing": [...], "conversions": [...]}},
                    ensure_ascii=False))
   - results: [{{"subquestion_id": "q1", "value": <float>, "unit": "...", "label": "..."}}]. \
Para un valor por categoría: "value": [{{"label": "2019", "value": <float>}}, ...]. Si la \
respuesta es una categoría (p. ej. qué departamento), "value" es su número y la categoría va \
en "label": [{{"label": "Norte", "value": 9.8}}]. "value" nunca es texto. Convertí con \
float(); nunca NaN.
   - Proporciones, participaciones, variaciones y tasas: en porcentaje (0-100) con \
"unit": "%", salvo que la subpregunta pida otra unidad.
   - missing: [{{"subquestion_id": "q2", "reason": "..."}}]
   - conversions: textos que describan las conversiones aplicadas (p. ej. "miles de toneladas \
→ toneladas"), o [] si no hubo.
Podés imprimir resultados intermedios antes, pero la última línea tiene que ser el JSON.
"""


def code_messages(
    subquestions: list[SubQuestion],
    tables: list[tuple[TableMetadata, str]],
    *,
    excluded: list[tuple[SubQuestion, str]] | None = None,
    previous_code: str | None = None,
    previous_error: str | None = None,
) -> list[BaseMessage]:
    """No incluye la pregunta original: solo las subpreguntas cubiertas (autocontenidas) y, aparte,
    las que NO hay que calcular, para que el código no responda partes sin datos (BR-013)."""
    described = "\n\n".join(
        f"### {meta.table_id}\n{describe_table(meta, preview)}" for meta, preview in tables
    )
    parts = [f"Subpreguntas a calcular:\n{_subquestions_text(subquestions)}"]
    if excluded:
        lines = "\n".join(f"- {s.id}: {s.text} — motivo: {reason}" for s, reason in excluded)
        parts += [
            "",
            "Partes que NO hay que calcular (no hay datos para responderlas; no incluyas ningún "
            f"valor sobre ellas):\n{lines}",
        ]
    parts += ["", f"## Tablas disponibles\n\n{described}"]
    if previous_code and previous_error:
        parts += [
            "",
            "## Tu programa anterior falló. Corregilo.",
            f"Código anterior:\n```python\n{previous_code}\n```",
            f"Error:\n{previous_error}",
        ]
    return [SystemMessage(CODE_SYSTEM), HumanMessage("\n".join(parts))]


# --------------------------------------------------------------------------------------
# 4. Redactar la respuesta
# --------------------------------------------------------------------------------------

ANSWER_SYSTEM = """\
Redactás la respuesta final para el usuario, en español, breve y clara.

- Usá SOLO los resultados que se te dan, con los números EXACTAMENTE como están escritos \
(ya están formateados). No agregues otros números ni hagas cuentas.
- Mencioná qué tablas y páginas se usaron y explicá el cálculo en una o dos oraciones, \
incluidas las conversiones aplicadas.
- Si el estado es "partial", indicá claramente qué parte no se pudo responder y qué dato falta, \
sin dar ningún número ni estimación para esa parte.
- No inventes información que no esté en lo que se te pasa.
"""


def answer_messages(
    question: str,
    status: str,
    results_text: str,
    tables_text: str,
    explanation: str,
    conversions: list[str],
    missing_text: str,
) -> list[BaseMessage]:
    parts = [
        f"Pregunta: {question}",
        f"Estado: {status}",
        f"Resultados:\n{results_text}",
        f"Tablas usadas:\n{tables_text}",
        f"Cálculo: {explanation or '-'}",
        f"Conversiones: {'; '.join(conversions) if conversions else 'ninguna'}",
    ]
    if missing_text:
        parts.append(f"Partes que no se pudieron responder:\n{missing_text}")
    return [SystemMessage(ANSWER_SYSTEM), HumanMessage("\n\n".join(parts))]
