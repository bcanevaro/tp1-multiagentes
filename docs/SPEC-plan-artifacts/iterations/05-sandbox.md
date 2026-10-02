# Iteración 05 — Sandbox de ejecución

**Estado**: código completo; backend subproceso verificado en el contenedor (Linux); **pendientes los criterios [usuario]**: tests de Docker y del subproceso en Windows.
**Commit**: lo hace el alumno con el mensaje `Sandbox: filtro AST, backends Docker y subproceso con selección automática`. SHA: _pendiente_.

## Resultados de criterios
| Criterio | Test | Resultado |
|---|---|---|
| VC-037 (ejecución + CodeResult) | `tests/sandbox/test_backends.py::test_vc037_subprocess_runs_code_with_tables` | PASS |
| VC-038 (7 casos de salida inválida) | `tests/sandbox/test_result.py::test_vc038_invalid_executions[*]` | PASS |
| VC-052 | `test_backends.py::test_vc052_subprocess_sees_only_selected_tables` | PASS |
| VC-053 (subproceso) | `test_backends.py::test_vc053_subprocess_does_not_inherit_secrets` | PASS |
| VC-054 | `test_backends.py::test_vc054_auto_falls_back_to_subprocess` | PASS |
| VC-055 | `tests/sandbox/test_ast_guard.py::test_vc055_forbidden_code_is_rejected[*]` (15 casos), `test_backends.py::test_vc055_rejected_code_is_not_executed` | PASS |
| VC-056 (subproceso) | `test_backends.py::test_vc056_timeout` (timeout 3 s, ≤ 10 s) | PASS |
| Red bloqueada en subproceso | `test_backends.py::test_subprocess_network_is_blocked` | PASS |
| Líneas del error apuntan a `program.py` | `test_backends.py::test_error_lines_refer_to_generated_program` | PASS |
| Suite completa | `uv run pytest -q` | PASS (171 passed, 5 skipped = tests Docker) |
| Lint / tipos | `uv run ruff check .`, `uv run mypy agents services` | PASS |
| [usuario] imagen + VC-050, VC-051, VC-053 (Docker), VC-056 (Docker) | `docker build -t mas-tp-sandbox sandbox/` y `uv run pytest tests/sandbox -m docker -v` | _pendiente_ |
| [usuario] suite del sandbox en Windows | `uv run pytest tests/sandbox -q` | _pendiente_ |

## Archivos
Agregados: `services/sandbox/{__init__,ast_guard,result,backends}.py`, `sandbox/Dockerfile`, `tests/sandbox/{__init__,conftest,test_ast_guard,test_result,test_backends}.py`, este registro.
Modificados: `services/config.py` y `.env.example` (`SANDBOX_IMAGE`), `CONTEXT.md`, `DECISIONS.md`.
Borrados: ninguno.

## Desvíos respecto del plan
- `services/sandbox/` en lugar de módulos sueltos `ast_guard.py`/`subprocess_backend.py`/`docker_backend.py`: un solo `backends.py` (comparten el directorio de trabajo) y `result.py` para el contrato.
- Variable nueva `SANDBOX_IMAGE`.
- El filtro AST además prohíbe métodos de E/S de pandas (`read_*`, `to_csv`…) y URLs, que el spec no listaba pero que permitirían leer o escribir fuera de las tablas.

## Problemas encontrados
- Reemplazar `socket.socket` por una función rompía `import ssl` (`class SSLSocket(socket)`): se anulan los métodos de conexión en lugar de la clase.
- En el contenedor del desarrollo no hay daemon de Docker: los 5 tests de Docker se saltean acá y se verifican en la PC del alumno.

## For the next iteration
- El Analista llama `run_code(code, {table_id: store.parquet_path(table_id)}, settings=...)` y luego `validate_execution`. El backend usado está en `execution.backend` (va al estado y a la traza, FR-061).
- El prompt de generación debe: usar `load_table("<table_id>")` (no rutas), no importar nada fuera de `ALLOWED_MODULES`, no leer/escribir archivos, e imprimir como última línea `json.dumps(CodeResult)` con `subquestion_id` igual a los ids del `QueryPlan`. Mostrar el motivo de `validate_execution` en el reintento (FR-029).
- `SandboxUnavailable` se lanza solo si `SANDBOX_BACKEND=docker` y Docker no está: la UI debe mostrarlo como error de configuración (FR-043).
