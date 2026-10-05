"""Pestaña Explorar: tablas del almacén local agrupadas por documento (FR-041)."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd
import streamlit as st

from agents.ingestion.schemas import TableMetadata
from services.config import Settings
from ui import runtime
from ui.errors import show_service_error


def columns_frame(meta: TableMetadata) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Columna": c.name,
                "Tipo": "texto" if c.dtype == "str" else "número",
                "Unidad": c.unit,
                "Escala": c.scale,
                "Valor": c.value_type,
                "Descripción": c.description,
            }
            for c in meta.columns
        ]
    )


def render(settings: Settings) -> None:
    st.subheader("Tablas indexadas")
    try:
        store = runtime.table_store(settings)
        tables = store.list_tables()
    except Exception as exc:  # noqa: BLE001
        show_service_error(exc, "la lectura del almacén local")
        return
    if not tables:
        st.info("Todavía no hay tablas. Subí un PDF en la pestaña «Subir PDF».")
        return

    by_doc: dict[str, list[TableMetadata]] = defaultdict(list)
    for meta in tables:
        by_doc[meta.doc_id].append(meta)
    st.caption(f"{len(tables)} tablas en {len(by_doc)} documento(s), guardadas en esta PC.")

    for doc_id, metas in by_doc.items():
        st.markdown(f"### 📄 {metas[0].source.pdf_name}")
        st.caption(f"{len(metas)} tabla(s) · doc_id `{doc_id}`")
        for meta in metas:
            pages = ", ".join(map(str, meta.source.pages))
            st.markdown(
                f"**{meta.name}** — página{'s' if len(meta.source.pages) > 1 else ''} {pages}"
            )
            st.caption(meta.description)
            with st.expander(f"Datos completos ({meta.n_rows} × {meta.n_cols})"):
                try:
                    st.dataframe(store.load_df(meta.table_id), hide_index=True)
                except Exception as exc:  # noqa: BLE001
                    show_service_error(exc, "la lectura de la tabla")
                st.markdown("**Columnas**")
                st.dataframe(columns_frame(meta), hide_index=True)
                if meta.notes:
                    st.markdown(f"**Notas:** {meta.notes}")
                if meta.caption:
                    st.caption(f"Epígrafe en el PDF: {meta.caption}")
        st.divider()
