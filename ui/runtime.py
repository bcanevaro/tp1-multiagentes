"""Acceso de la UI a la configuración y a los servicios.

Todo pasa por estas funciones para que los tests (`streamlit.testing.v1.AppTest`) puedan
reemplazarlas por fakes con `monkeypatch`, sin red ni LLM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.config import Settings, get_settings
from services.table_store import TableStore

if TYPE_CHECKING:
    from agents.analyst.graph import AnalystServices
    from agents.ingestion.graph import IngestionServices


def load_settings() -> Settings:
    return get_settings()


def ingestion_services(settings: Settings) -> IngestionServices:
    from agents.ingestion.graph import default_services

    return default_services(settings)


def analyst_services(settings: Settings) -> AnalystServices:
    from agents.analyst.graph import default_services

    return default_services(settings)


def table_store(settings: Settings) -> TableStore:
    return TableStore(settings.data_dir)


def sandbox_label(settings: Settings) -> str:
    """Backend del sandbox que se usaría ahora (FR-044)."""
    from services.sandbox import SandboxUnavailable, resolve_backend

    try:
        backend = resolve_backend(settings.SANDBOX_BACKEND, settings.SANDBOX_IMAGE)
    except SandboxUnavailable:
        return "docker (NO disponible)"
    if settings.SANDBOX_BACKEND == "auto":
        return f"{backend} (automático)"
    return backend
