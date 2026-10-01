"""Unión de tablas que continúan en la página siguiente (FR-007)."""

from __future__ import annotations

import re
from dataclasses import replace

from agents.ingestion.extract import CAPTION_RE, RawTable, flatten_header
from agents.ingestion.pdf_loader import LoadedPdf

_END_MARK_RE = re.compile(r"^\s*(fuente|nota)s?\b", re.IGNORECASE)


def _has_caption_above(table: RawTable, loaded: LoadedPdf) -> bool:
    page = loaded.page(table.page)
    return any(b.y1 <= table.bbox[1] + 1 and CAPTION_RE.match(b.text) for b in page.blocks)


def _has_end_mark_below(table: RawTable, loaded: LoadedPdf) -> bool:
    page = loaded.page(table.pages[-1])
    return any(b.y0 >= table.last_bbox[3] - 1 and _END_MARK_RE.match(b.text) for b in page.blocks)


def is_continuation(prev: RawTable, nxt: RawTable, loaded: LoadedPdf) -> bool:
    """`nxt` continúa a `prev` si empieza en la página siguiente con la misma cantidad de
    columnas, repite el encabezado (o no tiene), no tiene epígrafe propio y `prev` no cierra
    con una "Fuente"/"Nota".
    """
    if nxt.page != prev.pages[-1] + 1 or nxt.n_cols != prev.n_cols:
        return False
    same_header = flatten_header(nxt.header_rows, nxt.n_cols) == prev.columns
    if nxt.header_rows and not same_header:
        return False
    return not _has_caption_above(nxt, loaded) and not _has_end_mark_below(prev, loaded)


def merge_continuations(tables: list[RawTable], loaded: LoadedPdf) -> list[RawTable]:
    """Une cada tabla con su continuación (si la hay) en una sola tabla lógica.

    `tables` debe venir en orden de lectura (como lo devuelve `extract_tables`). Solo se
    considera la última tabla de una página y la primera de la siguiente.
    """
    ordered = sorted(tables, key=lambda t: (t.page, t.bbox[1], t.bbox[0]))
    merged: list[RawTable] = []
    for table in ordered:
        if merged:
            prev = merged[-1]
            first_on_page = all(t.page != table.page or t is table or t.bbox[1] > table.bbox[1]
                                for t in ordered)  # fmt: skip
            last_on_prev_page = all(t.page != prev.pages[-1] or t.bbox[1] <= prev.last_bbox[1]
                                    for t in ordered if t is not prev)  # fmt: skip
            if first_on_page and last_on_prev_page and is_continuation(prev, table, loaded):
                merged[-1] = replace(
                    prev,
                    pages=[*prev.pages, table.page],
                    last_bbox=table.last_bbox,
                    rows=[*prev.rows, *table.rows],
                )
                continue
        merged.append(table)
    return merged
