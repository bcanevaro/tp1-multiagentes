"""Genera los PDFs de casos borde que usan los tests de la ingesta.

Uso:  uv run python scripts/make_test_fixtures.py [directorio]
      (por defecto tests/fixtures/generated)

Los tests los generan en un directorio temporal (ver `tests/conftest.py`), así que estos
archivos no se versionan; el comando sirve para abrirlos y mirarlos.

`FIXTURES` describe, para cada archivo, qué caso cubre y qué debería pasar al ingerirlo.
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402
from reportlab import rl_config  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
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

rl_config.invariant = 1
_BODY = getSampleStyleSheet()["BodyText"]
_GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)])
PASSWORD = "secreta"

# nombre de archivo -> (caso que cubre, resultado esperado)
FIXTURES: dict[str, tuple[str, str]] = {
    "solo_imagen.pdf": (
        "PDF escaneado: una página que es solo una imagen",
        "FR-002: sin capa de texto",
    ),
    "solo_texto.pdf": ("PDF con texto y sin tablas", "FR-019: 0 tablas, sin llamar al LLM"),
    "tabla_imagen_y_texto.pdf": (
        "Una tabla como imagen grande y una tabla de texto",
        "FR-008: se procesa solo la tabla de texto y hay un aviso por la imagen",
    ),
    "logo_y_tabla.pdf": ("Logo chico (< 10 % del área) y una tabla", "FR-008: sin aviso"),
    "protegido.pdf": (
        f"PDF con contraseña de apertura ('{PASSWORD}')",
        "FR-019b: no se puede abrir",
    ),
    "no_es_pdf.pdf": ("Archivo de texto con extensión .pdf", "FR-019b: no se puede abrir"),
    "columnas_distintas.pdf": (
        "Tabla al final de la página 1 (3 columnas) y otra al inicio de la página 2 (4 columnas)",
        "FR-007: dos tablas separadas",
    ),
    "continuacion_sin_encabezado.pdf": (
        "Tabla que continúa en la página siguiente sin repetir el encabezado",
        "FR-007: una sola tabla lógica en páginas [1, 2]",
    ),
    "tabla_vacia.pdf": ("Tabla con más del 90 % de celdas vacías", "FR-008: se saltea con aviso"),
}

SMALL_TABLE = [
    ["Región", "2022", "2023"],
    ["Norte", "1.234,5", "1.310,2"],
    ["Sur", "987,1", "1.002,7"],
    ["Centro", "2.450,0", "2.611,3"],
]


def _doc(path: Path) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )  # fmt: skip


def _table(data: list[list[str]], repeat: int = 1) -> Table:
    t = Table(data, repeatRows=repeat)
    t.setStyle(_GRID)
    return t


def _table_png(scale: float = 2.0) -> bytes:
    """Renderiza SMALL_TABLE a PNG (para simular una tabla escaneada)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=(10 * cm, 5 * cm), leftMargin=5, rightMargin=5,
                            topMargin=5, bottomMargin=5)  # fmt: skip
    doc.build([_table(SMALL_TABLE)])
    src = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    png: bytes = src[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale)).tobytes("png")
    src.close()
    return png


def _with_images(src: Path, dst: Path, images: list[tuple[pymupdf.Rect, bytes]]) -> None:
    doc = pymupdf.open(src)
    for rect, png in images:
        doc[0].insert_image(rect, stream=png)
    doc.save(dst, deflate=True, no_new_id=True)
    doc.close()


def build_all(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_tmp.pdf"
    paths = {name: out_dir / name for name in FIXTURES}

    # Solo imagen: una página A4 que contiene únicamente la imagen de una tabla.
    doc = pymupdf.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    page.insert_image(pymupdf.Rect(50, 50, 545, 300), stream=_table_png())
    doc.save(paths["solo_imagen.pdf"], no_new_id=True)
    doc.close()

    # Solo texto.
    _doc(paths["solo_texto.pdf"]).build(
        [Paragraph("Informe sin tablas", _BODY)]
        + [Paragraph("Este documento solo contiene párrafos de texto. " * 6, _BODY)] * 4
    )

    # Tabla como imagen grande + tabla de texto.
    _doc(tmp).build(
        [Paragraph("Cuadro 1. Tabla de texto", _BODY), _table(SMALL_TABLE), Spacer(1, 330)]
    )
    _with_images(tmp, paths["tabla_imagen_y_texto.pdf"],
                 [(pymupdf.Rect(57, 450, 540, 700), _table_png())])  # fmt: skip

    # Logo chico + tabla.
    _doc(tmp).build([Spacer(1, 60), Paragraph("Cuadro 1. Tabla con logo", _BODY),
                     _table(SMALL_TABLE)])  # fmt: skip
    _with_images(tmp, paths["logo_y_tabla.pdf"],
                 [(pymupdf.Rect(57, 40, 117, 80), _table_png(0.5))])  # fmt: skip

    # Protegido con contraseña.
    _doc(tmp).build([Paragraph("Cuadro 1. Protegido", _BODY), _table(SMALL_TABLE)])
    doc = pymupdf.open(tmp)
    doc.save(paths["protegido.pdf"], encryption=pymupdf.PDF_ENCRYPT_AES_256,
             user_pw=PASSWORD, owner_pw=PASSWORD + "-owner", no_new_id=True)  # fmt: skip
    doc.close()

    # No es un PDF.
    paths["no_es_pdf.pdf"].write_text("Esto es un archivo de texto, no un PDF.\n", encoding="utf-8")

    # Tablas consecutivas con distinta cantidad de columnas.
    three = [["A", "B", "C"]] + [[f"a{i}", f"{i},5", f"{i * 2},0"] for i in range(5)]
    four = [["A", "B", "C", "D"]] + [[f"x{i}", f"{i},1", f"{i},2", f"{i},3"] for i in range(5)]
    story: list[Flowable] = [Paragraph("Texto de relleno. " * 30, _BODY)] * 5
    _doc(paths["columnas_distintas.pdf"]).build(
        [*story, Paragraph("Cuadro A", _BODY), _table(three), PageBreak(), _table(four)]
    )

    # Continuación sin repetir el encabezado (repeatRows=0).
    long_rows = [["Mes", "Valor", "Variación"]] + [
        [f"Mes {i:02d}", f"{1000 + i * 37},0", f"{i % 7},{i % 10} %"] for i in range(1, 61)
    ]
    long_table = LongTable(long_rows, repeatRows=0)
    long_table.setStyle(_GRID)
    _doc(paths["continuacion_sin_encabezado.pdf"]).build(
        [Paragraph("Texto de relleno. " * 30, _BODY), Paragraph("Cuadro B", _BODY), long_table]
    )

    # Tabla casi vacía (bordes dibujados, sin texto en las celdas salvo una).
    empty = [["Total", "", "", ""]] + [["", "", "", ""] for _ in range(9)]
    _doc(paths["tabla_vacia.pdf"]).build([Paragraph("Formulario", _BODY), _table(empty, 0)])

    tmp.unlink(missing_ok=True)
    return paths


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/generated")
    for name, path in build_all(target).items():
        case, expected = FIXTURES[name]
        print(f"{path}: {case} -> {expected}")
