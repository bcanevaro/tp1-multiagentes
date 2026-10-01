"""Configuración tipada del sistema, cargada desde variables de entorno y `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SandboxBackend = Literal["auto", "docker", "subprocess"]
StructuredMethod = Literal["function_calling", "json_schema", "json_mode"]
Feature = Literal["ingest", "ask", "explore"]

# Variables obligatorias (spec §7.1) y qué funcionalidades las necesitan (FR-045).
_LLM_VARS = ("LITELLM_BASE_URL", "LITELLM_API_KEY", "LLM_MODEL")
_EMBEDDING_VARS = ("EMBEDDING_MODEL", "EMBEDDING_DIM")
_PINECONE_VARS = ("PINECONE_API_KEY", "PINECONE_INDEX_NAME")
_LANGSMITH_VARS = ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT")

REQUIRED_BY_FEATURE: dict[Feature, tuple[str, ...]] = {
    "ingest": _LLM_VARS + _EMBEDDING_VARS + _PINECONE_VARS + _LANGSMITH_VARS,
    "ask": _LLM_VARS + _EMBEDDING_VARS + _PINECONE_VARS + _LANGSMITH_VARS,
    "explore": (),
}
REQUIRED_VARS: tuple[str, ...] = tuple(
    dict.fromkeys(v for vars_ in REQUIRED_BY_FEATURE.values() for v in vars_)
)


class Settings(BaseSettings):
    """Todas las variables de entorno del sistema (spec §7.1)."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Proxy LiteLLM
    LITELLM_BASE_URL: str | None = None
    LITELLM_API_KEY: str | None = None
    LLM_MODEL: str | None = None
    EMBEDDING_MODEL: str | None = None
    EMBEDDING_DIM: int | None = None
    # Método de salida estructurada que soporta el modelo del proxy (spec A-3).
    LLM_STRUCTURED_METHOD: StructuredMethod = "function_calling"

    # Pinecone
    PINECONE_API_KEY: str | None = None
    PINECONE_INDEX_NAME: str | None = "mas-2026s2-tables"

    # LangSmith
    LANGSMITH_TRACING: bool = True
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str | None = None

    # Sandbox
    SANDBOX_BACKEND: SandboxBackend = "auto"
    SANDBOX_TIMEOUT_S: int = Field(default=30, ge=1, le=600)

    # Agentes
    INGEST_MAX_RETRIES: int = Field(default=2, ge=0, le=10)
    ANALYST_MAX_RETRIES: int = Field(default=3, ge=0, le=10)
    RETRIEVAL_K: int = Field(default=6, ge=1, le=50)

    # Desarrollo
    LLM_CACHE: bool = True
    DATA_DIR: Path = Path("data/store")
    CACHE_DIR: Path = Path(".cache")

    def missing_required(self, feature: Feature | None = None) -> list[str]:
        """Devuelve las variables obligatorias ausentes o vacías.

        Si se indica `feature`, solo considera las variables que esa funcionalidad necesita.
        """
        names = REQUIRED_VARS if feature is None else REQUIRED_BY_FEATURE[feature]
        missing: list[str] = []
        for name in names:
            value = getattr(self, name)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(name)
        return missing

    def resolve_path(self, path: Path) -> Path:
        """Resuelve rutas relativas contra la raíz del proyecto."""
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def data_dir(self) -> Path:
        return self.resolve_path(self.DATA_DIR)

    @property
    def cache_dir(self) -> Path:
        return self.resolve_path(self.CACHE_DIR)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la configuración global.

    También vuelca `.env` a `os.environ` (sin pisar variables ya definidas), porque
    LangSmith y LangChain leen `LANGSMITH_*` directamente del entorno del proceso.
    """
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return Settings()
