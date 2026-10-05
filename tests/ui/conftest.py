"""Fixtures de la UI: `AppTest` sobre `app.py` con servicios simulados (sin red ni LLM)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from agents.analyst.graph import AnalystServices
from agents.analyst.schemas import Selection
from agents.ingestion.graph import IngestionServices
from services.config import PROJECT_ROOT, Settings
from services.table_store import TableStore
from services.vector_index import InMemoryIndex
from tests.analyst.fakes import Recorder, code, cover, plan, sub
from tests.analyst.fakes import make_services as make_analyst_services
from tests.analyst.test_graph import SHARE_CODE, SHARE_COVER, SHARE_SUB
from tests.ingestion.fakes import DIM
from tests.ingestion.fakes import make_services as make_ingestion_services
from ui import runtime

APP = str(PROJECT_ROOT / "app.py")
TIMEOUT = 60


@dataclass
class UiEnv:
    """Estado compartido por la app simulada: almacén, índice y fábricas reemplazables."""

    settings: Settings
    store: TableStore
    index: InMemoryIndex
    ingestion: Callable[[Settings], IngestionServices]
    analyst: Callable[[Settings], AnalystServices]
    writer: Recorder = field(default_factory=lambda: Recorder("La proporción fue 1,15 %."))

    def app(self) -> AppTest:
        at = AppTest.from_file(APP, default_timeout=TIMEOUT)
        at.run()
        return at


def share_analyst(env: UiEnv, planner: Any = None) -> AnalystServices:
    return make_analyst_services(
        env.store,
        env.index,
        env.settings,
        planner=planner or Recorder(plan(SHARE_SUB)),
        selector=Recorder(Selection(coverage=[SHARE_COVER])),
        coder=Recorder(code(SHARE_CODE)),
        writer=env.writer,
    )


def uncovered_analyst(env: UiEnv) -> AnalystServices:
    q = sub("q1", "Resultado financiero en 2024", periods=["2024"])
    return make_analyst_services(
        env.store,
        env.index,
        env.settings,
        planner=Recorder(plan(q)),
        selector=Recorder(Selection(coverage=[cover("q1", ["sint-t01"], ["2024"])])),
        coder=Recorder(code(SHARE_CODE)),
        writer=env.writer,
    )


@pytest.fixture
def ui_env(
    tmp_path: Path, make_settings: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch
) -> UiEnv:
    from tests.analyst.fakes import populate

    data_dir = tmp_path / "store"
    store, index = populate(data_dir)
    settings = make_settings(DATA_DIR=data_dir, SANDBOX_BACKEND="subprocess", SANDBOX_TIMEOUT_S=20)
    env = UiEnv(
        settings=settings,
        store=store,
        index=index,
        ingestion=lambda s: make_ingestion_services(data_dir, index=index),
        analyst=lambda s: share_analyst(env),
    )
    install(env, monkeypatch)
    assert index.dimension == DIM
    return env


def install(env: UiEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "load_settings", lambda: env.settings)
    monkeypatch.setattr(runtime, "ingestion_services", lambda s: env.ingestion(s))
    monkeypatch.setattr(runtime, "analyst_services", lambda s: env.analyst(s))
    monkeypatch.setattr(runtime, "table_store", lambda s: env.store)
