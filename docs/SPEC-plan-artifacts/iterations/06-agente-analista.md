# Iteración 06 — Agente Analista completo

**Estado**: COMPLETA (todos los criterios PASS, incluidos los [usuario]).
**Commit**: lo hace el alumno con el mensaje `Agente Analista: plan de consulta, selección con cobertura, código autocorregido y estados de respuesta`. SHA: `622239eaa4d838d4c8b94bcbe7434f4c3294fde0` (incluye los cuatro paquetes de la iteración: base, 6b, 6c y 6d).

## Resultados de criterios
| Criterio | Test | Resultado |
|---|---|---|
| VC-030 (plan con 2 partes recorre el grafo, 2 tablas) | `tests/analyst/test_graph.py::test_vc030_two_part_question_two_tables` | PASS (la descomposición real: [usuario]) |
| VC-031 | `test_graph.py::test_vc031_candidates_are_deduplicated` | PASS |
| VC-032 | `test_graph.py::test_vc032_empty_index` | PASS |
| VC-034 | `tests/analyst/test_coverage.py::test_vc034_*`, `test_graph.py::test_vc034_vc035_uncovered_period_skips_code` | PASS |
| VC-034b | `test_coverage.py::test_vc034b_normalized_entity_and_year_inside_column_name` | PASS |
| VC-034c / VC-048 | `test_coverage.py::test_vc034c_*` (3 casos) | PASS |
| VC-035 | `test_graph.py::test_vc034_vc035_uncovered_period_skips_code` | PASS |
| VC-036 | `test_graph.py::test_vc036_code_prompt_has_columns_dtypes_units_and_table_id` | PASS |
| VC-037 | `test_graph.py::test_vc037_answered_end_to_end` (sandbox subproceso real) | PASS |
| VC-039 | `test_graph.py::test_vc039_retry_after_failure_includes_previous_error` | PASS |
| VC-040 | `test_graph.py::test_vc040_always_failing_generator` | PASS |
| VC-041 | `tests/analyst/test_status_answer.py::test_vc041_decision_table[*]` | PASS |
| VC-044 | `test_graph.py::test_vc044_answer_node_only_returns_answer` | PASS |
| VC-049 | `test_status_answer.py::test_vc049_*`, `test_graph.py::test_vc040_*` | PASS |
| Reintentos por filtro AST y JSON incompleto (D-027) | `test_graph.py::test_rejected_code_and_incomplete_json_trigger_retries` | PASS |
| Formato argentino | `test_status_answer.py::test_argentine_number_format[*]` | PASS |
| Suite completa | `uv run pytest -q` | PASS (217 passed, 5 skipped = tests Docker, en el contenedor) |
| Lint / tipos | `uv run ruff check .`, `uv run mypy agents services` | PASS |
| VC-034d, VC-047 (FR-024c) | `test_coverage.py::test_non_concrete_period_*`, `test_month_names_*`, `test_document_scope_entity_*`, `test_entity_found_in_description_*`, `test_vc047_*`, `test_reference_average_*` | PASS |
| [usuario] preguntas syn-01…syn-11 por CLI con servicios reales (Docker) | `uv run python -m agents.analyst.cli --doc informe_sintetico.pdf` | 1ª corrida: 8/11 estados (syn-02, syn-04, syn-08 corregidos, D-029); 2ª: 11/11 estados, con valores a corregir en syn-01, syn-02 y syn-04 (D-030); 3ª: **11/11 estados y todos los valores dentro de la tolerancia** (syn-01 84,88 %; syn-02 1,13/1,07/1,17/1,23/1,15 %; syn-04 Norte 9,8 % sin la diferencia; syn-05; syn-06 7,49 %; syn-08 956,69) — PASS |
| [usuario] trazas `analyst:<pregunta>` con `question_id`, `model`, `sandbox_backend` (VC-066, VC-067) | LangSmith, traza de syn-05: tag `analyst`, metadatos `model=gpt-4.1-mini`, `question_id=syn-05`, `sandbox_backend=docker` | PASS |
| [usuario] suite completa en Windows | `uv run pytest -q` | PASS |

## Archivos
Agregados: `agents/analyst/{schemas,coverage,status,prompts,answer,graph,cli}.py`, `tests/analyst/{conftest,fakes,test_coverage,test_status_answer,test_graph}.py`, este registro.
Modificados: `services/config.py` y `.env.example` (`LLM_CODE_MODEL`), `services/llm.py` (`get_chat_model(model=...)`), `tests/test_llm.py`, `docs/SPEC-plan.md`, `eval/questions.yaml` (syn-01 reformulada), `services/sandbox/ast_guard.py` y `tests/sandbox/test_ast_guard.py` (`rename`/`remove` permitidos), `tests/test_questions.py` (solo formato), `docs/SPEC.md` (v0.6), `CONTEXT.md`, `DECISIONS.md`.
Borrados: ninguno.

## Desvíos respecto del plan
- `AnalystState` está en `graph.py` (TypedDict), no en `schemas.py`.
- `decide_status(subquestions, coverage, code_result, error)` recibe también las subpreguntas (para los textos de lo que falta).
- El código carga tablas con `load_table(table_id)` en vez de rutas (FR-026 y VC-036 ajustados en spec v0.5).
- CLI con `--id` y `--doc` para correr preguntas de `eval/questions.yaml` y comparar el estado esperado.

## Problemas encontrados
- Primera corrida real: falsos `cannot_answer` en syn-02 (período "todos los años disponibles") y syn-08 (entidad "provincia"), y syn-04 respondida con un promedio provincial calculado como promedio simple de departamentos (BR-013). Corregido con spec v0.6 y FR-024c (D-029).
- El test VC-034c mostró que la primera versión de FR-024b excluía columnas llamadas "2021", "2022"… (tablas anchas), con lo que la pregunta de salario real habría quedado cubierta. Corregido en código y spec (D-026).

- Segunda corrida real: proporciones como fracción (syn-02), el código respondió una parte sin datos dentro de otra subpregunta (syn-04) y syn-01 era ambigua. Corregido (D-030).

- Tercera corrida: dos reintentos evitables por el filtro AST: `exit()` (ahora el prompt lo prohíbe explícitamente) y `df.rename(...)`, rechazado por parecerse a `os.rename`; se quitaron `rename` y `remove` de los métodos prohibidos (no son alcanzables como operaciones de archivo sin importar os/pathlib), con test.

## For the next iteration
- UI: usar `stream_answer(question, question_id=None, services=None, settings=None)` → `(nodo, actualización)`; cada actualización trae `log: [línea]`. Al final, armar el estado acumulado y llamar `to_outcome(state)` → `AnalystOutcome(question, status, error, answer, code_result, missing, tables, code, executions, retries)`.
- Mostrar: `status` como badge, `answer`, `tables` (nombre, PDF, páginas), `missing` (con `related_table`), `code` y `executions[-1].stdout/stderr`, `retries` y el motivo de cada intento fallido (`executions[i].error`), `executions[-1].backend`.
- `default_services(settings)` puede lanzar `SandboxUnavailable` si `SANDBOX_BACKEND=docker` sin Docker: mostrarlo como error de configuración (FR-043).
