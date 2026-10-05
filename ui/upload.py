"""Pestaña Subir PDF: ingesta con progreso en vivo (FR-018), resumen (FR-017) y avisos (FR-040)."""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import streamlit as st

from agents.ingestion.graph import IngestionState, stream_ingest
from agents.ingestion.schemas import TableMetadata
from services.config import Settings
from ui import runtime
from ui.errors import show_service_error

RESULT_KEY = "last_ingest"


@dataclass
class IngestResult:
    pdf_name: str
    log: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    indexed: list[TableMetadata] = field(default_factory=list)
    error: str | None = None  # mensajes del agente (FR-002, FR-019, FR-019b, FR-064…)
    service_error: str | None = None  # falla de un servicio externo (FR-043)
    seconds: float = 0.0


def run_ingestion(pdf_name: str, data: bytes, settings: Settings) -> IngestResult:
    """Corre la ingesta mostrando una línea por nodo dentro de un `st.status`."""
    result = IngestResult(pdf_name=pdf_name)
    start = time.perf_counter()
    with st.status(f"Ingiriendo {pdf_name}…", expanded=True) as status:
        try:
            services = runtime.ingestion_services(settings)
            with tempfile.TemporaryDirectory(prefix="upload-") as tmp:
                path = Path(tmp) / Path(pdf_name).name
                path.write_bytes(data)
                final: IngestionState = {}
                for _node, update in stream_ingest(path, pdf_name, services, settings):
                    for line in update.get("log", []):
                        elapsed = time.perf_counter() - start
                        status.write(f"`{elapsed:5.1f} s` {line}")
                        result.log.append(line)
                    result.warnings += update.get("warnings", [])
                    rest = {k: v for k, v in update.items() if k not in ("log", "warnings")}
                    final.update(cast(IngestionState, rest))
            result.indexed = list(final.get("indexed", []))
            result.error = final.get("error")
        except Exception as exc:  # noqa: BLE001 — FR-043: la app no se cae
            result.service_error = show_service_error(exc, "la ingesta")
        result.seconds = time.perf_counter() - start
        failed = result.error or result.service_error
        status.update(
            label=f"{pdf_name}: {'con errores' if failed else 'ingesta terminada'} "
            f"({result.seconds:.1f} s)",
            state="error" if failed else "complete",
            expanded=False,
        )
    return result


def render_table_summary(meta: TableMetadata, settings: Settings) -> None:
    """Los 6 elementos de FR-017."""
    pages = ", ".join(map(str, meta.source.pages))
    st.markdown(f"#### {meta.name}")
    st.caption(
        f"Páginas {pages} · {meta.n_rows} filas × {meta.n_cols} columnas · `{meta.table_id}`"
    )
    st.write(meta.description)
    st.markdown(
        "**Columnas:** " + "; ".join(f"{c.name} ({c.unit or 'texto'})" for c in meta.columns)
    )
    if meta.row_headers:
        more = f" … (+{len(meta.row_headers) - 15})" if len(meta.row_headers) > 15 else ""
        st.markdown(
            f"**Filas ({meta.row_header_column}):** {', '.join(meta.row_headers[:15])}{more}"
        )
    try:
        df = runtime.table_store(settings).load_df(meta.table_id)
        st.dataframe(df.head(5), hide_index=True)
    except Exception as exc:  # noqa: BLE001
        show_service_error(exc, "la lectura de la tabla")


def render_result(result: IngestResult, settings: Settings, show_log: bool) -> None:
    if show_log and result.log:
        with st.expander(f"Progreso de la ingesta de {result.pdf_name}"):
            st.markdown("\n".join(f"- {line}" for line in result.log))
    if result.service_error and show_log:
        st.error(result.service_error)
    if result.error:
        st.error(result.error)
    if result.warnings:
        st.warning("**Avisos:**\n\n" + "\n".join(f"- {w}" for w in dict.fromkeys(result.warnings)))
    if result.indexed:
        st.success(
            f"{len(result.indexed)} tabla(s) de {result.pdf_name} indexadas "
            f"en {result.seconds:.1f} s."
        )
        for meta in result.indexed:
            render_table_summary(meta, settings)
            st.divider()


def render(settings: Settings, missing: list[str]) -> None:
    st.subheader("Subir un PDF")
    blocked = bool(missing)
    if blocked:
        st.warning(
            "Esta pestaña está bloqueada: faltan "
            + ", ".join(f"`{m}`" for m in missing)
            + " en el `.env`."
        )
    uploaded = st.file_uploader("PDF con tablas", type=["pdf"], disabled=blocked, key="upload_file")
    clicked = st.button(
        "Ingerir", type="primary", disabled=blocked or uploaded is None, key="upload_go"
    )
    if clicked and uploaded is not None:
        result = run_ingestion(uploaded.name, uploaded.getvalue(), settings)
        st.session_state[RESULT_KEY] = result
        render_result(result, settings, show_log=False)
    elif RESULT_KEY in st.session_state:
        render_result(st.session_state[RESULT_KEY], settings, show_log=True)
