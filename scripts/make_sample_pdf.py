"""Genera el PDF sintético de ejemplo y su archivo de verdad para los tests.

Uso:  uv run python scripts/make_sample_pdf.py

Salidas:
- data/sample_pdfs/informe_sintetico.pdf
- tests/fixtures/sample_truth.json  (estructura, contexto y valores esperados de cada tabla)

La generación es determinística (`invariant=1`): correrlo dos veces produce el mismo PDF.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402
from reportlab import rl_config  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Flowable,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from scripts import sample_data as sd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = ROOT / "data" / "sample_pdfs" / "informe_sintetico.pdf"
TRUTH_PATH = ROOT / "tests" / "fixtures" / "sample_truth.json"

rl_config.invariant = 1  # PDF reproducible (sin fechas ni IDs aleatorios)

_styles = getSampleStyleSheet()
TITLE = ParagraphStyle("Titulo", parent=_styles["Title"], fontSize=18, leading=22)
SECTION = ParagraphStyle(
    "Seccion", parent=_styles["Heading2"], fontSize=14, leading=18, spaceBefore=10
)
BODY = ParagraphStyle("Cuerpo", parent=_styles["BodyText"], fontSize=10, leading=13)
CAPTION = ParagraphStyle(
    "Epigrafe", parent=BODY, fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=4
)
NOTE = ParagraphStyle("Nota", parent=BODY, fontSize=8, leading=10, spaceBefore=3)
CELL = ParagraphStyle("Celda", parent=BODY, fontSize=8.5, leading=10)
CELL_HEAD = ParagraphStyle("CeldaEnc", parent=CELL, fontName="Helvetica-Bold")

GRID = [
    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
]


@dataclass
class TableTruth:
    """Lo que la extracción debería obtener para una tabla del PDF."""

    key: str
    caption: str
    section_title: str
    paragraph_before: str
    footnote: str
    paragraph_after: str
    columns: list[str]
    rows_text: list[list[str]]
    values: list[list[Any]]
    header_rows: int
    line_style: str
    pages: list[int] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return len(self.rows_text)

    @property
    def n_cols(self) -> int:
        return len(self.columns)


def _pct(v: float | None) -> str:
    return "s/d" if v is None else f"{sd.fmt_ar(v)} %"


def _money(v: int | None) -> str:
    return "s/d" if v is None else f"$ {sd.fmt_ar(v, 0)}"


def build_tables() -> list[TableTruth]:
    tables: list[TableTruth] = []

    # Cuadro 1 — Finanzas públicas (grilla completa, negativos entre paréntesis).
    years = [str(y) for y in sd.YEARS_FINANCE]
    rows = [
        [concept] + [sd.fmt_ar_parens(v) for v in values] for concept, values in sd.FINANCE.items()
    ]
    tables.append(
        TableTruth(
            key="finanzas",
            caption="Cuadro 1. Ingresos y gastos del sector público provincial. "
            "Años 2019-2023. En millones de pesos corrientes",
            section_title="1. Finanzas públicas",
            paragraph_before=(
                "El sector público provincial cerró 2023 con un déficit financiero, luego del "
                "superávit registrado en 2022. El gasto en ciencia y tecnología mantuvo una "
                "participación cercana al 1,1 % del gasto total."
            ),
            footnote="Fuente: Contaduría General de la Provincia (datos ficticios). "
            "Nota: los valores negativos se presentan entre paréntesis.",
            paragraph_after="",
            columns=["Concepto", *years],
            rows_text=rows,
            values=[[c, *v] for c, v in sd.FINANCE.items()],
            header_rows=1,
            line_style="grid",
        )
    )

    # Cuadro 2 — Desempleo (porcentajes con "%", celda "s/d").
    years = [str(y) for y in sd.UNEMPLOYMENT_YEARS]
    tables.append(
        TableTruth(
            key="desempleo",
            caption="Cuadro 2. Tasa de desempleo por departamento. Años 2021-2023",
            section_title="2. Mercado de trabajo",
            paragraph_before=(
                "La tasa de desempleo descendió en la mayoría de los departamentos durante el "
                "período. El departamento Norte registró las tasas más elevadas de la provincia."
            ),
            footnote="Fuente: Encuesta Provincial de Hogares (datos ficticios). "
            "Nota: s/d = sin dato. Porcentaje de la población económicamente activa.",
            paragraph_after=(
                "Los salarios del sector privado registrado crecieron en todos los sectores, "
                "con mayor dinamismo en la industria."
            ),
            columns=["Departamento", *years],
            rows_text=[[d, *[_pct(v) for v in vals]] for d, vals in sd.UNEMPLOYMENT.items()],
            values=[[d, *vals] for d, vals in sd.UNEMPLOYMENT.items()],
            header_rows=1,
            line_style="grid",
        )
    )

    # Cuadro 3 — Salarios (solo líneas horizontales, "$", sin aclarar nominal/real).
    years = [str(y) for y in sd.WAGE_YEARS]
    tables.append(
        TableTruth(
            key="salarios",
            caption="Cuadro 3. Salario bruto promedio mensual por sector de actividad. "
            "Años 2021-2023. En pesos",
            section_title="2. Mercado de trabajo",
            paragraph_before=tables[-1].paragraph_after,
            footnote="Fuente: Registro Provincial de Empleo (datos ficticios). "
            "Nota: trabajadores asalariados registrados. s/d = sin dato.",
            paragraph_after="",
            columns=["Sector", *years],
            rows_text=[[s, *[_money(v) for v in vals]] for s, vals in sd.WAGES.items()],
            values=[[s, *vals] for s, vals in sd.WAGES.items()],
            header_rows=1,
            line_style="horizontal",
        )
    )

    # Cuadro 4 — Producción con encabezado de dos niveles.
    cols = ["Departamento"] + [f"{c} | {y}" for c in sd.CROPS for y in sd.CROP_YEARS]
    rows = [
        [d] + [sd.fmt_ar(sd.PRODUCTION[d][c][i]) for c in sd.CROPS for i in range(2)]
        for d in sd.DEPARTMENTS
    ]
    tables.append(
        TableTruth(
            key="produccion",
            caption="Cuadro 4. Producción de soja y maíz por departamento. "
            "Campañas 2022 y 2023. En miles de toneladas",
            section_title="3. Producción agrícola",
            paragraph_before=(
                "La sequía afectó la campaña 2023: la producción de soja cayó en todos los "
                "departamentos, mientras que el maíz mostró un comportamiento dispar."
            ),
            footnote="Fuente: Ministerio de Producción provincial (datos ficticios).",
            paragraph_after="",
            columns=cols,
            rows_text=rows,
            values=[
                [d] + [sd.PRODUCTION[d][c][i] for c in sd.CROPS for i in range(2)]
                for d in sd.DEPARTMENTS
            ],
            header_rows=2,
            line_style="grid",
        )
    )

    # Cuadro 5 — Población y superficie.
    tables.append(
        TableTruth(
            key="poblacion",
            caption="Cuadro 5. Población y superficie por departamento. Año 2023",
            section_title="4. Población",
            paragraph_before=(
                "La población provincial se concentra en el departamento Capital, que reúne "
                "más de la mitad de los habitantes."
            ),
            footnote="Fuente: proyecciones de población de la Dirección Provincial de "
            "Estadística (datos ficticios).",
            paragraph_after="",
            columns=["Departamento", "Población (habitantes)", "Superficie (km²)"],
            rows_text=[
                [d, sd.fmt_ar(sd.POPULATION[d], 0), sd.fmt_ar(sd.AREA_KM2[d], 0)]
                for d in sd.DEPARTMENTS
            ],
            values=[[d, sd.POPULATION[d], sd.AREA_KM2[d]] for d in sd.DEPARTMENTS],
            header_rows=1,
            line_style="grid",
        )
    )

    # Cuadro 6 — Exportaciones mensuales (larga, continúa en la página siguiente).
    rows_text: list[list[str]] = []
    values: list[list[Any]] = []
    for year in sd.EXPORT_YEARS:
        for m, month in enumerate(sd.MONTHS):
            parts = [sd.EXPORTS[year][r][m] for r in sd.EXPORT_RUBROS]
            total = sd.export_total(year, m)
            rows_text.append([str(year), month, *[sd.fmt_ar(p) for p in parts], sd.fmt_ar(total)])
            values.append([year, month, *parts, total])
    tables.append(
        TableTruth(
            key="exportaciones",
            caption="Cuadro 6. Exportaciones mensuales por grandes rubros. "
            "Años 2022-2023. En miles de dólares estadounidenses (US$)",
            section_title="5. Comercio exterior",
            paragraph_before=(
                "El cuadro siguiente presenta la serie mensual de exportaciones de la provincia "
                "para los años 2022 y 2023, desagregada por grandes rubros."
            ),
            footnote="Fuente: Dirección Provincial de Comercio Exterior (datos ficticios). "
            "Nota: valores FOB.",
            paragraph_after=(
                "En 2023 las exportaciones de productos primarios fueron las más afectadas por "
                "la caída de la cosecha."
            ),
            columns=["Año", "Mes", *sd.EXPORT_RUBROS, "Total"],
            rows_text=rows_text,
            values=values,
            header_rows=1,
            line_style="grid",
        )
    )
    return tables


def _simple_table(t: TableTruth, col_widths: list[float] | None = None) -> Table:
    data = [[Paragraph(c, CELL_HEAD) for c in t.columns], *t.rows_text]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    if t.line_style == "grid":
        table.setStyle(TableStyle(GRID))
    else:  # solo líneas horizontales, típico de informes estadísticos
        table.setStyle(
            TableStyle(
                [
                    ("LINEABOVE", (0, 0), (-1, 0), 1, colors.black),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                    ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ]
            )
        )
    return table


def _two_level_table(t: TableTruth) -> Table:
    head1 = ["Departamento", "Soja", "", "Maíz", ""]
    head2 = ["", *[str(y) for y in sd.CROP_YEARS] * 2]
    table = Table([head1, head2, *t.rows_text], colWidths=[4 * cm] + [2.6 * cm] * 4)
    table.setStyle(
        TableStyle(
            [
                *GRID,
                ("SPAN", (0, 0), (0, 1)),
                ("SPAN", (1, 0), (2, 0)),
                ("SPAN", (3, 0), (4, 0)),
                ("ALIGN", (1, 0), (-1, 1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
            ]
        )
    )
    return table


def _exports_table(t: TableTruth) -> LongTable:
    data = [[Paragraph(c, CELL_HEAD) for c in t.columns], *t.rows_text]
    widths = [1.3 * cm, 2.2 * cm, 3.2 * cm, 3.6 * cm, 3.6 * cm, 2.6 * cm]
    table = LongTable(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([*GRID, ("ALIGN", (0, 0), (1, -1), "LEFT")]))
    return table


def _block(t: TableTruth, table: Flowable) -> list[Flowable]:
    return [Paragraph(t.caption, CAPTION), table, Paragraph(t.footnote, NOTE), Spacer(1, 8)]


def build_story(tables: list[TableTruth]) -> list[Flowable]:
    fin, des, sal, prod, pob, exp = tables
    filler = (
        "La Dirección Provincial de Estadística elabora este anuario a partir de registros "
        "administrativos y encuestas propias. Las cifras del último año son provisorias y "
        "pueden ser revisadas en ediciones posteriores. Los datos de este documento son "
        "ficticios y se publican con fines exclusivamente didácticos."
    )
    return [
        Paragraph("Anuario Estadístico 2023", TITLE),
        Paragraph(
            "Provincia de San Aurelio (ficticia) — Dirección Provincial de Estadística", BODY
        ),
        Spacer(1, 10),
        Paragraph(filler, BODY),
        Paragraph(fin.section_title, SECTION),
        Paragraph(fin.paragraph_before, BODY),
        *_block(fin, _simple_table(fin)),
        Paragraph(des.section_title, SECTION),
        Paragraph(des.paragraph_before, BODY),
        *_block(des, _simple_table(des, [4 * cm, 3 * cm, 3 * cm, 3 * cm])),
        Paragraph(sal.paragraph_before, BODY),
        *_block(sal, _simple_table(sal, [4 * cm, 3 * cm, 3 * cm, 3 * cm])),
        PageBreak(),
        Paragraph(prod.section_title, SECTION),
        Paragraph(prod.paragraph_before, BODY),
        *_block(prod, _two_level_table(prod)),
        Paragraph(pob.section_title, SECTION),
        Paragraph(pob.paragraph_before, BODY),
        *_block(pob, _simple_table(pob, [4 * cm, 4 * cm, 4 * cm])),
        Paragraph(exp.section_title, SECTION),
        Paragraph(filler, BODY),
        Paragraph(exp.paragraph_before, BODY),
        *_block(exp, _exports_table(exp)),
        Paragraph(exp.paragraph_after, BODY),
        Paragraph("Notas metodológicas", SECTION),
        Paragraph(filler, BODY),
    ]


def _locate_pages(pdf_path: Path, tables: list[TableTruth]) -> int:
    """Completa `pages` de cada tabla buscando su epígrafe y su última fila en el PDF."""
    doc = pymupdf.open(pdf_path)
    try:
        for t in tables:
            first_needle = t.caption.split(".")[0] + "."  # "Cuadro N."
            last_needle = t.rows_text[-1][-1]
            start = next(p.number for p in doc if p.search_for(first_needle))
            end = next(p.number for p in doc if p.number >= start and p.search_for(last_needle))
            t.pages = list(range(start + 1, end + 2))
        return int(doc.page_count)
    finally:
        doc.close()


def build(pdf_path: Path = PDF_PATH, truth_path: Path = TRUTH_PATH) -> dict[str, Any]:
    tables = build_tables()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Anuario Estadístico 2023 - Provincia de San Aurelio (ficticia)",
        author="Dirección Provincial de Estadística (ficticia)",
    )
    doc.build(build_story(tables))
    page_count = _locate_pages(pdf_path, tables)
    truth = {
        "pdf": pdf_path.relative_to(ROOT).as_posix()
        if pdf_path.is_relative_to(ROOT)
        else pdf_path.name,
        "page_count": page_count,
        "tables": [{**asdict(t), "n_rows": t.n_rows, "n_cols": t.n_cols} for t in tables],
    }
    truth_path.parent.mkdir(parents=True, exist_ok=True)
    truth_path.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    return truth


if __name__ == "__main__":
    result = build()
    for t in result["tables"]:
        print(f"{t['key']:<14} páginas {t['pages']}  {t['n_rows']}x{t['n_cols']}")
    print(f"PDF: {result['pdf']} ({result['page_count']} páginas)")
