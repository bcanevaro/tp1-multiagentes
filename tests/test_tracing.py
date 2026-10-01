from __future__ import annotations

from services.tracing import run_config, run_name


def test_analyst_run_name_is_truncated() -> None:
    config = run_config("analyst", "x" * 100, question_id="q1", model=None)
    name = config["run_name"]
    assert name.startswith("analyst:")
    assert len(name) == 68
    assert config["metadata"] == {"question_id": "q1"}
    assert config["tags"] == ["analyst"]


def test_ingest_run_name_keeps_full_pdf_name() -> None:
    long_name = "informe_" + "a" * 80 + ".pdf"
    assert run_name("ingest", long_name) == f"ingest:{long_name}"


def test_run_name_collapses_whitespace() -> None:
    assert run_name("analyst", "¿Cuánto\n creció   X?") == "analyst:¿Cuánto creció X?"
