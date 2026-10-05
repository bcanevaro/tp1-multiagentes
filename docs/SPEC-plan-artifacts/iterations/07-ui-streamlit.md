# Iteración 07 — Interfaz Streamlit

**Estado**: COMPLETA (todos los criterios PASS, incluidos los [usuario]).
**Commit**: lo hace el alumno con el mensaje `UI Streamlit: subir con progreso, explorar tablas y preguntar con historial`. SHA: `d1526aca1997ef5ca92d3a30f0e6e7f4c3ccedf8`.

## Resultados de criterios
| Criterio | Test | Resultado |
|---|---|---|
| VC-065b (pestañas bloqueadas sin `PINECONE_API_KEY`) | `tests/ui/test_app.py::test_vc065b_missing_pinecone_key_blocks_upload_and_ask` | PASS |
| VC-065 (barra lateral sin claves) | `test_app.py::test_vc065_sidebar_shows_configuration_without_keys` | PASS |
| VC-063 (LiteLLM caído al preguntar, la siguiente pregunta funciona) | `test_app.py::test_vc063_litellm_error_is_shown_and_next_question_works` | PASS |
| VC-064 (Pinecone con clave inválida al subir, la app sigue) | `test_app.py::test_vc064_pinecone_error_is_shown_and_app_survives` | PASS |
| VC-002, VC-002b, VC-002c (mensajes en la UI) | `test_app.py::test_vc002_invalid_pdfs_show_messages[*]` (4 casos) | PASS |
| VC-022, VC-023, VC-061 (simulados) | `test_app.py::test_upload_shows_progress_summary_and_feeds_explore` | PASS |
| VC-062 (simulado: 2 preguntas con los 7 elementos) | `test_app.py::test_two_questions_keep_history_with_all_elements` | PASS |
| Sandbox no disponible, `.env` inválido, preguntas de ejemplo | `test_app.py::test_sandbox_unavailable_is_reported`, `test_invalid_env_value_*`, `test_example_question_runs_with_its_id` | PASS |
| Clasificación de errores | `tests/ui/test_errors.py` | PASS |
| Clave de LiteLLM inválida en la ingesta (D-034) | `tests/ingestion/test_graph.py::test_service_error_on_every_table_stops_ingestion` | PASS |
| Suite completa | `uv run pytest -q` | PASS (234 passed, 5 skipped = tests Docker, en el contenedor) |
| Lint / tipos | `uv run ruff check .`, `uv run mypy agents services ui app.py` | PASS |
| [usuario] VC-022, VC-023, VC-060: subir el PDF sintético desde la UI | `uv run streamlit run app.py` | PASS (el alumno usó la app y cerró la iteración con el commit) |
| [usuario] VC-061: Explorar con los dos PDFs ingeridos | idem | PASS (el alumno usó la app y cerró la iteración con el commit) |
| [usuario] VC-062: dos preguntas en el historial con los 7 elementos | idem | PASS (el alumno usó la app y cerró la iteración con el commit) |

## Archivos
Agregados: `ui/{__init__,runtime,errors,sidebar,upload,explore,ask}.py`, `tests/ui/{__init__,conftest,test_app,test_errors}.py`, este registro.
Modificados: `app.py` (la app completa), `agents/ingestion/graph.py` (`is_service_error`, escalado en `enrich`), `tests/ingestion/test_graph.py`, `CONTEXT.md`, `DECISIONS.md`, `iterations/06-agente-analista.md` (COMPLETA con SHA).
Borrados: ninguno.

## Desvíos respecto del plan
- `ui/runtime.py` agregado (punto de inyección para los tests, D-033).
- Extras elegidos por el alumno: progreso en vivo del Analista y preguntas de ejemplo (D-031).
- `mypy` ahora también cubre `ui` y `app.py`.

## Problemas encontrados
- Con una clave de LiteLLM inválida, la ingesta reintentaba cada tabla como si los metadatos fueran inválidos y terminaba con un mensaje que no mencionaba LiteLLM. Corregido (D-034).

## For the next iteration
- La evaluación (iteración 8) reutiliza `agents.analyst.graph.answer_question(question, question_id)` + `to_outcome`, y `agents.analyst.cli.load_questions()`.
