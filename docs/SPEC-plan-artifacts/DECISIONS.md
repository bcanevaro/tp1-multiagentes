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

## D-020: Preludio de confianza + `program.py` ejecutado con `runpy`  (Iteration 5)
**Context**: El código generado necesita cargar las tablas sin conocer rutas, y los errores deben señalar líneas del programa generado para la autocorrección.
**Decision**: el directorio de trabajo tiene `main.py` (preludio: importa pandas, define `load_table(table_id)` sobre copias `<table_id>.parquet` con rutas relativas, bloquea la red) y `program.py` (código generado), que se ejecuta con `runpy.run_path`. Mismo layout en ambos backends (en Docker se monta en `/data`).
**Consequences**: el prompt del Analista debe decir "usá `load_table('<table_id>')`" e imprimir el JSON al final.

## D-021: Defensa en capas para el subproceso (Windows no aísla red ni archivos)  (Iteration 5)
**Decision**: (1) filtro AST: lista blanca de imports (BR-020), sin `eval/exec/open/getattr/__import__…`, sin atributos dunder, sin métodos `read_*`/`to_csv`…, sin URLs; (2) subproceso `python -I -X utf8` con entorno construido desde cero (sin claves, NFR-002), directorio temporal con solo las tablas elegidas, `RLIMIT_CPU` en POSIX y timeout; (3) el preludio anula `socket.connect/connect_ex/sendto`, `create_connection` y `getaddrinfo` (reemplazar la clase rompía `ssl`).
**Consequences**: aislamiento parcial documentado como limitación; Docker es el backend recomendado.

## D-022: Configuración del contenedor  (Iteration 5)
**Decision**: imagen `mas-tp-sandbox` (python:3.11-slim + pandas/numpy/pyarrow con las mismas versiones que `uv.lock`), `--network none`, raíz de solo lectura, `/data` montado `ro`, `tmpfs /tmp` 64 MB, 512 MB de memoria, 1 CPU, 64 procesos, usuario 10001, contenedor eliminado al terminar. `docker_status(image)` se evalúa una vez por proceso (si se instala Docker con la app abierta, hay que reiniciarla).

## D-023: LLM del Analista inyectados como funciones sobre mensajes  (Iteration 6)
**Decision**: `AnalystServices` recibe cuatro funciones `(mensajes, config) -> resultado`: `plan` (`QueryPlan`), `select` (`Selection`), `code` (`GeneratedCode`) y `write` (texto), más fábricas de embeddings e índice, el `TableStore` y `run_code`. Los prompts se arman en los nodos (`agents/analyst/prompts.py`), así los tests verifican el contenido exacto de lo que recibe cada LLM con `Recorder`. El estado guarda modelos Pydantic (sin checkpointer no hace falta serializarlo).
**Consequences**: cada llamada al LLM es un span hijo del nodo en LangSmith (se pasa el `config`).

## D-024: `LLM_CODE_MODEL` opcional para la generación de código  (Iteration 6)
**Decision** (elegida por el alumno): variable opcional; vacía = usa `LLM_MODEL` (`gpt-4.1-mini`). Permite probar un modelo más fuerte solo para el código sin cambiar el resto.

## D-025: Números con formato argentino formateados por el sistema  (Iteration 6)
**Decision** (elegida por el alumno): `fmt_number` (punto de miles, coma decimal; 2 decimales si |v| ≥ 1, si no 4; sin ceros finales). Los resultados se formatean ANTES de pasarlos al LLM redactor, que tiene la instrucción de copiarlos tal cual y no hacer cuentas.
**Consequences**: la evaluación (iteración 8) compara contra `code_result` (floats), no contra el texto.

## D-026: FR-024b acotado y columnas "año" de tablas anchas  (Iteration 6)
**Context**: La versión inicial de FR-024b marcaba no cubierta cualquier columna con unidad desconocida o monto `unknown`, lo que daba falsos `cannot_answer` (p. ej. una columna Año, o "¿cuánto crecieron los salarios?" sin pedir valores reales). Al escribir los tests apareció además que excluir columnas *llamadas* como un año ("2021") anulaba el chequeo en tablas anchas, justo el caso de la pregunta syn-09.
**Decision**: spec v0.5 — se excluyen solo las columnas identificadoras por nombre (Año, Mes, Período, Fecha, Trimestre); la regla nominal/real aplica a montos con `value_type = unknown` solo si la subpregunta menciona real/nominal/inflación/constantes/corrientes/poder adquisitivo; `ambiguity_ok` del LLM la desactiva.

## D-027: La salida del código debe mencionar cada subpregunta cubierta  (Iteration 6)
**Decision**: además de FR-028, `validate_output` exige que cada subpregunta cubierta aparezca en `results` o en `missing` del JSON; si falta alguna, la ejecución es inválida y se reintenta con ese motivo. Evita que una subpregunta "desaparezca" sin explicación.

