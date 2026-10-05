"""Agente Analista: StateGraph de LangGraph (spec §7.7).

    understand → retrieve ─(índice vacío)→ decide_status
    retrieve → select ─(ninguna subpregunta cubierta)→ decide_status
    select → generate_code → execute → validate_output
    validate_output ─(salida inválida y quedan reintentos)→ generate_code
    validate_output ─(resto)→ decide_status → answer → END

El estado (`status`, `missing`, `error`) lo decide `decide_status` con reglas fijas (BR-010);
`answer` solo redacta el texto (FR-033). Los LLM, el índice, el almacén y el sandbox se inyectan
con `AnalystServices`, así los tests usan fakes.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict, cast
from uuid import UUID

from langchain_core.embeddings import Embeddings
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from agents.analyst.answer import (
    cannot_answer_text,
    format_missing,
    format_results,
    format_tables,
)
from agents.analyst.coverage import apply_deterministic_checks
from agents.analyst.prompts import answer_messages, code_messages, plan_messages, select_messages
from agents.analyst.schemas import (
    AnalystError,
    AnalystOutcome,
    Candidate,
    ExecutionSummary,
    GeneratedCode,
    MissingInfo,
    QueryPlan,
    Selection,
    Status,
    SubquestionCoverage,
    UsedTable,
)
from agents.analyst.status import decide_status
from agents.ingestion.schemas import preview_markdown
from services.config import Settings, get_settings
from services.sandbox.result import CodeResult, ExecutionResult, validate_execution
from services.table_store import TableStore
from services.tracing import run_config
from services.vector_index import VectorIndex, get_vector_index

MAX_CANDIDATES = 10
STDIO_LIMIT = 4000  # caracteres de stdout/stderr que se guardan en el estado

Messages = list[BaseMessage]


@dataclass
class AnalystServices:
    plan: Callable[[Messages, RunnableConfig | None], QueryPlan]
    select: Callable[[Messages, RunnableConfig | None], Selection]
    code: Callable[[Messages, RunnableConfig | None], GeneratedCode]
    write: Callable[[Messages, RunnableConfig | None], str]
    embeddings_factory: Callable[[], Embeddings]
    index_factory: Callable[[], VectorIndex]
    store: TableStore
    run_code: Callable[[str, dict[str, Path]], ExecutionResult]
    max_retries: int = 3
    retrieval_k: int = 6
    sandbox_backend: str = ""
    model: str = ""


def default_services(settings: Settings | None = None) -> AnalystServices:
    """Servicios reales: LLM del proxy, Pinecone, almacén local y sandbox configurado."""
    settings = settings or get_settings()
    from services.llm import get_chat_model, get_embeddings, with_structured
    from services.sandbox import resolve_backend
    from services.sandbox import run_code as sandbox_run

    def structured(schema: type[Any], model: str | None = None) -> Callable[..., Any]:
        def call(messages: Messages, config: RunnableConfig | None) -> Any:
            llm = with_structured(get_chat_model(settings, model=model), schema, settings)
            return llm.invoke(messages, config=config)

        return call

    def write(messages: Messages, config: RunnableConfig | None) -> str:
        return str(get_chat_model(settings).invoke(messages, config=config).content)

    return AnalystServices(
        plan=structured(QueryPlan),
        select=structured(Selection),
        code=structured(GeneratedCode, model=settings.LLM_CODE_MODEL or None),
        write=write,
        embeddings_factory=lambda: get_embeddings(settings),
        index_factory=lambda: get_vector_index(settings),
        store=TableStore(settings.data_dir),
        run_code=lambda code, tables: sandbox_run(code, tables, settings=settings),
        max_retries=settings.ANALYST_MAX_RETRIES,
        retrieval_k=settings.RETRIEVAL_K,
        sandbox_backend=resolve_backend(settings.SANDBOX_BACKEND, settings.SANDBOX_IMAGE),
        model=settings.LLM_MODEL or "",
    )


class AnalystState(TypedDict, total=False):
    question: str
    question_id: str | None
    query_plan: QueryPlan
    candidates: list[Candidate]
    selection: list[SubquestionCoverage]
    code: str
    explanation: str
    attempts: int
    executions: list[ExecutionSummary]
    last_error: str | None
    code_result: CodeResult | None
    status: Status
    missing: list[MissingInfo]
    error: AnalystError | None
    tables_used: list[UsedTable]
    answer: str
    log: Annotated[list[str], operator.add]


def _covered(state: AnalystState) -> list[SubquestionCoverage]:
    return [c for c in state.get("selection", []) if c.covered]


def _trim(text: str) -> str:
    return text if len(text) <= STDIO_LIMIT else text[:STDIO_LIMIT] + "\n…(recortado)"


def build_analyst_graph(services: AnalystServices) -> Any:
    store = services.store

    def understand(state: AnalystState, config: RunnableConfig) -> AnalystState:
        plan = services.plan(plan_messages(state["question"]), config)
        subs = ", ".join(f"{s.id}: {s.text}" for s in plan.subquestions)
        return {
            "query_plan": plan,
            "attempts": 0,
            "executions": [],
            "error": None,
            "log": [f"understand: {len(plan.subquestions)} subpreguntas ({subs})"],
        }

    def retrieve(state: AnalystState) -> AnalystState:
        plan = state["query_plan"]
        queries = plan.search_queries or [state["question"]]
        vectors = services.embeddings_factory().embed_documents(queries)
        index = services.index_factory()
        best: dict[str, float] = {}
        for vector in vectors:
            for match in index.query(list(vector), services.retrieval_k):
                best[match.id] = max(best.get(match.id, float("-inf")), match.score)
        if not best:
            return {
                "candidates": [],
                "error": "no_tables_indexed",
                "log": ["retrieve: el índice no tiene tablas"],
            }
        candidates: list[Candidate] = []
        for table_id, score in sorted(best.items(), key=lambda kv: kv[1], reverse=True):
            if not store.metadata_path(table_id).exists():
                continue  # está en Pinecone pero no en el almacén local
            df = store.load_df(table_id)
            candidates.append(
                Candidate(
                    table_id=table_id,
                    score=score,
                    metadata=store.load_metadata(table_id),
                    preview_markdown=preview_markdown(df, max_rows=5),
                )
            )
            if len(candidates) >= MAX_CANDIDATES:
                break
        if not candidates:
            return {
                "candidates": [],
                "error": "no_tables_indexed",
                "log": ["retrieve: las tablas del índice no están en el almacén local"],
            }
        names = "; ".join(f"{c.metadata.name} ({c.score:.2f})" for c in candidates)
        return {
            "candidates": candidates,
            "log": [
                f"retrieve: {len(candidates)} candidatas con {len(queries)} búsquedas: {names}"
            ],
        }

    def select(state: AnalystState, config: RunnableConfig) -> AnalystState:
        plan, candidates = state["query_plan"], state["candidates"]
        proposal = services.select(select_messages(state["question"], plan, candidates), config)
        selection = apply_deterministic_checks(plan.subquestions, proposal.coverage, candidates)
        llm_covered = {c.subquestion_id for c in proposal.coverage if c.covered}
        removed = [
            c.subquestion_id for c in selection if not c.covered and c.subquestion_id in llm_covered
        ]
        covered = [c for c in selection if c.covered]
        tables = sorted({t for c in covered for t in c.table_ids})
        note = f"; descubiertas por chequeo determinístico: {', '.join(removed)}" if removed else ""
        return {
            "selection": selection,
            "log": [
                f"select: {len(covered)}/{len(selection)} subpreguntas cubiertas con "
                f"{len(tables)} tabla(s) {tables}{note}"
            ],
        }

    def generate_code(state: AnalystState, config: RunnableConfig) -> AnalystState:
        covered = _covered(state)
        covered_ids = {c.subquestion_id for c in covered}
        subs = [s for s in state["query_plan"].subquestions if s.id in covered_ids]
        reasons = {c.subquestion_id: c.missing for c in state["selection"] if not c.covered}
        excluded = [
            (s, reasons.get(s.id) or "sin datos")
            for s in state["query_plan"].subquestions
            if s.id not in covered_ids
        ]
        candidates = {c.table_id: c for c in state["candidates"]}
        table_ids = sorted({t for c in covered for t in c.table_ids})
        tables = [(candidates[t].metadata, candidates[t].preview_markdown) for t in table_ids]
        attempt = state.get("attempts", 0) + 1
        previous = state.get("code") if attempt > 1 else None
        error = state.get("last_error") if attempt > 1 else None
        generated = services.code(
            code_messages(
                subs, tables, excluded=excluded, previous_code=previous, previous_error=error
            ),
            config,
        )
        label = "intento 1" if attempt == 1 else f"reintento {attempt - 1}"
        return {
            "code": generated.code,
            "explanation": generated.explanation,
            "attempts": attempt,
            "log": [
                f"generate_code: programa de {generated.code.count(chr(10)) + 1} líneas ({label})"
            ],
        }

    def execute(state: AnalystState) -> AnalystState:
        table_ids = sorted({t for c in _covered(state) for t in c.table_ids})
        result = services.run_code(state["code"], {t: store.parquet_path(t) for t in table_ids})
        summary = ExecutionSummary(
            attempt=state["attempts"],
            code=state["code"],
            stdout=_trim(result.stdout),
            stderr=_trim(result.stderr),
            exit_code=result.exit_code,
            duration_s=round(result.duration_s, 3),
            backend=result.backend,
            timed_out=result.timed_out,
            rejected=result.rejected,
        )
        outcome = (
            "rechazado por el filtro"
            if result.rejected
            else ("timeout" if result.timed_out else f"exit {result.exit_code}")
        )
        return {
            "executions": [*state.get("executions", []), summary],
            "log": [f"execute: {result.backend}, {outcome}, {result.duration_s:.1f} s"],
        }

    def validate_output(state: AnalystState) -> AnalystState:
        last = state["executions"][-1]
        execution = ExecutionResult(
            last.stdout,
            last.stderr,
            last.exit_code,
            last.duration_s,
            cast(Literal["docker", "subprocess"], last.backend),
            last.timed_out,
            last.rejected,
        )
        result, error = validate_execution(execution)
        if result is not None:
            reported = {r.subquestion_id for r in result.results} | {
                m.subquestion_id for m in result.missing
            }
            lacking = [
                c.subquestion_id for c in _covered(state) if c.subquestion_id not in reported
            ]
            if lacking:
                result, error = (
                    None,
                    (
                        "el JSON no incluye resultado ni motivo para: "
                        + ", ".join(lacking)
                        + ". Cada subpregunta tiene que aparecer en 'results' o en 'missing'."
                    ),
                )
        executions = [*state["executions"][:-1], last.model_copy(update={"error": error})]
        if error is None:
            return {
                "code_result": result,
                "last_error": None,
                "executions": executions,
                "log": ["validate_output: salida válida"],
            }
        left = services.max_retries + 1 - state["attempts"]
        return {
            "code_result": None,
            "last_error": error,
            "executions": executions,
            "log": [
                f"validate_output: salida inválida ({error.splitlines()[0][:120]}); "
                f"quedan {max(left, 0)} intento(s)"
            ],
        }

    def decide(state: AnalystState) -> AnalystState:
        plan = state.get("query_plan") or QueryPlan(subquestions=[], search_queries=["-"])
        error = state.get("error")
        if error is None and state.get("last_error") and state.get("code_result") is None:
            error = "execution_failed"
        status, missing = decide_status(
            plan.subquestions, state.get("selection", []), state.get("code_result"), error
        )
        candidates = {c.table_id: c for c in state.get("candidates", [])}
        used = sorted({t for c in _covered(state) for t in c.table_ids})
        tables = [
            UsedTable(
                table_id=t,
                name=candidates[t].metadata.name,
                pages=candidates[t].metadata.source.pages,
                pdf_name=candidates[t].metadata.source.pdf_name,
            )
            for t in used
            if t in candidates
        ]
        return {
            "status": status,
            "missing": missing,
            "error": error,
            "tables_used": tables,
            "log": [f"decide_status: {status}" + (f" (error: {error})" if error else "")],
        }

    def answer(state: AnalystState, config: RunnableConfig) -> AnalystState:
        if state["status"] == "cannot_answer":
            return {"answer": cannot_answer_text(state["missing"])}
        result = state.get("code_result")
        text = services.write(
            answer_messages(
                state["question"],
                state["status"],
                format_results(result),
                format_tables(state.get("tables_used", [])),
                state.get("explanation", ""),
                result.conversions if result else [],
                format_missing(state.get("missing", [])),
            ),
            config,
        )
        return {"answer": text}

    def after_retrieve(state: AnalystState) -> Literal["select", "decide_status"]:
        return "decide_status" if state.get("error") else "select"

    def after_select(state: AnalystState) -> Literal["generate_code", "decide_status"]:
        return "generate_code" if _covered(state) else "decide_status"

    def after_validate(state: AnalystState) -> Literal["generate_code", "decide_status"]:
        retry = state.get("last_error") and state["attempts"] <= services.max_retries
        return "generate_code" if retry else "decide_status"

    graph = StateGraph(AnalystState)
    graph.add_node("understand", understand)
    graph.add_node("retrieve", retrieve)
    graph.add_node("select", select)
    graph.add_node("generate_code", generate_code)
    graph.add_node("execute", execute)
    graph.add_node("validate_output", validate_output)
    graph.add_node("decide_status", decide)
    graph.add_node("answer", answer)
    graph.add_edge(START, "understand")
    graph.add_edge("understand", "retrieve")
    graph.add_conditional_edges("retrieve", after_retrieve)
    graph.add_conditional_edges("select", after_select)
    graph.add_edge("generate_code", "execute")
    graph.add_edge("execute", "validate_output")
    graph.add_conditional_edges("validate_output", after_validate)
    graph.add_edge("decide_status", "answer")
    graph.add_edge("answer", END)
    return graph.compile()


# --------------------------------------------------------------------------------------
# Puntos de entrada
# --------------------------------------------------------------------------------------


def _config(
    question: str,
    question_id: str | None,
    services: AnalystServices,
    run_id: UUID | None = None,
) -> RunnableConfig:
    config = run_config(
        "analyst",
        question,
        question_id=question_id,
        model=services.model or None,
        sandbox_backend=services.sandbox_backend or None,
    )
    if run_id is not None:
        config["run_id"] = run_id  # id de la traza raíz: permite armar el link (FR-062)
    return config


def answer_question(
    question: str,
    question_id: str | None = None,
    services: AnalystServices | None = None,
    settings: Settings | None = None,
    run_id: UUID | None = None,
) -> AnalystState:
    services = services or default_services(settings)
    graph = build_analyst_graph(services)
    initial: AnalystState = {"question": question, "question_id": question_id, "log": []}
    config = _config(question, question_id, services, run_id)
    result: AnalystState = graph.invoke(initial, config=config)
    return result


def stream_answer(
    question: str,
    question_id: str | None = None,
    services: AnalystServices | None = None,
    settings: Settings | None = None,
) -> Iterator[tuple[str, AnalystState]]:
    """Emite `(nodo, actualización)` al terminar cada nodo."""
    services = services or default_services(settings)
    graph = build_analyst_graph(services)
    initial: AnalystState = {"question": question, "question_id": question_id, "log": []}
    for chunk in graph.stream(
        initial, config=_config(question, question_id, services), stream_mode="updates"
    ):
        for node, update in chunk.items():
            yield str(node), cast(AnalystState, update or {})


def to_outcome(state: AnalystState) -> AnalystOutcome:
    """Resumen final para la UI, el CLI y la evaluación."""
    executions = state.get("executions", [])
    return AnalystOutcome(
        question=state["question"],
        status=state["status"],
        error=state.get("error"),
        answer=state.get("answer", ""),
        code_result=state.get("code_result"),
        missing=state.get("missing", []),
        tables=state.get("tables_used", []),
        code=state.get("code", ""),
        executions=executions,
        retries=max(len(executions) - 1, 0),
    )
