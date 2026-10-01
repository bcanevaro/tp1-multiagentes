# Iteración 01 — Fundaciones, configuración y chequeo de servicios

**Estado**: COMPLETA (todos los criterios PASS, incluidos los [usuario]).
**Commit**: lo hace el alumno con el mensaje `Fundaciones: proyecto uv, configuración, fábricas LLM/embeddings y chequeo de servicios`. SHA: `5736c3eea6dc39a72caac4293b5f7cdfdb3ee7f8`. Los arreglos posteriores (config, check_services, D-007, `.env.example` con modelos) entran en el commit de la Iteración 2.

## Resultados de criterios
| Criterio | Comando | Resultado |
|---|---|---|
| Tests | `uv run pytest -q -W error` | PASS (13 passed) |
| Lint | `uv run ruff check .` | PASS |
| Tipos | `uv run mypy agents services` | PASS (0 errores, strict) |
| VC-065b (config) | `tests/test_config.py::test_missing_pinecone_key_is_reported` | PASS |
| VC-065d | `tests/test_llm.py::test_dimension_mismatch_reports_both_values` | PASS |
| run_config 68 chars | `tests/test_tracing.py::test_analyst_run_name_is_truncated` | PASS |
| `.gitignore` contiene `.env` | inspección | PASS |
| [usuario] `.env` fuera del repo | el alumno sube por la web de GitHub sin el `.env` | PASS (a confirmar visualmente en GitHub) |
| [usuario] `check_services.py` todo PASS | en la PC del alumno (Windows, Python 3.14) | PASS: 7/7; gpt-4.1-mini responde en 2.0 s; salida estructurada: function_calling, json_schema y json_mode funcionan; embeddings dim 1536; Pinecone OK (índice aún no creado); LangSmith OK (proyecto mas-2026s2-62179) |

Prueba en seco de `check_services.py` sin `.env`: informa las variables faltantes y omite cada chequeo con el motivo (no explota).

## Archivos
Agregados: `pyproject.toml`, `uv.lock`, `.gitignore`, `.env.example`, `README.md` (placeholder), `app.py`, `agents/__init__.py`, `agents/ingestion/__init__.py`, `agents/analyst/__init__.py`, `services/__init__.py`, `services/config.py`, `services/llm.py`, `services/tracing.py`, `scripts/__init__.py`, `scripts/check_services.py`, `eval/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_config.py`, `tests/test_llm.py`, `tests/test_tracing.py`, `data/sample_pdfs/.gitkeep`, `docs/SPEC.md`, `docs/SPEC-plan.md`, `docs/SPEC-plan-artifacts/*`.
Borrados: ninguno.

## Desvíos respecto del plan
- Se quitó `langchain-community` de las dependencias (D-002).
- Se agregó la variable `LLM_STRUCTURED_METHOD` (D-003).
- Versiones resueltas: langgraph 1.2.12, langchain 1.4.3, langchain-core 1.6.6, langchain-openai 1.6.7, langsmith 0.14.2, pinecone 10.0.0, streamlit 1.64.0, pymupdf 1.28.2, pandas 3.0.6, pyarrow 25.0.1, pydantic 2.13.5.

## Problemas encontrados
- `langchain_core.load.loads` emite `LangChainBetaWarning` y un aviso de `allowed_objects`: se pasa `allowed_objects="core"` y se silencia el aviso beta localmente.
- mypy + plugin pydantic no reconoce los alias `base_url`/`api_key` de `OpenAIEmbeddings` (sí los de `ChatOpenAI`): `type: ignore[call-arg]` puntual.
- `OpenAIEmbeddings` necesita `check_embedding_ctx_length=False` para modelos que no son de OpenAI detrás de LiteLLM.

## For the next iteration
- Usá `make_settings(...)` de `tests/conftest.py` en los tests; no llames a `get_settings()` en tests.
- `reportlab` ya está en las dependencias de desarrollo para generar el PDF sintético.
- Si el alumno informa que `function_calling` no funciona con el proxy, actualizá el default de `LLM_STRUCTURED_METHOD` en `.env.example` según lo que reporte `check_services.py`.

## Correcciones tras la prueba en la PC del alumno (Windows, Python 3.14)
- Smart App Control de Windows bloqueó la DLL de `uuid_utils` (dependencia de langsmith/langchain-core). El alumno lo resolvió en su PC; queda como limitación a documentar en el README (alternativa: WSL).
- `EMBEDDING_DIM=` vacío rompía `Settings` → `env_ignore_empty=True` (test `test_empty_values_in_env_file_are_treated_as_unset`).
- `.env` guardado con BOM por el Bloc de notas → `env_file_encoding="utf-8-sig"` (test `test_env_file_with_bom_is_read`).
- `check_services.py`: el listado de modelos corre aunque `LLM_MODEL`/`EMBEDDING_MODEL` estén vacíos, para poder descubrir sus nombres.
- Tests: 15 passed.
