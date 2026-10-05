# CONTEXT — estado actual del proyecto

_Última actualización: Iteración 9 (documentación final). Describe el sistema entregado._

## Current state
- Proyecto Python 3.11 gestionado con `uv` (`pyproject.toml` + `uv.lock`), sin empaquetar (`[tool.uv] package = false`): los módulos se importan desde la raíz del repo.
- Configuración tipada (`services/config.py`) que lee `.env` y detecta variables obligatorias faltantes, en total o por funcionalidad.
- Fábricas de chat y embeddings contra el proxy LiteLLM con caché SQLite local opcional (`services/llm.py`) y verificación de la dimensión de embeddings.
- Helper de configuración de trazas LangSmith (`services/tracing.py`), todavía sin usar por ningún grafo.
- `scripts/check_services.py` verifica en la PC del alumno los servicios externos. **UI Streamlit** (`uv run streamlit run app.py`): pestañas Subir PDF (progreso nodo por nodo, resumen por tabla, avisos y errores), Explorar (tablas del almacén local agrupadas por documento, datos completos y columnas) y Preguntar (historial tipo chat con estado coloreado, faltantes, tablas, código, salida y reintentos; progreso en vivo; preguntas de ejemplo). Barra lateral con la configuración sin claves. Si faltan variables, Subir y Preguntar quedan bloqueadas. Errores de LiteLLM, Pinecone y sandbox se muestran con `st.error` sin tirar la app.
- **Agente Analista completo** (`agents/analyst/graph.py`): StateGraph `understand → retrieve → select → generate_code → execute → validate_output (⇄ generate_code) → decide_status → answer`, con cortes a `decide_status` si el índice está vacío o ninguna subpregunta está cubierta. Chequeos determinísticos FR-024/FR-024b/FR-024c, reintentos hasta `ANALYST_MAX_RETRIES`, estado por reglas (BR-010) y respuesta `cannot_answer` sin LLM. CLI: `uv run python -m agents.analyst.cli "<pregunta>"` o `--id syn-01` / `--doc informe_sintetico.pdf`. Probado con LLM simulados y sandbox real por subproceso; la corrida con servicios reales la hace el alumno.
- **Sandbox** (`services/sandbox/`): `run_code(code, {table_id: parquet})` con filtro AST + backend Docker (`--network none`, solo lectura, 512 MB, 1 CPU, 64 procesos, usuario 10001) o subproceso (`python -I`, entorno vacío, directorio temporal con solo las tablas elegidas, red bloqueada en el preludio, timeout). `validate_execution` aplica FR-028 y devuelve `CodeResult`. Imagen: `sandbox/Dockerfile`.
- **Agente de Ingesta completo** (`agents/ingestion/graph.py`): StateGraph `load_pdf → extract_tables → merge_continuations → collect_context → enrich ⇄ validate → persist_and_index`, con anotación por LLM (salida estructurada, una llamada por tabla en paralelo), validación BR-001…004 con reintento solo de las tablas inválidas, almacén Parquet+JSON, copia del PDF y Pinecone idempotente. CLI: `uv run python -m agents.ingestion.cli <pdf>`. Probado con servicios simulados; la ingesta real la corre el alumno.
- Extracción determinística completa (sin LLM): carga del PDF, detección de tablas (PyMuPDF `lines` + respaldo propio por líneas horizontales), filtro de detecciones que no son tablas, aplanado de encabezados, normalización numérica, unión multipágina y contexto. Sobre el PDF sintético reproduce exactamente `sample_truth.json`; sobre INDEC obtiene los Cuadros 1-10 y la tabla de diagnósticos de la p. 35. CLI de diagnóstico: `uv run python -m agents.ingestion.extract <pdf>`.
- PDF sintético reproducible `data/sample_pdfs/informe_sintetico.pdf` (3 páginas, 6 cuadros) con su verdad en `tests/fixtures/sample_truth.json`; 9 PDFs de casos borde que se generan en los tests; 11 preguntas de evaluación en `eval/questions.yaml` con valores verificados por test.

