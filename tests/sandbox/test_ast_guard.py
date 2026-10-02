"""VC-055: filtro estático del código generado (FR-053, BR-020)."""

from __future__ import annotations

import pytest

from services.sandbox.ast_guard import CodeRejected, check_code, ensure_safe

OK_CODE = """
import json
import math
import numpy as np
from statistics import mean
df = load_table("doc-t01")
total = float(df["Población"].sum())
print(json.dumps({"results": [{"subquestion_id": "q1", "value": total}]}))
"""


def test_allowed_code_passes() -> None:
    assert check_code(OK_CODE) == []
    ensure_safe(OK_CODE)


@pytest.mark.parametrize(
    ("code", "fragment"),
    [
        ("import os", "import de 'os'"),
        ("import subprocess", "import de 'subprocess'"),
        ("from socket import socket", "import de 'socket'"),
        ("import urllib.request", "import de 'urllib.request'"),
        ("eval('1+1')", "'eval'"),
        ("exec('x=1')", "'exec'"),
        ("open('x.txt', 'w')", "'open'"),
        ("__import__('os')", "'__import__'"),
        ("().__class__.__bases__", "'__class__'"),
        ("getattr(pd, 'read_csv')", "'getattr'"),
        ("load_table('t').to_csv('salida.csv')", "'.to_csv'"),
        ("pd.read_csv('/etc/passwd')", "'.read_csv'"),
        ("x = 'https://example.com'", "URLs"),
        ("from . import algo", "import relativo"),
        ("def f(:", "error de sintaxis"),
    ],
)
def test_vc055_forbidden_code_is_rejected(code: str, fragment: str) -> None:
    reasons = check_code(code)
    assert any(fragment in r for r in reasons), reasons
    with pytest.raises(CodeRejected):
        ensure_safe(code)


def test_common_pandas_and_list_methods_are_allowed() -> None:
    """Corrida real (syn-05): `df.rename(...)` se rechazaba por parecerse a os.rename."""
    code = (
        "df = load_table('t')\n"
        "df = df.rename(columns={'a': 'b'})\n"
        "items = [1, 2]\n"
        "items.remove(1)\n"
    )
    assert check_code(code) == []
