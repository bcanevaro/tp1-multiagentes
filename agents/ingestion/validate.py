"""Validación determinística de los metadatos del LLM (BR-001 a BR-004) y armado del resultado."""

from __future__ import annotations

import re

from agents.ingestion.schemas import (
    ColumnInfo,
    Source,
    TableAnnotation,
    TableDraft,
    TableMetadata,
)

UNKNOWN_UNIT = "desconocida"
_GENERIC_NAME_RE = re.compile(
    r"^\s*(tabla|table|cuadro)(\s+(n[°º.]?\s*)?[\dIVXLC]+)?\s*\.?\s*$", re.IGNORECASE
)
# Fin de oración: . ! ? seguido de espacio y mayúscula/apertura (no corta "12.5" ni "S.A. de").
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"“(0-9])")


# BR-004b: palabras que afirman nominal/real y las que las respaldan en el documento.
_NOMINAL_REAL_RE = re.compile(r"\b(corrientes?|constantes?|nominal(?:es)?|real(?:es)?)\b", re.I)
_SUPPORT = {
    "nominal": ("corriente", "nominal"),
    "real": ("constante", "real", "deflactad"),
}


def _stem(word: str) -> str:
    w = word.lower()
    if w.startswith(("corriente", "nominal")):
        return "nominal"
    return "real"


def _evidence_text(draft: TableDraft) -> str:
    c = draft.context
    parts = [c.caption, c.section_title, c.paragraph_before, c.paragraph_after, c.footnotes]
    return " ".join([*parts, *draft.columns]).lower()


def _supported(kind: str, evidence: str) -> bool:
    return any(re.search(rf"\b{w}", evidence) for w in _SUPPORT[kind])


def count_sentences(text: str) -> int:
    parts = [p for p in _SENTENCE_SPLIT_RE.split(text.strip()) if p.strip()]
    return len(parts)


def validate_annotation(annotation: TableAnnotation, draft: TableDraft) -> list[str]:
    """Devuelve la lista de errores (vacía si los metadatos son válidos)."""
    errors: list[str] = []

    # BR-001: una entrada por columna, mismo nombre exacto y mismo orden.
    names = [c.name for c in annotation.columns]
    if len(names) != draft.n_cols:
        errors.append(
            f"BR-001: hay {len(names)} columnas en los metadatos pero la tabla tiene "
            f"{draft.n_cols}; se esperaban exactamente: {draft.columns}"
        )
    else:
        wrong = [
            (i, got, exp)
            for i, (got, exp) in enumerate(zip(names, draft.columns, strict=True))
            if got != exp
        ]
        for i, got, exp in wrong:
            errors.append(f"BR-001: la columna {i + 1} se llama {exp!r}, no {got!r}")

    # BR-002: la columna de encabezados de fila existe y es de texto.
    rhc = annotation.row_header_column
    if rhc is not None and rhc not in draft.text_columns():
        errors.append(
            f"BR-002: row_header_column={rhc!r} no es una columna de texto de la tabla; "
            f"opciones válidas: {draft.text_columns()} o null"
        )

    # BR-003: nombre no genérico y descripción de 2 a 4 oraciones.
    if len(annotation.name.strip()) < 3 or _GENERIC_NAME_RE.match(annotation.name):
        errors.append(f"BR-003: el nombre {annotation.name!r} es demasiado genérico")
    sentences = count_sentences(annotation.description)
    if not 2 <= sentences <= 4:
        errors.append(f"BR-003: la descripción tiene {sentences} oración(es); debe tener de 2 a 4")

    # BR-004: toda columna numérica tiene unidad (puede ser "desconocida").
    numeric = set(draft.numeric_columns())
    for col in annotation.columns:
        if col.name in numeric and not col.unit.strip():
            errors.append(
                f"BR-004: la columna numérica {col.name!r} no tiene unidad "
                f"(usar {UNKNOWN_UNIT!r} si no se puede deducir)"
            )
    # BR-004b: nominal/real solo si el documento lo respalda.
    evidence = _evidence_text(draft)
    for col in annotation.columns:
        if col.value_type in _SUPPORT and not _supported(col.value_type, evidence):
            errors.append(
                f"BR-004b: la columna {col.name!r} está marcada como {col.value_type!r} pero el "
                "documento no lo indica; usá 'unknown'"
            )
    claimed = {_stem(m.group(1)) for m in _NOMINAL_REAL_RE.finditer(annotation.description)}
    for kind in sorted(claimed):
        if not _supported(kind, evidence):
            errors.append(
                f"BR-004b: la descripción afirma que los valores son {kind}es "
                "(corrientes/constantes) pero el documento no lo dice; quitá esa afirmación"
            )
    return errors


def build_metadata(
    annotation: TableAnnotation, draft: TableDraft, *, table_id: str, doc_id: str, pdf_name: str
) -> TableMetadata:
    """Combina la anotación (ya validada) con los campos que completa el sistema."""
    dtypes = dict(zip(draft.columns, draft.dtypes, strict=True))
    columns = [
        ColumnInfo(
            name=c.name,
            description=c.description,
            dtype=dtypes[c.name],
            unit=c.unit.strip() or ("" if dtypes[c.name] == "str" else UNKNOWN_UNIT),
            scale=c.scale,
            value_type=c.value_type,
        )
        for c in annotation.columns
    ]
    row_headers: list[str] = []
    if annotation.row_header_column is not None:
        i = draft.columns.index(annotation.row_header_column)
        row_headers = [str(r[i]) for r in draft.rows if r[i] not in (None, "")]
    notes = " ".join(part for part in [annotation.notes.strip(), *draft.extraction_notes] if part)
    return TableMetadata(
        table_id=table_id,
        doc_id=doc_id,
        name=annotation.name.strip(),
        description=annotation.description.strip(),
        columns=columns,
        row_header_column=annotation.row_header_column,
        row_headers=row_headers,
        periods_covered=annotation.periods_covered,
        entities_covered=annotation.entities_covered,
        notes=notes,
        source=Source(
            pdf_name=pdf_name,
            doc_id=doc_id,
            pages=draft.pages,
            section_title=draft.context.section_title,
        ),
        n_rows=draft.n_rows,
        n_cols=draft.n_cols,
        caption=draft.context.caption,
    )


def table_id_for(doc_id: str, index: int) -> str:
    """BR-005: `{doc_id}-t{NN}` con NN el orden de la tabla lógica (01, 02, …)."""
    return f"{doc_id}-t{index + 1:02d}"
