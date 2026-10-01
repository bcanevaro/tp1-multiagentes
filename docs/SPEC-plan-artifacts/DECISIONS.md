# DECISIONS — registro de decisiones (append-only)

Las decisiones de diseño principales del sistema están en el spec §10 (tomadas por el alumno el 2026-10-01): PyMuPDF, Parquet + JSON, un vector por tabla, sandbox Docker con fallback a subproceso, `cannot_answer` + `error` al agotar reintentos, estado decidido por lógica, unión multipágina determinística, bonus = evals en LangSmith. Acá se registran las decisiones de implementación.

## D-001: Layout de paquetes en la raíz, sin empaquetar  (Iteration 1)
**Context**: La consigna (§9.2) sugiere `app.py`, `agents/`, `services/` en la raíz.
**Decision**: Paquetes `agents`, `services`, `eval`, `scripts` en la raíz; `[tool.uv] package = false`; todo se ejecuta desde la raíz (`uv run python -m ...`).
**Rejected**: layout `src/` — se aparta de la estructura sugerida por la cátedra.
**Consequences**: los imports son absolutos desde la raíz (`from services.config import ...`); los scripts en `scripts/` agregan la raíz a `sys.path`.

## D-002: Cachés propias en SQLite en lugar de langchain-community  (Iteration 1)
**Context**: NFR-009 pide caché de LLM y de embeddings. `SQLiteCache` y `CacheBackedEmbeddings` viven en `langchain-community`/`langchain-classic`, y `langchain-community` emite un aviso de que está siendo discontinuado.
**Decision**: `SQLiteLLMCache(BaseCache)` y `CachedEmbeddings(Embeddings)` propias en `services/llm.py` (~80 líneas), en `CACHE_DIR` (`.cache/`).
**Rejected**: `langchain-community` (discontinuado); `InMemoryCache` (no sobrevive entre corridas).
**Consequences**: no hay dependencia de `langchain-community`. Para invalidar la caché basta con borrar `.cache/`.

## D-003: Variable `LLM_STRUCTURED_METHOD`  (Iteration 1)
**Context**: Spec A-3: no se sabe qué método de salida estructurada soporta el modelo del proxy.
**Decision**: Nueva variable `LLM_STRUCTURED_METHOD` (`function_calling` por defecto); toda salida estructurada pasa por `services.llm.with_structured`. `check_services.py` prueba los tres métodos y recomienda uno.
**Rejected**: hardcodear un método.
**Consequences**: §7.1 del spec gana una variable (agregada a `.env.example`).

## D-004: `get_settings()` vuelca `.env` al entorno del proceso  (Iteration 1)
**Context**: pydantic-settings lee `.env` pero no lo exporta; LangSmith/LangChain leen `LANGSMITH_*` de `os.environ`.
**Decision**: `get_settings()` llama a `load_dotenv(override=False)` antes de crear `Settings`.
**Consequences**: hay que llamar a `get_settings()` antes de invocar cualquier grafo para que las trazas funcionen. NFR-002: el sandbox (iteración 5) debe construir su entorno desde cero, sin heredar `os.environ`.

## D-005: El alumno hace los commits; la copia de trabajo no tiene git  (Iteration 1)
**Context**: La autoría de los commits importa para la entrega.
**Decision**: Se desarrolla y testea en el contenedor; al cerrar cada iteración se copian los archivos a `C:\Users\BautistaCanevaro\OneDrive - FERSI SA\Documentos\tp1-multiagentes` y el alumno commitea con el mensaje sugerido.
**Consequences**: los registros de iteración anotan el SHA que informa el alumno. Si se borra un archivo, hay que avisarle explícitamente al alumno.

## D-006: Las iteraciones las implementa el orquestador, no subagentes  (Iteration 1)
**Context**: El alumno pidió ser consultado ante cada duda de diseño; un subagente no puede consultarlo en vivo.
**Decision**: Se sigue el protocolo de artefactos del plan, pero la implementación la hace la sesión principal.
**Consequences**: los artefactos siguen siendo obligatorios: son el registro del proceso y sirven para el oral.
