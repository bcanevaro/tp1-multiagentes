"""Analista desde la línea de comandos.

Uso:
    uv run python -m agents.analyst.cli "<pregunta>"
    uv run python -m agents.analyst.cli --id syn-01 [--id syn-02 ...]   (de eval/questions.yaml)
    uv run python -m agents.analyst.cli --doc informe_sintetico.pdf     (todas las de ese PDF)

Muestra el progreso nodo por nodo y, al final, el estado, la respuesta, las tablas usadas, el
código generado, la salida del sandbox y los reintentos (FR-034). Con `--id` compara además el
estado con el esperado.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from agents.analyst.answer import format_results
from agents.analyst.graph import AnalystState, default_services, stream_answer, to_outcome
from agents.analyst.schemas import AnalystOutcome
from services.config import PROJECT_ROOT, get_settings

QUESTIONS_FILE = PROJECT_ROOT / "eval" / "questions.yaml"


def load_questions(path: Path = QUESTIONS_FILE) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("questions", []))


def print_outcome(outcome: AnalystOutcome, show_code: bool = True) -> None:
    print(f"\nEstado: {outcome.status}" + (f"  (error: {outcome.error})" if outcome.error else ""))
    print(f"\n{outcome.answer}")
    if outcome.code_result is not None:
        print(f"\nResultados del código:\n{format_results(outcome.code_result)}")
        if outcome.code_result.conversions:
            print("Conversiones: " + "; ".join(outcome.code_result.conversions))
    if outcome.tables:
        print("\nTablas usadas:")
        for t in outcome.tables:
            pages = ", ".join(map(str, t.pages))
            print(f"  - {t.name} [{t.table_id}] ({t.pdf_name}, páginas {pages})")
    if outcome.missing:
        print("\nFaltantes:")
        for m in outcome.missing:
            extra = f" — {m.related_table}" if m.related_table else ""
            print(f"  - [{m.subquestion_id}] {m.reason}{extra}")
    if show_code and outcome.executions:
        last = outcome.executions[-1]
        print(f"\nCódigo (intento {last.attempt}, {last.backend}, {last.duration_s:.1f} s):")
        for line in last.code.splitlines():
            print(f"    {line}")
        if last.stdout.strip():
            print("Salida:")
            for line in last.stdout.strip().splitlines()[-15:]:
                print(f"    {line}")
        if last.stderr.strip():
            print("Errores:")
            for line in last.stderr.strip().splitlines()[-15:]:
                print(f"    {line}")
    print(f"\nReintentos: {outcome.retries}")
    for e in outcome.executions:
        if e.error:
            print(f"  - intento {e.attempt}: {e.error.splitlines()[0][:150]}")


def ask(question: str, question_id: str | None = None, show_code: bool = True) -> AnalystOutcome:
    settings = get_settings()
    services = default_services(settings)
    print(f"\nPregunta{f' {question_id}' if question_id else ''}: {question}")
    print(f"(modelo {services.model}, sandbox {services.sandbox_backend})")
    start = time.perf_counter()
    final: AnalystState = {}
    for _node, update in stream_answer(question, question_id, services=services):
        for line in update.get("log", []):
            print(f"  [{time.perf_counter() - start:5.1f}s] {line}")
        final.update({k: v for k, v in update.items() if k != "log"})  # type: ignore[typeddict-item]
    final["question"] = question
    outcome = to_outcome(final)
    print_outcome(outcome, show_code)
    print(f"Tiempo total: {time.perf_counter() - start:.1f} s")
    return outcome


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agents.analyst.cli", description=__doc__.split("\n")[0])
    parser.add_argument("question", nargs="?", help="pregunta en lenguaje natural")
    parser.add_argument("--id", action="append", default=[], help="id de eval/questions.yaml")
    parser.add_argument("--doc", help="todas las preguntas de ese PDF en eval/questions.yaml")
    parser.add_argument("--no-code", action="store_true", help="no mostrar el código generado")
    args = parser.parse_args(argv)

    missing = get_settings().missing_required("ask")
    if missing:
        print(f"Faltan variables en el .env: {', '.join(missing)}")
        return 2

    if args.question:
        ask(args.question, show_code=not args.no_code)
        return 0
    if not args.id and not args.doc:
        parser.print_help()
        return 2

    questions = load_questions()
    by_id = {q["id"]: q for q in questions}
    unknown = [i for i in args.id if i not in by_id]
    if unknown:
        print(f"No existen en {QUESTIONS_FILE.name}: {', '.join(unknown)}")
        return 2
    selected = [by_id[i] for i in args.id] + [
        q for q in questions if args.doc and q["doc"] == args.doc and q["id"] not in args.id
    ]
    summary: list[tuple[str, str, str]] = []
    for q in selected:
        print("\n" + "=" * 100)
        outcome = ask(q["question"], q["id"], show_code=not args.no_code)
        summary.append((q["id"], q["expected_status"], outcome.status))
    print("\n" + "=" * 100 + "\nResumen (estado esperado → obtenido):")
    for qid, expected, got in summary:
        mark = "OK " if expected == got else "DIF"
        print(f"  {mark} {qid}: {expected} → {got}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