## File map
| Archivo | Responsabilidad |
|---|---|
| `pyproject.toml`, `uv.lock` | Dependencias y configuración de ruff, mypy (strict) y pytest |
| `.env.example` | Todas las variables de spec §7.1 + `LLM_STRUCTURED_METHOD` |
| `.gitignore` | Excluye `.env`, `.venv/`, `.cache/`, `data/store/` |
| `services/config.py` | `Settings`, `get_settings()`, `REQUIRED_BY_FEATURE`, `PROJECT_ROOT` |
| `services/llm.py` | `get_chat_model`, `with_structured`, `get_embeddings`, `check_embedding_dim`, cachés |
| `services/tracing.py` | `run_name`, `run_config` |
| `scripts/check_services.py` | Diagnóstico PASS/FAIL de .env, LiteLLM, salida estructurada, embeddings, Pinecone, LangSmith |
| `app.py` | App Streamlit: configuración, barra lateral y las 3 pestañas |
| `ui/runtime.py` | `load_settings`, `ingestion_services`, `analyst_services`, `table_store`, `sandbox_label` (punto de inyección para tests) |
| `ui/errors.py` | `classify(exc) -> (servicio, mensaje)`, `format_service_error`, `show_service_error(exc, during)` |
| `ui/sidebar.py` | `render_sidebar(settings, missing)` |
| `ui/upload.py` | `IngestResult`, `run_ingestion(pdf_name, data, settings)`, `render_table_summary`, `render_result`, `render(settings, missing)`; resultado en `st.session_state["last_ingest"]` |
| `ui/explore.py` | `render(settings)`, `columns_frame(meta)` |
| `ui/ask.py` | `HistoryEntry`, `run_question`, `render_outcome`, `render_entry`, `render(settings, missing)`; historial en `st.session_state["ask_history"]`; claves de widgets `example`, `ask_example`, `ask_input` |
| `eval/scoring.py` | `close`, `obtained_pool`, `score(question, status, code_result) -> Score(status_ok, values_ok, correct, details)`, `expected_text` (BR-030, D-035) |
| `eval/run_local.py` | `uv run python -m eval.run_local [--id X] [--doc Y]`: `load_questions`, `run_question`, `evaluate(questions, services, store, project)`, `render_report`, `write_outputs`, `missing_docs`; escribe `EVALUATION.md` y `eval/last_run.json` |
| `eval/run_langsmith.py` | `uv run python -m eval.run_langsmith [--doc Y]`: `sync_dataset`, `make_target`, evaluadores `estado`, `valores`, `correcta`, resumen `exactitud` |
| `tests/eval/` | Tests de `scoring`, `run_local` (Analista simulado) y `run_langsmith` (cliente falso) |
| `tests/ingestion/test_indec_questions.py` | Recalcula los valores esperados de INDEC desde las tablas extraídas |
| `README.md` | Documentación para quien corrige: instalación, uso, diagramas, decisiones, evaluación, limitaciones, problemas frecuentes, créditos |
| `EVALUATION.md` | Reporte de `eval.run_local` (corrida final 16/16) + `eval/notes.md` |
| `eval/notes.md` | Trazas representativas y análisis, escritos a mano; `eval.run_local` los copia en cada reporte |
| `docs/ARCHITECTURE.md` | Estados de los grafos, contratos, persistencia, sandbox, servicios, evaluación y tests |
| `docs/graphs/*.mmd`, `scripts/export_graphs.py` | Diagramas Mermaid de los grafos (`draw_mermaid()`); `uv run python scripts/export_graphs.py` los regenera |
| `tests/test_docs.py` | Docs sin referencias internas, diagramas al día, variables del `.env` documentadas |
| `tests/ui/` | `conftest.py` (`UiEnv`, fixture `ui_env` que reemplaza `ui.runtime` con fakes, `share_analyst`, `uncovered_analyst`), `test_app.py` (AppTest), `test_errors.py` |
| `agents/ingestion/pdf_loader.py` | `open_pdf`, `load_pdf`, `read_pdf`, `compute_doc_id`; dataclasses `LoadedPdf`, `PageData`, `TextBlock`, `PageImage`; errores `PdfOpenError`, `NoTextLayerError` |
| `agents/ingestion/extract.py` | `extract_tables`, `RawTable`, `ExtractionWarning`, `split_header`, `flatten_header`, `is_data_number`, `clean_cell`, `CAPTION_RE`; CLI `main` |
| `agents/ingestion/normalize.py` | `normalize_table`, `parse_number`, `MISSING_MARKERS` |
| `agents/ingestion/merge.py` | `merge_continuations`, `is_continuation` |
| `agents/ingestion/context.py` | `collect_context`, `TableContext` |
| `agents/ingestion/schemas.py` | `TableAnnotation`/`ColumnAnnotation` (salida del LLM), `TableMetadata`/`ColumnInfo`/`Source` (spec §7.2), `TableDraft` (tabla JSON en el estado, `to_dataframe()`), `TableContextData`, `preview_markdown()` |
| `agents/ingestion/validate.py` | `validate_annotation` (BR-001…004, errores con prefijo "BR-00N"), `build_metadata`, `table_id_for`, `count_sentences` |
| `agents/ingestion/prompts.py` | `SYSTEM_PROMPT`, `build_messages(draft, pdf_name, previous_errors)` |
| `agents/ingestion/graph.py` | `IngestionServices`, `default_services`, `llm_annotator`, `IngestionState`, `RawTableData`, `build_ingestion_graph`, `ingest_pdf`, `stream_ingest` |
| `agents/ingestion/cli.py` | CLI de ingesta con progreso, resumen (FR-017), avisos y conteo de vectores en Pinecone |
| `services/table_store.py` | `TableStore(data_dir)`: `save`, `save_pdf`, `delete_doc`, `load_df`, `load_metadata`, `list_tables(doc_id=None)`, rutas |
| `services/vector_index.py` | `VectorIndex` (Protocol), `PineconeIndex`, `InMemoryIndex`, `get_vector_index`, `embedding_text`, `pinecone_metadata`, `IndexDimensionError`, `VectorRecord`, `Match` |
| `services/sandbox/__init__.py` | `run_code`, `resolve_backend`, `SandboxUnavailable`; reexporta `CodeResult`, `ExecutionResult`, `validate_execution`, `parse_code_result`, `check_code`, `ALLOWED_MODULES` |
| `services/sandbox/ast_guard.py` | `check_code(code) -> list[str]`, `ensure_safe`, `CodeRejected`, `ALLOWED_MODULES`, `FORBIDDEN_NAMES` |
| `services/sandbox/result.py` | `ExecutionResult`, `CodeResult` (`results[ResultItem{subquestion_id, value: float \| list[LabeledValue{label,value}], unit, label}]`, `missing[MissingItem{subquestion_id, reason}]`, `conversions[str]`), `parse_code_result`, `validate_execution` |
| `services/sandbox/backends.py` | `PRELUDE`, `prepare_workdir`, `run_subprocess`, `run_docker`, `docker_status(image)` (cacheado por proceso) |
| `sandbox/Dockerfile` | python:3.11-slim + pandas 3.0.6, numpy 2.4.6, pyarrow 25.0.1; usuario 10001 |
| `agents/analyst/schemas.py` | `SubQuestion`, `QueryPlan`, `SubquestionCoverage`, `Selection`, `GeneratedCode` (salidas del LLM); `Candidate`, `MissingInfo`, `ExecutionSummary`, `UsedTable`, `AnalystOutcome`; `Status`, `AnalystError` |
| `agents/analyst/coverage.py` | `apply_deterministic_checks(subquestions, coverage, candidates)` (FR-024, FR-024b, FR-024c), `check_periods_and_entities`, `check_units`, `check_reference_value`, `is_checkable_period`, `GENERIC_ENTITIES`, `normalize` |
| `agents/analyst/status.py` | `decide_status(subquestions, coverage, code_result, error) -> (status, missing)` (BR-010) |
| `agents/analyst/prompts.py` | `plan_messages`, `select_messages`, `code_messages`, `answer_messages`, `describe_table` |
| `agents/analyst/answer.py` | `fmt_number` (formato argentino), `fmt_with_unit`, `format_results`, `format_tables`, `format_missing`, `cannot_answer_text` |
| `agents/analyst/graph.py` | `AnalystServices`, `default_services`, `AnalystState`, `build_analyst_graph`, `answer_question`, `stream_answer`, `to_outcome` |
| `agents/analyst/cli.py` | CLI con progreso, resultado, código, salida, reintentos; `--id`/`--doc` comparan con el estado esperado |
| `tests/analyst/` | `fakes.py` (`synthetic_tables()` con 4 tablas del PDF sintético, `populate(dir) -> (TableStore, InMemoryIndex)`, `Recorder`, `sub`, `plan`, `cover`, `code`, `make_services`), `test_coverage.py`, `test_status_answer.py`, `test_graph.py` |
| `data/sample_pdfs/indec_ica.pdf` | PDF real de INDEC (ICA, cifras de agosto de 2026, 36 páginas) |
| `data/sample_pdfs/informe_sintetico.pdf` | PDF sintético versionado (entregable de la consigna). Se regenera con `scripts/make_sample_pdf.py`. El alumno agregará `indec_ica.pdf` |
| `scripts/sample_data.py` | Única fuente de los números del PDF sintético; `fmt_ar`, `fmt_ar_parens`, `export_total` |
| `scripts/make_sample_pdf.py` | Genera el PDF sintético (reportlab, `invariant=1`) y `tests/fixtures/sample_truth.json`; `build(pdf_path, truth_path)` |
| `scripts/make_test_fixtures.py` | `build_all(out_dir) -> dict[nombre, Path]` y `FIXTURES` (caso y resultado esperado de cada PDF de borde) |
| `tests/fixtures/sample_truth.json` | Por tabla: `key`, `caption`, `section_title`, `paragraph_before`, `footnote`, `paragraph_after`, `columns` (nombres aplanados esperados), `rows_text` (celdas como se imprimen), `values` (valores normalizados esperados; `null` = s/d), `header_rows`, `line_style` (`grid`/`horizontal`), `pages` (1-based), `n_rows`, `n_cols` |
| `eval/questions.yaml` | 16 preguntas: 11 del PDF sintético (`syn-01`…`syn-11`) y 5 de INDEC (`ind-01`…`ind-05`); campos `id, doc, question, expected_status, expected_values[{label, value\|values, unit}], expected_missing, tables, kind, notes` |
| `tests/conftest.py` | Fixture autouse que limpia variables de entorno de servicios; `make_settings(**overrides)` crea `Settings` sin leer `.env`; `edge_pdfs` (scope session) genera los PDFs de borde en un tmp y devuelve `dict[nombre, Path]` |
| `tests/test_config.py`, `tests/test_llm.py`, `tests/test_tracing.py` | Tests de la iteración 1 |
| `tests/test_sample_pdf.py`, `tests/test_edge_pdfs.py`, `tests/test_questions.py` | Tests de la iteración 2 |
| `tests/ingestion/conftest.py` | `Extraction` (loaded, raw, tables, warnings, `.context(t)`), `run_extraction(path)`; fixtures de sesión `sample`, `indec`, `edge` |
| `tests/ingestion/test_{loader,extract,normalize,context}.py` | Tests de la iteración 3 (VC-001…VC-010) |
| `tests/ingestion/fakes.py` | `FakeAnnotator(failures={idx: n})` (cuenta llamadas y errores recibidos), `good_annotation`, `bad_annotation`, `HashEmbeddings` (dim 8), `make_services(data_dir, annotator, index, index_factory, max_retries)` |
| `tests/ingestion/test_validate.py`, `tests/ingestion/test_graph.py` | Tests de la iteración 4 |
| `tests/sandbox/` | `conftest.py` (`table`, `sub_settings`, `docker_ready()`), `test_ast_guard.py`, `test_result.py`, `test_backends.py` (tests Docker con `@pytest.mark.docker`, se saltean si no hay daemon o imagen) |

