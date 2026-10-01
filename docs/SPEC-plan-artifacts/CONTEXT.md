# CONTEXT — estado actual del proyecto

_Última actualización: Iteración 2 (PDF sintético, fixtures y preguntas)._

## Current state
- Proyecto Python 3.11 gestionado con `uv` (`pyproject.toml` + `uv.lock`), sin empaquetar (`[tool.uv] package = false`): los módulos se importan desde la raíz del repo.
- Configuración tipada (`services/config.py`) que lee `.env` y detecta variables obligatorias faltantes, en total o por funcionalidad.
- Fábricas de chat y embeddings contra el proxy LiteLLM con caché SQLite local opcional (`services/llm.py`) y verificación de la dimensión de embeddings.
- Helper de configuración de trazas LangSmith (`services/tracing.py`), todavía sin usar por ningún grafo.
- `scripts/check_services.py` verifica en la PC del alumno los servicios externos. `app.py` es un placeholder que solo muestra el estado de la configuración. No hay agentes todavía.
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
| `agents/ingestion/`, `agents/analyst/`, `sandbox/` | Vacíos (solo `__init__.py` donde aplica) |
| `data/sample_pdfs/informe_sintetico.pdf` | PDF sintético versionado (entregable de la consigna). Se regenera con `scripts/make_sample_pdf.py`. El alumno agregará `indec_ica.pdf` |
| `scripts/sample_data.py` | Única fuente de los números del PDF sintético; `fmt_ar`, `fmt_ar_parens`, `export_total` |
| `scripts/make_sample_pdf.py` | Genera el PDF sintético (reportlab, `invariant=1`) y `tests/fixtures/sample_truth.json`; `build(pdf_path, truth_path)` |
| `scripts/make_test_fixtures.py` | `build_all(out_dir) -> dict[nombre, Path]` y `FIXTURES` (caso y resultado esperado de cada PDF de borde) |
| `tests/fixtures/sample_truth.json` | Por tabla: `key`, `caption`, `section_title`, `paragraph_before`, `footnote`, `paragraph_after`, `columns` (nombres aplanados esperados), `rows_text` (celdas como se imprimen), `values` (valores normalizados esperados; `null` = s/d), `header_rows`, `line_style` (`grid`/`horizontal`), `pages` (1-based), `n_rows`, `n_cols` |
| `eval/questions.yaml` | 11 preguntas del PDF sintético (`syn-01`…`syn-11`); campos `id, doc, question, expected_status, expected_values[{label, value\|values, unit}], expected_missing, tables, kind, notes` |
| `tests/conftest.py` | Fixture autouse que limpia variables de entorno de servicios; `make_settings(**overrides)` crea `Settings` sin leer `.env`; `edge_pdfs` (scope session) genera los PDFs de borde en un tmp y devuelve `dict[nombre, Path]` |
| `tests/test_config.py`, `tests/test_llm.py`, `tests/test_tracing.py` | Tests de la iteración 1 |
| `tests/test_sample_pdf.py`, `tests/test_edge_pdfs.py`, `tests/test_questions.py` | Tests de la iteración 2 |

## Public interfaces
- `services.config.Settings` (pydantic-settings, `case_sensitive=True`). Campos: los de spec §7.1 más `LLM_STRUCTURED_METHOD: Literal["function_calling","json_schema","json_mode"]` (default `function_calling`) y `CACHE_DIR: Path` (default `.cache`). Métodos/propiedades: `missing_required(feature: Literal["ingest","ask","explore"] | None = None) -> list[str]`, `resolve_path(Path) -> Path`, `data_dir`, `cache_dir` (rutas absolutas resueltas contra `PROJECT_ROOT`).
- `services.config.get_settings() -> Settings` (cacheada con `lru_cache`; también hace `load_dotenv` sin pisar el entorno).
- `services.config.REQUIRED_BY_FEATURE: dict[Feature, tuple[str, ...]]` — `ingest` y `ask` necesitan LiteLLM + embeddings + Pinecone + LangSmith; `explore` no necesita nada.
- `services.llm.get_chat_model(settings=None, temperature=0.0) -> BaseChatModel` (activa la caché global si `LLM_CACHE`); lanza `ConfigurationError` si falta configuración.
- `services.llm.with_structured(llm, schema, settings=None) -> Runnable[Any, schema]` — usar SIEMPRE esto para salida estructurada (respeta `LLM_STRUCTURED_METHOD`).
- `services.llm.get_embeddings(settings=None) -> Embeddings` (envuelto en `CachedEmbeddings` si `LLM_CACHE`).
- `services.llm.check_embedding_dim(embeddings, expected) -> int`; lanza `EmbeddingDimensionError(actual, expected)`.
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
- Lo que ve PyMuPDF hoy sobre el PDF sintético (para la iteración 3): `find_tables()` con la estrategia por defecto **no detecta** el Cuadro 3 (solo líneas horizontales); toma la línea del epígrafe como encabezado externo en los cuadros 1 y 4 (`header.names` = `['corrientes', ...]`, `['das', ...]`); los encabezados con salto de línea vienen con `\n` (`'Productos\nprimarios'`); la tabla de exportaciones aparece como 6 filas en la página 2 y 20 en la 3, ambas con el encabezado repetido.
- OQ-1 resuelta con la consigna completa (spec v0.2): BR-003 exige descripción de 2 a 4 oraciones.
- Servicios verificados en la PC del alumno: modelos `gpt-4.1-mini` / `text-embedding-3-small` (1536), los tres métodos de salida estructurada funcionan (se usa `function_calling`).
