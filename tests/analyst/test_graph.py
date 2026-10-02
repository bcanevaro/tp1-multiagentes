"""Grafo del Analista con LLM simulados, índice en memoria y sandbox real por subproceso.

VC-031, VC-032, VC-034 (en el grafo), VC-035, VC-036, VC-037, VC-039, VC-040, VC-044, VC-049.
"""

from __future__ import annotations

import re

import pytest

from agents.analyst.graph import answer_question, stream_answer, to_outcome
from agents.analyst.prompts import code_messages
from agents.analyst.schemas import Selection
from agents.analyst.status import EXECUTION_FAILED_REASON
from services.config import Settings
from services.table_store import TableStore
from services.vector_index import InMemoryIndex
from tests.analyst.fakes import (
    FINANCE_ID,
    POPULATION_ID,
    UNEMPLOYMENT_ID,
    Recorder,
    code,
    cover,
    make_services,
    plan,
    sub,
    synthetic_tables,
)
from tests.ingestion.fakes import DIM

Populated = tuple[TableStore, InMemoryIndex]

SHARE_CODE = """
import json
df = load_table("sint-t01").set_index("Concepto")
share = df.loc["Gasto en ciencia y tecnología", "2023"] / df.loc["Gastos totales", "2023"] * 100
print("proporción:", share)
print(json.dumps({"results": [{"subquestion_id": "q1", "value": float(share), "unit": "%",
                               "label": "Ciencia y tecnología / gastos totales 2023"}]}))
"""
SHARE_2023 = 21940.2 / 1902775.3 * 100

DENSITY_CODE = """
import json
df = load_table("sint-t05").set_index("Departamento")
print(json.dumps({"results": [{"subquestion_id": "q1",
    "value": float(df.loc["Norte", "Población"] / df.loc["Norte", "Superficie"]),
    "unit": "hab/km²"}]}))
"""

BROKEN_CODE = 'df = load_table("sint-t01")\nprint(df["Columna inexistente"].sum())\n'

SHARE_SUB = sub(
    "q1",
    "Proporción del gasto en ciencia y tecnología sobre el gasto total en 2023",
    periods=["2023"],
)
SHARE_COVER = cover("q1", [FINANCE_ID], ["Concepto", "2023"])


def share_services(populated: Populated, settings: Settings, coder: Recorder, **kw: object):  # type: ignore[no-untyped-def]
    store, index = populated
    return make_services(
        store,
        index,
        settings,
        planner=Recorder(plan(SHARE_SUB, queries=["finanzas públicas", "gasto en ciencia"])),
        selector=Recorder(Selection(coverage=[SHARE_COVER])),
        coder=coder,
        **kw,  # type: ignore[arg-type]
    )


def test_vc037_answered_end_to_end(populated: Populated, sub_settings: Settings) -> None:
    writer = Recorder("La proporción fue 1,15 %.")
    services = share_services(populated, sub_settings, Recorder(code(SHARE_CODE)), writer=writer)
    state = answer_question("¿Qué proporción…?", "t-01", services=services)
    outcome = to_outcome(state)
    assert outcome.status == "answered" and outcome.error is None
    assert outcome.executions[0].exit_code == 0 and outcome.executions[0].backend == "subprocess"
    assert outcome.code_result is not None
    assert outcome.code_result.results[0].value == pytest.approx(SHARE_2023)
    assert outcome.retries == 0
    assert [t.table_id for t in outcome.tables] == [FINANCE_ID]
    assert outcome.tables[0].pages == [1] and outcome.answer == "La proporción fue 1,15 %."
    prompt = writer.prompt()  # FR-032: el redactor recibe valor formateado, tabla y página
    assert "1,15 %" in prompt and "Finanzas del sector público provincial" in prompt
    assert "página 1" in prompt and "Estado: answered" in prompt


