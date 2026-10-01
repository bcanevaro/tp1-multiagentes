from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration

from services.config import Settings
from services.llm import (
    CachedEmbeddings,
    ConfigurationError,
    EmbeddingDimensionError,
    SQLiteLLMCache,
    check_embedding_dim,
    get_chat_model,
)


class _FakeEmbeddings(Embeddings):
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += len(texts)
        return [[float(len(t))] * self.dim for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def test_dimension_mismatch_reports_both_values() -> None:
    """VC-065d."""
    with pytest.raises(EmbeddingDimensionError) as err:
        check_embedding_dim(_FakeEmbeddings(dim=3), expected=1536)
    assert "3" in str(err.value) and "1536" in str(err.value)


def test_dimension_match_returns_dim() -> None:
    assert check_embedding_dim(_FakeEmbeddings(dim=8), expected=8) == 8


def test_cached_embeddings_do_not_recompute(tmp_path: Path) -> None:
    """NFR-009: repetir un texto no vuelve a llamar al modelo."""
    inner = _FakeEmbeddings(dim=4)
    cached = CachedEmbeddings(inner, "m", tmp_path / "emb.sqlite")
    first = cached.embed_documents(["a", "bb", "a"])
    calls_after_first = inner.calls
    second = cached.embed_documents(["bb", "a"])
    assert inner.calls == calls_after_first
    assert second == [first[1], first[0]]
    assert cached.embed_query("a") == first[0]


def test_sqlite_llm_cache_roundtrip(tmp_path: Path) -> None:
    cache = SQLiteLLMCache(tmp_path / "llm.sqlite")
    assert cache.lookup("p", "llm") is None
    gen = ChatGeneration(message=AIMessage(content="hola"))
    cache.update("p", "llm", [gen])
    hit = cache.lookup("p", "llm")
    assert hit is not None and hit[0].text == "hola"
    assert cache.lookup("p", "otro-llm") is None


def test_chat_model_requires_proxy_config(make_settings: Callable[..., Settings]) -> None:
    with pytest.raises(ConfigurationError, match="LITELLM_BASE_URL"):
        get_chat_model(make_settings(LITELLM_BASE_URL=None))


def test_chat_model_points_to_proxy(make_settings: Callable[..., Settings]) -> None:
    llm = get_chat_model(make_settings(LLM_CACHE=False))
    assert llm.openai_api_base == "http://proxy.test/v1"  # type: ignore[attr-defined]
    assert llm.model_name == "chat-model"  # type: ignore[attr-defined]
