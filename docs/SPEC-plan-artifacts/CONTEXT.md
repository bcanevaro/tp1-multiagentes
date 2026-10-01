# CONTEXT — estado actual del proyecto

_Última actualización: Iteración 3 (extracción determinística)._

## Current state
- Proyecto Python 3.11 gestionado con `uv` (`pyproject.toml` + `uv.lock`), sin empaquetar (`[tool.uv] package = false`): los módulos se importan desde la raíz del repo.
- Configuración tipada (`services/config.py`) que lee `.env` y detecta variables obligatorias faltantes, en total o por funcionalidad.
- Fábricas de chat y embeddings contra el proxy LiteLLM con caché SQLite local opcional (`services/llm.py`) y verificación de la dimensión de embeddings.
- Helper de configuración de trazas LangSmith (`services/tracing.py`), todavía sin usar por ningún grafo.
- `scripts/check_services.py` verifica en la PC del alumno los servicios externos. `app.py` es un placeholder que solo muestra el estado de la configuración. No hay agentes todavía.
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
| `app.py` | Placeholder de Streamlit |
| `agents/ingestion/pdf_loader.py` | `open_pdf`, `load_pdf`, `read_pdf`, `compute_doc_id`; dataclasses `LoadedPdf`, `PageData`, `TextBlock`, `PageImage`; errores `PdfOpenError`, `NoTextLayerError` |
| `agents/ingestion/extract.py` | `extract_tables`, `RawTable`, `ExtractionWarning`, `split_header`, `flatten_header`, `is_data_number`, `clean_cell`, `CAPTION_RE`; CLI `main` |
| `agents/ingestion/normalize.py` | `normalize_table`, `parse_number`, `MISSING_MARKERS` |
| `agents/ingestion/merge.py` | `merge_continuations`, `is_continuation` |
| `agents/ingestion/context.py` | `collect_context`, `TableContext` |
| `agents/analyst/`, `sandbox/` | Vacíos |
| `data/sample_pdfs/indec_ica.pdf` | PDF real de INDEC (ICA, cifras de agosto de 2026, 36 páginas) |
| `data/sample_pdfs/informe_sintetico.pdf` | PDF sintético versionado (entregable de la consigna). Se regenera con `scripts/make_sample_pdf.py`. El alumno agregará `indec_ica.pdf` |
| `scripts/sample_data.py` | Única fuente de los números del PDF sintético; `fmt_ar`, `fmt_ar_parens`, `export_total` |
| `scripts/make_sample_pdf.py` | Genera el PDF sintético (reportlab, `invariant=1`) y `tests/fixtures/sample_truth.json`; `build(pdf_path, truth_path)` |
| `scripts/make_test_fixtures.py` | `build_all(out_dir) -> dict[nombre, Path]` y `FIXTURES` (caso y resultado esperado de cada PDF de borde) |
| `tests/fixtures/sample_truth.json` | Por tabla: `key`, `caption`, `section_title`, `paragraph_before`, `footnote`, `paragraph_after`, `columns` (nombres aplanados esperados), `rows_text` (celdas como se imprimen), `values` (valores normalizados esperados; `null` = s/d), `header_rows`, `line_style` (`grid`/`horizontal`), `pages` (1-based), `n_rows`, `n_cols` |
| `eval/questions.yaml` | 11 preguntas del PDF sintético (`syn-01`…`syn-11`); campos `id, doc, question, expected_status, expected_values[{label, value\|values, unit}], expected_missing, tables, kind, notes` |
| `tests/conftest.py` | Fixture autouse que limpia variables de entorno de servicios; `make_settings(**overrides)` crea `Settings` sin leer `.env`; `edge_pdfs` (scope session) genera los PDFs de borde en un tmp y devuelve `dict[nombre, Path]` |
| `tests/test_config.py`, `tests/test_llm.py`, `tests/test_tracing.py` | Tests de la iteración 1 |
| `tests/test_sample_pdf.py`, `tests/test_edge_pdfs.py`, `tests/test_questions.py` | Tests de la iteración 2 |
| `tests/ingestion/conftest.py` | `Extraction` (loaded, raw, tables, warnings, `.context(t)`), `run_extraction(path)`; fixtures de sesión `sample`, `indec`, `edge` |
| `tests/ingestion/test_{loader,extract,normalize,context}.py` | Tests de la iteración 3 (VC-001…VC-010) |

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
uv sync
uv run pytest -q
uv run ruff check .
uv run mypy agents services
uv run python scripts/check_services.py      # requiere .env completo y red (PC del alumno)
uv run streamlit run app.py
```

## Known gaps
- Agentes, almacén, Pinecone, sandbox y UI real: iteraciones 3 a 7.
- PDF de INDEC: lo agrega el alumno (necesario en iteración 3). Preguntas sobre ese PDF: iteración 8.
- Limitaciones conocidas de la extracción (documentar en README): en el Cuadro 3 de INDEC (p. 13) PyMuPDF mezcla dos columnas en una celda ("-3,1 8.883") y deja encabezados cortados ("A preci Cantidad corrient"); la tabla de diagnósticos de la p. 35 no tiene epígrafe; los títulos de sección de INDEC con el mismo tamaño que el cuerpo no se detectan (el Cuadro 8 hereda "3.3 …"); el respaldo `hrules` asume que cada columna tiene datos alineados (falla si una columna está vacía en todas las filas). La página 1 de INDEC genera un aviso `image_region` por las imágenes de tapa (falso positivo inofensivo).
- No usamos `table.header` de PyMuPDF (toma el epígrafe como encabezado externo): el encabezado se detecta con `split_header` sobre `table.extract()`.
- OQ-1 resuelta con la consigna completa (spec v0.2): BR-003 exige descripción de 2 a 4 oraciones.
- Servicios verificados en la PC del alumno: modelos `gpt-4.1-mini` / `text-embedding-3-small` (1536), los tres métodos de salida estructurada funcionan (se usa `function_calling`).
