"""Fixtures del Analista: almacén e índice con tablas del PDF sintético, sandbox por subproceso."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from services.config import Settings
from services.table_store import TableStore
from services.vector_index import InMemoryIndex
from tests.analyst.fakes import populate


@pytest.fixture
def sub_settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(SANDBOX_BACKEND="subprocess", SANDBOX_TIMEOUT_S=20)


@pytest.fixture
def populated(tmp_path: Path) -> tuple[TableStore, InMemoryIndex]:
    return populate(tmp_path / "store")
