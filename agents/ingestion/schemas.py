"""Modelos de datos de la Ingesta (spec §7.2).

- `TableAnnotation`: lo que se le pide al LLM (salida estructurada).
- `TableMetadata`: los metadatos finales, que combinan lo del LLM con lo que completa el sistema.
- `TableDraft`: una tabla extraída y normalizada, serializable a JSON para viajar en el estado
  del grafo (sin DataFrames).
"""

from __future__ import annotations

import math
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

Scale = Literal["unidades", "miles", "millones", "miles de millones", "desconocida"]
ValueType = Literal["nominal", "real", "porcentaje", "conteo", "indice", "texto", "unknown"]
CellValue = float | str | None

# --------------------------------------------------------------------------------------
# Salida del LLM
# --------------------------------------------------------------------------------------


class ColumnAnnotation(BaseModel):
    name: str = Field(description="Nombre EXACTO de la columna, copiado tal cual de la lista dada")
    description: str = Field(description="Qué contiene la columna, en una oración")
    unit: str = Field(
        description="Unidad de los valores (p. ej. 'millones de USD', '%', 'habitantes', "
        "'pesos'). Usar 'desconocida' si el contexto no la indica. Vacío solo en columnas de texto"
    )
    scale: Scale = Field(description="Escala de los valores numéricos")
    value_type: ValueType = Field(
        description="'nominal' o 'real' SOLO si el documento lo dice explícitamente; si no se "
        "sabe si un monto es nominal o real, 'unknown'"
    )


class TableAnnotation(BaseModel):
    """Metadatos semánticos que infiere el LLM a partir de la tabla y su contexto."""

    name: str = Field(description="Nombre corto y legible de la tabla (no 'Tabla 3' a secas)")
    description: str = Field(
        description="Entre 2 y 4 oraciones: qué mide la tabla, sus unidades, período y alcance"
    )
    columns: list[ColumnAnnotation] = Field(
        description="Una entrada por columna, en el mismo orden"
    )
    row_header_column: str | None = Field(
        description="Nombre exacto de la columna de texto que identifica cada fila "
        "(p. ej. 'Departamento'), o null si no hay"
    )
    periods_covered: list[str] = Field(
        description="Períodos presentes en la tabla, p. ej. ['2019', '2020'] o ['agosto de 2026']"
    )
    entities_covered: list[str] = Field(
        description="Entidades presentes en las filas o columnas (regiones, productos, rubros)"
    )
    notes: str = Field(description="Notas al pie y aclaraciones relevantes; vacío si no hay")


# --------------------------------------------------------------------------------------
# Metadatos finales
# --------------------------------------------------------------------------------------


class ColumnInfo(BaseModel):
    name: str
    description: str
    dtype: str  # lo completa el sistema: "float64" | "str"
    unit: str
    scale: Scale
    value_type: ValueType


class Source(BaseModel):
    pdf_name: str
    doc_id: str
    pages: list[int]
    section_title: str = ""


class TableMetadata(BaseModel):
    table_id: str
    doc_id: str
    name: str
    description: str
    columns: list[ColumnInfo]
    row_header_column: str | None
    row_headers: list[str]
    periods_covered: list[str]
    entities_covered: list[str]
    notes: str
    source: Source
    n_rows: int
    n_cols: int
    caption: str = ""


# --------------------------------------------------------------------------------------
# Tabla en tránsito por el grafo
# --------------------------------------------------------------------------------------


class TableContextData(BaseModel):
    caption: str = ""
    paragraph_before: str = ""
    paragraph_after: str = ""
    section_title: str = ""
    footnotes: str = ""


class TableDraft(BaseModel):
    """Tabla extraída y normalizada (JSON). `index` es su orden en el documento (0-based)."""

    index: int
    pages: list[int]
    strategy: str
    columns: list[str]
    dtypes: list[str]
    rows: list[list[CellValue]]
    context: TableContextData
    extraction_notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_dataframe(
        cls,
        index: int,
        pages: list[int],
        strategy: str,
        df: pd.DataFrame,
        context: TableContextData,
        notes: list[str],
    ) -> TableDraft:
        rows: list[list[CellValue]] = []
        for record in df.itertuples(index=False):
            row: list[CellValue] = []
            for value in record:
                if isinstance(value, float) and math.isnan(value):
                    row.append(None)
                elif isinstance(value, int | float):
                    row.append(float(value))
                else:
                    row.append(str(value))
            rows.append(row)
        return cls(
            index=index,
            pages=pages,
            strategy=strategy,
            columns=[str(c) for c in df.columns],
            dtypes=["float64" if str(t).startswith("float") else "str" for t in df.dtypes],
            rows=rows,
            context=context,
            extraction_notes=notes,
        )

    def to_dataframe(self) -> pd.DataFrame:
        data: dict[str, Any] = {}
        for i, (col, dtype) in enumerate(zip(self.columns, self.dtypes, strict=True)):
            values = [row[i] for row in self.rows]
            if dtype == "float64":
                data[col] = pd.Series(
                    [math.nan if v is None else float(v) for v in values], dtype="float64"
                )
            else:
                data[col] = pd.Series(["" if v is None else str(v) for v in values], dtype="str")
        return pd.DataFrame(data, columns=self.columns)

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        return len(self.columns)

    def text_columns(self) -> list[str]:
        return [c for c, t in zip(self.columns, self.dtypes, strict=True) if t == "str"]

    def numeric_columns(self) -> list[str]:
        return [c for c, t in zip(self.columns, self.dtypes, strict=True) if t == "float64"]


def preview_markdown(df: pd.DataFrame, max_rows: int = 5, max_cell: int = 40) -> str:
    """Primeras filas como tabla Markdown (para prompts y metadatos de Pinecone)."""

    def fmt(value: Any) -> str:
        if isinstance(value, float):
            return "" if math.isnan(value) else f"{value:g}"
        return str(value).replace("|", "/")[:max_cell]

    header = "| " + " | ".join(str(c).replace("|", "/") for c in df.columns) + " |"
    sep = "|" + "---|" * len(df.columns)
    rows = [
        "| " + " | ".join(fmt(v) for v in row) + " |"
        for row in df.head(max_rows).itertuples(index=False)
    ]
    return "\n".join([header, sep, *rows])
