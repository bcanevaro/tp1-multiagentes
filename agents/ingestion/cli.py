"""Ingesta desde la línea de comandos.

Uso:  uv run python -m agents.ingestion.cli <archivo.pdf> [<otro.pdf> ...]

Muestra el progreso nodo por nodo (FR-018) y, al final, el resumen de cada tabla indexada
(FR-017) y los avisos.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from agents.ingestion.graph import IngestionState, stream_ingest
from agents.ingestion.schemas import TableMetadata
from services.config import get_settings
from services.table_store import TableStore


def print_summary(meta: TableMetadata, store: TableStore) -> None:
    pages = ", ".join(map(str, meta.source.pages))
    print(f"\n■ {meta.name}  [{meta.table_id}]  páginas {pages}  ({meta.n_rows}×{meta.n_cols})")
    print(f"  {meta.description}")
    print("  Columnas: " + "; ".join(f"{c.name} ({c.unit or 'texto'})" for c in meta.columns))
    if meta.row_headers:
        more = "…" if len(meta.row_headers) > 8 else ""
        print(f"  Filas ({meta.row_header_column}): {', '.join(meta.row_headers[:8])}{more}")
    df = store.load_df(meta.table_id)
    print("  Vista previa:")
    for line in df.head(5).to_string(max_colwidth=25).splitlines():
        print(f"    {line}")


def ingest(path: Path) -> int:
    settings = get_settings()
    missing = settings.missing_required("ingest")
    if missing:
        print(f"Faltan variables en el .env: {', '.join(missing)}")
        return 2
    start = time.perf_counter()
    final: IngestionState = {}
    warnings: list[str] = []
    print(f"Ingiriendo {path.name}…")
    for _node, update in stream_ingest(path, settings=settings):
        for line in update.get("log", []):
            print(f"  [{time.perf_counter() - start:5.1f}s] {line}")
        warnings += update.get("warnings", [])
        final.update(update)
    if final.get("error"):
        print(f"\nERROR: {final['error']}")
    store = TableStore(settings.data_dir)
    for meta in final.get("indexed", []):
        print_summary(meta, store)
    if warnings:
        print("\nAvisos:")
        for w in dict.fromkeys(warnings):
            print(f"  - {w}")
    print(f"\nTiempo total: {time.perf_counter() - start:.1f} s")
    if final.get("indexed"):
        report_index(final["doc_id"])
    return 1 if final.get("error") else 0


def report_index(doc_id: str) -> None:
    """Cuenta los vectores del documento en Pinecone (para verificar la idempotencia, FR-016)."""
    from services.vector_index import get_vector_index

    time.sleep(3)  # Pinecone serverless tarda unos segundos en reflejar los upserts
    ids = get_vector_index().list_ids(f"{doc_id}-t")
    print(f"Pinecone: {len(ids)} vectores del documento {doc_id}: {', '.join(sorted(ids))}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    return max(ingest(Path(arg)) for arg in argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