## Public interfaces
- `services.config.Settings` (pydantic-settings, `case_sensitive=True`). Campos: los de spec §7.1 más `LLM_STRUCTURED_METHOD: Literal["function_calling","json_schema","json_mode"]` (default `function_calling`) y `CACHE_DIR: Path` (default `.cache`). Métodos/propiedades: `missing_required(feature: Literal["ingest","ask","explore"] | None = None) -> list[str]`, `resolve_path(Path) -> Path`, `data_dir`, `cache_dir` (rutas absolutas resueltas contra `PROJECT_ROOT`).
- `services.config.get_settings() -> Settings` (cacheada con `lru_cache`; también hace `load_dotenv` sin pisar el entorno).
- `services.config.REQUIRED_BY_FEATURE: dict[Feature, tuple[str, ...]]` — `ingest` y `ask` necesitan LiteLLM + embeddings + Pinecone + LangSmith; `explore` no necesita nada.
- `services.llm.get_chat_model(settings=None, temperature=0.0) -> BaseChatModel` (activa la caché global si `LLM_CACHE`); lanza `ConfigurationError` si falta configuración.
- `services.llm.with_structured(llm, schema, settings=None) -> Runnable[Any, schema]` — usar SIEMPRE esto para salida estructurada (respeta `LLM_STRUCTURED_METHOD`).
- `services.llm.get_embeddings(settings=None) -> Embeddings` (envuelto en `CachedEmbeddings` si `LLM_CACHE`).
- `services.llm.check_embedding_dim(embeddings, expected) -> int`; lanza `EmbeddingDimensionError(actual, expected)`.
- `agents.ingestion.pdf_loader.read_pdf(source: bytes | Path, name=None) -> (pymupdf.Document, LoadedPdf)` — el llamador cierra el Document. Lanza `PdfOpenError(reason)` (mensaje "No se pudo abrir el PDF: <motivo>") o `NoTextLayerError`. `LoadedPdf`: `doc_id`, `name`, `pages: list[PageData]`, `zero_dash` (el doc declara "-" = cero), `decimal_comma`, `body_font_size`, `page(n)` (1-based).
- `agents.ingestion.extract.extract_tables(doc, loaded) -> (list[RawTable], list[ExtractionWarning])` — por página, en orden de lectura, sin unir. `RawTable`: `pages`, `bbox`, `last_bbox`, `header_rows` (celdas crudas, `None` = combinada), `rows` (datos como texto limpio), `strategy` (`lines`/`hrules`), `n_cols`, `page`, `columns` (nombres aplanados, únicos). `ExtractionWarning(page, code, message)`, codes: `image_region`, `page_without_text`, `empty_table`, `not_a_table`, `unparsed_cells`.
- `agents.ingestion.merge.merge_continuations(tables, loaded) -> list[RawTable]`.
- `agents.ingestion.context.collect_context(table, loaded, all_tables=None) -> TableContext(caption, paragraph_before, paragraph_after, section_title, footnotes)`; `TableContext.as_prompt_text()` arma el bloque de contexto para el prompt. Pasar `all_tables` para que no se tome texto de otras tablas como contexto.
- `agents.ingestion.normalize.normalize_table(table, loaded) -> (pd.DataFrame, notes: list[str], warnings)` — columnas numéricas en float64 (porcentajes en escala 0-100, moneda sin símbolo), texto como str; `notes` explica convenciones aplicadas ("-" como cero/faltante, "*" provisorio) y va a `TableMetadata.notes`.
- `agents.ingestion.graph.ingest_pdf(pdf_path, pdf_name=None, services=None, settings=None) -> IngestionState` y `stream_ingest(...)` → iterador de `(nodo, actualización)`; cada actualización trae `log: [línea]` (FR-018) y puede traer `warnings: [str]`. Estado final: `doc_id`, `drafts: list[TableDraft]`, `indexed: list[TableMetadata]`, `failed: list[int]`, `warnings`, `error: str | None` (mensajes de FR-002, FR-019, FR-019b, FR-064 o "Ninguna tabla pasó la validación…"). Sin `services` usa `default_services(get_settings())`.
- `IngestionServices(annotate, embeddings_factory, index_factory, store, max_retries, index_name)`; `Annotator = Callable[[list[(TableDraft, errores_previos)], pdf_name, config], list[TableAnnotation | Exception]]`.
- Pinecone: id = `table_id`; metadatos según spec §7.3, `pages` como lista de strings (Pinecone no admite listas de números); índice serverless coseno en `PINECONE_CLOUD`/`PINECONE_REGION` (aws/us-east-1).
- `services.table_store.TableStore`: `tables/{table_id}.parquet|.json`, `pdfs/{doc_id}.pdf` bajo `DATA_DIR`. Los textos se leen del Parquet como dtype `str` de pandas 3.
- `services.sandbox.run_code(code, tables: dict[table_id, Path], *, settings=None, backend=None, timeout=None, guard=True) -> ExecutionResult(stdout, stderr, exit_code, duration_s, backend, timed_out, rejected)`. Dentro del programa existen `pd` y `load_table(table_id) -> DataFrame` (y `TABLES`); el programa debe imprimir como **última línea** un JSON `CodeResult`. Los errores muestran líneas de `program.py` (= código generado). `validate_execution(execution) -> (CodeResult | None, motivo | None)`.
- `SANDBOX_IMAGE` (default `mas-tp-sandbox`) en `Settings`/`.env.example`; `SANDBOX_BACKEND=auto` elige Docker si `docker_status` da OK.
- `agents.analyst.graph.answer_question(question, question_id=None, services=None, settings=None) -> AnalystState` y `stream_answer(...)` → `(nodo, actualización)` con `log: [línea]`. `to_outcome(state) -> AnalystOutcome(question, status, error, answer, code_result, missing[MissingInfo(subquestion_id, text, reason, related_table)], tables[UsedTable(table_id, name, pages, pdf_name)], code, executions[ExecutionSummary(attempt, code, stdout, stderr, exit_code, duration_s, backend, timed_out, rejected, error)], retries)`. Nodos: `understand`, `retrieve`, `select`, `generate_code`, `execute`, `validate_output`, `decide_status`, `answer` (este último devuelve solo `{"answer": ...}`).
- `AnalystServices(plan, select, code, write, embeddings_factory, index_factory, store, run_code, max_retries, retrieval_k, sandbox_backend, model)`; los cuatro LLM son `(mensajes, config) -> resultado`. `default_services(settings)` puede lanzar `SandboxUnavailable`.
- `LLM_CODE_MODEL` (opcional) en `Settings`: modelo para generar código; vacío = `LLM_MODEL`. `get_chat_model(settings=None, temperature=0.0, model=None)`.
- `services.tracing.trace_url(run_id, project) -> str` ("" si no se puede) y `flush_traces()`; `answer_question(..., run_id=UUID)` fija el id de la traza raíz.
- `services.tracing.run_config(kind: Literal["ingest","analyst"], label: str, **metadata) -> RunnableConfig` — `run_name` = `ingest:<label>` o `analyst:<label[:60]>`, `tags=[kind]`, metadata sin valores `None`.

