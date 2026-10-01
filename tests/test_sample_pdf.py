"""Iteración 2: el PDF sintético y su archivo de verdad son consistentes y reproducibles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from scripts.make_sample_pdf import PDF_PATH, TRUTH_PATH, build

TRUTH: dict[str, Any] = json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
TABLES = {t["key"]: t for t in TRUTH["tables"]}


def _page_texts(path: Path) -> list[str]:
    with pymupdf.open(path) as doc:
        return [page.get_text() for page in doc]


def test_every_page_has_text() -> None:
    texts = _page_texts(PDF_PATH)
    assert len(texts) == TRUTH["page_count"] <= 10
    assert all(t.strip() for t in texts)


def test_has_multipage_table() -> None:
    assert TABLES["exportaciones"]["pages"] == [2, 3]
    assert sum(len(t["pages"]) > 1 for t in TRUTH["tables"]) >= 1


def test_truth_shapes_are_consistent() -> None:
    assert 1 <= len(TRUTH["tables"]) <= 8
    for t in TRUTH["tables"]:
        assert len(t["columns"]) == t["n_cols"]
        assert len(t["rows_text"]) == len(t["values"]) == t["n_rows"]
        assert all(len(row) == t["n_cols"] for row in t["rows_text"])


def test_required_edge_cases_are_present() -> None:
    assert TABLES["produccion"]["header_rows"] == 2
    assert TABLES["salarios"]["line_style"] == "horizontal"
    cells = [c for t in TRUTH["tables"] for row in t["rows_text"] for c in row]
    assert any(c.startswith("(") and c.endswith(")") for c in cells)  # negativos
    assert any(c.endswith("%") for c in cells)
    assert any(c.startswith("$") for c in cells)
    assert "s/d" in cells
    assert any("." in c and "," in c for c in cells)  # formato 1.234,5


def test_captions_and_rows_appear_in_pdf_text() -> None:
    full = " ".join(" ".join(_page_texts(PDF_PATH)).split())
    for t in TRUTH["tables"]:
        assert t["caption"].split(".")[0] in full
        assert t["footnote"].split(".")[0] in full
        assert t["rows_text"][-1][-1] in full


def test_generation_is_reproducible(tmp_path: Path) -> None:
    pdf, truth = tmp_path / "a.pdf", tmp_path / "a.json"
    regenerated = build(pdf, truth)
    assert _page_texts(pdf) == _page_texts(PDF_PATH)
    assert regenerated["tables"] == TRUTH["tables"]


@pytest.mark.parametrize("key", list(TABLES))
def test_each_table_has_context(key: str) -> None:
    t = TABLES[key]
    assert t["caption"].startswith("Cuadro")
    assert t["section_title"] and t["paragraph_before"] and t["footnote"]
