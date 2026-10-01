"""Prompts del enriquecimiento con LLM (FR-010, FR-012)."""

from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agents.ingestion.schemas import TableDraft, preview_markdown

MAX_PROMPT_ROWS = 30

SYSTEM_PROMPT = """\
Sos un analista de datos que documenta tablas extraídas de informes en PDF.
Recibís una tabla (sus columnas exactas, sus tipos y sus filas) y el texto que la rodea en el \
documento (epígrafe, título de sección, párrafos y notas al pie). Tu tarea es completar sus \
metadatos para que después se pueda encontrar la tabla y calcular con ella.

Reglas:
- Basate SOLO en la tabla y su contexto. No agregues datos ni supuestos externos.
- `columns`: exactamente una entrada por columna, en el mismo orden, con el nombre copiado \
carácter por carácter (incluidos los " | ").
- `name`: corto y descriptivo (p. ej. "Exportaciones por provincia, agosto 2026"). Nunca solo \
"Cuadro 3" o "Tabla".
- `description`: de 2 a 4 oraciones completas que digan qué mide la tabla, en qué unidades, \
para qué período y con qué alcance (país, provincia, sector).
- `unit`: tomala del epígrafe, los encabezados o las notas ("En millones de pesos corrientes" \
→ "millones de pesos"). Si no se puede deducir, escribí "desconocida". En columnas de texto \
dejala vacía.
- `value_type`: "nominal" o "real" solo si el documento lo dice ("pesos corrientes" = nominal, \
"pesos constantes" = real). Si es un monto y no se aclara, "unknown".
- No uses las palabras "corrientes", "constantes", "nominal" ni "real" en la descripción si no \
aparecen en el documento. Si no se aclara, escribí "el documento no indica si los montos están \
ajustados por inflación".
- `row_header_column`: la columna de texto que nombra cada fila (p. ej. "Departamento"), o null.
- `periods_covered`: todos los períodos que aparecen (años, meses, "acumulado hasta agosto").
- `entities_covered`: las entidades que aparecen como filas o columnas (regiones, productos…).
- `notes`: resumí notas al pie, fuentes y aclaraciones metodológicas relevantes.
"""


def build_messages(
    draft: TableDraft, pdf_name: str, previous_errors: list[str] | None = None
) -> list[BaseMessage]:
    """Mensajes para anotar una tabla; si hubo errores de validación, se incluyen (FR-012)."""
    df = draft.to_dataframe()
    columns = "\n".join(
        f"- {name!r} (tipo: {dtype})"
        for name, dtype in zip(draft.columns, draft.dtypes, strict=True)
    )
    shown = min(draft.n_rows, MAX_PROMPT_ROWS)
    parts = [
        f"Documento: {pdf_name} — página(s) {', '.join(map(str, draft.pages))}",
        "",
        "## Contexto",
        _context_text(draft) or "(sin texto alrededor)",
        "",
        f"## Columnas ({draft.n_cols})",
        columns,
        "",
        f"## Filas ({shown} de {draft.n_rows})",
        preview_markdown(df, max_rows=MAX_PROMPT_ROWS, max_cell=60),
    ]
    if draft.extraction_notes:
        parts += ["", "## Notas de la extracción", *draft.extraction_notes]
    if previous_errors:
        parts += [
            "",
            "## Corregí estos errores de tu respuesta anterior",
            *[f"- {e}" for e in previous_errors],
        ]
    return [SystemMessage(SYSTEM_PROMPT), HumanMessage("\n".join(parts))]


def _context_text(draft: TableDraft) -> str:
    c = draft.context
    items = [
        ("Título de la sección", c.section_title),
        ("Epígrafe", c.caption),
        ("Texto anterior", c.paragraph_before),
        ("Texto posterior", c.paragraph_after),
        ("Notas al pie", c.footnotes),
    ]
    return "\n".join(f"{k}: {v}" for k, v in items if v)
