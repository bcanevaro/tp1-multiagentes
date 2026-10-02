"""Backends de ejecución: subproceso aislado y contenedor Docker sin red (FR-050, FR-051, FR-054).

Los dos ejecutan el mismo directorio de trabajo, armado por `prepare_workdir`:

    main.py          preludio de confianza: carga pandas, bloquea la red y define load_table()
    program.py       el código generado (ya pasó el filtro AST)
    <table_id>.parquet  copias de las tablas seleccionadas (y nada más)

`main.py` ejecuta `program.py` con `runpy`, así los errores muestran los números de línea del
programa generado (útil para la autocorrección).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

from services.sandbox.result import ExecutionResult

PRELUDE = '''\
import runpy

import pandas as pd

TABLES = {tables!r}


def load_table(table_id):
    """Devuelve la tabla `table_id` como DataFrame de pandas."""
    if table_id not in TABLES:
        raise KeyError(f"Tabla desconocida: {{table_id!r}}. Disponibles: {{sorted(TABLES)}}")
    return pd.read_parquet(TABLES[table_id])


# Sin red: cualquier intento de abrir una conexión falla (Docker además corre con --network none).
import socket as _socket


def _no_network(*args, **kwargs):
    raise OSError("La red está deshabilitada en el sandbox")


_socket.socket.connect = _no_network
_socket.socket.connect_ex = _no_network
_socket.socket.sendto = _no_network
_socket.create_connection = _no_network
_socket.getaddrinfo = _no_network

runpy.run_path(
    "program.py",
    init_globals={{"pd": pd, "load_table": load_table, "TABLES": dict(TABLES)}},
    run_name="__main__",
)
'''

DOCKER_MEMORY = "512m"
DOCKER_NANO_CPUS = 1_000_000_000  # 1 CPU
DOCKER_PIDS = 64


def prepare_workdir(workdir: Path, code: str, tables: dict[str, Path]) -> None:
    """Escribe preludio, programa y copias de las tablas (legibles por cualquier usuario)."""
    workdir.chmod(0o755)
    names = {table_id: f"{table_id}.parquet" for table_id in tables}
    for table_id, src in tables.items():
        dst = workdir / names[table_id]
        shutil.copyfile(src, dst)
        dst.chmod(0o644)
    (workdir / "main.py").write_text(PRELUDE.format(tables=names), encoding="utf-8")
    (workdir / "program.py").write_text(code, encoding="utf-8")
    for name in ("main.py", "program.py"):
        (workdir / name).chmod(0o644)


# --------------------------------------------------------------------------------------
# Subproceso
# --------------------------------------------------------------------------------------


def _minimal_env(workdir: Path) -> dict[str, str]:
    """Entorno desde cero: no hereda ninguna variable (ni claves de API, NFR-002)."""
    env = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": str(workdir),
        "TMP": str(workdir),
        "TEMP": str(workdir),
    }
    if sys.platform == "win32":  # Windows necesita SYSTEMROOT para inicializar Python
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return env


def _posix_limits(timeout: int) -> None:  # pragma: no cover - corre en el proceso hijo
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (timeout + 1, timeout + 1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_subprocess(workdir: Path, timeout: int) -> ExecutionResult:
    start = time.perf_counter()
    cmd = [sys.executable, "-I", "-X", "utf8", "main.py"]
    preexec = (lambda: _posix_limits(timeout)) if os.name == "posix" else None
    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            env=_minimal_env(workdir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            preexec_fn=preexec,  # noqa: PLW1509
        )
    except subprocess.TimeoutExpired as exc:
        out = (
            exc.stdout
            if isinstance(exc.stdout, str)
            else (exc.stdout or b"").decode(errors="replace")
        )
        err = (
            exc.stderr
            if isinstance(exc.stderr, str)
            else (exc.stderr or b"").decode(errors="replace")
        )
        return ExecutionResult(
            out, err, None, time.perf_counter() - start, "subprocess", timed_out=True
        )
    return ExecutionResult(
        proc.stdout, proc.stderr, proc.returncode, time.perf_counter() - start, "subprocess"
    )


# --------------------------------------------------------------------------------------
# Docker
# --------------------------------------------------------------------------------------


@lru_cache(maxsize=4)
def docker_status(image: str) -> tuple[bool, str]:
    """¿Se puede usar Docker? Devuelve (disponible, motivo). Se evalúa una vez por proceso."""
    try:
        import docker

        client = docker.from_env(timeout=5)
        client.ping()
    except Exception as exc:  # noqa: BLE001 - cualquier falla significa "no disponible"
        return False, f"Docker no responde ({type(exc).__name__})"
    try:
        client.images.get(image)
    except Exception:  # noqa: BLE001
        return (
            False,
            f"falta la imagen '{image}' (construila con: docker build -t {image} sandbox/)",
        )
    return True, "ok"


def run_docker(workdir: Path, timeout: int, image: str) -> ExecutionResult:
    import docker
    from requests.exceptions import ConnectionError as RequestsConnectionError
    from requests.exceptions import ReadTimeout

    client = docker.from_env()
    start = time.perf_counter()
    container = client.containers.run(
        image,
        command=["python", "-I", "-X", "utf8", "/data/main.py"],
        volumes={str(workdir.resolve()): {"bind": "/data", "mode": "ro"}},
        working_dir="/data",
        network_mode="none",
        read_only=True,
        tmpfs={"/tmp": "size=64m"},
        mem_limit=DOCKER_MEMORY,
        nano_cpus=DOCKER_NANO_CPUS,
        pids_limit=DOCKER_PIDS,
        environment={"PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp"},
        detach=True,
    )
    timed_out = False
    exit_code: int | None = None
    try:
        try:
            status = container.wait(timeout=timeout)
            exit_code = int(status.get("StatusCode", -1))
        except (ReadTimeout, RequestsConnectionError):
            timed_out = True
            container.kill()
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
    finally:
        container.remove(force=True)
    return ExecutionResult(
        stdout, stderr, exit_code, time.perf_counter() - start, "docker", timed_out=timed_out
    )
