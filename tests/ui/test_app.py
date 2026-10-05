"""UI Streamlit con `AppTest` y servicios simulados.

VC-065b, VC-065, VC-063, VC-064, VC-002/VC-002b/VC-002c; además subir → explorar → preguntar
(VC-022, VC-023, VC-061 y VC-062 en versión simulada; la versión real es [usuario]).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import openai
import pytest
from pinecone.exceptions import UnauthorizedException
from streamlit.testing.v1 import AppTest

from agents.analyst.schemas import QueryPlan
from agents.ingestion.graph import NO_TABLES_MESSAGE
from services.config import PROJECT_ROOT
from tests.analyst.fakes import Recorder, plan
from tests.analyst.test_graph import SHARE_SUB
from tests.ingestion.fakes import make_services as make_ingestion_services
from tests.ui.conftest import UiEnv, share_analyst, uncovered_analyst

SAMPLE_PDF = PROJECT_ROOT / "data" / "sample_pdfs" / "informe_sintetico.pdf"
SECRETS = ("test-key", "pc-test", "ls-test")


def texts(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [e.value for e in at.error]
    parts += [w.value for w in at.warning] + [c.value for c in at.caption]
    parts += [s.value for s in at.success]
    return "\n".join(str(p) for p in parts)


def upload(at: AppTest, path: Path, name: str | None = None) -> AppTest:
    at.file_uploader(key="upload_file").set_value(
        (name or path.name, path.read_bytes(), "application/pdf")
    ).run()
    at.button(key="upload_go").click().run()
    return at


def ask(at: AppTest, question: str) -> AppTest:
    at.chat_input(key="ask_input").set_value(question).run()
    return at


def auth_error() -> openai.AuthenticationError:
    response = httpx.Response(401, request=httpx.Request("POST", "http://proxy.test/v1/chat"))
    return openai.AuthenticationError("Invalid API key", response=response, body=None)


# --------------------------------------------------------------------------------------
# Configuración (FR-044, FR-045)
# --------------------------------------------------------------------------------------


def test_vc065b_missing_pinecone_key_blocks_upload_and_ask(ui_env: UiEnv) -> None:
    ui_env.settings = ui_env.settings.model_copy(update={"PINECONE_API_KEY": None})
    at = ui_env.app()
    assert not at.exception
    assert "PINECONE_API_KEY" in at.warning[0].value
    assert at.file_uploader(key="upload_file").disabled
    assert at.button(key="upload_go").disabled
    assert at.chat_input(key="ask_input").disabled
    assert at.selectbox(key="example").disabled
    assert any("PINECONE_API_KEY" in e.value for e in at.sidebar.error)
    # Explorar no necesita configuración: sigue mostrando las tablas
    assert "Finanzas del sector público provincial" in texts(at)


def test_vc065_sidebar_shows_configuration_without_keys(ui_env: UiEnv) -> None:
    at = ui_env.app()
    sidebar = "\n".join(m.value for m in at.sidebar.markdown)
    for expected in ("chat-model", "emb-model", "idx-test", "subprocess", "proj-test"):
        assert expected in sidebar
    everything = sidebar + texts(at)
    assert not any(secret in everything for secret in SECRETS)


def test_invalid_env_value_shows_error_instead_of_crashing(
    ui_env: UiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ui import runtime

    def broken() -> Any:
        raise ValueError("EMBEDDING_DIM: Input should be a valid integer")

    monkeypatch.setattr(runtime, "load_settings", broken)
    at = ui_env.app()
    assert not at.exception
    assert "EMBEDDING_DIM" in at.error[0].value


# --------------------------------------------------------------------------------------
# Subir PDF (FR-040, FR-017, FR-018) y Explorar (FR-041)
# --------------------------------------------------------------------------------------


def test_upload_shows_progress_summary_and_feeds_explore(ui_env: UiEnv) -> None:
    at = upload(ui_env.app(), SAMPLE_PDF)
    assert not at.exception
    status = at.status[0]
    assert "ingesta terminada" in status.label
    progress = "\n".join(m.value for m in status.markdown)
    nodes = [
        "load_pdf",
        "extract_tables",
        "merge_continuations",
        "collect_context",
        "enrich",
        "validate",
        "persist_and_index",
    ]
    positions = [progress.index(n) for n in nodes]
    assert positions == sorted(positions)  # VC-023: una línea por nodo, en orden
    assert "6 tabla(s) de informe_sintetico.pdf indexadas" in at.success[0].value
    body = texts(at)
    for element in ("Columnas:", "Filas (", "Páginas "):  # VC-022 (FR-017)
        assert body.count(element) >= 6
    assert len(at.dataframe) >= 6  # vista previa de cada tabla
    # Al volver a correr (otra interacción), el resultado sigue visible con el progreso
    at.run()
    assert "Progreso de la ingesta" in "\n".join(e.label for e in at.expander)
    # VC-061 (simulado): Explorar agrupa por documento; el PDF ingerido aparece como grupo
    groups = [m.value for m in at.markdown if m.value.startswith("### 📄")]
    assert any("informe_sintetico.pdf" in g for g in groups)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("solo_imagen.pdf", "no tiene capa de texto"),  # VC-002 (FR-002)
        ("solo_texto.pdf", NO_TABLES_MESSAGE),  # VC-002b (FR-019)
        ("no_es_pdf.pdf", "No se pudo abrir el PDF"),  # VC-002c (FR-019b)
        ("protegido.pdf", "No se pudo abrir el PDF"),  # VC-002c
    ],
)
def test_vc002_invalid_pdfs_show_messages(
    ui_env: UiEnv, edge_pdfs: dict[str, Path], name: str, expected: str
) -> None:
    at = upload(ui_env.app(), edge_pdfs[name])
    assert not at.exception
    errors = "\n".join(e.value for e in at.error)
    assert expected.lower() in errors.lower()
    assert not at.success


def test_vc064_pinecone_error_is_shown_and_app_survives(ui_env: UiEnv, tmp_path: Path) -> None:
    def failing_index() -> Any:
        raise UnauthorizedException("Invalid API Key")

    ui_env.ingestion = lambda s: make_ingestion_services(
        ui_env.settings.data_dir, index_factory=failing_index
    )
    at = upload(ui_env.app(), SAMPLE_PDF)
    assert not at.exception
    assert any("Pinecone" in e.value and "Invalid API Key" in e.value for e in at.error)
    ask(at, "¿Qué proporción…?")  # la sesión sigue usable
    assert not at.exception and at.status[-1].label.startswith("Listo")


# --------------------------------------------------------------------------------------
# Preguntar (FR-042, FR-043)
# --------------------------------------------------------------------------------------


def test_two_questions_keep_history_with_all_elements(ui_env: UiEnv) -> None:
    at = ask(ui_env.app(), "¿Qué proporción del gasto fue ciencia y tecnología en 2023?")
    ui_env.analyst = lambda s: uncovered_analyst(ui_env)
    ask(at, "¿Cuál fue el resultado financiero en 2024?")
    assert not at.exception
    body = texts(at)
    assert body.index("ciencia y tecnología en 2023") < body.index("resultado financiero en 2024")
    # 1) respuesta, 2) estado coloreado
    assert ":green-badge[Respondida]" in body and ":red-badge[No se puede responder]" in body
    assert "La proporción fue 1,15 %." in body
    # 3) faltantes de la que no se pudo responder
    assert "Lo que falta" in body and "2024" in body
    # 4) tablas (expander con datos), 5) código, 6) salida, 7) reintentos
    labels = "\n".join(e.label for e in at.expander)
    assert "Tablas usadas (1)" in labels and "Código generado" in labels
    assert "Salida de la ejecución (subprocess" in labels
    assert "Reintentos: 0" in body
    assert any("load_table" in c.value for c in at.code)
    assert len(at.chat_message) == 4  # 2 preguntas + 2 respuestas


def test_vc063_litellm_error_is_shown_and_next_question_works(ui_env: UiEnv) -> None:
    class Failing:
        def __call__(self, messages: Any, config: Any) -> QueryPlan:
            raise auth_error()

    ui_env.analyst = lambda s: share_analyst(ui_env, planner=Failing())
    at = ask(ui_env.app(), "¿Qué proporción…?")
    assert not at.exception
    assert any("LiteLLM" in e.value and "Invalid API key" in e.value for e in at.error)
    ui_env.analyst = lambda s: share_analyst(ui_env, planner=Recorder(plan(SHARE_SUB)))
    ask(at, "¿Qué proporción…?")
    assert not at.exception
    assert ":green-badge[Respondida]" in texts(at)
    assert any("LiteLLM" in e.value for e in at.error)  # el error queda en el historial


def test_sandbox_unavailable_is_reported(ui_env: UiEnv) -> None:
    from services.sandbox import SandboxUnavailable

    def unavailable(settings: Any) -> Any:
        raise SandboxUnavailable("SANDBOX_BACKEND=docker pero Docker no responde")

    ui_env.analyst = unavailable
    at = ask(ui_env.app(), "¿Qué proporción…?")
    assert not at.exception
    assert any("Sandbox" in e.value and "Docker no responde" in e.value for e in at.error)


def test_example_question_runs_with_its_id(ui_env: UiEnv) -> None:
    at = ui_env.app()
    select = at.selectbox(key="example")
    option = next(o for o in select.options if o.startswith("syn-02"))
    select.set_value(option).run()
    at.button(key="ask_example").click().run()
    assert not at.exception
    assert "_(syn-02)_" in texts(at)
    assert ":green-badge[Respondida]" in texts(at)
