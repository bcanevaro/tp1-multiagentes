"""Evaluación local con el Analista simulado (VC-068 en versión simulada)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agents.analyst.schemas import QueryPlan, Selection
from eval.run_local import (
    evaluate,
    missing_docs,
    refresh_notes,
    render_report,
    write_outputs,
)
from services.config import Settings
from tests.analyst.fakes import (
    FINANCE_ID,
    Recorder,
    code,
    cover,
    make_services,
    plan,
    populate,
    sub,
)
from tests.analyst.test_graph import SHARE_2023, SHARE_CODE

Q_2023 = sub("q1", "Proporción del gasto en ciencia y tecnología en 2023", periods=["2023"])
Q_2024 = sub("q1", "Resultado financiero en 2024", periods=["2024"])

QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "t-01",
        "doc": "informe_sintetico.pdf",
        "question": "¿Qué proporción del gasto total fue ciencia y tecnología en 2023?",
        "expected_status": "answered",
        "expected_values": [
            {"label": "Proporción 2023", "value": round(SHARE_2023, 4), "unit": "%"}
        ],
        "tables": ["Finanzas del sector público provincial"],
        "kind": "una tabla",
    },
    {
        "id": "t-02",
        "doc": "informe_sintetico.pdf",
        "question": "¿Cuál fue el resultado financiero en 2024?",
        "expected_status": "cannot_answer",
        "expected_values": [],
        "expected_missing": "No hay datos de 2024",
        "tables": ["Finanzas del sector público provincial"],
        "kind": "falta un período",
    },
    {
        "id": "t-03",
        "doc": "informe_sintetico.pdf",
        "question": "¿Qué proporción fue ciencia y tecnología en 2023? (esperado mal a propósito)",
        "expected_status": "answered",
        "expected_values": [{"label": "Proporción 2023", "value": 5.0, "unit": "%"}],
        "tables": [],
        "kind": "valor incorrecto",
    },
]


def by_question(when_2024: Any, otherwise: Any) -> Callable[..., Any]:
    def call(messages: Any, config: Any) -> Any:
        text = "\n".join(str(m.content) for m in messages)
        return when_2024 if "2024" in text else otherwise

    return call


@pytest.fixture
def runs(tmp_path: Path, make_settings: Callable[..., Settings]) -> Any:
    store, index = populate(tmp_path / "store")
    settings = make_settings(DATA_DIR=tmp_path / "store", SANDBOX_BACKEND="subprocess")
    services = make_services(
        store,
        index,
        settings,
        planner=by_question(plan(Q_2024), plan(Q_2023)),  # type: ignore[arg-type]
        selector=by_question(  # type: ignore[arg-type]
            Selection(coverage=[cover("q1", [FINANCE_ID], ["2024"])]),
            Selection(coverage=[cover("q1", [FINANCE_ID], ["Concepto", "2023"])]),
        ),
        coder=Recorder(code(SHARE_CODE)),
    )
    return evaluate(QUESTIONS, services, store), store


def test_scores_and_statuses(runs: Any) -> None:
    results, _ = runs
    assert [r.status for r in results] == ["answered", "cannot_answer", "answered"]
    assert [r.score.correct for r in results] == [True, True, False]
    assert results[0].tables_ok is True
    assert results[2].score.status_ok and not results[2].score.values_ok
    assert all(r.trace == "" for r in results)  # sin LangSmith en los tests


def test_vc068_report_has_one_row_per_question_with_six_fields(runs: Any, tmp_path: Path) -> None:
    results, _ = runs
    report = render_report(results, {"Modelo": "`fake`"}, notes="## Trazas representativas\n- x")
    assert report.index("## Trazas representativas") < report.index("## Resultados por pregunta")
    header = (
        "| ID | Estado esperado | Estado obtenido | Respuesta esperada | Respuesta obtenida "
        "| Correcta | Reintentos | Traza |"
    )
    assert header in report
    rows = [line for line in report.splitlines() if line.startswith("| t-0")]
    assert len(rows) == 3
    assert "✅" in rows[0] and "1,15 %" in rows[0] and "| 0 |" in rows[0]
    assert "`cannot_answer`" in rows[1] and "Falta:" in rows[1]
    assert "❌" in rows[2]
    assert "**Correctas:** 2/3 (67%)" in report
    assert "Qué falló:** falta Proporción 2023 = 5.0" in report

    out, raw = tmp_path / "EVALUATION.md", tmp_path / "last_run.json"
    write_outputs(results, {"Modelo": "`fake`"}, out, raw)
    assert out.read_text(encoding="utf-8").startswith("# Evaluación del Agente Analista")
    data = json.loads(raw.read_text(encoding="utf-8"))
    assert [r["id"] for r in data["runs"]] == ["t-01", "t-02", "t-03"]
    assert data["runs"][0]["outcome"]["status"] == "answered"


def test_missing_docs(runs: Any) -> None:
    _, store = runs
    assert missing_docs(QUESTIONS, store) == []
    assert missing_docs([{"doc": "indec_ica.pdf"}], store) == ["indec_ica.pdf"]


def test_question_that_raises_is_reported_as_error(
    tmp_path: Path, make_settings: Callable[..., Settings]
) -> None:
    store, index = populate(tmp_path / "store")
    settings = make_settings(DATA_DIR=tmp_path / "store", SANDBOX_BACKEND="subprocess")

    def boom(messages: Any, config: Any) -> QueryPlan:
        raise RuntimeError("proxy caído")

    services = make_services(
        store,
        index,
        settings,
        planner=boom,  # type: ignore[arg-type]
        selector=Recorder(),
        coder=Recorder(),
    )
    [run] = evaluate(QUESTIONS[:1], services, store)
    assert run.status == "error" and not run.score.correct
    assert "proxy caído" in (run.error or "")
    assert "Error:" in render_report([run], {})


@pytest.mark.parametrize("old_notes", ["", "## Notas viejas\n\nTexto viejo."])
def test_refresh_notes_matches_a_fresh_render(old_notes: str) -> None:
    """`--solo-notas`: cambiar el análisis no obliga a volver a correr las preguntas."""
    from eval.run_local import QuestionRun
    from eval.scoring import Score

    runs = [
        QuestionRun(
            question=QUESTIONS[0],
            status="error",
            score=Score(False, False, False, []),
            error="sin servicio",
        )
    ]
    header = {"Fecha": "2026-10-11"}
    new_notes = "## Trazas representativas\n\n- una\n\n## Análisis\n\nTexto nuevo."
    old = render_report(runs, header, old_notes)
    assert refresh_notes(old, new_notes) == render_report(runs, header, new_notes)