def test_vc031_candidates_are_deduplicated(populated: Populated, sub_settings: Settings) -> None:
    services = share_services(populated, sub_settings, Recorder(code(SHARE_CODE)))
    state = answer_question("¿Qué proporción…?", services=services)
    ids = [c.table_id for c in state["candidates"]]
    assert len(ids) == len(set(ids)) == len(synthetic_tables())
    scores = [c.score for c in state["candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_vc032_empty_index(tmp_path, sub_settings: Settings) -> None:  # type: ignore[no-untyped-def]
    coder, writer = Recorder(code(SHARE_CODE)), Recorder("no debería llamarse")
    services = make_services(
        TableStore(tmp_path / "vacio"),
        InMemoryIndex(DIM),
        sub_settings,
        planner=Recorder(plan(SHARE_SUB)),
        selector=Recorder(Selection(coverage=[SHARE_COVER])),
        coder=coder,
        writer=writer,
    )
    outcome = to_outcome(answer_question("¿Qué proporción…?", services=services))
    assert outcome.status == "cannot_answer" and outcome.error == "no_tables_indexed"
    assert coder.calls == [] and writer.calls == []
    assert "No hay tablas indexadas" in outcome.answer


def test_vc034_vc035_uncovered_period_skips_code(
    populated: Populated, sub_settings: Settings
) -> None:
    store, index = populated
    q = sub("q1", "Ingresos totales en 2024", periods=["2024"])
    coder, writer = Recorder(code(SHARE_CODE)), Recorder("no debería llamarse")
    services = make_services(
        store,
        index,
        sub_settings,
        planner=Recorder(plan(q)),
        selector=Recorder(Selection(coverage=[cover("q1", [FINANCE_ID], ["Concepto", "2024"])])),
        coder=coder,
        writer=writer,
    )
    outcome = to_outcome(answer_question("¿Cuánto fueron los ingresos en 2024?", services=services))
    assert outcome.status == "cannot_answer" and outcome.error is None
    assert coder.calls == [] and writer.calls == []  # VC-035 y VC-044
    assert "2024" in outcome.answer and "2019" in outcome.answer and "2023" in outcome.answer
    assert outcome.code_result is None and outcome.executions == []


def test_partial_when_one_subquestion_is_uncovered(
    populated: Populated, sub_settings: Settings
) -> None:
    store, index = populated
    q2 = sub("q2", "Desempleo de Norte en 2024", periods=["2024"], entities=["Norte"])
    writer, coder = Recorder("Respuesta parcial."), Recorder(code(SHARE_CODE))
    services = make_services(
        store,
        index,
        sub_settings,
        planner=Recorder(plan(SHARE_SUB, q2)),
        selector=Recorder(
            Selection(
                coverage=[SHARE_COVER, cover("q2", [UNEMPLOYMENT_ID], ["Departamento", "2024"])]
            )
        ),
        coder=coder,
        writer=writer,
    )
    state = answer_question("¿Proporción en 2023 y desempleo de Norte en 2024?", services=services)
    outcome = to_outcome(state)
    assert outcome.status == "partial"
    assert [m.subquestion_id for m in outcome.missing] == ["q2"]
    assert "2024" in outcome.missing[0].reason
    prompt = writer.prompt()
    assert "Estado: partial" in prompt and "Partes que no se pudieron responder" in prompt
    # syn-04: el código no recibe la pregunta original y sabe qué partes NO calcular
    code_prompt = coder.prompt()
    assert "¿Proporción en 2023" not in code_prompt
    assert "NO hay que calcular" in code_prompt and "q2: Desempleo de Norte en 2024" in code_prompt
    assert "Falta el período 2024" in code_prompt


def test_vc036_code_prompt_has_columns_dtypes_units_and_table_id() -> None:
    meta, df = synthetic_tables()[3]
    messages = code_messages([sub("q1", "densidad")], [(meta, "|prev|")])
    text = "\n".join(str(m.content) for m in messages)
    assert 'load_table("<table_id>")' in text and f"table_id: {POPULATION_ID}" in text
    for column in df.columns:
        assert repr(column) in text
    assert "(texto;" in text and "(número;" in text
    assert "unidad: habitantes" in text and "unidad: km²" in text
    assert "|prev|" in text  # primeras filas


def test_vc039_retry_after_failure_includes_previous_error(
    populated: Populated, sub_settings: Settings
) -> None:
    coder = Recorder(code(BROKEN_CODE), code(SHARE_CODE))
    services = share_services(populated, sub_settings, coder)
    outcome = to_outcome(answer_question("¿Qué proporción…?", services=services))
    assert len(coder.calls) == 2 and outcome.retries == 1
    assert outcome.status == "answered"
    second = coder.prompt(1)
    assert "Tu programa anterior falló" in second and "Columna inexistente" in second
    assert "KeyError" in second  # el stderr del primer intento
    assert outcome.executions[0].error and outcome.executions[1].error is None


def test_vc040_always_failing_generator(populated: Populated, sub_settings: Settings) -> None:
    coder, writer = Recorder(code(BROKEN_CODE)), Recorder("no debería llamarse")
    services = share_services(populated, sub_settings, coder, writer=writer, max_retries=2)
    outcome = to_outcome(answer_question("¿Qué proporción…?", services=services))
    assert len(coder.calls) == 3 and len(outcome.executions) == 3
    assert outcome.status == "cannot_answer" and outcome.error == "execution_failed"
    assert outcome.code_result is None and writer.calls == []
    assert EXECUTION_FAILED_REASON in outcome.answer
    # VC-049: el texto no trae números calculados (solo los de la propia pregunta, como 2023)
    numbers = set(re.findall(r"\d+(?:[.,]\d+)*", outcome.answer))
    assert numbers <= {"2023"}


def test_rejected_code_and_incomplete_json_trigger_retries(
    populated: Populated, sub_settings: Settings
) -> None:
    store, index = populated
    q2 = sub("q2", "Densidad de Norte")
    incomplete = SHARE_CODE  # solo informa q1
    both = SHARE_CODE.replace(
        'print(json.dumps({"results": [',
        'print(json.dumps({"missing": [{"subquestion_id": "q2", "reason": "sin superficie"}], '
        '"results": [',
    )
    coder = Recorder(code("import os\nprint(os.listdir('.'))"), code(incomplete), code(both))
    services = make_services(
        store,
        index,
        sub_settings,
        planner=Recorder(plan(SHARE_SUB, q2)),
        selector=Recorder(
            Selection(
                coverage=[SHARE_COVER, cover("q2", [POPULATION_ID], ["Población", "Superficie"])]
            )
        ),
        coder=coder,
    )
    outcome = to_outcome(answer_question("¿Proporción y densidad?", services=services))
    errors = [e.error or "" for e in outcome.executions]
    assert outcome.executions[0].rejected and "os" in errors[0]
    assert "q2" in errors[1] and "missing" in errors[1]
    assert errors[2] == "" and outcome.retries == 2
    assert outcome.status == "partial"
    assert outcome.missing[0].reason == "sin superficie"


def test_vc044_answer_node_only_returns_answer(
    populated: Populated, sub_settings: Settings
) -> None:
    store, index = populated
    for coder_code in (DENSITY_CODE, BROKEN_CODE):
        writer = Recorder("texto")
        services = make_services(
            store,
            index,
            sub_settings,
            planner=Recorder(plan(sub("q1", "Densidad de Norte"))),
            selector=Recorder(
                Selection(coverage=[cover("q1", [POPULATION_ID], ["Población", "Superficie"])])
            ),
            coder=Recorder(code(coder_code)),
            writer=writer,
            max_retries=0,
        )
        updates = dict(stream_answer("¿Densidad de Norte?", services=services))
        assert set(updates["answer"]) == {"answer"}
        if coder_code is BROKEN_CODE:
            assert writer.calls == []
        else:
            assert len(writer.calls) == 1


def test_trace_config_has_name_and_metadata(populated: Populated, sub_settings: Settings) -> None:
    from agents.analyst.graph import _config

    services = share_services(populated, sub_settings, Recorder(code(SHARE_CODE)))
    config = _config("¿Qué proporción del gasto total fue ciencia?", "syn-02", services)
    assert config["run_name"] == "analyst:¿Qué proporción del gasto total fue ciencia?"
    metadata = config["metadata"]
    assert metadata["question_id"] == "syn-02" and metadata["model"] == "fake-model"
    assert metadata["sandbox_backend"] == "subprocess"


def test_default_services_wiring(make_settings) -> None:  # type: ignore[no-untyped-def]
    from agents.analyst.graph import default_services

    settings = make_settings(
        SANDBOX_BACKEND="subprocess",
        LLM_CODE_MODEL="code-model",
        ANALYST_MAX_RETRIES=1,
        RETRIEVAL_K=4,
    )
    services = default_services(settings)
    assert services.model == "chat-model" and services.sandbox_backend == "subprocess"
    assert services.max_retries == 1 and services.retrieval_k == 4
    assert services.store.root == settings.data_dir


def test_cli_questions_file_has_unique_ids() -> None:
    from agents.analyst.cli import load_questions

    ids = [q["id"] for q in load_questions()]
    assert len(ids) == len(set(ids)) and "syn-01" in ids


TWO_PART_CODE = """
import json
fin = load_table("sint-t01").set_index("Concepto")
pop = load_table("sint-t05").set_index("Departamento")
share = fin.loc["Gasto en ciencia y tecnología", "2023"] / fin.loc["Gastos totales", "2023"] * 100
density = pop.loc["Norte", "Población"] / pop.loc["Norte", "Superficie"]
print(json.dumps({"results": [
    {"subquestion_id": "q1", "value": float(share), "unit": "%"},
    {"subquestion_id": "q2", "value": float(density), "unit": "hab/km²"}]}))
"""


def test_vc030_two_part_question_two_tables(populated: Populated, sub_settings: Settings) -> None:
    """Con un plan de 2 subpreguntas, ambas viajan por el grafo y se responden con 2 tablas.

    La descomposición en sí la hace el LLM real: se verifica por CLI ([usuario]) y en la
    evaluación; acá se comprueba el prompt y el manejo de un plan con varias partes.
    """
    from agents.analyst.prompts import plan_messages

    assert "separalas" in str(plan_messages("¿X en 2023 y cuál fue Y en 2022?")[0].content)
    store, index = populated
    q2 = sub("q2", "Densidad de población de Norte", entities=["Norte"])
    coder = Recorder(code(TWO_PART_CODE))
    services = make_services(
        store,
        index,
        sub_settings,
        planner=Recorder(plan(SHARE_SUB, q2)),
        selector=Recorder(
            Selection(
                coverage=[
                    SHARE_COVER,
                    cover("q2", [POPULATION_ID], ["Departamento", "Población", "Superficie"]),
                ]
            )
        ),
        coder=coder,
    )
    outcome = to_outcome(
        answer_question("¿Proporción en 2023 y densidad de Norte?", services=services)
    )
    assert outcome.status == "answered" and outcome.missing == []
    assert {t.table_id for t in outcome.tables} == {FINANCE_ID, POPULATION_ID}
    assert outcome.code_result is not None
    values = {r.subquestion_id: r.value for r in outcome.code_result.results}
    assert values["q2"] == pytest.approx(184300 / 18430)
    prompt = coder.prompt()
    assert f"### {FINANCE_ID}" in prompt and f"### {POPULATION_ID}" in prompt
