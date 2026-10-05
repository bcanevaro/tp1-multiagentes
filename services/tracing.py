"""Configuración de ejecución: cada corrida de un agente es una traza legible en LangSmith."""

from __future__ import annotations

import warnings
from types import SimpleNamespace
from typing import Any, Literal, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig

AgentKind = Literal["ingest", "analyst"]

ANALYST_LABEL_MAX = 60


def run_name(kind: AgentKind, label: str) -> str:
    """`ingest:<nombre del pdf>` o `analyst:<primeros 60 caracteres de la pregunta>` (FR-061)."""
    clean = " ".join(label.split())
    if kind == "analyst":
        clean = clean[:ANALYST_LABEL_MAX]
    return f"{kind}:{clean}"


def run_config(kind: AgentKind, label: str, **metadata: Any) -> RunnableConfig:
    """Arma el `RunnableConfig` para invocar un grafo con nombre, tags y metadatos de traza.

    Los metadatos con valor `None` se omiten.
    """
    return RunnableConfig(
        run_name=run_name(kind, label),
        tags=[kind],
        metadata={k: v for k, v in metadata.items() if v is not None},
    )


def trace_url(run_id: UUID, project: str | None) -> str:
    """Link a la traza en LangSmith, o "" si no se puede armar (sin red, sin clave…).

    No consulta la corrida: arma la URL con el id que se le pasó al grafo (`config["run_id"]`)
    y el id del proyecto, así funciona aunque la traza todavía se esté subiendo.
    """
    if not project:
        return ""
    try:
        from langsmith import Client

        client = Client()
        project_id = client.read_project(project_name=project).id
        run = SimpleNamespace(id=run_id, session_id=project_id)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # get_run_url está marcado como deprecado
            return str(client.get_run_url(run=cast(Any, run), project_id=project_id))
    except Exception:  # noqa: BLE001 — el link es opcional
        return ""


def flush_traces() -> None:
    """Espera a que se suban las trazas pendientes (antes de terminar un script)."""
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()
    except Exception:  # noqa: BLE001
        pass
