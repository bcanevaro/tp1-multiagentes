"""Exporta los diagramas Mermaid de los dos grafos con `draw_mermaid()` de LangGraph.

Uso:  uv run python scripts/export_graphs.py

Escribe `docs/graphs/ingestion.mmd` y `docs/graphs/analyst.mmd`. No necesita `.env` ni red:
los grafos se construyen con servicios vacíos (solo se dibuja la estructura).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.analyst.graph import AnalystServices, build_analyst_graph  # noqa: E402
from agents.ingestion.graph import IngestionServices, build_ingestion_graph  # noqa: E402
from services.table_store import TableStore  # noqa: E402

OUT = ROOT / "docs" / "graphs"


def _unused(*_: Any) -> Any:
    raise RuntimeError("solo para dibujar el grafo")


def mermaid_diagrams() -> dict[str, str]:
    store = TableStore(ROOT / "data" / "store")
    ingestion = build_ingestion_graph(
        IngestionServices(
            annotate=_unused,
            embeddings_factory=_unused,
            index_factory=_unused,
            store=store,
            max_retries=2,
        )
    )
    analyst = build_analyst_graph(
        AnalystServices(
            plan=_unused,
            select=_unused,
            code=_unused,
            write=_unused,
            embeddings_factory=_unused,
            index_factory=_unused,
            store=store,
            run_code=_unused,
        )
    )
    return {
        "ingestion": ingestion.get_graph().draw_mermaid(),
        "analyst": analyst.get_graph().draw_mermaid(),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in mermaid_diagrams().items():
        (OUT / f"{name}.mmd").write_text(text, encoding="utf-8")
        print(f"--- {name} ---\n{text}")


if __name__ == "__main__":
    main()
