"""Detección y extracción de tablas desde la capa de texto (FR-003, FR-004, FR-008, FR-008b).

Dos detectores:
- `lines`: `page.find_tables(strategy="lines")` de PyMuPDF, para tablas con líneas (grilla o
  separadores de fila, como los cuadros de INDEC).
- `hrules`: respaldo propio para tablas delimitadas solo por 2 o más líneas horizontales
  (arriba, debajo del encabezado y al final), que `lines` no detecta. Agrupa las palabras en
  filas por su posición vertical y en columnas según las celdas del encabezado.

Uso de diagnóstico:  uv run python -m agents.ingestion.extract <archivo.pdf>
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from agents.ingestion.pdf_loader import LoadedPdf, PageData

Cell = str | None
BBox = tuple[float, float, float, float]

CAPTION_RE = re.compile(r"^\s*(cuadro|tabla|gr[aá]fico)\s+(n[°º.]?\s*)?[\dIVXLC]+\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_NUMBER_RE = re.compile(r"^\d[\d.,]*$")
_FLAG_PREFIX_RE = re.compile(r"^(?:[*eiu]\s+)+(?=\d)")

MIN_IMAGE_AREA_RATIO = 0.10  # FR-008
MIN_FILL_RATIO = 0.50  # FR-008b
MIN_TEXT_RATIO = 0.10  # FR-008: más de 90 % de celdas vacías
MAX_HEADER_ROWS = 4
# El respaldo por líneas horizontales exige al menos una columna (fuera de la primera) con
# >= 80 % de celdas numéricas y >= 3 valores: descarta infografías con líneas decorativas.
HRULES_NUMERIC_COLUMN_RATIO = 0.80
HRULES_MIN_NUMERIC_VALUES = 3
_MISSING_TOKENS = {"", "-", "—", "–", "s/d", "n/d", "...", "…", "///", "."}


def _has_numeric_column(data: list[list[Cell]]) -> bool:
    n_cols = max((len(r) for r in data), default=0)
    for c in range(1, n_cols):
        values = [clean_cell(r[c]) for r in data if c < len(r)]
        values = [v for v in values if v.lower() not in _MISSING_TOKENS]
        numeric = sum(is_data_number(v) for v in values)
        if (
            numeric >= HRULES_MIN_NUMERIC_VALUES
            and numeric / len(values) >= HRULES_NUMERIC_COLUMN_RATIO
        ):
            return True
    return False


@dataclass(frozen=True)
class ExtractionWarning:
    page: int | None
    code: str  # image_region | page_without_text | empty_table | not_a_table | unparsed_cells
    message: str


@dataclass
class RawTable:
    """Una tabla lógica extraída, todavía con celdas como texto."""

    pages: list[int]
    bbox: BBox  # en la primera página
    last_bbox: BBox  # en la última página (igual a bbox si ocupa una sola)
    header_rows: list[list[Cell]]
    rows: list[list[str]]
    strategy: str  # "lines" | "hrules"
    n_cols: int = field(init=False)

    def __post_init__(self) -> None:
        widths = [len(r) for r in self.header_rows] + [len(r) for r in self.rows]
        self.n_cols = max(widths)

    @property
    def page(self) -> int:
        return self.pages[0]

    @property
    def columns(self) -> list[str]:
        return flatten_header(self.header_rows, self.n_cols)


# --------------------------------------------------------------------------------------
# Celdas y encabezados
# --------------------------------------------------------------------------------------


def clean_cell(value: Cell) -> str:
    return "" if value is None else " ".join(str(value).split())


def _clean_header_text(value: str) -> str:
    return _FLAG_PREFIX_RE.sub("", clean_cell(value)).strip()


def is_data_number(value: Cell) -> bool:
    """¿La celda es un valor numérico de datos? (los años sueltos no cuentan: son encabezados)."""
    text = clean_cell(value)
    for token in ("US$", "$", "€", "%", "*", " "):
        text = text.replace(token, "")
    text = text.strip("()").lstrip("-−")
    return bool(_NUMBER_RE.match(text)) and not _YEAR_RE.match(text)


def split_header(rows: list[list[Cell]]) -> tuple[list[list[Cell]], list[list[Cell]]]:
    """Separa las filas de encabezado (las primeras sin valores numéricos de datos) de los datos.

    Si la tabla no tiene ningún número, el encabezado es la primera fila. Si la primera fila
    ya tiene números, la tabla no tiene encabezado (continuación sin encabezado, FR-007).
    """
    n = 0
    while n < len(rows) and not any(is_data_number(c) for c in rows[n]):
        n += 1
    if n == len(rows) or n > MAX_HEADER_ROWS:
        n = 1 if rows else 0
    return rows[:n], rows[n:]


def flatten_header(header_rows: list[list[Cell]], n_cols: int) -> list[str]:
    """Aplana encabezados de varias filas con `" | "` (FR-004).

    Las celdas combinadas llegan como `None` y heredan el valor de la izquierda cuando
    pertenecen al mismo grupo del primer nivel, o cuando la fila tiene una sola etiqueta fuera
    de la primera columna (típicamente una unidad como "Millones de USD" que abarca todas).
    """
    if not header_rows:
        return [f"columna_{i + 1}" for i in range(n_cols)]
    grid = [[*row, *([None] * (n_cols - len(row)))] for row in header_rows]
    filled: list[list[str]] = []
    for r, row in enumerate(grid):
        sparse = sum(1 for c in row[1:] if clean_cell(c)) <= 1
        out: list[str] = []
        for c, cell in enumerate(row):
            if cell is None and c > 0:
                same_group = r == 0 or filled[0][c] == filled[0][c - 1]
                out.append(out[c - 1] if (sparse or same_group) else "")
            else:
                out.append(_clean_header_text(cell or ""))
        filled.append(out)
    names: list[str] = []
    for c in range(n_cols):
        parts: list[str] = []
        for r in range(len(filled)):
            part = filled[r][c]
            if part and (not parts or parts[-1] != part):
                parts.append(part)
        names.append(" | ".join(parts) or f"columna_{c + 1}")
    seen: dict[str, int] = {}
    unique: list[str] = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        unique.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    return unique


def _fill_ratio(rows: list[list[Cell]]) -> float:
    cells = [c for row in rows for c in row]
    return sum(1 for c in cells if clean_cell(c)) / len(cells) if cells else 0.0


def _build_table(rows: list[list[Cell]], bbox: BBox, page: int, strategy: str) -> RawTable | None:
    rows = [r for r in rows if any(clean_cell(c) for c in r)]
    if not rows:
        return None
    header, data = split_header(rows)
    return RawTable(
        pages=[page],
        bbox=bbox,
        last_bbox=bbox,
        header_rows=header,
        rows=[[clean_cell(c) for c in r] for r in data],
        strategy=strategy,
    )


def _check(rows: list[list[Cell]], page: int) -> ExtractionWarning | None:
    """Filtros de FR-008 (tabla sin texto) y FR-008b (detección que no es una tabla)."""
    n_rows = len(rows)
    n_cols = max((len(r) for r in rows), default=0)
    fill = _fill_ratio(rows)
    if n_rows and n_cols and fill < MIN_TEXT_RATIO:
        return ExtractionWarning(page, "empty_table", f"Página {page}: tabla sin texto legible")
    _, data = split_header([r for r in rows if any(clean_cell(c) for c in r)])
    if len(data) < 2 or n_cols < 2 or fill < MIN_FILL_RATIO:
        return ExtractionWarning(
            page,
            "not_a_table",
            f"Página {page}: se descartó una detección que no parece una tabla "
            f"({n_rows} filas × {n_cols} columnas, {fill:.0%} de celdas con texto)",
        )
    return None


# --------------------------------------------------------------------------------------
# Respaldo: tablas delimitadas solo por líneas horizontales
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Rule:
    x0: float
    y: float
    x1: float


def _horizontal_rules(page: pymupdf.Page) -> list[_Rule]:
    rules: list[_Rule] = []
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 1.5 and abs(p2.x - p1.x) > 100:
                    rules.append(_Rule(min(p1.x, p2.x), p1.y, max(p1.x, p2.x)))
            elif item[0] == "re":
                r = item[1]
                if r.height < 2.5 and r.width > 100:
                    rules.append(_Rule(r.x0, (r.y0 + r.y1) / 2, r.x1))
    return sorted(rules, key=lambda r: r.y)


def _rule_groups(rules: list[_Rule], max_gap: float = 250.0) -> list[list[_Rule]]:
    """Agrupa líneas con el mismo ancho (±3 pt) y separadas por menos de `max_gap`."""
    groups: list[list[_Rule]] = []
    for rule in rules:
        for g in groups:
            last = g[-1]
            same_width = abs(last.x0 - rule.x0) < 3 and abs(last.x1 - rule.x1) < 3
            if same_width and 2 < rule.y - last.y < max_gap:
                g.append(rule)
                break
        else:
            groups.append([rule])
    return [g for g in groups if len(g) >= 2]


def _word_cells(
    words: list[tuple[float, float, str]], gap: float = 6.0
) -> list[tuple[float, float, str]]:
    """Une palabras consecutivas de una línea en celdas (x0, x1, texto) según la distancia."""
    cells: list[tuple[float, float, str]] = []
    for x0, x1, text in sorted(words):
        if cells and x0 - cells[-1][1] <= gap:
            px0, _, ptext = cells[-1]
            cells[-1] = (px0, x1, f"{ptext} {text}")
        else:
            cells.append((x0, x1, text))
    return cells


def _column_segments(
    cells: list[tuple[float, float, str]], gap: float = 8.0
) -> list[tuple[float, float]]:
    """Columnas = intervalos horizontales ocupados por texto, separados por "ríos" de blanco."""
    segments: list[tuple[float, float]] = []
    for x0, x1, _ in sorted(cells):
        if segments and x0 - segments[-1][1] <= gap:
            segments[-1] = (segments[-1][0], max(segments[-1][1], x1))
        else:
            segments.append((x0, x1))
    return segments


def _segment_of(cell: tuple[float, float, str], segments: list[tuple[float, float]]) -> int:
    """Columna de una celda según su centro.

    Cada columna abarca desde el borde derecho de la anterior hasta su propio borde derecho,
    porque los números van alineados a la derecha y su encabezado puede empezar bastante antes.
    """
    center = (cell[0] + cell[1]) / 2
    for i, (_, right) in enumerate(segments):
        if center <= right:
            return i
    return len(segments) - 1


def _parse_hrule_table(
    page: pymupdf.Page, group: list[_Rule]
) -> tuple[list[list[Cell]], BBox] | None:
    """Lee una tabla delimitada por líneas horizontales.

    Las filas salen de agrupar palabras por altura; las columnas, de los espacios en blanco
    verticales entre los datos (los números suelen estar alineados a la derecha y los
    encabezados a la izquierda, así que el encabezado no sirve para ubicar las columnas).
    """
    x0, x1 = min(r.x0 for r in group), max(r.x1 for r in group)
    top, bottom = group[0].y, group[-1].y
    header_bottom = group[1].y if len(group) >= 3 else None
    words = page.get_text("words", clip=pymupdf.Rect(x0 - 2, top, x1 + 2, bottom))
    if not words:
        return None
    lines: list[tuple[float, list[tuple[float, float, str]]]] = []
    for w in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
        yc = (w[1] + w[3]) / 2
        if lines and abs(lines[-1][0] - yc) <= 3:
            lines[-1][1].append((w[0], w[2], w[4]))
        else:
            lines.append((yc, [(w[0], w[2], w[4])]))
    cell_lines = [(yc, _word_cells(ws)) for yc, ws in lines]
    n_header = sum(1 for yc, _ in cell_lines if header_bottom is not None and yc < header_bottom)
    n_header = n_header or 1
    data_cells = [c for _, cells in cell_lines[n_header:] for c in cells]
    segments = _column_segments(data_cells)
    if len(segments) < 2:
        return None
    rows: list[list[Cell]] = []
    for _, cells in cell_lines:
        row = [""] * len(segments)
        for cell in cells:
            col = _segment_of(cell, segments)
            row[col] = f"{row[col]} {cell[2]}".strip()
        rows.append(list(row))
    return rows, (x0, top, x1, bottom)


def _overlaps(a: BBox, b: BBox) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


# --------------------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------------------


def _page_warnings(page: PageData, doc_has_text: bool) -> list[ExtractionWarning]:
    out: list[ExtractionWarning] = []
    if doc_has_text and not page.has_text:
        out.append(
            ExtractionWarning(
                page.number,
                "page_without_text",
                f"Página {page.number}: página sin texto; no se procesó",
            )  # fmt: skip
        )
    elif any(img.area_ratio >= MIN_IMAGE_AREA_RATIO for img in page.images):
        out.append(
            ExtractionWarning(
                page.number,
                "image_region",
                f"Página {page.number}: posible tabla como imagen; no se procesó",
            )
        )
    return out


def extract_tables(
    doc: pymupdf.Document, loaded: LoadedPdf
) -> tuple[list[RawTable], list[ExtractionWarning]]:
    """Detecta y extrae las tablas de cada página, en orden de lectura.

    No une todavía las tablas que continúan en otra página (ver `merge.merge_continuations`).
    """
    tables: list[RawTable] = []
    warnings: list[ExtractionWarning] = []
    doc_has_text = any(p.has_text for p in loaded.pages)
    for page in doc.pages():
        number = page.number + 1
        page_data = loaded.page(number)
        warnings.extend(_page_warnings(page_data, doc_has_text))
        if not page_data.has_text:
            continue
        taken: list[BBox] = []
        found: list[RawTable] = []
        for t in page.find_tables(strategy="lines").tables:
            x0, y0, x1, y1 = t.bbox
            bbox: BBox = (x0, y0, x1, y1)
            taken.append(bbox)
            rows: list[list[Cell]] = t.extract()
            problem = _check(rows, number)
            if problem:
                warnings.append(problem)
                continue
            table = _build_table(rows, bbox, number, "lines")
            if table:
                found.append(table)
        free_rules = [
            r for r in _horizontal_rules(page)
            if not any(b[0] - 2 <= r.x0 and r.x1 <= b[2] + 2 and b[1] - 2 <= r.y <= b[3] + 2
                       for b in taken)
        ]  # fmt: skip
        for group in _rule_groups(free_rules):
            region: BBox = (group[0].x0, group[0].y, group[-1].x1, group[-1].y)
            if any(_overlaps(region, b) for b in taken):
                continue
            parsed = _parse_hrule_table(page, group)
            if parsed is None:
                continue
            rows, bbox = parsed
            _, data = split_header(rows)
            if _has_numeric_column(data) and _check(rows, number) is None:
                table = _build_table(rows, bbox, number, "hrules")
                if table:
                    found.append(table)
                    taken.append(bbox)
        tables.extend(sorted(found, key=lambda t: (t.bbox[1], t.bbox[0])))
    return tables, warnings


def main(argv: list[str]) -> int:
    from agents.ingestion.context import collect_context
    from agents.ingestion.merge import merge_continuations
    from agents.ingestion.normalize import normalize_table
    from agents.ingestion.pdf_loader import read_pdf

    if len(argv) != 1:
        print("Uso: python -m agents.ingestion.extract <archivo.pdf>")
        return 2
    path = Path(argv[0])
    doc, loaded = read_pdf(path)
    try:
        raw, warnings = extract_tables(doc, loaded)
    finally:
        doc.close()
    tables = merge_continuations(raw, loaded)
    print(f"{path.name}: {loaded.page_count} páginas, doc_id={loaded.doc_id}, "
          f"'-' = cero: {loaded.zero_dash}, {len(tables)} tablas\n")  # fmt: skip
    for i, t in enumerate(tables, 1):
        ctx = collect_context(t, loaded)
        df, notes, _ = normalize_table(t, loaded)
        print(f"[{i}] páginas {t.pages} ({t.strategy}) {df.shape[0]}x{df.shape[1]}")
        print(f"    epígrafe: {ctx.caption[:110]}")
        print(f"    sección:  {ctx.section_title[:80]}")
        print(f"    columnas: {list(df.columns)}")
        print(f"    tipos:    {[str(d) for d in df.dtypes]}")
        if notes:
            print(f"    notas:    {notes}")
        print()
    for w in warnings:
        print(f"AVISO {w.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
