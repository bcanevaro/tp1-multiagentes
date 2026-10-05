"""Sincronización del dataset y evaluadores de LangSmith, sin red (FR-063)."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from eval.run_langsmith import (
    correcta,
    estado,
    exactitud,
    example_inputs,
    example_metadata,
    example_outputs,
    sync_dataset,
    valores,
)
from eval.run_local import load_questions


@dataclass
class FakeClient:
    examples: list[Any] = field(default_factory=list)
    created_dataset: bool = False
    updated: list[Any] = field(default_factory=list)
    deleted: list[Any] = field(default_factory=list)

    def has_dataset(self, *, dataset_name: str) -> bool:
        return self.created_dataset

    def read_dataset(self, *, dataset_name: str) -> Any:
        return SimpleNamespace(id="ds")

    def create_dataset(self, dataset_name: str, *, description: str) -> Any:
        self.created_dataset = True
        return SimpleNamespace(id="ds")

    def list_examples(self, *, dataset_id: Any) -> Any:
        return list(self.examples)

    def update_example(self, example_id: Any, **kwargs: Any) -> None:
        self.updated.append(example_id)
        for ex in self.examples:
            if ex.id == example_id:
                ex.inputs, ex.outputs = kwargs["inputs"], kwargs["outputs"]
                ex.metadata = kwargs["metadata"]

    def create_examples(self, **kwargs: Any) -> None:
        for e in kwargs["examples"]:
            self.examples.append(SimpleNamespace(id=uuid4(), **e))

    def delete_examples(self, example_ids: Any) -> None:
        self.deleted += list(example_ids)
        self.examples = [e for e in self.examples if e.id not in set(example_ids)]


def test_sync_creates_then_is_idempotent_and_tracks_changes() -> None:
    questions = load_questions()
    client = FakeClient()
    _, counts = sync_dataset(client, questions)
    assert counts["creados"] == len(questions) and client.created_dataset
    _, counts = sync_dataset(client, questions)
    assert counts == {"creados": 0, "actualizados": 0, "borrados": 0, "sin cambios": len(questions)}

    changed = [dict(q) for q in questions[:-1]]
    changed[0]["question"] = "otra redacción"
    _, counts = sync_dataset(client, changed)
    assert counts["actualizados"] == 1 and counts["borrados"] == 1
    assert len(client.examples) == len(questions) - 1


def test_example_shapes() -> None:
    q = next(q for q in load_questions() if q["id"] == "syn-04")
    assert example_inputs(q) == {"question": q["question"], "question_id": "syn-04"}
    assert example_outputs(q)["expected_status"] == "partial"
    assert example_metadata(q)["doc"] == "informe_sintetico.pdf"


def test_evaluators() -> None:
    reference = {
        "expected_status": "answered",
        "expected_values": [{"label": "x", "value": 84.8792, "unit": "%"}],
    }
    good = {
        "status": "answered",
        "code_result": {"results": [{"subquestion_id": "q1", "value": 84.88, "unit": "%"}]},
    }
    bad_value = {
        "status": "answered",
        "code_result": {"results": [{"subquestion_id": "q1", "value": 78.55, "unit": "%"}]},
    }
    assert estado(good, reference)["score"] == 1 and valores(good, reference)["score"] == 1
    assert correcta(good, reference)["score"] == 1
    assert estado(bad_value, reference)["score"] == 1
    assert (
        valores(bad_value, reference)["score"] == 0 and correcta(bad_value, reference)["score"] == 0
    )

    cannot = {"expected_status": "cannot_answer", "expected_values": []}
    out = {"status": "cannot_answer", "code_result": None}
    assert valores(out, cannot)["score"] is None and correcta(out, cannot)["score"] == 1
    assert exactitud([good, bad_value], [reference, reference])["score"] == 0.5
