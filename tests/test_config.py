from __future__ import annotations

from collections.abc import Callable

from services.config import Settings


def test_complete_settings_have_no_missing(make_settings: Callable[..., Settings]) -> None:
    assert make_settings().missing_required() == []


def test_missing_pinecone_key_is_reported(make_settings: Callable[..., Settings]) -> None:
    """VC-065b (parte de configuración): falta PINECONE_API_KEY."""
    settings = make_settings(PINECONE_API_KEY=None)
    assert "PINECONE_API_KEY" in settings.missing_required()
    assert "PINECONE_API_KEY" in settings.missing_required("ingest")
    assert "PINECONE_API_KEY" in settings.missing_required("ask")
    assert settings.missing_required("explore") == []


def test_blank_values_count_as_missing(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings(LITELLM_API_KEY="   ", LLM_MODEL="")
    assert {"LITELLM_API_KEY", "LLM_MODEL"} <= set(settings.missing_required())


def test_defaults_match_spec(make_settings: Callable[..., Settings]) -> None:
    s = make_settings()
    assert s.SANDBOX_BACKEND == "auto"
    assert s.SANDBOX_TIMEOUT_S == 30
    assert s.INGEST_MAX_RETRIES == 2
    assert s.ANALYST_MAX_RETRIES == 3
    assert s.RETRIEVAL_K == 6
    assert s.LANGSMITH_TRACING is True
