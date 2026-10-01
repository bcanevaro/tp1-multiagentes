"""Fixtures de la extracción: PDFs ya procesados una vez por sesión."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from agents.ingestion.context import TableContext, collect_context
from agents.ingestion.extract import ExtractionWarning, RawTable, extract_tables
from agents.ingestion.merge import merge_continuations
from agents.ingestion.pdf_loader import LoadedPdf, read_pdf

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "sample_pdfs" / "informe_sintetico.pdf"
INDEC = ROOT / "data" / "sample_pdfs" / "indec_ica.pdf"


@dataclass
class Extraction:
    loaded: LoadedPdf
    raw: list[RawTable]
    tables: list[RawTable]
    warnings: list[ExtractionWarning]

    def context(self, table: RawTable) -> TableContext:
        return collect_context(table, self.loaded, self.tables)


def run_extraction(path: Path) -> Extraction:
    doc, loaded = read_pdf(path)
    try:
        raw, warnings = extract_tables(doc, loaded)
    finally:
        doc.close()
    return Extraction(loaded, raw, merge_continuations(raw, loaded), warnings)


@pytest.fixture(scope="session")
def sample() -> Extraction:
    return run_extraction(SAMPLE)


@pytest.fixture(scope="session")
def indec() -> Extraction:
    return run_extraction(INDEC)


@pytest.fixture(scope="session")
def edge(edge_pdfs: dict[str, Path]) -> dict[str, Extraction]:
    skip = {"solo_imagen.pdf", "protegido.pdf", "no_es_pdf.pdf"}
    return {name: run_extraction(path) for name, path in edge_pdfs.items() if name not in skip}
