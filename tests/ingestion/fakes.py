"""Fakes de los servicios externos de la Ingesta (LLM, embeddings, índice)."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_core.runnables import RunnableConfig

from agents.ingestion.graph import IngestionServices
from agents.ingestion.schemas import ColumnAnnotation, TableAnnotation, TableDraft
from services.table_store import TableStore
from services.vector_index import InMemoryIndex

DIM = 8


def good_annotation(draft: TableDraft) -> TableAnnotation:
    """Anotación válida construida a partir de la tabla (lo que haría un LLM obediente)."""
    caption = draft.context.caption or f"Tabla de la página {draft.pages[0]}"
    text_cols = draft.text_columns()
    return TableAnnotation(
        name=caption.split(". ", 1)[-1][:80] or "Datos de la tabla",
        description=f"Tabla extraída de la página {draft.pages[0]}. Contiene {draft.n_rows} filas.",
        columns=[
            ColumnAnnotation(
                name=c,
                description=f"Columna {c}.",
                unit="" if t == "str" else "desconocida",
                scale="desconocida",
                value_type="texto" if t == "str" else "unknown",
            )
            for c, t in zip(draft.columns, draft.dtypes, strict=True)
        ],
        row_header_column=text_cols[0] if text_cols else None,
        periods_covered=[],
        entities_covered=[],
        notes="",
    )


def bad_annotation(draft: TableDraft) -> TableAnnotation:
    """Anotación inválida: le falta una columna y el nombre es genérico (BR-001, BR-003)."""
    good = good_annotation(draft)
    return good.model_copy(update={"name": "Tabla 1", "columns": good.columns[:-1]})


class FakeAnnotator:
    """Responde bien salvo para las tablas de `failures` (índice -> intentos que falla)."""

    def __init__(self, failures: dict[int, int] | None = None) -> None:
        self.failures = failures or {}
        self.calls: Counter[int] = Counter()
        self.prompt_errors: dict[int, list[list[str]]] = {}

    def __call__(
        self, jobs: list[tuple[TableDraft, list[str]]], pdf_name: str, config: RunnableConfig | None
    ) -> list[TableAnnotation | Exception]:
        out: list[TableAnnotation | Exception] = []
        for draft, errors in jobs:
            self.calls[draft.index] += 1
            self.prompt_errors.setdefault(draft.index, []).append(errors)
            if self.calls[draft.index] <= self.failures.get(draft.index, 0):
                out.append(bad_annotation(draft))
            else:
                out.append(good_annotation(draft))
        return out


class HashEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [b / 255 + 0.01 for b in digest[:DIM]]


def make_services(
    data_dir: Path,
    annotator: FakeAnnotator | None = None,
    index: InMemoryIndex | None = None,
    index_factory: Callable[[], InMemoryIndex] | None = None,
    max_retries: int = 2,
) -> IngestionServices:
    idx = index or InMemoryIndex(DIM)
    return IngestionServices(
        annotate=annotator or FakeAnnotator(),
        embeddings_factory=HashEmbeddings,
        index_factory=index_factory or (lambda: idx),
        store=TableStore(data_dir),
        max_retries=max_retries,
    )
