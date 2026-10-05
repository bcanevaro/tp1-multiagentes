"""Errores de servicios externos mostrados sin tirar la app (FR-043)."""

from __future__ import annotations

from collections.abc import Iterator

import streamlit as st

from services.llm import ConfigurationError, EmbeddingDimensionError
from services.sandbox import SandboxUnavailable
from services.vector_index import IndexDimensionError

MAX_MESSAGE = 600

# Paquete raíz de la clase de la excepción -> servicio afectado.
_SERVICE_BY_PACKAGE = {
    "openai": "LiteLLM (proxy de modelos)",
    "langchain_openai": "LiteLLM (proxy de modelos)",
    "pinecone": "Pinecone",
    "docker": "Docker (sandbox)",
    "langsmith": "LangSmith",
}


def _chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def classify(exc: BaseException) -> tuple[str, str]:
    """Devuelve `(servicio, mensaje)` para una excepción de cualquier capa."""
    message = f"{type(exc).__name__}: {exc}"
    for err in _chain(exc):
        if isinstance(err, SandboxUnavailable):
            return "Sandbox", str(err)
        if isinstance(err, IndexDimensionError):
            return "Pinecone", str(err)
        if isinstance(err, EmbeddingDimensionError | ConfigurationError):
            return "Configuración", str(err)
        package = type(err).__module__.split(".")[0]
        if package in _SERVICE_BY_PACKAGE:
            return _SERVICE_BY_PACKAGE[package], f"{type(err).__name__}: {err}"
    return "Error inesperado", message


def format_service_error(exc: BaseException, during: str) -> str:
    service, message = classify(exc)
    if len(message) > MAX_MESSAGE:
        message = message[:MAX_MESSAGE] + "…"
    return f"**{service}** — falló durante {during}. {message}"


def show_service_error(exc: BaseException, during: str) -> str:
    """Muestra el error con `st.error` y devuelve el texto (para guardarlo en el historial)."""
    text = format_service_error(exc, during)
    st.error(text)
    return text
