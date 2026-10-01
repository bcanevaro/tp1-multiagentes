"""Configuración de ejecución: cada corrida de un agente es una traza legible en LangSmith."""

from __future__ import annotations

from typing import Any, Literal

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
