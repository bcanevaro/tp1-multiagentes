"""Evals en LangSmith (FR-063, bonus).

Uso:
    uv run python -m eval.run_langsmith                      (todas las preguntas)
    uv run python -m eval.run_langsmith --doc indec_ica.pdf  (solo las de un PDF)

1. Crea o actualiza el dataset `mas-tp-tablas-preguntas` con las preguntas de
   `eval/questions.yaml` (una por ejemplo; se sincroniza por `question_id`).
2. Corre un experimento: el Analista responde cada ejemplo y tres evaluadores automáticos
   puntúan `estado` (estado esperado = obtenido), `valores` (valores esperados encontrados con la
   tolerancia de BR-030; no aplica a `cannot_answer`) y `correcta` (las dos cosas). Un evaluador
   de resumen calcula la `exactitud` del experimento.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Protocol, cast

from agents.analyst.graph import AnalystServices, answer_question, default_services, to_outcome
from eval.run_local import load_questions, missing_docs
from eval.scoring import score
from services.config import get_settings
from services.sandbox.result import CodeResult
from services.table_store import TableStore

DATASET = "mas-tp-tablas-preguntas"
DESCRIPTION = (
    "Preguntas sobre las tablas de informe_sintetico.pdf e indec_ica.pdf, con estado y valores "
    "esperados (eval/questions.yaml)."
)

# --------------------------------------------------------------------------------------
# Dataset
# --------------------------------------------------------------------------------------


def example_inputs(q: dict[str, Any]) -> dict[str, Any]:
    return {"question": q["question"], "question_id": q["id"]}


def example_outputs(q: dict[str, Any]) -> dict[str, Any]:
    return {
        "expected_status": q["expected_status"],
        "expected_values": q.get("expected_values", []),
        "expected_missing": q.get("expected_missing", ""),
        "tables": q.get("tables", []),
    }


def example_metadata(q: dict[str, Any]) -> dict[str, Any]:
    return {"question_id": q["id"], "doc": q["doc"], "kind": q.get("kind", "")}


class DatasetClient(Protocol):
    """Lo que se usa del `langsmith.Client` (así los tests pasan un fake)."""

    def has_dataset(self, *, dataset_name: str) -> bool: ...
    def read_dataset(self, *, dataset_name: str) -> Any: ...
    def create_dataset(self, dataset_name: str, *, description: str) -> Any: ...
    def list_examples(self, *, dataset_id: Any) -> Any: ...
    def update_example(self, example_id: Any, **kwargs: Any) -> Any: ...
    def create_examples(self, **kwargs: Any) -> Any: ...
    def delete_examples(self, example_ids: Any) -> Any: ...


def sync_dataset(
    client: DatasetClient, questions: list[dict[str, Any]], name: str = DATASET
) -> tuple[Any, dict[str, int]]:
    """Deja el dataset igual a `questions`. Devuelve el dataset y cuántos ejemplos se crearon,
    actualizaron, borraron o quedaron igual."""
    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
    else:
        dataset = client.create_dataset(name, description=DESCRIPTION)
    existing: dict[str, Any] = {}
    for ex in client.list_examples(dataset_id=dataset.id):
        qid = (ex.metadata or {}).get("question_id")
        if qid:
            existing[qid] = ex
    counts = {"creados": 0, "actualizados": 0, "borrados": 0, "sin cambios": 0}
    to_create: list[dict[str, Any]] = []
    for q in questions:
        inputs, outputs, metadata = example_inputs(q), example_outputs(q), example_metadata(q)
        ex = existing.pop(q["id"], None)
        if ex is None:
            to_create.append({"inputs": inputs, "outputs": outputs, "metadata": metadata})
            counts["creados"] += 1
        elif ex.inputs != inputs or ex.outputs != outputs or (ex.metadata or {}) != metadata:
            client.update_example(ex.id, inputs=inputs, outputs=outputs, metadata=metadata)
            counts["actualizados"] += 1
        else:
            counts["sin cambios"] += 1
    if to_create:
        client.create_examples(dataset_id=dataset.id, examples=to_create)
    if existing:
        client.delete_examples([ex.id for ex in existing.values()])
        counts["borrados"] = len(existing)
    return dataset, counts


# --------------------------------------------------------------------------------------
# Experimento: objetivo y evaluadores
# --------------------------------------------------------------------------------------


def make_target(services: AnalystServices) -> Any:
    def analista(inputs: dict[str, Any]) -> dict[str, Any]:
        state = answer_question(inputs["question"], inputs.get("question_id"), services)
        outcome = to_outcome(state)
        return {
            "status": outcome.status,
            "answer": outcome.answer,
            "code_result": outcome.code_result.model_dump() if outcome.code_result else None,
            "retries": outcome.retries,
            "tables": [t.name for t in outcome.tables],
        }

    return analista


def _score(outputs: dict[str, Any], reference: dict[str, Any]) -> Any:
    result = outputs.get("code_result")
    code_result = CodeResult.model_validate(result) if result else None
    return score(reference, str(outputs.get("status")), code_result)


def estado(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    ok = outputs.get("status") == reference_outputs["expected_status"]
    return {"key": "estado", "score": int(ok), "comment": f"obtenido: {outputs.get('status')}"}


def valores(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    if reference_outputs["expected_status"] == "cannot_answer":
        return {"key": "valores", "score": None, "comment": "no aplica (cannot_answer)"}
    result = _score(outputs, reference_outputs)
    return {
        "key": "valores",
        "score": int(result.values_ok),
        "comment": "; ".join(result.details) or "todos los valores esperados encontrados",
    }


def correcta(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    return {"key": "correcta", "score": int(_score(outputs, reference_outputs).correct)}


def exactitud(
    outputs: list[dict[str, Any]], reference_outputs: list[dict[str, Any]]
) -> dict[str, Any]:
    scores = [_score(o, r).correct for o, r in zip(outputs, reference_outputs, strict=True)]
    return {"key": "exactitud", "score": sum(scores) / len(scores) if scores else 0.0}


# --------------------------------------------------------------------------------------
# Punto de entrada
# --------------------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="eval.run_langsmith", description=__doc__.split("\n")[0])
    parser.add_argument("--doc", help="solo las preguntas de este PDF")
    parser.add_argument("--dataset", default=DATASET, help="nombre del dataset en LangSmith")
    parser.add_argument("--concurrency", type=int, default=2, help="preguntas en paralelo")
    args = parser.parse_args(argv)

    settings = get_settings()
    missing = settings.missing_required("ask")
    if missing:
        print(f"Faltan variables en el .env: {', '.join(missing)}")
        return 2
    questions = load_questions()
    not_ingested = missing_docs(questions, TableStore(settings.data_dir))
    if not_ingested:
        print("Primero hay que ingerir en esta PC:")
        for doc in not_ingested:
            print(f"  uv run python -m agents.ingestion.cli data/sample_pdfs/{doc}")
        return 2

    from langsmith import Client

    client = Client()
    dataset, counts = sync_dataset(cast(DatasetClient, client), questions, args.dataset)
    print(f"Dataset «{args.dataset}»: " + ", ".join(f"{v} {k}" for k, v in counts.items()))

    data: Any = args.dataset
    if args.doc:
        data = [
            ex
            for ex in client.list_examples(dataset_id=dataset.id)
            if (ex.metadata or {}).get("doc") == args.doc
        ]
        print(f"Experimento solo con {len(data)} preguntas de {args.doc}")

    services = default_services(settings)
    model = settings.LLM_MODEL or "modelo"
    results = client.evaluate(
        make_target(services),
        data=data,
        evaluators=[estado, valores, correcta],
        summary_evaluators=[cast(Any, exactitud)],  # firma (outputs, reference_outputs)
        experiment_prefix=f"analista-{model}",
        description="Agente Analista sobre eval/questions.yaml (BR-030)",
        metadata={
            "model": model,
            "code_model": settings.LLM_CODE_MODEL or model,
            "sandbox_backend": services.sandbox_backend,
        },
        max_concurrency=args.concurrency,
    )
    name = getattr(results, "experiment_name", "")
    print(f"\nExperimento listo: {name}. Abrilo en LangSmith → Datasets → {args.dataset}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
