"""La documentación entregable es autónoma y sus diagramas están al día."""

from __future__ import annotations

import re

import pytest

from scripts.export_graphs import mermaid_diagrams
from services.config import PROJECT_ROOT

DOCS = ["README.md", "EVALUATION.md", "docs/ARCHITECTURE.md"]
INTERNAL = re.compile(r"SPEC|plan-artifacts|VC-|FR-|BR-|Iteration")


@pytest.mark.parametrize("doc", DOCS)
def test_docs_do_not_reference_internal_artifacts(doc: str) -> None:
    text = (PROJECT_ROOT / doc).read_text(encoding="utf-8")
    assert not INTERNAL.findall(text)


def test_readme_diagrams_match_the_graphs() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    for name, diagram in mermaid_diagrams().items():
        assert diagram.strip() in readme, f"diagrama desactualizado: {name}"
        saved = (PROJECT_ROOT / "docs" / "graphs" / f"{name}.mmd").read_text(encoding="utf-8")
        assert saved.strip() == diagram.strip()


def test_readme_documents_every_env_variable() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    names = re.findall(r"^([A-Z_]+)=", example, flags=re.M)
    assert names
    assert [n for n in names if n not in readme] == []
