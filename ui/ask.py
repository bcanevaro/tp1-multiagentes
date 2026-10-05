"""Pestaña Preguntar: historial tipo chat con los 7 elementos de FR-042.

Extras elegidos por el alumno (D-031): progreso en vivo del Analista y preguntas de ejemplo de
`eval/questions.yaml`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import streamlit as st

from agents.analyst.answer import format_results
from agents.analyst.graph import AnalystState, stream_answer, to_outcome
from agents.analyst.schemas import AnalystOutcome
from services.config import Settings
from ui import runtime
from ui.errors import show_service_error

HISTORY_KEY = "ask_history"
NO_EXAMPLE = "— Elegí una pregunta de ejemplo —"

BadgeColor = Literal["green", "orange", "red", "gray"]
STATUS_STYLE: dict[str, tuple[BadgeColor, str]] = {
    "answered": ("green", "Respondida"),
    "partial": ("orange", "Respuesta parcial"),
    "cannot_answer": ("red", "No se puede responder"),
}


@dataclass
class HistoryEntry:
    question: str
    question_id: str | None = None
    outcome: AnalystOutcome | None = None
    log: list[str] = field(default_factory=list)
    service_error: str | None = None
    seconds: float = 0.0


def load_examples() -> list[dict[str, Any]]:
    try:
        from agents.analyst.cli import load_questions

        return load_questions()
    except Exception:  # noqa: BLE001 — sin ejemplos la pestaña sigue funcionando
        return []


def run_question(question: str, question_id: str | None, settings: Settings) -> HistoryEntry:
    """Corre el Analista mostrando una línea por nodo dentro de un `st.status`."""
    entry = HistoryEntry(question=question, question_id=question_id)
    start = time.perf_counter()
    with st.status("Analizando la pregunta…", expanded=True) as status:
        try:
            services = runtime.analyst_services(settings)
            final: AnalystState = {"question": question}
            for _node, update in stream_answer(question, question_id, services=services):
                for line in update.get("log", []):
                    status.write(f"`{time.perf_counter() - start:5.1f} s` {line}")
                    entry.log.append(line)
                final.update(cast(AnalystState, {k: v for k, v in update.items() if k != "log"}))
            entry.outcome = to_outcome(final)
        except Exception as exc:  # noqa: BLE001 — FR-043: la app no se cae
            entry.service_error = show_service_error(exc, "la consulta")
        entry.seconds = time.perf_counter() - start
        status.update(
            label=f"Listo en {entry.seconds:.1f} s" if entry.outcome else "La consulta falló",
            state="complete" if entry.outcome else "error",
            expanded=False,
        )
    return entry


def render_outcome(outcome: AnalystOutcome, settings: Settings) -> None:
    """Respuesta, estado, faltantes, tablas, código, salida y reintentos (FR-042)."""
    color, label = STATUS_STYLE[outcome.status]
    st.badge(label, color=color)
    st.markdown(outcome.answer)

    if outcome.status != "answered" and outcome.missing:
        lines = []
        for m in outcome.missing:
            extra = f" _({m.related_table})_" if m.related_table else ""
            lines.append(f"- **{m.text or m.subquestion_id}:** {m.reason}{extra}")
        st.markdown("**Lo que falta:**\n" + "\n".join(lines))

    if outcome.tables:
        with st.expander(f"Tablas usadas ({len(outcome.tables)})"):
            store = runtime.table_store(settings)
            for t in outcome.tables:
                pages = ", ".join(map(str, t.pages))
                st.markdown(f"**{t.name}** — {t.pdf_name}, página(s) {pages} · `{t.table_id}`")
                try:
                    st.dataframe(store.load_df(t.table_id), hide_index=True)
                except Exception as exc:  # noqa: BLE001
                    show_service_error(exc, "la lectura de la tabla")

    if outcome.code:
        with st.expander("Código generado"):
            st.code(outcome.code, language="python")

    if outcome.executions:
        last = outcome.executions[-1]
        with st.expander(f"Salida de la ejecución ({last.backend}, {last.duration_s:.1f} s)"):
            if outcome.code_result is not None:
                st.markdown("**Resultados:**\n" + format_results(outcome.code_result))
            st.text(last.stdout.strip() or "(sin salida)")
            if last.stderr.strip():
                st.text(last.stderr.strip())

    retries = f"Reintentos: {outcome.retries}"
    failures = [e for e in outcome.executions if e.error]
    if failures:
        retries += " — " + "; ".join(
            f"intento {e.attempt}: {e.error.splitlines()[0][:120]}" for e in failures if e.error
        )
    st.caption(retries)


def render_entry(entry: HistoryEntry, settings: Settings) -> None:
    with st.chat_message("user"):
        st.markdown(entry.question + (f"  \n_({entry.question_id})_" if entry.question_id else ""))
    with st.chat_message("assistant"):
        if entry.log:
            with st.expander(f"Progreso ({entry.seconds:.1f} s)"):
                st.markdown("\n".join(f"- {line}" for line in entry.log))
        if entry.service_error:
            st.error(entry.service_error)
        if entry.outcome is not None:
            render_outcome(entry.outcome, settings)


def render(settings: Settings, missing: list[str]) -> None:
    st.subheader("Preguntar")
    blocked = bool(missing)
    if blocked:
        st.warning(
            "Esta pestaña está bloqueada: faltan "
            + ", ".join(f"`{m}`" for m in missing)
            + " en el `.env`."
        )

    examples = load_examples()
    example_question: tuple[str, str | None] | None = None
    if examples:
        labels = [NO_EXAMPLE] + [f"{q['id']} · {q['question']}" for q in examples]
        cols = st.columns([5, 1], vertical_alignment="bottom")
        choice = cols[0].selectbox("Preguntas de ejemplo", labels, disabled=blocked, key="example")
        if cols[1].button("Preguntar", disabled=blocked or choice == NO_EXAMPLE, key="ask_example"):
            q = examples[labels.index(choice) - 1]
            example_question = (q["question"], q["id"])

    history: list[HistoryEntry] = st.session_state.setdefault(HISTORY_KEY, [])
    for entry in history:
        render_entry(entry, settings)

    typed = st.chat_input(
        "Escribí tu pregunta sobre las tablas…", disabled=blocked, key="ask_input"
    )
    new = example_question or ((typed, None) if typed else None)
    if new and not blocked:
        question, question_id = new
        with st.chat_message("user"):
            st.markdown(question + (f"  \n_({question_id})_" if question_id else ""))
        with st.chat_message("assistant"):
            entry = run_question(question, question_id, settings)
            if entry.outcome is not None:
                render_outcome(entry.outcome, settings)
        history.append(entry)
