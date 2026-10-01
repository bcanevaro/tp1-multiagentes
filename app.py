"""Punto de entrada de Streamlit (versión inicial: muestra el estado de la configuración)."""

from __future__ import annotations

import streamlit as st

from services.config import get_settings


def main() -> None:
    st.set_page_config(page_title="QA sobre tablas en PDFs", layout="wide")
    st.title("QA multiagente sobre tablas en PDFs")
    st.info("La aplicación está en construcción: por ahora solo verifica la configuración.")

    settings = get_settings()
    missing = settings.missing_required()
    if missing:
        items = "\n".join(f"- `{m}`" for m in missing)
        st.error(f"Faltan variables de entorno en el `.env`:\n\n{items}")
    else:
        st.success("La configuración está completa.")


if __name__ == "__main__":
    main()