## D-028: Recuperación: unión de búsquedas y tablas ausentes del almacén local  (Iteration 6)
**Decision**: se embebe cada `search_query`, se consulta Pinecone con `RETRIEVAL_K` por búsqueda, se deduplica por `table_id` quedando el mayor score (FR-021) y se toman hasta 10 candidatas. Los IDs que están en Pinecone pero no en el almacén local (p. ej. ingestados desde otra PC) se ignoran; si no queda ninguno, el error es `no_tables_indexed`.
**Consequences**: el índice de Pinecone es compartido, el almacén es local: hay que ingerir los PDF en la misma PC donde se pregunta (se documenta en el README).

## D-029: Ajustes tras la primera corrida real del Analista (spec v0.6)  (Iteration 6)
**Context**: Con servicios reales, 8/11 preguntas sintéticas dieron el estado esperado. syn-02: el plan anotó el período "todos los años disponibles" y FR-024 lo buscó textual. syn-08: el plan anotó la entidad "provincia" (alcance del documento). syn-04: el LLM de selección dio por cubierto el "promedio provincial" y el código lo calculó como promedio simple de los departamentos (viola BR-013).
**Decision**: (1) FR-024 verifica solo períodos concretos (con número o nombre de mes) e ignora palabras de alcance (`GENERIC_ENTITIES`); las entidades se buscan también en descripción, notas y título de sección. (2) FR-024c: chequeo determinístico de BR-013 (mismo enfoque "prompt + regla automática" que eligió el alumno para BR-004b en D-019). (3) Prompts reforzados: períodos/entidades en el plan, BR-013 en selección y código, y "value" nunca es texto (en syn-04 el primer intento puso el nombre del departamento como valor).
**Consequences**: el chequeo de BR-013 se basa en palabras ("promedio provincial", "media nacional"…): una referencia expresada de otra forma queda a cargo del LLM.

## D-030: Segunda corrida real: proporciones en %, partes sin datos fuera del código, syn-01 reformulada  (Iteration 6)
**Context**: Segunda corrida: 11/11 estados correctos, pero (a) syn-02 devolvió proporciones como fracción (0,0113) con unidad "proporción"; (b) en syn-04 el código, que recibía la pregunta original, calculó igual la diferencia con el "promedio provincial" dentro del resultado de q1, y el redactor la informó; (c) syn-01 se calculó como tasa compuesta (78,55 %) en vez del promedio de variaciones (84,88 %): la pregunta era ambigua.
**Decision**: (a) el prompt de código pide proporciones, variaciones y tasas en % (0-100). (b) `code_messages` ya no recibe la pregunta original: solo las subpreguntas cubiertas (autocontenidas) y una lista aparte de partes que NO hay que calcular, con su motivo; el redactor no da números para partes faltantes. (c) Elegido por el alumno: reformular syn-01 ("promedio simple de las variaciones interanuales"). Rechazado: aceptar ambos valores; fijar la lectura en el prompt (ajustaría el sistema a la evaluación).

## D-031: Extras de la UI  (Iteration 7)
**Decision** (elegida por el alumno): además de lo que pide el spec, la pestaña Preguntar muestra el progreso del Analista nodo por nodo mientras corre (como la ingesta) y ofrece un desplegable con las preguntas de `eval/questions.yaml` (se envían con su `question_id`, que queda en la traza).
**Rejected** (por ahora): borrar un documento desde Explorar; descargar tablas en CSV.

## D-032: Pestañas bloqueadas en vez de ocultas (FR-045)  (Iteration 7)
**Context**: `st.tabs` no permite deshabilitar una pestaña.
**Decision** (elegida por el alumno): las tres pestañas se ven siempre; si faltan variables, Subir y Preguntar muestran cuáles faltan y sus controles (subir, ingerir, ejemplos, chat) quedan con `disabled=True`. Explorar no necesita configuración. Un `.env` con un valor inválido se muestra como `st.error` sin tirar la app.

## D-033: La UI accede a servicios a través de `ui/runtime.py`  (Iteration 7)
**Decision**: `load_settings`, `ingestion_services`, `analyst_services` y `table_store` viven en `ui.runtime` y la UI los llama por atributo del módulo; los tests de `AppTest` los reemplazan con `monkeypatch` (almacén e índice en memoria, LLM simulados, sandbox real por subproceso).

## D-034: Errores de servicio: clasificación por paquete y escalado en la ingesta  (Iteration 7)
**Decision**: `ui.errors.classify` recorre la cadena `__cause__`/`__context__` y decide el servicio por el paquete de la clase (`openai` → LiteLLM, `pinecone` → Pinecone, `docker`, `langsmith`) o por tipo propio (`SandboxUnavailable`, `IndexDimensionError`, `ConfigurationError`/`EmbeddingDimensionError`). En la ingesta, si TODAS las llamadas al LLM de una ronda fallan con errores de conexión o autenticación (`openai`/`httpx`), el nodo `enrich` relanza el primero en vez de tratarlo como metadatos inválidos; antes, una clave inválida terminaba en "Ninguna tabla pasó la validación" tras 3 intentos por tabla, sin mencionar LiteLLM.
