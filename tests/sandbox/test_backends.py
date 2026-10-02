"""VC-050 a VC-054, VC-056, VC-037: ejecución aislada (subproceso siempre; Docker si está)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from services.config import Settings
from services.sandbox import SandboxUnavailable, resolve_backend, run_code, validate_execution
from services.sandbox.backends import docker_status
from tests.sandbox.conftest import docker_ready

SUM_CODE = """
import json
df = load_table("doc-t01")
print("filas:", len(df))
print(json.dumps({"results": [{"subquestion_id": "q1", "value": float(df["Población"].sum()),
                               "unit": "habitantes"}]}))
"""
SECRET_PREFIXES = ("LITELLM_", "PINECONE_", "LANGSMITH_", "OPENAI_")


def test_vc037_subprocess_runs_code_with_tables(
    table: dict[str, Path], sub_settings: Settings
) -> None:
    execution = run_code(SUM_CODE, table, settings=sub_settings)
    assert execution.backend == "subprocess"
    assert execution.exit_code == 0, execution.stderr
    result, error = validate_execution(execution)
    assert error is None and result is not None
    assert result.results[0].value == pytest.approx(867965.0)


def test_error_lines_refer_to_generated_program(
    table: dict[str, Path], sub_settings: Settings
) -> None:
    code = "df = load_table('doc-t01')\n\ndf['Poblacion'].sum()\n"
    execution = run_code(code, table, settings=sub_settings)
    assert execution.exit_code != 0
    assert 'program.py", line 3' in execution.stderr
    assert "KeyError" in execution.stderr


def test_vc052_subprocess_sees_only_selected_tables(
    table: dict[str, Path], sub_settings: Settings, tmp_path: Path
) -> None:
    (tmp_path / "otra-tabla.parquet").write_bytes(b"no deberia verse")
    code = "import os, json\nprint(json.dumps(sorted(os.listdir('.'))))"
    execution = run_code(code, table, settings=sub_settings, guard=False)
    assert (
        execution.stdout.strip().splitlines()[-1] == '["doc-t01.parquet", "main.py", "program.py"]'
    )


def test_vc053_subprocess_does_not_inherit_secrets(
    table: dict[str, Path], sub_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("LITELLM_API_KEY", "PINECONE_API_KEY", "LANGSMITH_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, "secreto")
    code = "import os\nprint('\\n'.join(os.environ))"
    execution = run_code(code, table, settings=sub_settings, guard=False)
    assert execution.exit_code == 0, execution.stderr
    assert not [v for v in execution.stdout.split() if v.startswith(SECRET_PREFIXES)]


def test_subprocess_network_is_blocked(table: dict[str, Path], sub_settings: Settings) -> None:
    code = "import urllib.request\nurllib.request.urlopen('http://93.184.216.34', timeout=3)"
    execution = run_code(code, table, settings=sub_settings, guard=False)
    assert execution.exit_code != 0
    assert "red está deshabilitada" in execution.stderr


def test_vc056_timeout(table: dict[str, Path], sub_settings: Settings) -> None:
    start = time.perf_counter()
    execution = run_code("while True:\n    pass", table, settings=sub_settings, timeout=3)
    assert execution.timed_out and execution.exit_code is None
    assert time.perf_counter() - start <= 10
    assert "timeout" in (validate_execution(execution)[1] or "")


def test_vc055_rejected_code_is_not_executed(
    table: dict[str, Path], sub_settings: Settings
) -> None:
    execution = run_code("import os\nos.remove('main.py')", table, settings=sub_settings)
    assert execution.rejected and "import de 'os'" in execution.rejected
    assert execution.exit_code is None and execution.duration_s == 0.0


def test_vc054_auto_falls_back_to_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.sandbox.docker_status", lambda image: (False, "Docker no responde")
    )
    assert resolve_backend("auto", "mas-tp-sandbox") == "subprocess"
    with pytest.raises(SandboxUnavailable, match="Docker no responde"):
        resolve_backend("docker", "mas-tp-sandbox")
    monkeypatch.setattr("services.sandbox.docker_status", lambda image: (True, "ok"))
    assert resolve_backend("auto", "mas-tp-sandbox") == "docker"
    assert resolve_backend("subprocess", "mas-tp-sandbox") == "subprocess"


def test_docker_status_reports_missing_daemon_or_image() -> None:
    available, reason = docker_status("imagen-que-no-existe-xyz")
    assert available is False
    assert "Docker no responde" in reason or "falta la imagen" in reason


# --- Docker (se saltean si no hay daemon o falta la imagen) ---------------------------

docker = pytest.mark.skipif(
    not docker_ready(), reason="Docker o la imagen mas-tp-sandbox no disponibles"
)


@pytest.fixture
def docker_settings(make_settings: object) -> Settings:
    return make_settings(SANDBOX_BACKEND="docker", SANDBOX_TIMEOUT_S=30)  # type: ignore[operator]


@pytest.mark.docker
@docker
def test_docker_runs_code(table: dict[str, Path], docker_settings: Settings) -> None:
    execution = run_code(SUM_CODE, table, settings=docker_settings)
    assert execution.backend == "docker", execution
    result, error = validate_execution(execution)
    assert error is None and result is not None
    assert result.results[0].value == pytest.approx(867965.0)


@pytest.mark.docker
@docker
def test_vc050_docker_has_no_network(table: dict[str, Path], docker_settings: Settings) -> None:
    # Sin el preludio de bloqueo: se prueba la red del contenedor (--network none).
    code = (
        "import importlib, socket\nimportlib.reload(socket)\n"
        "socket.create_connection(('1.1.1.1', 53), timeout=3)"
    )
    execution = run_code(code, table, settings=docker_settings, guard=False)
    assert execution.exit_code != 0
    assert "OSError" in execution.stderr or "unreachable" in execution.stderr.lower()


@pytest.mark.docker
@docker
def test_vc051_docker_data_is_read_only(table: dict[str, Path], docker_settings: Settings) -> None:
    code = "f = open('/data/x.txt', 'w')"
    execution = run_code(code, table, settings=docker_settings, guard=False)
    assert execution.exit_code != 0
    assert "Read-only file system" in execution.stderr


@pytest.mark.docker
@docker
def test_vc053_docker_does_not_inherit_secrets(
    table: dict[str, Path], docker_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_API_KEY", "secreto")
    code = "import os\nprint('\\n'.join(os.environ))"
    execution = run_code(code, table, settings=docker_settings, guard=False)
    assert execution.exit_code == 0, execution.stderr
    assert not [v for v in execution.stdout.split() if v.startswith(SECRET_PREFIXES)]


@pytest.mark.docker
@docker
def test_vc056_docker_timeout(table: dict[str, Path], docker_settings: Settings) -> None:
    execution = run_code("while True:\n    pass", table, settings=docker_settings, timeout=3)
    assert execution.timed_out
