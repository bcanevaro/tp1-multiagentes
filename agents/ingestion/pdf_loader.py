"""Carga del PDF: apertura segura, texto por página y bloques con posición (FR-001/002/019b)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

import pymupdf

# "- Cero absoluto", "-: dato igual a cero", "– igual a cero" en los signos convencionales.
# Números cuyo formato es inequívoco: con ambos separadores, o con 1-2 decimales.
_COMMA_DECIMAL_RE = re.compile(r"\b\d{1,3}(?:\.\d{3})+,\d+\b|\b\d+,\d{1,2}\b(?![.,]\d)")
_DOT_DECIMAL_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+\.\d+\b|\b\d+\.\d{1,2}\b(?![.,]\d)")
_ZERO_DASH_RE = re.compile(
    r"(?:^|\s)[-–]\s*[:=]?\s*(?:cero absoluto|dato igual a cero|igual a cero)", re.IGNORECASE
)


class PdfOpenError(Exception):
    """El archivo no se puede abrir como PDF (FR-019b)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"No se pudo abrir el PDF: {reason}")


class NoTextLayerError(Exception):
    """Ninguna página tiene texto extraíble (FR-002)."""

    def __init__(self) -> None:
        super().__init__("El PDF no tiene capa de texto; los PDFs escaneados no están soportados")


@dataclass(frozen=True)
class TextBlock:
    """Un bloque de texto de una página, con su posición y estilo dominante."""

    page: int  # 1-based
    x0: float
    y0: float
    x1: float
    y1: float
    text: str  # líneas unidas con espacios
    font_size: float  # tamaño máximo de las letras del bloque
    bold: bool  # todas las letras del bloque son negrita

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass(frozen=True)
class PageImage:
    page: int
    bbox: tuple[float, float, float, float]
    area_ratio: float  # área de la imagen / área de la página


@dataclass
class PageData:
    number: int  # 1-based
    width: float
    height: float
    text: str
    blocks: list[TextBlock] = field(default_factory=list)
    images: list[PageImage] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


@dataclass
class LoadedPdf:
    doc_id: str
    name: str
    pages: list[PageData]
    zero_dash: bool  # el documento declara que "-" significa cero (FR-005)
    decimal_comma: bool  # formato numérico mayoritario del documento: 1.234,5 (True) o 1,234.5
    body_font_size: float  # tamaño de letra más frecuente del documento

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def page(self, number: int) -> PageData:
        return self.pages[number - 1]


def compute_doc_id(data: bytes) -> str:
    """`doc_id` = primeros 16 caracteres hex del SHA-256 del contenido (BR-005)."""
    return hashlib.sha256(data).hexdigest()[:16]


def open_pdf(source: bytes | Path) -> pymupdf.Document:
    """Abre un PDF desde bytes o ruta. Lanza `PdfOpenError` si no es un PDF válido o cifrado."""
    try:
        if isinstance(source, Path):
            doc = pymupdf.open(source, filetype="pdf")
        else:
            doc = pymupdf.open(stream=source, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise PdfOpenError("el archivo está dañado o no es un PDF") from exc
    if doc.needs_pass:
        doc.close()
        raise PdfOpenError("el PDF está protegido con contraseña")
    if doc.page_count == 0:
        doc.close()
        raise PdfOpenError("el PDF no tiene páginas")
    return doc


def _blocks(page: pymupdf.Page, number: int) -> list[TextBlock]:
    out: list[TextBlock] = []
    data = page.get_text("dict")
    for block in data["blocks"]:
        if block.get("type") != 0:  # 0 = texto, 1 = imagen
            continue
        spans = [s for line in block["lines"] for s in line["spans"] if s["text"].strip()]
        if not spans:
            continue
        lines = ["".join(s["text"] for s in line["spans"]).strip() for line in block["lines"]]
        text = " ".join(" ".join(x for x in lines if x).split())
        x0, y0, x1, y1 = block["bbox"]
        out.append(
            TextBlock(
                page=number,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                text=text,
                font_size=round(max(s["size"] for s in spans), 1),
                bold=all(bool(s["flags"] & 16) or "Bold" in s["font"] for s in spans),
            )
        )
    return sorted(out, key=lambda b: (round(b.y0), b.x0))


def _images(page: pymupdf.Page, number: int) -> list[PageImage]:
    area = page.rect.get_area() or 1.0
    out: list[PageImage] = []
    for img in page.get_images(full=True):
        for rect in page.get_image_rects(img[0]):
            r = rect & page.rect
            if r.is_empty:
                continue
            out.append(PageImage(number, (r.x0, r.y0, r.x1, r.y1), r.get_area() / area))
    return out


def load_pdf(doc: pymupdf.Document, name: str, data: bytes) -> LoadedPdf:
    """Lee texto, bloques e imágenes de cada página (FR-001).

    Lanza `NoTextLayerError` si ninguna página tiene texto (FR-002).
    """
    pages: list[PageData] = []
    for page in doc.pages():
        number = page.number + 1
        pages.append(
            PageData(
                number=number,
                width=page.rect.width,
                height=page.rect.height,
                text=page.get_text(),
                blocks=_blocks(page, number),
                images=_images(page, number),
            )
        )
    if not any(p.has_text for p in pages):
        raise NoTextLayerError()
    full_text = "\n".join(p.text for p in pages)
    # Tamaño del cuerpo: mediana de los bloques "de párrafo" (≥ 60 caracteres), así las celdas
    # de las tablas (bloques cortos y en letra chica) no lo distorsionan.
    blocks = [b for p in pages for b in p.blocks]
    sizes = [b.font_size for b in blocks if len(b.text) >= 60] or [b.font_size for b in blocks]
    return LoadedPdf(
        doc_id=compute_doc_id(data),
        name=name,
        pages=pages,
        zero_dash=bool(_ZERO_DASH_RE.search(full_text)),
        decimal_comma=len(_COMMA_DECIMAL_RE.findall(full_text))
        >= len(_DOT_DECIMAL_RE.findall(full_text)),
        body_font_size=float(median(sizes)) if sizes else 10.0,
    )


def read_pdf(source: bytes | Path, name: str | None = None) -> tuple[pymupdf.Document, LoadedPdf]:
    """Atajo: abre y carga el PDF. El llamador debe cerrar el `Document`."""
    data = source.read_bytes() if isinstance(source, Path) else source
    doc = open_pdf(data)
    try:
        loaded = load_pdf(
            doc, name or (source.name if isinstance(source, Path) else "documento.pdf"), data
        )
    except NoTextLayerError:
        doc.close()
        raise
    return doc, loaded
