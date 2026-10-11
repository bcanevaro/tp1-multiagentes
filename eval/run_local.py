"""Evaluación local del Analista.

Uso:
    uv run python -m eval.run_local                       (todas las preguntas)
    uv run python -m eval.run_local --doc indec_ica.pdf   (las de un PDF)
    uv run python -m eval.run_local --id syn-01 --id ind-02

Corre el Analista sobre cada pregunta de `eval/questions.yaml`, la corrige (ver `eval/scoring.py`) y
escribe `EVALUATION.md` (por pregunta: estado esperado y obtenido, respuesta esperada y obtenida,
correcta/incorrecta, reintentos y link a la traza) y `eval/last_run.json` con los datos crudos.
Los PDF de las preguntas tienen que estar ingeridos en esta PC.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.analyst.answer import format_item
from agents.analyst.graph import AnalystServices, answer_question, default_services, to_outcome
from agents.analyst.schemas import AnalystOutcome
from eval.scoring import Score, expected_text, score
from services.config import PROJECT_ROOT, get_settings
from services.table_store import TableStore
from services.tracing import flush_traces, trace_url

QUESTIONS_FILE = PROJECT_ROOT / "eval" / "questions.yaml"
REPORT_FILE = PROJECT_ROOT / "EVALUATION.md"
RAW_FILE = PROJECT_ROOT / "eval" / "last_run.json"
# Texto escrito a mano (trazas representativas y análisis) que se copia en cada reporte.
NOTES_FILE = PROJECT_ROOT / "eval" / "notes.md"
CUADRO_RE = re.compile(r"^(Cuadro \d+)")


def load_questions(path: Path = QUESTIONS_FILE) -> list[dict[str, Any]]:
    import yaml

    return list(yaml.safe_load(path.read_text(encoding="utf-8"))["questions"])


@dataclass
class QuestionRun:
    question: dict[str, Any]
    status: str
    score: Score
    outcome: AnalystOutcome | None = None
    error: str | None = None
    seconds: float = 0.0
    trace: str = ""
    tables: list[str] = field(default_factory=list)  # "Cuadro N" (o nombre) de cada tabla usada

    @property
    def tables_ok(self) -> bool | None:
        """VC-033: ¿usó las tablas esperadas? (solo si respondió algo y se esperaban tablas)."""
        expected = set(self.question.get("tables", []))
        if not expected or self.status not in ("answered", "partial"):
            return None
        return expected <= set(self.tables)


def table_labels(outcome: AnalystOutcome, store: TableStore) -> list[str]:
    labels: list[str] = []
    for t in outcome.tables:
        try:
            caption = store.load_metadata(t.table_id).caption
        except OSError:
            caption = ""
        match = CUADRO_RE.match(caption)
        labels.append(match.group(1) if match else t.name)
    return labels


def run_question(
    question: dict[str, Any],
    services: AnalystServices,
    store: TableStore,
    project: str | None,
) -> QuestionRun:
    run_id = uuid4()
    start = time.perf_counter()
    outcome: AnalystOutcome | None = None
    error: str | None = None
    try:
        state = answer_question(question["question"], question["id"], services, run_id=run_id)
        outcome = to_outcome(state)
    except Exception as exc:  # noqa: BLE001 — una pregunta que falla no corta la evaluación
        from ui.errors import format_service_error

        error = format_service_error(exc, "la pregunta").replace("**", "")
    status = outcome.status if outcome else "error"
    run = QuestionRun(
        question=question,
        status=status,
        score=score(question, status, outcome.code_result if outcome else None),
        outcome=outcome,
        error=error,
        seconds=time.perf_counter() - start,
        trace=trace_url(run_id, project),
    )
    if outcome is not None:
        run.tables = table_labels(outcome, store)
    return run


# --------------------------------------------------------------------------------------
# Reporte
# --------------------------------------------------------------------------------------


def _cell(text: str, limit: int = 220) -> str:
    text = " ".join(text.split()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def obtained_text(run: QuestionRun) -> str:
    if run.error:
        return f"Error: {run.error}"
    assert run.outcome is not None
    parts = (
        [format_item(r) for r in run.outcome.code_result.results] if run.outcome.code_result else []
    )
    parts += [f"Falta: {m.reason}" for m in run.outcome.missing]
    return " · ".join(parts) or "(sin resultados)"


def _pct(n: int, total: int) -> str:
    return f"{n}/{total} ({n / total:.0%})" if total else "0/0"


def render_report(runs: list[QuestionRun], header: dict[str, str], notes: str = "") -> str:
    total = len(runs)
    correct = sum(r.score.correct for r in runs)
    status_ok = sum(r.score.status_ok for r in runs)
    with_values = [r for r in runs if r.question["expected_status"] in ("answered", "partial")]
    values_ok = sum(r.score.values_ok for r in with_values)
    lines = [
        "# Evaluación del Agente Analista",
        "",
        "Generado por `uv run python -m eval.run_local`. Una respuesta es correcta si el "
        "estado coincide con el esperado y, para `answered`/`partial`, cada valor esperado "
        "tiene que "
        "aparecer entre los resultados del código con tolerancia relativa de 0,5 % (absoluta de "
        "0,01 si el esperado es 0).",
        "",
        *[f"- **{k}:** {v}" for k, v in header.items()],
        "",
        "## Resumen",
        "",
        f"- **Correctas:** {_pct(correct, total)}",
        f"- **Estado correcto:** {_pct(status_ok, total)}",
        "- **Valores correctos** (preguntas `answered`/`partial`): "
        + _pct(values_ok, len(with_values)),
        f"- **Reintentos de código:** {sum(r.outcome.retries for r in runs if r.outcome)} en total",
        "",
        "| Grupo | Correctas |",
        "|---|---|",
    ]
    for key, label in (("doc", "PDF"), ("expected_status", "Estado esperado")):
        groups: Counter[str] = Counter(str(r.question[key]) for r in runs)
        for value in groups:
            group = [r for r in runs if str(r.question[key]) == value]
            lines.append(
                f"| {label}: `{value}` | {_pct(sum(r.score.correct for r in group), len(group))} |"
            )
    if notes.strip():
        lines += ["", notes.strip()]
    lines += [
        "",
        "## Resultados por pregunta",
        "",
        "| ID | Estado esperado | Estado obtenido | Respuesta esperada | Respuesta obtenida "
        "| Correcta | Reintentos | Traza |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        q = r.question
        mark = "✅" if r.score.correct else "❌"
        retries = str(r.outcome.retries) if r.outcome else "-"
        trace = f"[ver]({r.trace})" if r.trace else "—"
        lines.append(
            f"| {q['id']} | `{q['expected_status']}` | `{r.status}` | {_cell(expected_text(q))} "
            f"| {_cell(obtained_text(r))} | {mark} | {retries} | {trace} |"
        )
    lines += ["", "## Detalle", ""]
    for r in runs:
        q = r.question
        lines += [f"### {q['id']} — {q['question']}", ""]
        lines.append(f"- **Caso:** {q.get('kind', '-')}")
        if r.tables_ok is not None:
            ok = "✅" if r.tables_ok else "❌"
            lines.append(
                f"- **Tablas usadas:** {', '.join(r.tables)} (esperadas: "
                f"{', '.join(q['tables'])}) {ok}"
            )
        elif r.tables:
            lines.append(f"- **Tablas usadas:** {', '.join(r.tables)}")
        if not r.score.correct:
            problems = ([] if r.score.status_ok else [f"estado `{r.status}`"]) + r.score.details
            lines.append(f"- **Qué falló:** {'; '.join(problems)}")
        lines.append(f"- **Tiempo:** {r.seconds:.1f} s")
        if r.outcome is not None:
            answer = "\n".join(
                f"> {line}" if line else ">" for line in r.outcome.answer.splitlines()
            )
            lines += ["", "Respuesta del agente:", "", answer]
        elif r.error:
            lines += ["", f"Error: {r.error}"]
        lines.append("")
    return "\n".join(lines)


def raw_record(r: QuestionRun) -> dict[str, Any]:
    return {
        "id": r.question["id"],
        "doc": r.question["doc"],
        "expected_status": r.question["expected_status"],
        "status": r.status,
        "correct": r.score.correct,
        "status_ok": r.score.status_ok,
        "values_ok": r.score.values_ok,
        "problems": r.score.details,
        "tables": r.tables,
        "tables_ok": r.tables_ok,
        "retries": r.outcome.retries if r.outcome else None,
        "seconds": round(r.seconds, 2),
        "trace": r.trace,
        "error": r.error,
        "outcome": r.outcome.model_dump(mode="json") if r.outcome else None,
    }


# --------------------------------------------------------------------------------------
# Punto de entrada
# --------------------------------------------------------------------------------------


def missing_docs(questions: list[dict[str, Any]], store: TableStore) -> list[str]:
    ingested = {m.source.pdf_name for m in store.list_tables()}
    return sorted({q["doc"] for q in questions} - ingested)


def evaluate(
    questions: list[dict[str, Any]],
    services: AnalystServices,
    store: TableStore,
    project: str | None = None,
    on_result: Callable[[QuestionRun], None] | None = None,
) -> list[QuestionRun]:
    """`project`: proyecto de LangSmith para armar el link de cada traza (None = sin links)."""
    runs: list[QuestionRun] = []
    for q in questions:
        run = run_question(q, services, store, project)
        runs.append(run)
        if on_result:
            on_result(run)
    return runs


RESULTS_HEADING = "\n## Resultados por pregunta"


def refresh_notes(report_text: str, notes: str) -> str:
    """Reemplaza en un reporte ya generado el texto de `eval/notes.md` (lo que va entre la tabla
    del resumen y "Resultados por pregunta"), sin volver a correr las preguntas."""
    start = report_text.index("\n## ", report_text.index("\n## Resumen") + 1)
    end = report_text.index(RESULTS_HEADING)
    if start > end:  # el reporte no tenía notas
        start = end
    block = f"\n\n{notes.strip()}\n" if notes.strip() else "\n"
    return report_text[:start].rstrip("\n") + block + report_text[end:]


def write_outputs(runs: list[QuestionRun], header: dict[str, str], report: Path, raw: Path) -> None:
    notes = NOTES_FILE.read_text(encoding="utf-8") if NOTES_FILE.exists() else ""
    report.write_text(render_report(runs, header, notes) + "\n", encoding="utf-8")
    raw.write_text(
        json.dumps(
            {"header": header, "runs": [raw_record(r) for r in runs]}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="eval.run_local", description=__doc__.split("\n")[0])
    parser.add_argument("--id", action="append", default=[], help="id de una pregunta")
    parser.add_argument("--doc", help="solo las preguntas de este PDF")
    parser.add_argument("--out", type=Path, default=REPORT_FILE, help="archivo del reporte")
    parser.add_argument(
        "--solo-notas",
        action="store_true",
        help="no corre preguntas: actualiza en el reporte el texto de eval/notes.md",
    )
    args = parser.parse_args(argv)

    if args.solo_notas:
        notes = NOTES_FILE.read_text(encoding="utf-8") if NOTES_FILE.exists() else ""
        args.out.write_text(
            refresh_notes(args.out.read_text(encoding="utf-8"), notes), encoding="utf-8"
        )
        print(f"Notas actualizadas en {args.out.name} (sin volver a evaluar).")
        return 0

    settings = get_settings()
    missing = settings.missing_required("ask")
    if missing:
        print(f"Faltan variables en el .env: {', '.join(missing)}")
        return 2
    questions = load_questions()
    if args.id:
        unknown = set(args.id) - {q["id"] for q in questions}
        if unknown:
            print(f"No existen: {', '.join(sorted(unknown))}")
            return 2
        questions = [q for q in questions if q["id"] in args.id]
    if args.doc:
        questions = [q for q in questions if q["doc"] == args.doc]

    store = TableStore(settings.data_dir)
    not_ingested = missing_docs(questions, store)
    if not_ingested:
        print("Primero hay que ingerir en esta PC:")
        for doc in not_ingested:
            print(f"  uv run python -m agents.ingestion.cli data/sample_pdfs/{doc}")
        return 2

    services = default_services(settings)
    start = time.perf_counter()
    print(
        f"Evaluando {len(questions)} preguntas (modelo {services.model}, "
        f"sandbox {services.sandbox_backend})…"
    )

    def show(run: QuestionRun) -> None:
        mark = "OK " if run.score.correct else "MAL"
        print(
            f"  {mark} {run.question['id']}: esperado {run.question['expected_status']}, "
            f"obtenido {run.status} ({run.seconds:.1f} s)"
        )

    tracing = settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY
    project = settings.LANGSMITH_PROJECT if tracing else None
    runs = evaluate(questions, services, store, project, on_result=show)
    flush_traces()
    header = {
        "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Modelo": f"`{settings.LLM_MODEL}`"
        + (f" (código: `{settings.LLM_CODE_MODEL}`)" if settings.LLM_CODE_MODEL else ""),
        "Embeddings": f"`{settings.EMBEDDING_MODEL}`",
        "Sandbox": services.sandbox_backend,
        "Preguntas": str(len(runs)),
        "Duración total": f"{time.perf_counter() - start:.0f} s",
    }
    write_outputs(runs, header, args.out, RAW_FILE)
    correct = sum(r.score.correct for r in runs)
    print(f"\nCorrectas: {correct}/{len(runs)}. Reporte: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
