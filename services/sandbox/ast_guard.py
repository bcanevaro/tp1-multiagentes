"""Filtro estático del código generado (FR-053, BR-020).

Analiza el AST antes de ejecutar y rechaza el programa si:
- importa un módulo fuera de la lista permitida (BR-020);
- usa funciones que permiten escapar del sandbox (`eval`, `exec`, `open`, `__import__`, …);
- accede a atributos "dunder" (`obj.__class__`, `__globals__`, …);
- llama a métodos de pandas que leen o escriben archivos (`to_csv`, `read_csv`, …);
- contiene URLs (textos con "://").

Es una primera barrera: el aislamiento real lo da el backend (Docker sin red, o subproceso
con entorno vacío y directorio temporal).
"""

from __future__ import annotations

import ast
import re

ALLOWED_MODULES = frozenset(
    {"pandas", "numpy", "math", "json", "statistics", "datetime", "re", "decimal", "fractions"}
)
FORBIDDEN_NAMES = frozenset(
    {
        "eval", "exec", "compile", "__import__", "open", "input", "breakpoint", "globals",
        "locals", "vars", "getattr", "setattr", "delattr", "help", "exit", "quit", "memoryview",
        "__builtins__", "__loader__", "__spec__",
    }
)  # fmt: skip
_IO_ATTR_RE = re.compile(
    r"^(read_\w+|to_(csv|parquet|excel|pickle|json|sql|hdf|feather|stata|html|xml|latex|"
    r"clipboard|orc|gbq)|system|popen|spawn\w*|fork|remove|unlink|rmdir|rename)$"
)


class CodeRejected(Exception):
    """El código no pasó el filtro estático."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("Código rechazado por el filtro de seguridad: " + "; ".join(reasons))


def check_code(code: str) -> list[str]:
    """Devuelve los motivos de rechazo (lista vacía si el código es aceptable)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"error de sintaxis en la línea {exc.lineno}: {exc.msg}"]
    reasons: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name, reasons)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                reasons.append("import relativo no permitido")
            else:
                _check_module(node.module or "", reasons)
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            reasons.append(f"uso de '{node.id}' no permitido")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                reasons.append(f"acceso al atributo '{node.attr}' no permitido")
            elif _IO_ATTR_RE.match(node.attr):
                reasons.append(
                    f"'.{node.attr}' no permitido: el código no puede leer ni escribir archivos"
                )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "://" in node.value:
            reasons.append("el código no puede usar URLs")
    return list(dict.fromkeys(reasons))


def _check_module(name: str, reasons: list[str]) -> None:
    top = name.split(".")[0]
    if top not in ALLOWED_MODULES:
        allowed = ", ".join(sorted(ALLOWED_MODULES))
        reasons.append(f"import de '{name}' no permitido (permitidos: {allowed})")


def ensure_safe(code: str) -> None:
    """Lanza `CodeRejected` si el código no pasa el filtro."""
    reasons = check_code(code)
    if reasons:
        raise CodeRejected(reasons)