## Conventions & invariants
- Identificadores en inglés; textos de UI, prompts, mensajes de error y documentación en español.
- Todo acceso a LLM/embeddings pasa por `services.llm` (nunca instanciar `ChatOpenAI`/`OpenAIEmbeddings` en otro lado).
- Todo grafo se invoca con `config=run_config(...)`.
- Tests: no usan red; usan `make_settings(...)` en lugar de `get_settings()`; servicios externos con fakes.
- `mypy --strict` sobre `agents` y `services` sin errores; `ruff` (E,F,I,B,UP,SIM; línea 100) sin errores.
- No hay git en la copia de trabajo del contenedor: el alumno sube los archivos a GitHub desde la web (sin usar git local, por credenciales laborales en su PC) — ver D-005. El alumno trabaja en Windows (`D:\ITBA\5-anio\Multiagentes\tp1-multiagentes`, Python 3.14); cuando la PC no está vinculada a la sesión, los archivos se le entregan para descargar. Hay que avisarle explícitamente qué archivos reemplazar o borrar.

## Commands
```
docker build -t mas-tp-sandbox sandbox/      # imagen del sandbox (PC del alumno)
uv run pytest tests/sandbox -m docker -q     # tests del backend Docker
uv sync
uv run pytest -q
uv run ruff check .
uv run mypy agents services
uv run python scripts/check_services.py      # requiere .env completo y red (PC del alumno)
uv run streamlit run app.py                 # la app (PC del alumno, con .env)
uv run mypy agents services ui eval app.py
uv run python -m eval.run_local             # EVALUATION.md (PC del alumno)
uv run python -m eval.run_langsmith         # dataset + experimento en LangSmith
```

