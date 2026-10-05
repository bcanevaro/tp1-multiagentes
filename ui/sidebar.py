"""Barra lateral: configuración activa sin claves (FR-044) y variables faltantes (FR-045)."""

from __future__ import annotations

import streamlit as st

from services.config import Settings
from ui import runtime


def render_sidebar(settings: Settings, missing: list[str]) -> None:
    with st.sidebar:
        st.header("Configuración")
        code_model = settings.LLM_CODE_MODEL or "(el mismo)"
        dim = settings.EMBEDDING_DIM or "?"
        tracing = (
            f"activas, proyecto `{settings.LANGSMITH_PROJECT}`"
            if settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY
            else "desactivadas"
        )
        st.markdown(
            "\n".join(
                [
                    f"- **Modelo de chat:** `{settings.LLM_MODEL or '-'}`",
                    f"- **Modelo para código:** `{code_model}`",
                    f"- **Embeddings:** `{settings.EMBEDDING_MODEL or '-'}` ({dim} dim.)",
                    f"- **Índice Pinecone:** `{settings.PINECONE_INDEX_NAME or '-'}`",
                    f"- **Sandbox:** {runtime.sandbox_label(settings)}",
                    f"- **Trazas LangSmith:** {tracing}",
                ]
            )
        )
        if missing:
            items = "\n".join(f"- `{m}`" for m in missing)
            st.error(f"Faltan variables en el `.env`:\n\n{items}")
        st.caption("Las claves nunca se muestran.")
