"""Recolección del contexto de cada tabla: epígrafe, párrafos, sección y notas (FR-009)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agents.ingestion.extract import CAPTION_RE, RawTable
from agents.ingestion.pdf_loader import LoadedPdf, TextBlock

_FOOTNOTE_RE = re.compile(r"^\s*(fuente|nota|notas|\(\d+\)|\*|ref\.)", re.IGNORECASE)
SECTION_MIN_DELTA = 1.5  # puntos por encima del tamaño de letra del cuerpo
SECTION_MAX_LEN = 140


@dataclass(frozen=True)
class TableContext:
    caption: str = ""
    paragraph_before: str = ""
    paragraph_after: str = ""
    section_title: str = ""
    footnotes: str = ""

    def as_prompt_text(self) -> str:
        parts = [
            ("Título de la sección", self.section_title),
            ("Epígrafe", self.caption),
            ("Texto anterior", self.paragraph_before),
            ("Texto posterior", self.paragraph_after),
            ("Notas al pie", self.footnotes),
        ]
        return "\n".join(f"{k}: {v}" for k, v in parts if v)


def _inside(block: TextBlock, bbox: tuple[float, float, float, float]) -> bool:
    cx, cy = (block.x0 + block.x1) / 2, (block.y0 + block.y1) / 2
    return bbox[0] - 2 <= cx <= bbox[2] + 2 and bbox[1] - 2 <= cy <= bbox[3] + 2


def _is_section(block: TextBlock, body: float) -> bool:
    return (
        block.font_size >= body + SECTION_MIN_DELTA
        and len(block.text) <= SECTION_MAX_LEN
        and not CAPTION_RE.match(block.text)
    )


def _table_regions(
    table: RawTable, loaded: LoadedPdf, others: list[RawTable]
) -> dict[int, list[tuple[float, float, float, float]]]:
    regions: dict[int, list[tuple[float, float, float, float]]] = {}
    for t in [table, *others]:
        regions.setdefault(t.pages[0], []).append(t.bbox)
        if len(t.pages) > 1:
            for p in t.pages[1:-1]:
                page = loaded.page(p)
                regions.setdefault(p, []).append((0, 0, page.width, page.height))
            regions.setdefault(t.pages[-1], []).append(t.last_bbox)
    return regions


def collect_context(
    table: RawTable, loaded: LoadedPdf, all_tables: list[RawTable] | None = None
) -> TableContext:
    """Busca el texto alrededor de la tabla.

    - epígrafe: bloques justo encima de la tabla, desde el último que empieza con
      "Cuadro/Tabla N" (o el último bloque en negrita) hasta la tabla;
    - párrafo anterior: el bloque de cuerpo anterior al epígrafe;
    - título de sección: el último bloque con letra más grande que el cuerpo antes de la tabla
      (buscando también en páginas anteriores);
    - notas al pie: bloques debajo de la tabla que empiezan con "Fuente", "Nota", "(1)", "*";
    - párrafo posterior: el primer bloque de cuerpo después de las notas en la misma página, si
      no aparece antes un título o un epígrafe.
    """
    body = loaded.body_font_size
    regions = _table_regions(table, loaded, [t for t in (all_tables or []) if t is not table])

    def free(blocks: list[TextBlock], page: int) -> list[TextBlock]:
        return [b for b in blocks if not any(_inside(b, r) for r in regions.get(page, []))]

    first = loaded.page(table.page)
    above = [b for b in free(first.blocks, first.number) if b.y1 <= table.bbox[1] + 2]
    above.sort(key=lambda b: (b.y0, b.x0))

    caption_blocks: list[TextBlock] = []
    start = next(
        (i for i in range(len(above) - 1, -1, -1) if CAPTION_RE.match(above[i].text)), None
    )
    if start is not None and table.bbox[1] - above[start].y0 < 120:
        caption_blocks = above[start:]
    elif above and above[-1].bold and not _is_section(above[-1], body):
        caption_blocks = [above[-1]]
    caption = " ".join(b.text for b in caption_blocks)
    before = [b for b in above if b not in caption_blocks]

    paragraph_before = ""
    for b in reversed(before):
        if _is_section(b, body):
            break
        if not CAPTION_RE.match(b.text):
            paragraph_before = b.text
            break

    section_title = ""
    for b in reversed(before):
        if _is_section(b, body):
            section_title = b.text
            break
    if not section_title:
        for p in range(table.page - 1, 0, -1):
            candidates = [b for b in loaded.page(p).blocks if _is_section(b, body)]
            if candidates:
                section_title = max(candidates, key=lambda b: (b.y0, b.x0)).text
                break

    last = loaded.page(table.pages[-1])
    below = [b for b in free(last.blocks, last.number) if b.y0 >= table.last_bbox[3] - 2]
    below.sort(key=lambda b: (b.y0, b.x0))
    footnotes: list[str] = []
    paragraph_after = ""
    for b in below:
        if _FOOTNOTE_RE.match(b.text):
            footnotes.append(b.text)
            continue
        if b.font_size < body - 0.5 and footnotes:
            footnotes.append(b.text)  # continuación de una nota en letra chica
            continue
        if not _is_section(b, body) and not CAPTION_RE.match(b.text) and not b.bold:
            paragraph_after = b.text
        break
    return TableContext(
        caption=caption,
        paragraph_before=paragraph_before,
        paragraph_after=paragraph_after,
        section_title=section_title,
        footnotes=" ".join(footnotes),
    )