## Known gaps
- Pendiente del alumno: link del video demo en el README y la verificación desde un clon limpio. Los tests de Docker solo corren en la PC del alumno. La ingesta real contra el proxy y Pinecone queda verificada por el alumno.
- PDF de INDEC: lo agrega el alumno (necesario en iteración 3). Preguntas sobre ese PDF: iteración 8.
- Limitaciones conocidas de la extracción (documentar en README): en el Cuadro 3 de INDEC (p. 13) PyMuPDF mezcla dos columnas en una celda ("-3,1 8.883") y deja encabezados cortados ("A preci Cantidad corrient"); la tabla de diagnósticos de la p. 35 no tiene epígrafe; los títulos de sección de INDEC con el mismo tamaño que el cuerpo no se detectan (el Cuadro 8 hereda "3.3 …"); el respaldo `hrules` asume que cada columna tiene datos alineados (falla si una columna está vacía en todas las filas). La página 1 de INDEC genera un aviso `image_region` por las imágenes de tapa (falso positivo inofensivo).
- No usamos `table.header` de PyMuPDF (toma el epígrafe como encabezado externo): el encabezado se detecta con `split_header` sobre `table.extract()`.
- OQ-1 resuelta con la consigna completa (spec v0.2): BR-003 exige descripción de 2 a 4 oraciones.
- El índice de Pinecone es compartido pero el almacén Parquet+JSON es local: el Analista ignora IDs de Pinecone que no están en el almacén (D-028).
- Servicios verificados en la PC del alumno: modelos `gpt-4.1-mini` / `text-embedding-3-small` (1536), los tres métodos de salida estructurada funcionan (se usa `function_calling`).
