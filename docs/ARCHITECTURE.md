# Arquitectura

Referencia técnica del sistema: qué guarda cada grafo en su estado, los contratos entre componentes, dónde se persiste cada cosa y cómo se aísla el código generado. Para instalar y usar, ver el [README](../README.md).

```
            ┌──────────────── app.py (Streamlit) ────────────────┐
            │  Subir PDF          Explorar             Preguntar  │
            └─────┬──────────────────┬──────────────────────┬─────┘
                  │                  │                      │
          Agente de Ingesta     TableStore            Agente Analista
          (StateGraph)          (lectura)             (StateGraph)
            │      │                                    │   │   │
     LLM (proxy)   ├─► TableStore (Parquet + JSON) ◄────┘   │   └─► Sandbox
     embeddings    └─► Pinecone (1 vector por tabla) ◄──────┘       (Docker o subproceso)
                                                         LLM + embeddings (proxy)
                     Todo se traza en LangSmith (un run por ingesta y por pregunta)
```

Los agentes no se llaman entre sí: se comunican a través del almacén local y del índice. Los dos grafos reciben sus dependencias (LLM, embeddings, índice, almacén, sandbox) en un objeto de servicios; en producción lo arma `default_services(settings)` y en los tests se reemplaza por fakes.

---

## 1. Agente de Ingesta

`agents/ingestion/graph.py` — `build_ingestion_graph(IngestionServices)`; puntos de entrada `ingest_pdf(path)` y `stream_ingest(path)`, que emite `(nodo, actualización)` al terminar cada nodo.

### Estado (`IngestionState`, TypedDict serializable a JSON)

| Campo | Contenido |
|---|---|
| `pdf_path`, `pdf_name` | Archivo a ingerir y nombre a mostrar |
| `doc_id`, `page_count` | Hash de 16 caracteres del contenido del PDF; cantidad de páginas |
| `raw_tables` | Tablas detectadas (celdas como texto, encabezados, páginas, bbox) |
| `drafts` | `TableDraft`: tabla normalizada (columnas, tipos, filas como `float \| str \| None`) + contexto (epígrafe, sección, párrafos, notas) |
| `candidates` | Última anotación del LLM por tabla, antes de validar |
| `annotations` | Anotaciones válidas |
| `pending_errors` | Errores de validación de cada tabla pendiente (vuelven al prompt) |
| `attempts`, `failed` | Llamadas al LLM por tabla; tablas que agotaron los reintentos |
| `indexed` | `TableMetadata` de las tablas guardadas e indexadas |
| `warnings`, `log` | Avisos para la UI y una línea por nodo (se acumulan) |
| `error` | Mensaje que corta la ingesta (PDF inválido, sin texto, sin tablas, dimensión del índice…) |

El texto de las páginas no va al estado: se recalcula con caché por (ruta, fecha de modificación).

### Flujo

`load_pdf → extract_tables → merge_continuations → collect_context → enrich ⇄ validate → persist_and_index`. `load_pdf` y `extract_tables` terminan el grafo si hay error o no hay tablas (sin llamar al LLM). `validate` vuelve a `enrich` solo con las tablas inválidas mientras queden intentos (`INGEST_MAX_RETRIES`). `enrich` hace una llamada con salida estructurada por tabla, en paralelo (máx. 4); si **todas** fallan por error del servicio, relanza la excepción.

### Contrato: `TableMetadata` (`agents/ingestion/schemas.py`)

| Campo | Origen |
|---|---|
| `table_id` | Sistema: `{doc_id}-t{NN}` (NN = orden en el documento) |
| `doc_id`, `source` (`pdf_name`, `doc_id`, `pages`, `section_title`) | Sistema |
| `name`, `description` | LLM (nombre no genérico, descripción de 2 a 4 oraciones) |
| `columns[]`: `name`, `description`, `dtype`, `unit`, `scale`, `value_type` | `name` y `dtype` del sistema; el resto del LLM. `scale` ∈ unidades/miles/millones/miles de millones/desconocida; `value_type` ∈ nominal/real/porcentaje/conteo/índice/texto/unknown |
| `row_header_column` | LLM (tiene que ser una columna de texto) |
| `row_headers` | Sistema: valores de esa columna |
| `periods_covered`, `entities_covered`, `notes` | LLM (las notas incluyen las convenciones numéricas aplicadas) |
| `n_rows`, `n_cols`, `caption` | Sistema |

### Persistencia

- **Almacén local** (`services/table_store.py`, raíz `DATA_DIR`): `tables/{table_id}.parquet` (datos con sus tipos), `tables/{table_id}.json` (`TableMetadata`) y `pdfs/{doc_id}.pdf` (copia del original). Es lo que lee Explorar y lo que se monta en el sandbox.
- **Pinecone** (`services/vector_index.py`): índice serverless con métrica coseno y dimensión `EMBEDDING_DIM`, creado si no existe. Un registro por tabla, con id = `table_id`. Texto embebido: nombre, descripción, columnas con su descripción, encabezados de fila, períodos, entidades y sección. Metadatos: `doc_id`, `pdf_name`, `pages` (lista de strings), `name`, `description`, `columns`, `row_headers`, `periods_covered`, `entities_covered`, `n_rows`, `n_cols` y `preview_markdown`, recortados para quedar por debajo de 38 KB.
- **Orden de escritura**: índice (verifica dimensión) → embeddings de todas las tablas → borrar lo anterior del `doc_id` (índice y almacén) → escribir. Si algo falla antes del borrado, no se toca lo que había.

