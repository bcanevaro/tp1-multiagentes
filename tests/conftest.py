"""Fixtures compartidas: configuración aislada del `.env` y del entorno del proceso."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from services.config import Settings

_ENV_PREFIXES = ("LITELLM_", "LLM_", "EMBEDDING_", "PINECONE_", "LANGSMITH_", "SANDBOX_", "OPENAI_")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita que variables del entorno real se filtren en los tests."""
    import os

    for name in list(os.environ):
        if name.startswith(_ENV_PREFIXES):
            monkeypatch.delenv(name, raising=False)


FULL_ENV: dict[str, Any] = {
    "LITELLM_BASE_URL": "http://proxy.test/v1",
    "LITELLM_API_KEY": "test-key",
    "LLM_MODEL": "chat-model",
    "EMBEDDING_MODEL": "emb-model",
    "EMBEDDING_DIM": 8,
    "PINECONE_API_KEY": "pc-test",
    "PINECONE_INDEX_NAME": "idx-test",
    "LANGSMITH_API_KEY": "ls-test",
    "LANGSMITH_PROJECT": "proj-test",
}


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    """Crea `Settings` sin leer `.env`, con todas las variables obligatorias salvo overrides."""

    def _make(**overrides: Any) -> Settings:
        values = {**FULL_ENV, "CACHE_DIR": tmp_path / "cache", "DATA_DIR": tmp_path / "store"}
        values.update(overrides)
        return Settings(_env_file=None, **values)  # type: ignore[call-arg]

    return _make


@pytest.fixture(scope="session")
def edge_pdfs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """PDFs de casos borde generados por `scripts/make_test_fixtures.py` (una vez por sesión)."""
    from scripts.make_test_fixtures import build_all

    return build_all(tmp_path_factory.mktemp("edge_pdfs"))
