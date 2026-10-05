"""VC-002b, VC-016 a VC-021, VC-065c, FR-018, NFR-006: grafo de Ingesta con servicios simulados."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from agents.ingestion.graph import NO_TABLES_MESSAGE, ingest_pdf, stream_ingest
from agents.ingestion.schemas import (
    ColumnInfo,
    Source,
    TableMetadata,
)
from services.table_store import TableStore
from services.vector_index import IndexDimensionError, InMemoryIndex, pinecone_metadata
from tests.ingestion.conftest import SAMPLE
from tests.ingestion.fakes import FakeAnnotator, make_services

SPEC_METADATA_KEYS = {
    "doc_id",
    "pdf_name",
    "pages",
    "name",
    "description",
    "columns",
    "row_headers",
    "periods_covered",
    "entities_covered",
    "preview_markdown",
    "n_rows",
    "n_cols",
}


def test_full_ingestion_of_sample(tmp_path: Path) -> None:
    index = InMemoryIndex(8)
    result = ingest_pdf(SAMPLE, services=make_services(tmp_path, index=index))
    assert result.get("error") is None
    assert len(result["indexed"]) == 6
    doc_id = result["doc_id"]
    assert [m.table_id for m in result["indexed"]] == [f"{doc_id}-t{i:02d}" for i in range(1, 7)]


def test_vc018_parquet_and_json_per_table(tmp_path: Path) -> None:
    result = ingest_pdf(SAMPLE, services=make_services(tmp_path))
    store = TableStore(tmp_path)
    drafts = {d.index: d for d in result["drafts"]}
    for i, meta in enumerate(result["indexed"]):
        assert store.parquet_path(meta.table_id).exists()
        assert store.load_metadata(meta.table_id) == meta
        pd.testing.assert_frame_equal(store.load_df(meta.table_id), drafts[i].to_dataframe())
    assert store.pdf_path(result["doc_id"]).read_bytes() == SAMPLE.read_bytes()


def test_vc019_one_vector_per_table_with_spec_metadata(tmp_path: Path) -> None:
    index = InMemoryIndex(8)
    result = ingest_pdf(SAMPLE, services=make_services(tmp_path, index=index))
    assert sorted(index.records) == sorted(m.table_id for m in result["indexed"])
    for record in index.records.values():
        assert set(record.metadata) == SPEC_METADATA_KEYS
        assert all(isinstance(p, str) for p in record.metadata["pages"])  # Pinecone: lista de str
    exports = index.records[result["indexed"][-1].table_id].metadata
    assert exports["pages"] == ["2", "3"]


def test_vc016_retry_only_invalid_tables(tmp_path: Path) -> None:
    annotator = FakeAnnotator(failures={0: 1})
    result = ingest_pdf(SAMPLE, services=make_services(tmp_path, annotator=annotator))
    assert len(result["indexed"]) == 6
    assert annotator.calls[0] == 2
    assert all(annotator.calls[i] == 1 for i in range(1, 6))
    assert annotator.prompt_errors[0][0] == []  # primer intento sin errores
    assert any(e.startswith("BR-001") for e in annotator.prompt_errors[0][1])  # FR-012


def test_vc017_retries_exhausted_table_is_skipped(tmp_path: Path) -> None:
    annotator = FakeAnnotator(failures={2: 99})
    result = ingest_pdf(
        SAMPLE, services=make_services(tmp_path, annotator=annotator, max_retries=2)
    )
    assert annotator.calls[2] == 3  # INGEST_MAX_RETRIES + 1
    assert len(result["indexed"]) == 5
    assert 2 in result["failed"]
    assert any("Cuadro 3" in w and "3 intentos" in w for w in result["warnings"])


def test_vc020_reingest_same_content_other_name(tmp_path: Path) -> None:
    index = InMemoryIndex(8)
    services = make_services(tmp_path / "store", index=index)
    first = ingest_pdf(SAMPLE, services=services)
    ids_first = sorted(index.records)
    renamed = tmp_path / "copia_con_otro_nombre.pdf"
    shutil.copy(SAMPLE, renamed)
    second = ingest_pdf(renamed, services=services)
    assert second["doc_id"] == first["doc_id"]
    assert sorted(index.records) == ids_first
    assert len(TableStore(tmp_path / "store").list_tables()) == 6


def test_vc021_stale_tables_are_removed(tmp_path: Path) -> None:
    index = InMemoryIndex(8)
    ingest_pdf(SAMPLE, services=make_services(tmp_path, index=index))
    stale = sorted(index.records)[-1]
    # Segunda ingesta en la que la última tabla no pasa la validación: debe desaparecer.
    ingest_pdf(SAMPLE, services=make_services(tmp_path, FakeAnnotator({5: 99}), index=index))
    assert stale not in index.records
    assert len(index.records) == 5
    assert not TableStore(tmp_path).metadata_path(stale).exists()


def test_vc002b_text_only_pdf_does_not_call_llm(tmp_path: Path, edge_pdfs: dict[str, Path]) -> None:
    annotator = FakeAnnotator()
    result = ingest_pdf(edge_pdfs["solo_texto.pdf"], services=make_services(tmp_path, annotator))
    assert result["error"] == NO_TABLES_MESSAGE
    assert sum(annotator.calls.values()) == 0


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("solo_imagen.pdf", "no tiene capa de texto"),
        ("no_es_pdf.pdf", "No se pudo abrir el PDF"),
        ("protegido.pdf", "contraseña"),
    ],
)
def test_unreadable_pdfs_end_with_message(
    tmp_path: Path, edge_pdfs: dict[str, Path], name: str, message: str
) -> None:
    result = ingest_pdf(edge_pdfs[name], services=make_services(tmp_path))
    assert message in result["error"]
    assert not (tmp_path / "tables").exists()


def test_vc065c_dimension_mismatch_writes_nothing(tmp_path: Path) -> None:
    def broken_index() -> InMemoryIndex:
        raise IndexDimensionError("mas-2026s2-tables", 3072, 1536)

    result = ingest_pdf(SAMPLE, services=make_services(tmp_path, index_factory=broken_index))
    assert (
        result["error"]
        == "El índice 'mas-2026s2-tables' tiene dimensión 3072 y el modelo de embeddings 1536"
    )
    assert not (tmp_path / "tables").exists()


def test_fr018_stream_reports_each_node_in_order(tmp_path: Path) -> None:
    events = list(stream_ingest(SAMPLE, services=make_services(tmp_path, FakeAnnotator({1: 1}))))
    nodes = [node for node, _ in events]
    assert nodes == [
        "load_pdf",
        "extract_tables",
        "merge_continuations",
        "collect_context",
        "enrich",
        "validate",
        "enrich",
        "validate",
        "persist_and_index",
    ]
    assert all(update["log"] and update["log"][0].startswith(node) for node, update in events)
    assert "6 tablas lógicas (1 uniones" in events[2][1]["log"][0]


def test_nfr006_metadata_size_limit_with_huge_table() -> None:
    df = pd.DataFrame(
        {"Fila": [f"fila {i} " + "x" * 300 for i in range(5000)], "Valor": range(5000)}
    )
    meta = TableMetadata(
        table_id="d-t01",
        doc_id="d",
        name="Grande",
        description="Una. Dos.",
        columns=[
            ColumnInfo(
                name=c,
                description="",
                dtype="str",
                unit="",
                scale="desconocida",
                value_type="texto",
            )
            for c in df.columns
        ],
        row_header_column="Fila",
        row_headers=list(df["Fila"]),
        periods_covered=[],
        entities_covered=[f"entidad {i}" for i in range(3000)],
        notes="",
        source=Source(pdf_name="g.pdf", doc_id="d", pages=[1]),
        n_rows=5000,
        n_cols=2,
    )
    import json

    record = pinecone_metadata(meta, df)
    assert len(json.dumps(record, ensure_ascii=False).encode()) <= 38_000


def test_service_error_on_every_table_stops_ingestion(tmp_path: Path) -> None:
    """FR-043: si todas las llamadas al LLM fallan por el servicio (p. ej. clave inválida), no se
    reintenta como si fueran metadatos inválidos: el error sube para que la UI lo muestre."""
    import httpx
    import openai

    response = httpx.Response(401, request=httpx.Request("POST", "http://proxy.test/v1"))
    calls: list[int] = []

    def failing(jobs, pdf_name, config):  # type: ignore[no-untyped-def]
        calls.append(len(jobs))
        return [
            openai.AuthenticationError("Invalid API key", response=response, body=None)
            for _ in jobs
        ]

    services = make_services(tmp_path)
    services.annotate = failing
    with pytest.raises(openai.AuthenticationError):
        ingest_pdf(SAMPLE, services=services)
    assert len(calls) == 1
    assert TableStore(tmp_path).list_tables() == []
