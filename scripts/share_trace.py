"""Corre un agente y publica su traza de LangSmith con un link público (consigna §9.2.4).

Uso:
    uv run python scripts/share_trace.py --pdf data/sample_pdfs/indec_ica.pdf   (Ingesta)
    uv run python scripts/share_trace.py --id syn-10                            (Analista)
    uv run python scripts/share_trace.py "¿Cuántos turistas visitaron la provincia en 2023?"

Imprime el link público (se abre sin cuenta). Para que la traza muestre llamadas reales al LLM y
no respuestas de la caché, correrlo con LLM_CACHE=false.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.config import Settings, get_settings  # noqa: E402
from services.tracing import flush_traces  # noqa: E402

SHARE_ATTEMPTS = 10
SHARE_WAIT_S = 3.0


def run_ingestion(pdf: Path, settings: Settings, run_id: UUID) -> str:
    from agents.ingestion.graph import _config, _initial_state, build_ingestion_graph
    from agents.ingestion.graph import default_services as ingestion_services

    graph = build_ingestion_graph(ingestion_services(settings))
    config = {**_config(pdf, None, settings), "run_id": run_id}
    state = graph.invoke(_initial_state(pdf, None), config=config)
    if state.get("error"):
        return f"Ingesta con error: {state['error']}"
    return f"Ingesta terminada: {len(state.get('indexed', []))} tablas indexadas"


def run_question(question: str, question_id: str | None, settings: Settings, run_id: UUID) -> str:
    from agents.analyst.graph import answer_question, to_outcome

    outcome = to_outcome(answer_question(question, question_id, settings=settings, run_id=run_id))
    return f"Estado: {outcome.status} · reintentos: {outcome.retries}\n{outcome.answer}"


def share(run_id: UUID) -> str:
    """Publica la traza. Reintenta porque LangSmith tarda unos segundos en registrar la corrida."""
    from langsmith import Client

    flush_traces()
    client = Client()
    last: Exception | None = None
    for _ in range(SHARE_ATTEMPTS):
        try:
            return str(client.share_run(run_id))
        except Exception as exc:  # noqa: BLE001 — la corrida todavía no llegó
            last = exc
            time.sleep(SHARE_WAIT_S)
    raise RuntimeError(f"No se pudo publicar la traza {run_id}: {last}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="share_trace", description=__doc__.split("\n")[0])
    parser.add_argument("question", nargs="?", help="pregunta para el Analista")
    parser.add_argument("--id", help="id de una pregunta de eval/questions.yaml")
    parser.add_argument("--pdf", type=Path, help="PDF para la Ingesta")
    args = parser.parse_args(argv)
    if sum(x is not None for x in (args.question, args.id, args.pdf)) != 1:
        parser.error("indicá exactamente una opción: una pregunta, --id o --pdf")

    settings = get_settings()
    missing = settings.missing_required("ingest" if args.pdf else "ask")
    if missing:
        print(f"Faltan variables en el .env: {', '.join(missing)}")
        return 2

    run_id = uuid4()
    if args.pdf:
        print(run_ingestion(args.pdf, settings, run_id))
    else:
        question, question_id = args.question, None
        if args.id:
            from agents.analyst.cli import load_questions

            by_id = {q["id"]: q for q in load_questions()}
            if args.id not in by_id:
                print(f"No existe la pregunta {args.id} en eval/questions.yaml")
                return 2
            question, question_id = by_id[args.id]["question"], args.id
        print(run_question(question, question_id, settings, run_id))

    print(f"\nTraza pública: {share(run_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
