"""Fábricas de modelos de chat y embeddings contra el proxy LiteLLM, con caché local opcional.

Todas las llamadas a LLM y embeddings del sistema pasan por estas fábricas, así se
garantiza que usan el proxy de la universidad (consigna §3.2).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeVar

from langchain_core._api import LangChainBetaWarning
from langchain_core.caches import RETURN_VAL_TYPE, BaseCache
from langchain_core.embeddings import Embeddings
from langchain_core.globals import set_llm_cache
from langchain_core.language_models import BaseChatModel
from langchain_core.load import dumps, loads
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel

from services.config import Settings, get_settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ConfigurationError(RuntimeError):
    """Falta configuración necesaria para crear un cliente."""


class EmbeddingDimensionError(RuntimeError):
    """La dimensión real del modelo de embeddings no coincide con EMBEDDING_DIM (FR-065)."""

    def __init__(self, actual: int, expected: int | None) -> None:
        self.actual = actual
        self.expected = expected
        super().__init__(
            f"El modelo de embeddings devuelve vectores de dimensión {actual}, "
            f"pero EMBEDDING_DIM={expected}. Corregí EMBEDDING_DIM en el .env."
        )


# --------------------------------------------------------------------------------------
# Cachés locales (NFR-009)
# --------------------------------------------------------------------------------------


class SQLiteLLMCache(BaseCache):
    """Caché de respuestas del LLM en SQLite, indexada por prompt + configuración del modelo."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.commit()

    @staticmethod
    def _key(prompt: str, llm_string: str) -> str:
        return hashlib.sha256(f"{llm_string}\x00{prompt}".encode()).hexdigest()

    def lookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM llm_cache WHERE key = ?", (self._key(prompt, llm_string),)
            ).fetchone()
        if row is None:
            return None
        with warnings.catch_warnings():
            # `loads` está marcada como beta en langchain-core; el formato lo escribimos nosotros.
            warnings.simplefilter("ignore", LangChainBetaWarning)
            return [loads(item, allowed_objects="core") for item in json.loads(row[0])]

    def update(self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE) -> None:
        value = json.dumps([dumps(gen) for gen in return_val])
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, value) VALUES (?, ?)",
                (self._key(prompt, llm_string), value),
            )
            self._conn.commit()

    def clear(self, **kwargs: Any) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM llm_cache")
            self._conn.commit()


class CachedEmbeddings(Embeddings):
    """Envuelve un modelo de embeddings y guarda cada vector en SQLite por (modelo, texto)."""

    def __init__(self, inner: Embeddings, model_name: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._inner = inner
        self._model = model_name
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS emb_cache (key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.commit()

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self._model}\x00{text}".encode()).hexdigest()

    def _get(self, text: str) -> list[float] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM emb_cache WHERE key = ?", (self._key(text),)
            ).fetchone()
        return None if row is None else [float(x) for x in json.loads(row[0])]

    def _put(self, text: str, vector: Sequence[float]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO emb_cache (key, value) VALUES (?, ?)",
                (self._key(text), json.dumps(list(vector))),
            )
            self._conn.commit()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = [self._get(t) for t in texts]
        pending = [i for i, r in enumerate(results) if r is None]
        if pending:
            fresh = self._inner.embed_documents([texts[i] for i in pending])
            for i, vector in zip(pending, fresh, strict=True):
                self._put(texts[i], vector)
                results[i] = list(vector)
        return [r for r in results if r is not None]

    def embed_query(self, text: str) -> list[float]:
        cached = self._get(text)
        if cached is not None:
            return cached
        vector = self._inner.embed_query(text)
        self._put(text, vector)
        return list(vector)


# --------------------------------------------------------------------------------------
# Fábricas
# --------------------------------------------------------------------------------------

_cache_enabled = False


def enable_llm_cache(settings: Settings | None = None) -> bool:
    """Activa la caché global del LLM si `LLM_CACHE=true`. Devuelve si quedó activa."""
    global _cache_enabled
    settings = settings or get_settings()
    if settings.LLM_CACHE and not _cache_enabled:
        set_llm_cache(SQLiteLLMCache(settings.cache_dir / "llm_cache.sqlite"))
        _cache_enabled = True
    return _cache_enabled


def _require(settings: Settings, *names: str) -> None:
    missing = [n for n in names if not getattr(settings, n)]
    if missing:
        raise ConfigurationError(f"Faltan variables de entorno: {', '.join(missing)}")


def get_chat_model(settings: Settings | None = None, temperature: float = 0.0) -> BaseChatModel:
    """Modelo de chat del proxy LiteLLM (API compatible con OpenAI)."""
    settings = settings or get_settings()
    _require(settings, "LITELLM_BASE_URL", "LITELLM_API_KEY", "LLM_MODEL")
    enable_llm_cache(settings)
    return ChatOpenAI(
        base_url=settings.LITELLM_BASE_URL,
        api_key=settings.LITELLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=temperature,
        timeout=120,
        max_retries=2,
    )


def with_structured(
    llm: BaseChatModel, schema: type[SchemaT], settings: Settings | None = None
) -> Runnable[Any, SchemaT]:
    """Envuelve el modelo para que devuelva instancias de `schema` (salida estructurada).

    El método (`function_calling`, `json_schema` o `json_mode`) sale de
    `LLM_STRUCTURED_METHOD`, que se elige con `scripts/check_services.py`.
    """
    settings = settings or get_settings()
    return llm.with_structured_output(schema, method=settings.LLM_STRUCTURED_METHOD)  # type: ignore[return-value]


def get_embeddings(settings: Settings | None = None) -> Embeddings:
    """Modelo de embeddings del proxy LiteLLM, con caché local si `LLM_CACHE=true`."""
    settings = settings or get_settings()
    _require(settings, "LITELLM_BASE_URL", "LITELLM_API_KEY", "EMBEDDING_MODEL")
    inner = OpenAIEmbeddings(
        base_url=settings.LITELLM_BASE_URL,  # type: ignore[call-arg]
        api_key=settings.LITELLM_API_KEY,
        model=settings.EMBEDDING_MODEL,
        # El proxy puede servir modelos que no son de OpenAI: mandamos texto, no tokens de tiktoken.
        check_embedding_ctx_length=False,
    )
    if settings.LLM_CACHE:
        return CachedEmbeddings(
            inner, settings.EMBEDDING_MODEL or "", settings.cache_dir / "embeddings_cache.sqlite"
        )
    return inner


def check_embedding_dim(embeddings: Embeddings, expected: int | None) -> int:
    """Embebe un texto de prueba y verifica que la dimensión coincida con `expected` (FR-065).

    Devuelve la dimensión real. Lanza `EmbeddingDimensionError` si no coincide.
    """
    actual = len(embeddings.embed_query("prueba de dimensión"))
    if expected is None or actual != expected:
        raise EmbeddingDimensionError(actual, expected)
    return actual
