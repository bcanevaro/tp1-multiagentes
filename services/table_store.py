"""Almacén local de tablas: un Parquet + un JSON de metadatos por `table_id` (FR-014, BR-006).

Estructura de `DATA_DIR` (por defecto `data/store/`):

    tables/{table_id}.parquet   datos normalizados
    tables/{table_id}.json      TableMetadata
    pdfs/{doc_id}.pdf           copia del PDF original
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from agents.ingestion.schemas import TableMetadata


class TableStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir
        self.tables_dir = data_dir / "tables"
        self.pdfs_dir = data_dir / "pdfs"

    # --- rutas ---------------------------------------------------------------------

    def parquet_path(self, table_id: str) -> Path:
        return self.tables_dir / f"{table_id}.parquet"

    def metadata_path(self, table_id: str) -> Path:
        return self.tables_dir / f"{table_id}.json"

    def pdf_path(self, doc_id: str) -> Path:
        return self.pdfs_dir / f"{doc_id}.pdf"

    # --- escritura -----------------------------------------------------------------

    def save(self, metadata: TableMetadata, df: pd.DataFrame) -> None:
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(self.parquet_path(metadata.table_id), index=False)
        self.metadata_path(metadata.table_id).write_text(
            metadata.model_dump_json(indent=2), encoding="utf-8"
        )

    def save_pdf(self, doc_id: str, data: bytes) -> Path:
        self.pdfs_dir.mkdir(parents=True, exist_ok=True)
        path = self.pdf_path(doc_id)
        path.write_bytes(data)
        return path

    def delete_doc(self, doc_id: str) -> list[str]:
        """Borra todas las tablas de un documento (no el PDF). Devuelve los `table_id` borrados."""
        removed: list[str] = []
        if not self.tables_dir.exists():
            return removed
        for meta_file in sorted(self.tables_dir.glob(f"{doc_id}-t*.json")):
            table_id = meta_file.stem
            meta_file.unlink()
            self.parquet_path(table_id).unlink(missing_ok=True)
            removed.append(table_id)
        return removed

    # --- lectura -------------------------------------------------------------------

    def load_df(self, table_id: str) -> pd.DataFrame:
        return pd.read_parquet(self.parquet_path(table_id))

    def load_metadata(self, table_id: str) -> TableMetadata:
        return TableMetadata.model_validate_json(
            self.metadata_path(table_id).read_text(encoding="utf-8")
        )

    def list_tables(self, doc_id: str | None = None) -> list[TableMetadata]:
        if not self.tables_dir.exists():
            return []
        pattern = f"{doc_id}-t*.json" if doc_id else "*.json"
        return [self.load_metadata(p.stem) for p in sorted(self.tables_dir.glob(pattern))]
