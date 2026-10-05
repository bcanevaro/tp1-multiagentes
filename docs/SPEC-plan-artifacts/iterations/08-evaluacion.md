# Iteración 08 — Evaluación local y evals en LangSmith (bonus)

**Estado**: COMPLETA (criterios PASS; trazas con el desvío documentado).
**Commit**: lo hace el alumno con el mensaje `Evaluación: set de preguntas completo, corrida local y experimento en LangSmith`. SHA: `055f5bec6c6ff57d42b60e0ef672522a1dab05a5`.

## Resultados de criterios
| Criterio | Test | Resultado |
|---|---|---|
| Tolerancias de BR-030, incluido esperado = 0 | `tests/eval/test_scoring.py::test_br030_tolerances[*]` | PASS |
| Búsqueda de valores (escalares y por categoría), estado, `cannot_answer`, `partial` | `tests/eval/test_scoring.py` | PASS |
| VC-068 (simulado): reporte con una fila por pregunta y los 6 campos | `tests/eval/test_run_local.py::test_vc068_report_has_one_row_per_question_with_six_fields` | PASS |
| Pregunta que lanza excepción no corta la evaluación | `test_run_local.py::test_question_that_raises_is_reported_as_error` | PASS |
| Dataset de LangSmith idempotente y evaluadores | `tests/eval/test_run_langsmith.py` | PASS |
| Valores esperados de INDEC = tablas extraídas | `tests/ingestion/test_indec_questions.py` | PASS |
| Suite completa | `uv run pytest -q` | PASS (264 passed, 5 skipped = tests Docker, en el contenedor) |
| Lint / tipos | `uv run ruff check .`, `uv run mypy agents services ui eval app.py` | PASS |
| [usuario] valores de `ind-01`…`ind-05` verificados contra el PDF | — | PASS ("valores OK") |
| [usuario] VC-068: `uv run python -m eval.run_local` → `EVALUATION.md` | — | PASS (reporte con 16 filas y los 6 campos; 14/16 en la 1ª corrida) |
| [usuario] VC-069: `uv run python -m eval.run_langsmith` → experimento con puntajes | — | PASS (experimento con `estado`, `valores`, `correcta` y `exactitud`) |
| [usuario] trazas representativas compartidas | LangSmith (links públicos abajo) | PASS con desvío: 2 de 3 (ver «Trazas») |

## Archivos
Agregados: `eval/{scoring,run_local,run_langsmith}.py`, `tests/eval/{__init__,test_scoring,test_run_local,test_run_langsmith}.py`, `tests/ingestion/test_indec_questions.py`, este registro. Los genera el alumno al correr: `EVALUATION.md`, `eval/last_run.json`.
Modificados: `agents/analyst/coverage.py` y `docs/SPEC.md` (v0.7, D-039), `tests/analyst/test_coverage.py`, `.gitignore` (`.venv-*/`), `eval/questions.yaml` (preguntas `ind-01`…`ind-05`), `agents/analyst/graph.py` (`run_id` en `answer_question`), `services/tracing.py` (`trace_url`, `flush_traces`), `CONTEXT.md`, `DECISIONS.md`, `iterations/07-ui-streamlit.md` (COMPLETA con SHA).
Borrados: ninguno.

## Trazas
- `answered`, multitabla con el PDF real (ind-03): https://smith.langchain.com/public/2183c165-d3cf-4e3b-9412-a88335229d5a/r/8c6c0931-9f58-49dc-8e36-35e389bf9951
- `partial` (syn-04, valor de comparación faltante): https://smith.langchain.com/public/4ade60ee-1d51-48d7-8b55-30f9750d0151/r/50298fd4-00bd-4e28-8fcd-1797ff0d8ce0
- Con reintentos: no hay. La evaluación final tuvo 0 reintentos de código, y la traza del 2/10 con 2 intentos (syn-05, `df.rename` rechazado por el filtro AST) se borró del proyecto. El mecanismo queda cubierto por los tests VC-039/VC-040 y por las corridas reales de la iteración 6, registradas en `iterations/06-agente-analista.md` (syn-01: `exit()` rechazado; syn-04: `value` con texto; syn-05: `.rename`).

## Desvíos respecto del plan
- Solo 2 de las 3 trazas pedidas: no quedó ninguna traza con reintentos (ver «Trazas»).
- 5 preguntas de INDEC en lugar de "≥ 2", para cubrir también `partial`, `cannot_answer` y multitabla con datos reales.
- Columna extra en el detalle de `EVALUATION.md`: tablas usadas contra las esperadas (VC-033).

## Tasa de aciertos y fallas
- **1ª corrida local** (2026-10-05, `gpt-4.1-mini`, sandbox subproceso en WSL): **14/16 correctas (88 %)**; sintético 11/11, INDEC 3/5; 0 reintentos de código. Fallas: `ind-01` y `ind-02` dieron `cannot_answer` por el chequeo de períodos de FR-024 ("2026 hasta agosto", "enero 2026" buscados como frase). Corregido en spec v0.7 (D-039) con tests que reproducen ambos casos.
- **1er experimento en LangSmith** (`analista-gpt-4.1-mini-4a393190`, 16 ejemplos): exactitud 0,88; mismas dos fallas.
- **2ª corrida local** (después de D-039, proyecto LangSmith `mas-2026s2-62179`): **16/16 correctas (100 %)**; estado 16/16, valores 10/10; 0 reintentos; 68 s (la mayoría de las respuestas del LLM vinieron de la caché local). Es la versión de `EVALUATION.md` que se entrega.
- Nota: la 1ª corrida en WSL guardó las trazas en el proyecto `mas-2026s2-<tu-legajo>` porque el `.env` de esa PC tenía el valor de ejemplo; se corrigió antes de la 2ª.

## Problemas encontrados
- En Windows, Smart App Control bloqueó la DLL de `tiktoken` (dependencia de `langchain-openai`): la evaluación se corrió en WSL con un entorno aparte (`UV_PROJECT_ENVIRONMENT=.venv-wsl`). Se documenta en el README como alternativa.

## For the next iteration
- README y `docs/ARCHITECTURE.md` deben enlazar `EVALUATION.md` y explicar cómo correr la evaluación; las fallas de la corrida van a "Limitaciones".
