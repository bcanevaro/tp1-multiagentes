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

## D-007: Modelos del proxy  (Iteration 1)
**Context**: El proxy expone 29 modelos (familias Claude, GPT-4.1, GPT-5 y tres de embeddings); la cátedra no fijó uno.
**Decision** (elegida por el alumno): `LLM_MODEL=gpt-4.1-mini`, `EMBEDDING_MODEL=text-embedding-3-small` (`EMBEDDING_DIM=1536`). Se dejan como valores por defecto en `.env.example` (no son secretos).
**Rejected**: gpt-4.1 / claude-sonnet-4-5 (más caros por llamada); gpt-5-mini (lento y no acepta temperatura 0); text-embedding-3-large (3072 dims, más caro sin beneficio claro para textos de metadatos cortos).
**Consequences**: el índice de Pinecone se crea con dimensión 1536; cambiar de modelo de embeddings obliga a recrear el índice y re-ingerir. Si la generación de código falla seguido, evaluar un modelo más capaz solo para ese nodo.

## D-008: PDF sintético generado por código y versionado; PDFs de borde generados en los tests  (Iteration 2)
**Context**: Se necesitan PDFs con verdad conocida para testear la extracción y valores esperados exactos para la evaluación.
**Decision**: `scripts/sample_data.py` es la única fuente de los números; `make_sample_pdf.py` genera el PDF con reportlab en modo `invariant` (reproducible) y `sample_truth.json`. El PDF sintético se versiona (es entregable de la consigna); los 9 PDFs de borde se generan en un directorio temporal por sesión de pytest y no se versionan.
**Rejected**: armar los PDFs a mano en Word (no reproducible, sin verdad exacta); versionar los PDFs de borde (binarios que se desactualizan).
**Consequences**: si se cambia un dato hay que regenerar el PDF y el truth (`uv run python scripts/make_sample_pdf.py`); `test_generation_is_reproducible` detecta si quedaron desincronizados.

## D-009: Temática y casos del PDF sintético  (Iteration 2)
**Context**: El PDF debe cubrir los casos de la consigna §5.1, §5.2 y §6.4.
**Decision** (aprobada por el alumno): "Anuario Estadístico 2023 — Provincia de San Aurelio (ficticia)", 6 cuadros: finanzas 2019-2023 (paréntesis), desempleo por departamento (`%`, `s/d`, sin promedio provincial), salarios (`$`, solo líneas horizontales, sin aclarar nominal/real), producción con encabezado de 2 niveles, población, exportaciones mensuales multipágina (miles de US$). 11 preguntas `syn-01`…`syn-11` aprobadas por el alumno.
**Consequences**: el Analista debe resolver `syn-06` (promedio ponderado definido en la pregunta) como `answered` y `syn-04` como `partial`.

## D-010: Detección: PyMuPDF `lines` + respaldo propio por líneas horizontales  (Iteration 3)
**Context**: `find_tables(strategy="lines")` detecta grillas y los cuadros de INDEC, pero no tablas con solo 2-3 líneas horizontales (Cuadro 3 sintético). La estrategia `text` de PyMuPDF toma páginas enteras como tabla en INDEC y separa "$" del número.
**Decision**: `lines` primero; después, con las líneas horizontales que no están dentro de una tabla ya detectada, se agrupan las de igual ancho y se lee la región con palabras: filas por altura, columnas por "ríos" de blanco en los datos (no por el encabezado, que suele estar alineado a la izquierda y los números a la derecha). Se acepta solo si alguna columna tiene ≥ 80 % de celdas numéricas y ≥ 3 valores.
**Rejected**: estrategia `text` (ruido en INDEC); pdfplumber como segunda librería (más dependencias para un solo caso).
**Consequences**: el respaldo descarta en silencio sus candidatos fallidos (no generan avisos); las infografías de INDEC con líneas decorativas no pasan el filtro numérico.

## D-011: Encabezados: detección propia y aplanado con `" | "`  (Iteration 3)
**Context**: `table.header` de PyMuPDF toma el epígrafe como encabezado; los cuadros reales tienen hasta 4 filas de encabezado con años, marcas (`*`, `e`) y filas de unidades.
**Decision**: encabezado = filas iniciales sin valores numéricos de datos (los años sueltos no cuentan), hasta 4. Celdas `None` (combinadas) heredan de la izquierda si comparten el grupo del primer nivel o si la fila tiene una sola etiqueta fuera de la 1ª columna (unidades). Se quitan prefijos de marca antes de dígitos. Duplicados → " (2)"; vacíos → "columna_N".
**Consequences**: los nombres de INDEC son largos pero autoexplicativos (`Agosto | 2026e | Millones de USD`); la unidad queda en el nombre de la columna.