---

## 2. Agente Analista

`agents/analyst/graph.py` — `build_analyst_graph(AnalystServices)`; puntos de entrada `answer_question(question, question_id, run_id=…)`, `stream_answer(...)` y `to_outcome(state)`, que arma el resumen que usan la UI, la CLI y la evaluación.

### Estado (`AnalystState`)

| Campo | Contenido |
|---|---|
| `question`, `question_id` | Pregunta y su id si viene del set de evaluación |
| `query_plan` | `QueryPlan`: `subquestions[]` (`id`, `text`, `metrics`, `entities`, `periods`, `operation`) y `search_queries` (1 a 4) |
| `candidates` | Tablas recuperadas: `table_id`, `score`, `TableMetadata` completa, vista previa |
| `selection` | `SubquestionCoverage` por subpregunta: `covered`, `table_ids`, `columns_used`, `missing`, `related_table`, `ambiguity_ok` |
| `code`, `explanation`, `attempts` | Último programa generado, qué calcula, intentos |
| `executions` | Una entrada por intento: código, stdout, stderr, exit code, duración, backend, timeout, motivo de rechazo y motivo de invalidez |
| `last_error`, `code_result` | Motivo del último intento inválido; resultado válido |
| `status`, `missing`, `error` | `answered`/`partial`/`cannot_answer`; qué falta por subpregunta; `execution_failed` o `no_tables_indexed` |
| `tables_used`, `answer`, `log` | Tablas usadas (nombre, PDF, páginas); texto final; una línea por nodo |

### Flujo y decisiones

```
understand → retrieve ─(índice vacío)──────────────────────────► decide_status → answer
             retrieve → select ─(ninguna subpregunta cubierta)─► decide_status
                        select → generate_code → execute → validate_output
                                      ▲                         │ inválida y quedan intentos
                                      └─────────────────────────┘
                                                validate_output ─(resto)─► decide_status
```

- **Recuperación**: cada búsqueda del plan se embebe y consulta con `top_k = RETRIEVAL_K`; se deduplica por `table_id` quedándose con el mayor score (máx. 10 candidatas). Los ids que no están en el almacén local se ignoran.
- **Cobertura**: el LLM propone; los chequeos de `agents/analyst/coverage.py` solo pueden quitar cobertura:
  - *períodos y entidades*: cada año (como subcadena) y cada mes (como palabra) nombrado tiene que aparecer en encabezados de fila, columnas, nombre, epígrafe o períodos de las tablas elegidas; las entidades se buscan también en descripción y notas; se ignoran períodos no concretos ("cada año") y palabras de alcance ("provincia").
  - *unidad*: una columna numérica usada con unidad "desconocida" (salvo Año, Mes, Período…), o un monto con tipo `unknown` cuando la pregunta habla de valores reales, nominales o inflación, deja la subpregunta sin cubrir, salvo que el LLM justifique en `ambiguity_ok` que no cambia el resultado.
  - *valor de comparación*: "promedio/media provincial, nacional…" exige una fila Total/Promedio o una columna Promedio/Media/Total, salvo que la pregunta diga cómo calcularlo ("ponderado por población").
- **Generación de código**: el prompt incluye, por tabla, `table_id`, nombres exactos de columnas, tipo, unidad, escala, tipo de valor, encabezados de fila, notas y primeras filas; las subpreguntas a calcular; aparte, las que no hay que calcular y por qué; y en los reintentos, el código anterior y el error.
- **Validación de la salida**: exit code 0, sin timeout ni rechazo, última línea JSON que cumple `CodeResult`, sin `NaN`, y cada subpregunta cubierta presente en `results` o en `missing`.
- **Estado** (`agents/analyst/status.py`): una subpregunta está resuelta si está cubierta y el código devolvió un valor; `answered` = todas, `partial` = algunas, `cannot_answer` = ninguna o error.
- **Respuesta**: `cannot_answer` sale de una plantilla (sin LLM, sin números calculados); el resto lo redacta el LLM a partir de los resultados ya formateados en formato argentino.

### Contrato: `CodeResult` (`services/sandbox/result.py`)

Última línea de stdout del programa generado:
```json
{
  "results": [
    {"subquestion_id": "q1", "value": 9.88, "unit": "%", "label": "…"},
    {"subquestion_id": "q2", "value": [{"label": "2019", "value": 1.13}, {"label": "2020", "value": 1.07}],
     "unit": "%", "label": "…"}
  ],
  "missing": [{"subquestion_id": "q3", "reason": "no hay datos de 2025"}],
  "conversions": ["miles de toneladas → toneladas"]
}
```
`value` es un número o una lista de pares etiqueta-número (una categoría por elemento); nunca texto ni `NaN`.

