"""Fixtures del sandbox: una tabla Parquet de prueba y configuración sin `.env`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from services.config import Settings
from services.sandbox.backends import docker_status


@pytest.fixture
def table(tmp_path: Path) -> dict[str, Path]:
    path = tmp_path / "doc-t01.parquet"
    pd.DataFrame(
        {"Departamento": ["Capital", "Norte", "Sur"], "Población": [612450.0, 184300.0, 71215.0]}
    ).to_parquet(path, index=False)
    return {"doc-t01": path}


@pytest.fixture
def sub_settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(SANDBOX_BACKEND="subprocess", SANDBOX_TIMEOUT_S=20)


def docker_ready() -> bool:
    return docker_status("mas-tp-sandbox")[0]
