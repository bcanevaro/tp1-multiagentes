"""Ejecución aislada del código que genera el Analista (spec §4.4).

Uso:
    from services.sandbox import run_code, validate_execution
    execution = run_code(code, {"abc-t01": Path(".../abc-t01.parquet")})
    code_result, error = validate_execution(execution)

Dentro del programa generado están disponibles `pd` y `load_table(table_id)`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal

from services.config import Settings, get_settings
from services.sandbox.ast_guard import ALLOWED_MODULES, CodeRejected, check_code
from services.sandbox.backends import docker_status, prepare_workdir, run_docker, run_subprocess
from services.sandbox.result import (
    BackendName,
    CodeResult,
    ExecutionResult,
    LabeledValue,
    MissingItem,
    ResultItem,
    parse_code_result,
    validate_execution,
)

__all__ = [
    "ALLOWED_MODULES",
    "BackendName",
    "CodeRejected",
    "CodeResult",
    "ExecutionResult",
    "LabeledValue",
    "MissingItem",
    "ResultItem",
    "SandboxUnavailable",
    "check_code",
    "parse_code_result",
    "resolve_backend",
    "run_code",
    "validate_execution",
]


class SandboxUnavailable(RuntimeError):
    """Se pidió Docker explícitamente y no está disponible."""


def resolve_backend(requested: Literal["auto", "docker", "subprocess"], image: str) -> BackendName:
    """`auto` usa Docker si responde y la imagen existe; si no, subproceso (FR-052)."""
    if requested == "subprocess":
        return "subprocess"
    available, reason = docker_status(image)
    if available:
        return "docker"
    if requested == "docker":
        raise SandboxUnavailable(f"SANDBOX_BACKEND=docker pero {reason}")
    return "subprocess"


def run_code(
    code: str,
    tables: dict[str, Path],
    *,
    settings: Settings | None = None,
    backend: Literal["auto", "docker", "subprocess"] | None = None,
    timeout: int | None = None,
    guard: bool = True,
) -> ExecutionResult:
    """Ejecuta `code` en el sandbox con las tablas indicadas (`table_id` -> ruta del Parquet).

    `guard=False` desactiva el filtro AST (solo para los tests de aislamiento).
    """
    settings = settings or get_settings()
    chosen = resolve_backend(backend or settings.SANDBOX_BACKEND, settings.SANDBOX_IMAGE)
    timeout = timeout or settings.SANDBOX_TIMEOUT_S
    if guard:
        reasons = check_code(code)
        if reasons:
            return ExecutionResult("", "", None, 0.0, chosen, rejected="; ".join(reasons))
    with tempfile.TemporaryDirectory(prefix="sandbox-") as tmp:
        workdir = Path(tmp)
        prepare_workdir(workdir, code, tables)
        if chosen == "docker":
            return run_docker(workdir, timeout, settings.SANDBOX_IMAGE)
        return run_subprocess(workdir, timeout)
