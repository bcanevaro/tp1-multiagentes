"""Índice vectorial de tablas: Pinecone en producción, memoria en tests (FR-015/064, NFR-006)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from agents.ingestion.schemas import TableMetadata, preview_markdown
from services.config import Settings, get_settings
from services.llm import ConfigurationError

MAX_METADATA_BYTES = 38_000  # NFR-006: margen sobre el límite de ~40 KB de Pinecone
MAX_ROW_HEADERS = 100
PREVIEW_ROWS = 5


def get_vector_index(settings: Settings | None = None) -> PineconeIndex:
    """Índice de Pinecone según la configuración (lo crea si no existe)."""
    settings = settings or get_settings()
    if not (settings.PINECONE_API_KEY and settings.PINECONE_INDEX_NAME and settings.EMBEDDING_DIM):
        raise ConfigurationError(
            "Faltan variables de entorno: PINECONE_API_KEY, PINECONE_INDEX_NAME o EMBEDDING_DIM"
        )
    return PineconeIndex(
        settings.PINECONE_API_KEY,
        settings.PINECONE_INDEX_NAME,
        settings.EMBEDDING_DIM,
        cloud=settings.PINECONE_CLOUD,
        region=settings.PINECONE_REGION,
    )


class IndexDimensionError(RuntimeError):
    """El índice existe con una dimensión distinta a la del modelo de embeddings (FR-064)."""

    def __init__(self, index: str, actual: int, expected: int) -> None:
        super().__init__(
            f"El índice '{index}' tiene dimensión {actual} y el modelo de embeddings {expected}"
        )


@dataclass(frozen=True)
class VectorRecord:
    id: str
    values: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Match:
    id: str
    score: float
    metadata: dict[str, Any]


class VectorIndex(Protocol):
    def upsert(self, records: list[VectorRecord]) -> None: ...

    def list_ids(self, prefix: str) -> list[str]: ...

    def delete_ids(self, ids: list[str]) -> None: ...

    def query(self, vector: list[float], top_k: int) -> list[Match]: ...


# --------------------------------------------------------------------------------------
# Texto embebido y metadatos (FR-015, spec §7.3)
# --------------------------------------------------------------------------------------


def embedding_text(meta: TableMetadata) -> str:
    """Nombre + descripción + columnas + encabezados de fila (consigna §5.2) + períodos,
    entidades y título de sección."""
    columns = "; ".join(f"{c.name}: {c.description}" for c in meta.columns)
    parts = [
        f"Tabla: {meta.name}",
        f"Descripción: {meta.description}",
        f"Columnas: {columns}",
        f"Filas: {', '.join(meta.row_headers[:MAX_ROW_HEADERS])}" if meta.row_headers else "",
        f"Períodos: {', '.join(meta.periods_covered)}" if meta.periods_covered else "",
        f"Entidades: {', '.join(meta.entities_covered)}" if meta.entities_covered else "",
        f"Sección: {meta.source.section_title}" if meta.source.section_title else "",
    ]
    return "\n".join(p for p in parts if p)


def pinecone_metadata(meta: TableMetadata, df: pd.DataFrame) -> dict[str, Any]:
    """Metadatos del registro en Pinecone (spec §7.3), recortados a ≤ 38 KB (NFR-006).

    Pinecone solo admite strings, números, booleanos y listas de strings.
    """
    base: dict[str, Any] = {
        "doc_id": meta.doc_id,
        "pdf_name": meta.source.pdf_name,
        "pages": [str(p) for p in meta.source.pages],
        "name": meta.name,
        "description": meta.description,
        "columns": [c.name for c in meta.columns],
        "row_headers": meta.row_headers[:MAX_ROW_HEADERS],
        "periods_covered": meta.periods_covered,
        "entities_covered": meta.entities_covered,
        "n_rows": meta.n_rows,
        "n_cols": meta.n_cols,
    }
    rows = PREVIEW_ROWS
    while True:
        record = {**base, "preview_markdown": preview_markdown(df, max_rows=rows)}
        if _size(record) <= MAX_METADATA_BYTES:
            return record
        if rows > 0:
            rows -= 1
            continue
        # Último recurso para tablas gigantes: achicar a la mitad la lista que más pesa.
        shrinkable = [k for k in ("row_headers", "entities_covered", "periods_covered", "columns")
                      if len(base[k]) > 1]  # fmt: skip
        if not shrinkable:
            raise ValueError(
                f"Los metadatos de {meta.table_id} no entran en {MAX_METADATA_BYTES} bytes"
            )
        key = max(shrinkable, key=lambda k: _size({k: base[k]}))
        base[key] = base[key][: len(base[key]) // 2]


def _size(record: dict[str, Any]) -> int:
    return len(json.dumps(record, ensure_ascii=False).encode("utf-8"))


# --------------------------------------------------------------------------------------
# Implementaciones
# --------------------------------------------------------------------------------------


class InMemoryIndex:
    """Índice en memoria con similitud coseno (tests y desarrollo sin red)."""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        for r in records:
            if len(r.values) != self.dimension:
                raise IndexDimensionError("memoria", self.dimension, len(r.values))
            self.records[r.id] = r

    def list_ids(self, prefix: str) -> list[str]:
        return sorted(i for i in self.records if i.startswith(prefix))

    def delete_ids(self, ids: list[str]) -> None:
        for i in ids:
            self.records.pop(i, None)

    def query(self, vector: list[float], top_k: int) -> list[Match]:
        def cosine(a: list[float], b: list[float]) -> float:
            na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
            return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0

        scored = [Match(r.id, cosine(vector, r.values), r.metadata) for r in self.records.values()]
        return sorted(scored, key=lambda m: m.score, reverse=True)[:top_k]


class PineconeIndex:
    """Índice serverless de Pinecone. Lo crea si no existe y verifica su dimensión (FR-064)."""

    def __init__(
        self,
        api_key: str,
        name: str,
        dimension: int,
        *,
        cloud: str = "aws",
        region: str = "us-east-1",
    ) -> None:
        from pinecone import Pinecone, ServerlessSpec

        self.name = name
        pc = Pinecone(api_key=api_key)
        if not pc.has_index(name):
            pc.create_index(
                name=name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud=cloud, region=region),
            )
        actual = int(pc.describe_index(name).dimension or 0)
        if actual != dimension:
            raise IndexDimensionError(name, actual, dimension)
        self._index = pc.Index(name)

    def upsert(self, records: list[VectorRecord]) -> None:
        if records:
            self._index.upsert(
                vectors=[{"id": r.id, "values": r.values, "metadata": r.metadata} for r in records],
                show_progress=False,
            )

    def list_ids(self, prefix: str) -> list[str]:
        return [str(v.id) for page in self._index.list(prefix=prefix) for v in page.vectors]

    def delete_ids(self, ids: list[str]) -> None:
        if ids:
            self._index.delete(ids=ids)

    def query(self, vector: list[float], top_k: int) -> list[Match]:
        response = self._index.query(vector=vector, top_k=top_k, include_metadata=True)
        return [Match(m.id, float(m.score), dict(m.metadata or {})) for m in response.matches]