## D-012: Umbrales de filtrado  (Iteration 3)
**Decision**: FR-008b descarta < 2 filas de datos, < 2 columnas o < 50 % de celdas con texto (cuadros reales de INDEC: ≥ 57 %; gráficos: ≤ 36 %). FR-008: imagen ≥ 10 % del área; tabla con < 10 % de celdas con texto → "tabla sin texto legible". FR-006: columna numérica si ≥ 80 % de las celdas no faltantes convierten.
**Consequences**: una tabla real muy rala (< 50 % de celdas) se descartaría con aviso; está documentado.

## D-013: Convenciones numéricas por documento  (Iteration 3)
**Context**: INDEC define "-" como cero absoluto; otros documentos lo usan como "sin dato".
**Decision** (elegida por el alumno): `LoadedPdf.zero_dash` se activa si el texto declara "- Cero absoluto" (o "igual a cero"); entonces "-" → 0, si no → NaN, y la convención va a las notas de la tabla. El formato decimal se decide por columna (el que convierte más celdas) y, si empata (p. ej. "612.450"), por el formato mayoritario del documento (`LoadedPdf.decimal_comma`).
**Consequences**: el LLM y el código generado reciben la convención en `notes`.

## D-014: Reglas extra para no unir tablas consecutivas  (Iteration 3)
**Context**: El Cuadro 10 de INDEC empieza en la página siguiente al 9 con la misma estructura; la regla literal de la consigna los uniría.
**Decision** (spec v0.3, FR-007): no es continuación si hay un epígrafe ("Cuadro/Tabla/Gráfico N") encima de la tabla en la página N+1, o si la tabla de la página N tiene debajo un bloque "Fuente"/"Nota". Solo se consideran la última tabla de la página N y la primera de la N+1.
**Rejected**: excluir el 8 % superior de la página como encabezado (el epígrafe del Cuadro 10 está a 55 pt del borde).

## D-015: El estado de la Ingesta es JSON (Pydantic), sin DataFrames  (Iteration 4)
**Context**: El spec pide estado serializable; LangSmith muestra el estado de cada nodo.
**Decision** (elegida por el alumno): las tablas viajan como `RawTableData` y `TableDraft` (filas como listas de `float | str | None`, con `dtypes`). `TableDraft.to_dataframe()` reconstruye el DataFrame cuando hace falta. El `LoadedPdf` (bloques de texto) no va al estado: se recalcula con un `lru_cache` por (ruta, mtime).
**Rejected**: archivos temporales con rutas en el estado (trazas opacas, limpieza).
**Consequences**: las trazas muestran las tablas completas (son chicas en este TP).

## D-016: Una llamada al LLM por tabla, en paralelo, detrás de un `Annotator` inyectable  (Iteration 4)
**Decision** (elegida por el alumno): `llm_annotator` usa `with_structured(...).batch(..., max_concurrency=4, return_exceptions=True)`. Una excepción del LLM cuenta como intento fallido de esa tabla (se reintenta igual que un error de validación). Los tests inyectan `FakeAnnotator`, sin LLM.
**Consequences**: cada llamada es un span hijo de `enrich` en LangSmith (se pasa el `config` del nodo).

## D-017: Copia del PDF original en `DATA_DIR/pdfs/{doc_id}.pdf`  (Iteration 4)
**Decision** (elegida por el alumno): se guarda al indexar. Habilita descargar el PDF desde Explorar y re-ingerir sin el archivo original.

## D-018: Orden de escritura en `persist_and_index`  (Iteration 4)
**Decision**: primero se obtiene el índice (si la dimensión no coincide se corta sin escribir nada, FR-064) y se calculan todos los embeddings; recién después se borra lo anterior del documento (Pinecone por prefijo `"{doc_id}-t"` y almacén local, BR-006) y se escribe lo nuevo. Los `table_id` usan el orden de la tabla en el documento aunque otras fallen, así son estables.
**Consequences**: si Pinecone falla a mitad del upsert, el documento queda parcialmente indexado; re-ingerir lo corrige.

## D-019: BR-004b — nominal/real solo con respaldo textual  (Iteration 4)
**Context**: En la primera ingesta real, `gpt-4.1-mini` describió los salarios como "pesos corrientes" aunque el PDF no lo dice; eso anularía la detección de ambigüedad de BR-014 (pregunta syn-09).
**Decision** (elegida por el alumno): instrucción explícita en el prompt + validación determinística: `value_type` nominal/real o las palabras corriente/constante/nominal/real en la descripción exigen la misma familia de palabras en epígrafe, sección, párrafos, notas o nombres de columna; si no, error BR-004b y reintento.
**Rejected**: solo prompt (sin garantía); dejarlo como limitación.
**Consequences**: puede generar algún reintento extra; una descripción honesta usa "no indica si los montos están ajustados por inflación".
