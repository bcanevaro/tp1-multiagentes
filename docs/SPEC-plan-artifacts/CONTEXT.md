# CONTEXT — estado actual del proyecto

_Última actualización: Iteración 1 (fundaciones)._

## Current state
- Proyecto Python 3.11 gestionado con `uv` (`pyproject.toml` + `uv.lock`), sin empaquetar (`[tool.uv] package = false`): los módulos se importan desde la raíz del repo.
- Configuración tipada (`services/config.py`) que lee `.env` y detecta variables obligatorias faltantes, en total o por funcionalidad.
- Fábricas de chat y embeddings contra el proxy LiteLLM con caché SQLite local opcional (`services/llm.py`) y verificación de la dimensión de embeddings.
- Helper de configuración de trazas LangSmith (`services/tracing.py`), todavía sin usar por ningún grafo.
- `scripts/check_services.py` verifica en la PC del alumno los servicios externos. `app.py` es un placeholder que solo muestra el estado de la configuración. No hay agentes todavía.

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
| `agents/ingestion/`, `agents/analyst/`, `eval/`, `sandbox/` | Vacíos (solo `__init__.py` donde aplica) |
| `data/sample_pdfs/` | Vacío (`.gitkeep`); el alumno agregará `indec_ica.pdf` |
| `tests/conftest.py` | Fixture autouse que limpia variables de entorno de servicios; fixture `make_settings(**overrides)` que crea `Settings` sin leer `.env` |
| `tests/test_config.py`, `tests/test_llm.py`, `tests/test_tracing.py` | Tests de la iteración 1 |

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
- No hay git en la copia de trabajo del contenedor: el alumno commitea en su carpeta (ver DECISIONS D-005).

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
- PDF sintético y fixtures: iteración 2. PDF de INDEC: lo agrega el alumno (necesario en iteración 3).
- OQ-1 del spec (campos mínimos de metadatos de la cátedra) sigue abierta; impacta la iteración 4.
- Resultado real de `check_services.py` pendiente de la PC del alumno (método de salida estructurada y `EMBEDDING_DIM`).