---

## 3. Sandbox

`services/sandbox/` — `run_code(code, {table_id: ruta_parquet}) -> ExecutionResult` y `validate_execution(result) -> (CodeResult | None, motivo | None)`.

1. **Filtro estático** (`ast_guard.py`): imports permitidos `pandas`, `numpy`, `math`, `json`, `statistics`, `datetime`, `re`, `decimal`, `fractions`; prohibidos `eval`, `exec`, `compile`, `open`, `__import__`, `getattr`/`setattr`, `globals`, `exit`/`quit`, atributos `__dunder__`, métodos de E/S de pandas (`read_*`, `to_csv`…), `system`/`popen`/`fork` y URLs. Si falla, el programa no se ejecuta y el motivo vuelve al generador.
2. **Directorio de trabajo temporal**: `main.py` (preludio fijo: define `load_table(table_id)`, bloquea la red y ejecuta el programa con `runpy`), `program.py` (código generado) y una copia de cada Parquet elegido.
3. **Backend**:
   - *Docker* (`SANDBOX_IMAGE`, `sandbox/Dockerfile`: Python 3.11 con las mismas versiones de pandas, numpy y pyarrow): `--network none`, raíz de solo lectura, directorio montado en solo lectura, `/tmp` en memoria, 512 MB, 1 CPU, 64 procesos, usuario 10001, contenedor eliminado al terminar.
   - *Subproceso*: `python -I -X utf8`, entorno vacío (sin claves), solo el directorio temporal, red bloqueada en el preludio, límite de CPU en POSIX y timeout.
   - `SANDBOX_BACKEND=auto` usa Docker si responde y la imagen existe; `docker` falla con un error claro si no está.

---

## 4. Servicios transversales

| Módulo | Responsabilidad |
|---|---|
| `services/config.py` | `Settings` (pydantic-settings) desde `.env`; variables faltantes por funcionalidad (ingestar, preguntar, explorar). `get_settings()` también vuelca el `.env` al entorno para que LangSmith lo lea. |
| `services/llm.py` | Único punto de acceso al proxy: `get_chat_model`, `with_structured` (respeta `LLM_STRUCTURED_METHOD`), `get_embeddings`; cachés SQLite propias en `.cache/`; verificación de `EMBEDDING_DIM`. |
| `services/tracing.py` | `run_config(kind, label, **metadata)` arma el nombre (`ingest:…` / `analyst:…`), tags y metadatos de cada traza; `trace_url` arma el link a una traza a partir de su id. |
| `services/table_store.py` | Almacén Parquet + JSON. |
| `services/vector_index.py` | Interfaz `VectorIndex` con implementación Pinecone y una en memoria para tests; texto embebido y metadatos. |
| `ui/runtime.py`, `ui/errors.py` | Acceso de la UI a configuración y servicios (reemplazable en tests); clasificación de errores por servicio (LiteLLM, Pinecone, sandbox, configuración). |

---

## 5. Evaluación

- `eval/questions.yaml`: pregunta, PDF, estado esperado, valores esperados (`value` o `values` por categoría, con unidad), dato faltante esperado, tablas esperadas y tipo de caso.
- `eval/scoring.py`: correcta = estado igual y cada valor esperado presente entre los números devueltos por el código (tolerancia 0,5 % relativa, 0,01 absoluta si el esperado es 0); los valores por categoría tienen que coincidir también en la etiqueta. No se aceptan cambios de escala (una fracción en lugar de un porcentaje cuenta como error).
- `eval/run_local.py` → `EVALUATION.md` + `eval/last_run.json`; `eval/run_langsmith.py` → dataset sincronizado por id de pregunta y experimento con evaluadores `estado`, `valores`, `correcta` y el resumen `exactitud`.

---

## 6. Tests

`uv run pytest -q` corre sin red ni claves:

- **Extracción** contra el PDF sintético (cuya verdad está en `tests/fixtures/sample_truth.json`), el PDF real de INDEC y 9 PDFs de casos borde generados en cada corrida (imagen sola, sin tablas, protegido, no-PDF, columnas distintas entre páginas…).
- **Ingesta completa** con un LLM simulado, embeddings deterministas e índice en memoria (reintentos, idempotencia, reemplazo por documento, dimensión del índice).
- **Sandbox**: filtro estático, contrato de salida, aislamiento del subproceso (sin secretos, sin red, solo las tablas elegidas, timeout); los de Docker se marcan `docker` y se saltean si no hay imagen.
- **Analista** con LLM simulados y el sandbox real por subproceso: cobertura, estados, reintentos, formato de la respuesta.
- **UI** con `streamlit.testing.v1.AppTest` y servicios simulados: pestañas bloqueadas, errores por servicio, historial.
- **Evaluación**: corrección, reporte y sincronización del dataset.
