"""Aplicación Streamlit: Subir PDF, Explorar y Preguntar (spec §4.3).

Uso:  uv run streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from ui import ask, explore, runtime, upload
from ui.sidebar import render_sidebar


def main() -> None:
    st.set_page_config(page_title="QA sobre tablas en PDFs", page_icon="📊", layout="wide")
    st.title("QA multiagente sobre tablas en PDFs")
    st.caption(
        "Agente de Ingesta: extrae y documenta las tablas de un PDF · "
        "Agente Analista: responde preguntas calculando sobre esas tablas."
    )
    try:
        settings = runtime.load_settings()
    except Exception as exc:  # noqa: BLE001 — p. ej. un valor inválido en el .env
        st.error(f"No se pudo leer la configuración del `.env`: {exc}")
        return

    missing_all = settings.missing_required()
    missing_ingest = settings.missing_required("ingest")
    missing_ask = settings.missing_required("ask")
    render_sidebar(settings, missing_all)
    if missing_all:
        st.warning(
            "Faltan variables en el `.env`: "
            + ", ".join(f"`{m}`" for m in missing_all)
            + ". Las pestañas que las necesitan quedan bloqueadas (Explorar funciona igual)."
        )

    tab_upload, tab_explore, tab_ask = st.tabs(["📤 Subir PDF", "🔎 Explorar", "💬 Preguntar"])
    with tab_upload:
        upload.render(settings, missing_ingest)
    with tab_explore:
        explore.render(settings)
    with tab_ask:
        ask.render(settings, missing_ask)


main()
