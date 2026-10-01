"""Normalización de celdas: faltantes, números como texto y convenciones (FR-005, FR-006)."""

from __future__ import annotations

import math
import re

import pandas as pd

from agents.ingestion.extract import ExtractionWarning, RawTable, clean_cell
from agents.ingestion.pdf_loader import LoadedPdf

MISSING_MARKERS = {"", "—", "–", "s/d", "s/d.", "n/d", "...", "…", "///", ".", "nd", "sd"}
DASHES = {"-", "−"}
NUMERIC_COLUMN_THRESHOLD = 0.80

_COMMA_FORMAT = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?$")
_DOT_FORMAT = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")


def _strip(text: str) -> tuple[str, bool, bool]:
    """Quita moneda, %, marcas y signo. Devuelve (cuerpo, negativo, tenía_asterisco)."""
    t = text.replace(" ", " ")
    starred = "*" in t
    for token in ("US$", "U$S", "$", "€", "%", "*"):
        t = t.replace(token, "")
    t = t.replace(" ", "")
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative, t = True, t[1:-1]
    if t[:1] in {"-", "−"}:
        negative, t = (not negative), t[1:]
    return t, negative, starred


def parse_number(text: str, decimal_comma: bool) -> float | None:
    """Convierte `"1.234,5"`, `"(1.500)"`, `"12,5 %"`, `"$ 3.000"`, `"1.234*"` a float.

    `decimal_comma=True` interpreta `1.234,5`; `False` interpreta `1,234.5`. Devuelve None si
    el texto no es un número en ese formato.
    """
    body, negative, _ = _strip(clean_cell(text))
    if not body:
        return None
    if decimal_comma:
        if not _COMMA_FORMAT.match(body):
            return None
        value = float(body.replace(".", "").replace(",", "."))
    else:
        if not _DOT_FORMAT.match(body):
            return None
        value = float(body.replace(",", ""))
    return -value if negative else value


def _is_missing(text: str) -> bool:
    return text.lower() in MISSING_MARKERS


def _choose_format(values: list[str], doc_decimal_comma: bool) -> bool:
    """Elige el formato que convierte más celdas; si empatan, el mayoritario del documento."""
    comma = sum(parse_number(v, True) is not None for v in values)
    dot = sum(parse_number(v, False) is not None for v in values)
    if comma != dot:
        return comma > dot
    return doc_decimal_comma


def normalize_table(
    table: RawTable, loaded: LoadedPdf
) -> tuple[pd.DataFrame, list[str], list[ExtractionWarning]]:
    """Arma el DataFrame de una tabla y convierte a número las columnas numéricas.

    Devuelve (DataFrame, notas para los metadatos, avisos de celdas no convertidas).
    """
    columns = table.columns
    width = len(columns)
    rows = [[*r, *([""] * (width - len(r)))][:width] for r in table.rows]
    raw = pd.DataFrame(rows, columns=columns, dtype=object)

    notes: list[str] = []
    warnings: list[ExtractionWarning] = []
    dash_as_zero = dash_as_missing = starred = False
    out = pd.DataFrame(index=raw.index)

    for col in columns:
        texts = [clean_cell(v) for v in raw[col]]
        candidates = [t for t in texts if not _is_missing(t) and t not in DASHES]
        decimal_comma = _choose_format(candidates, loaded.decimal_comma)
        parsed = [parse_number(t, decimal_comma) for t in candidates]
        ok = sum(p is not None for p in parsed)
        is_numeric = bool(candidates) and ok / len(candidates) >= NUMERIC_COLUMN_THRESHOLD
        if not is_numeric:
            out[col] = texts
            continue
        values: list[float] = []
        failed = 0
        for t in texts:
            if t in DASHES:
                values.append(0.0 if loaded.zero_dash else math.nan)
                dash_as_zero |= loaded.zero_dash
                dash_as_missing |= not loaded.zero_dash
            elif _is_missing(t):
                values.append(math.nan)
            else:
                number = parse_number(t, decimal_comma)
                starred |= "*" in t
                if number is None:
                    failed += 1
                    values.append(math.nan)
                else:
                    values.append(number)
        out[col] = pd.Series(values, dtype="float64")
        if failed:
            warnings.append(
                ExtractionWarning(
                    table.page,
                    "unparsed_cells",
                    f"Página {table.page}: {failed} celda(s) de la columna '{col}' no se "
                    "pudieron convertir a número y quedaron vacías",
                )
            )
    if dash_as_zero:
        notes.append(
            "El signo '-' se interpretó como cero absoluto, según los signos convencionales "
            "del documento."
        )
    if dash_as_missing:
        notes.append("El signo '-' se interpretó como dato faltante.")
    if starred:
        notes.append("Los valores marcados con '*' son provisorios; se quitó la marca.")
    return out, notes, warnings
