"""Clasificación de errores por servicio (FR-043)."""

from __future__ import annotations

import httpx
import openai
from pinecone.exceptions import UnauthorizedException

from services.llm import EmbeddingDimensionError
from services.sandbox import SandboxUnavailable
from services.vector_index import IndexDimensionError
from ui.errors import classify, format_service_error


def test_classify_by_service() -> None:
    response = httpx.Response(401, request=httpx.Request("POST", "http://proxy.test/v1"))
    assert classify(openai.AuthenticationError("bad", response=response, body=None))[0].startswith(
        "LiteLLM"
    )
    assert classify(UnauthorizedException("Invalid API Key"))[0] == "Pinecone"
    assert classify(IndexDimensionError("idx", 8, 1536))[0] == "Pinecone"
    assert classify(SandboxUnavailable("sin Docker"))[0] == "Sandbox"
    assert classify(EmbeddingDimensionError(3, 1536))[0] == "Configuración"
    assert classify(KeyError("x"))[0] == "Error inesperado"


def test_wrapped_errors_are_found_through_the_cause_chain() -> None:
    try:
        try:
            raise UnauthorizedException("Invalid API Key")
        except UnauthorizedException as inner:
            raise RuntimeError("falló el nodo") from inner
    except RuntimeError as outer:
        assert classify(outer)[0] == "Pinecone"


def test_long_messages_are_truncated() -> None:
    text = format_service_error(RuntimeError("x" * 5000), "la consulta")
    assert len(text) < 800 and text.endswith("…")
