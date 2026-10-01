# SPEC — QA multiagente sobre tablas en PDFs

| Campo | Valor |
|---|---|
| Versión | 0.3 |
| Última actualización | 2026-10-01 |
| Estado | Aprobado por el alumno |
| Owner | Alumno — materia electiva Sistemas Multiagentes |
| Fuente | Consigna "Trabajo práctico — QA multiagente sobre tablas en PDFs" |

---

## 1. Propósito

Los informes en PDF (estados contables, anuarios estadísticos, publicaciones oficiales) guardan sus datos más útiles en tablas que son difíciles de consultar: hay que encontrar la tabla correcta, entender sus filas y columnas y hacer las cuentas a mano. Este sistema permite que un usuario suba PDFs legibles por máquina y haga preguntas en lenguaje natural cuyas respuestas se **calculan con código Python** sobre las tablas extraídas. Las respuestas usan **solo** datos de las tablas indexadas y declaran explícitamente cuándo la pregunta no se puede responder total o parcialmente. Beneficia al usuario que necesita respuestas numéricas trazables (qué tabla, qué página, qué cálculo) y al equipo docente, que evalúa el diseño multiagente.

## 2. Alcance

### Dentro del alcance
- Agente de Ingesta (StateGraph de LangGraph): carga de PDF, extracción de tablas con PyMuPDF, unión de tablas que continúan en la página siguiente, recolección de contexto, enriquecimiento con LLM (salida estructurada Pydantic), ciclo de validación/reintento, persistencia en almacén local Parquet + JSON e indexación en Pinecone.
- Agente Analista (StateGraph de LangGraph): comprensión de la consulta, recuperación en Pinecone, selección de una o más tablas, generación de código Python, ejecución aislada, autocorrección con límite de reintentos, decisión de estado (`answered` / `partial` / `cannot_answer`) y redacción de la respuesta.
- UI Streamlit con tres pestañas: Subir PDF, Explorar tablas, Hacer preguntas.
- Trazas en LangSmith para cada ejecución de ambos agentes.
- Set de evaluación (≥ 8 preguntas) con script de corrida local y **bonus: dataset + evaluador automático en LangSmith**.
- Dos PDFs de ejemplo: uno sintético generado por el proyecto y uno real de una publicación pública.

### Fuera del alcance
- PDFs escaneados u OCR (bonus no elegido). Las tablas que son imágenes se saltean y se informan.
- Bonus de human-in-the-loop y de visualización (no elegidos; pueden agregarse en una versión posterior).
- Persistencia del historial de chat entre sesiones del navegador.
- Multiusuario, autenticación y despliegue en la nube: el sistema corre localmente.
- Uso de conocimiento general del LLM, fuentes externas, interpolación o extrapolación para responder.
- Conversión de monedas, ajuste por inflación o cálculos per cápita sin una tabla indexada que provea el dato.

## 3. Actores

| Actor | Descripción | Permisos |
|---|---|---|
| Usuario | Persona que usa la app Streamlit | Subir PDFs, explorar tablas indexadas, hacer preguntas |
| Agente de Ingesta | Grafo LangGraph invocado desde la pestaña Subir PDF | Leer el PDF subido; escribir en el almacén local y en el índice Pinecone; llamar al LLM y a embeddings vía proxy LiteLLM |
| Agente Analista | Grafo LangGraph invocado desde la pestaña Hacer preguntas | Leer Pinecone y el almacén local; llamar al LLM y a embeddings vía proxy; lanzar el sandbox |
| Sandbox | Entorno donde corre el código generado | Solo lectura sobre los archivos de las tablas seleccionadas; sin red; sin variables de entorno con secretos |
| Equipo docente | Corrige la entrega | Clona el repo, configura su `.env`, ejecuta la app y los tests |

## 4. Requisitos funcionales

Prioridad MoSCoW: **M** = Must, **S** = Should, **C** = Could.

### 4.1 Agente de Ingesta

- **FR-001 (M) Carga del PDF** — Dado un PDF subido desde la UI, cuando se inicia la ingesta, entonces el agente lee todas las páginas y conserva el texto y los bloques de texto con sus coordenadas de cada página en el estado.
- **FR-002 (M) PDF sin capa de texto** — Dado un PDF en el que ninguna página tiene texto extraíble, cuando se ingiere, entonces la ingesta termina sin indexar nada y la UI muestra el mensaje "El PDF no tiene capa de texto; los PDFs escaneados no están soportados".
- **FR-019 (M) PDF sin tablas** — Dado un PDF con texto pero sin tablas detectables, cuando termina la extracción, entonces la ingesta termina sin indexar nada, sin llamar al LLM, y la UI muestra "No se detectaron tablas en el PDF".
- **FR-019b (M) Archivo inválido** — Dado un archivo que no se puede abrir como PDF (corrupto, protegido con contraseña o con otra extensión renombrada), cuando se ingiere, entonces la ingesta termina sin indexar nada y la UI muestra "No se pudo abrir el PDF: <motivo>".
- **FR-003 (M) Extracción de tablas** — Dado un PDF legible por máquina, cuando se ejecuta la extracción, entonces cada tabla detectada se convierte en un DataFrame con una fila por fila de datos y una columna por columna de la tabla. Se detectan tanto tablas con grilla completa como tablas delimitadas solo por líneas horizontales (estilo de informes estadísticos).
- **FR-004 (M) Encabezados de varias filas** — Dada una tabla cuyo encabezado ocupa más de una fila o tiene celdas combinadas, cuando se extrae, entonces los niveles se aplanan en un único nombre por columna unidos con `" | "` (por ejemplo `"Ingresos | 2023"`), y los nombres resultantes son únicos dentro de la tabla.
- **FR-005 (M) Celdas vacías** — Dada una celda vacía o con un marcador de dato faltante (`—`, `s/d`, `n/d`, `...`, `…`, `///`, `.`), cuando se normaliza, entonces su valor es nulo (NaN) y no cero. El guion `-` sigue la convención del documento: si el texto del PDF declara un signo convencional que define `-` como cero (por ejemplo, "- Cero absoluto" en los informes de INDEC), vale 0; si no, es nulo. La convención aplicada se agrega a las notas de la tabla.
- **FR-006 (M) Números como texto** — Dada una columna en la que al menos el 80 % de las celdas no vacías son números formateados como texto, cuando se normaliza, entonces se convierte a tipo numérico interpretando signo `%` (el valor se conserva en escala 0–100, `12,5%` → `12.5`), símbolos de moneda (`$`, `US$`, `€`) y paréntesis como negativo. Se quitan los marcadores de dato provisorio o estimado pegados al número (`*`). El formato de separadores se decide **por columna**: se elige entre `1.234,56` (coma decimal) y `1,234.56` (punto decimal) el que parsea más celdas; si empatan, se usa el formato mayoritario del documento. Las celdas que no parsean quedan nulas y se cuentan en un aviso. Las columnas por debajo del 80 % quedan como texto.
- **FR-007 (M) Unión de tablas multipágina** — Dada una tabla al comienzo de la página N+1 con la misma cantidad de columnas que la última tabla de la página N, y cuya primera fila repite el encabezado de esa tabla o no tiene fila de encabezado, cuando se extrae, entonces ambas se guardan como **una** tabla lógica cuyo `source.pages` lista todas las páginas que abarca, sin repetir la fila de encabezado en los datos. No es continuación (y se guardan como tablas distintas) si en la página N+1 hay un epígrafe (texto que empieza con "Cuadro", "Tabla" o "Gráfico" seguido de un número) entre el inicio del área de contenido y la tabla, (cualquier bloque por encima de la tabla en esa página), o si en la página N la tabla está seguida, más abajo en la misma página, por un bloque de texto que empieza con "Fuente" o "Nota".
- **FR-008 (M) Regiones no legibles** — Dada una página que contiene una imagen incrustada que ocupa al menos el 10 % del área de la página, o una página sin texto extraíble dentro de un PDF que sí tiene texto en otras páginas, cuando se ingiere, entonces esa región o página no se procesa como tabla, se registra un aviso "Página N: posible tabla como imagen / página sin texto; no se procesó", y la UI lo muestra al terminar. Una tabla detectada cuyas celdas están vacías en más del 90 % también se saltea con el aviso "Página N: tabla sin texto legible".
- **FR-008b (M) Detecciones que no son tablas** — Dada una región que el detector marca como tabla pero que tiene menos de 2 filas de datos, menos de 2 columnas, o menos del 50 % de celdas con texto (típico de gráficos, mapas e infografías con líneas de grilla), cuando se extrae, entonces se descarta y se registra el aviso "Página N: se descartó una detección que no parece una tabla (F filas × C columnas, X % de celdas con texto)".
- **FR-009 (M) Recolección de contexto** — Dada una tabla extraída, cuando se recolecta su contexto, entonces se capturan como textos separados: el epígrafe o título inmediatamente arriba, el párrafo anterior, el párrafo posterior, el título de la sección vigente y las notas al pie que siguen a la tabla, cada uno vacío si no existe.
- **FR-010 (M) Enriquecimiento con LLM** — Dada una tabla con su contexto, cuando se enriquece, entonces el LLM devuelve un objeto `TableMetadata` (ver §7.2) mediante salida estructurada de LangChain con un modelo Pydantic.
- **FR-011 (M) Validación de metadatos** — Dado un `TableMetadata` devuelto por el LLM, cuando se valida, entonces se aplican las reglas BR-001 a BR-004 y se obtiene una lista de errores (vacía si es válido).
- **FR-012 (M) Reintento del enriquecimiento** — Dado un `TableMetadata` con errores de validación, cuando quedan reintentos (ver NFR-004), entonces se vuelve a llamar al LLM incluyendo en el prompt la lista de errores, y solo se reintentan las tablas inválidas.
- **FR-013 (M) Agotamiento de reintentos de ingesta** — Dada una tabla que sigue inválida tras el último reintento, cuando termina el ciclo, entonces no se indexa, y la UI muestra un aviso con el nombre provisional, la página y los errores.
- **FR-014 (M) Persistencia de datos** — Dada una tabla válida, cuando se persiste, entonces se escribe `data/store/tables/{table_id}.parquet` con el DataFrame normalizado y `data/store/tables/{table_id}.json` con su `TableMetadata`.
- **FR-015 (M) Indexación** — Dada una tabla válida, cuando se indexa, entonces se hace upsert en Pinecone de **un** vector cuyo texto embebido es la concatenación de nombre, descripción, nombres y descripciones de columnas y encabezados de fila (mínimo de la consigna §5.2), más períodos, entidades y título de sección; y cuyos metadatos incluyen los campos de §7.3.
- **FR-016 (M) Re-ingesta idempotente** — Dado un PDF ya ingerido, cuando se vuelve a ingerir (aunque tenga otro nombre de archivo), entonces Pinecone y el almacén contienen exactamente las tablas de la última ingesta de ese documento: sin duplicados y sin tablas obsoletas de la ingesta anterior.
- **FR-017 (M) Resumen de ingesta en la UI** — Dada una ingesta terminada, cuando se muestra el resultado, entonces por cada tabla indexada se ve: nombre, descripción, encabezados de columna, encabezados de fila, vista previa de las primeras 5 filas y páginas de origen.
- **FR-018 (M) Progreso en streaming** — Dada una ingesta en curso, cuando cada nodo del grafo termina, entonces la UI muestra el nombre del nodo y un resumen de una línea (por ejemplo "extract_tables: 4 tablas detectadas en 6 páginas").

### 4.2 Agente Analista

- **FR-020 (M) Comprensión de la consulta** — Dada una pregunta, cuando se analiza, entonces el LLM devuelve un `QueryPlan` (§7.4) con una o más subpreguntas, cada una con métricas, entidades, períodos y operación, más una o más consultas de búsqueda reescritas.
- **FR-021 (M) Recuperación** — Dado un `QueryPlan`, cuando se recupera, entonces se ejecuta una búsqueda en Pinecone por cada consulta de búsqueda con `top_k = RETRIEVAL_K`, y los resultados se deduplican por `table_id` conservando el mayor score.
- **FR-022 (M) Índice vacío** — Dado un índice sin tablas, cuando se hace una pregunta, entonces el Analista termina con estado `cannot_answer` y el mensaje "No hay tablas indexadas", sin llamar al generador de código.
- **FR-023 (M) Selección de tablas** — Dadas las tablas candidatas, cuando se seleccionan, entonces el LLM recibe para cada una sus metadatos y la vista previa, y las reglas BR-011 a BR-014 en el prompt, y devuelve por cada subpregunta: las tablas necesarias (cero, una o varias), si está cubierta y, si no, qué dato falta y qué contiene la tabla relacionada más cercana. El LLM es responsable de aplicar BR-012 (conversiones externas) y BR-013 (valor de comparación); el sistema aplica además los chequeos determinísticos de FR-024 y FR-024b, que solo pueden *quitar* cobertura, nunca agregarla.
- **FR-024 (M) Chequeo determinístico de períodos y entidades** — Dada una subpregunta cubierta según el LLM, cuando pide períodos o entidades explícitos, entonces el sistema los compara contra la unión de `periods_covered`, `entities_covered`, `row_headers` y nombres de columna de las tablas seleccionadas, normalizando ambos lados (minúsculas, sin tildes, sin espacios extremos) y considerando que un período de 4 dígitos (año) está presente si aparece como subcadena de algún elemento normalizado; si alguno falta, la subpregunta se marca no cubierta con el motivo "Falta <período/entidad> X; la tabla T cubre Y".
- **FR-024b (M) Chequeo determinístico de unidad** — Dada una subpregunta cubierta según el LLM, cuando alguna columna de las tablas seleccionadas que el LLM declaró como usada tiene `unit = "desconocida"` o `value_type = "unknown"`, entonces la subpregunta se marca no cubierta con el motivo de BR-014, salvo que el LLM haya declarado que la ambigüedad no cambia el resultado (por ejemplo, una proporción entre valores de la misma columna) junto con la justificación, que se muestra en la respuesta.
- **FR-025 (M) Corte temprano** — Dada una selección en la que ninguna subpregunta está cubierta, cuando se evalúa la arista condicional, entonces el grafo va directo a la decisión de estado sin generar código.
- **FR-026 (M) Generación de código** — Dadas las tablas seleccionadas para las subpreguntas cubiertas, cuando se genera código, entonces el prompt incluye para cada tabla: ruta del archivo dentro del sandbox, nombres exactos de columnas, dtypes, las primeras 5 filas y los metadatos de unidad de cada columna; y el programa devuelto es autocontenido, carga las tablas con pandas e imprime como **última línea de stdout** un JSON que cumple el contrato `CodeResult` (§7.5).
- **FR-027 (M) Ejecución aislada** — Dado un programa generado, cuando se ejecuta, entonces corre en el sandbox (§4.4) y se capturan stdout, stderr, código de salida y duración.
- **FR-028 (M) Validación de la salida** — Dada una ejecución, cuando se valida, entonces es inválida si: el código de salida es distinto de 0, se superó el timeout, la última línea de stdout no es JSON, el JSON no cumple `CodeResult`, o algún valor numérico de `results` es NaN o infinito.
- **FR-029 (M) Autocorrección** — Dada una ejecución inválida, cuando quedan reintentos (NFR-005), entonces se vuelve al nodo de generación incluyendo el código anterior y el error (stderr o motivo de invalidez).
- **FR-030 (M) Agotamiento de reintentos del Analista** — Dada una ejecución que sigue inválida tras el último reintento, cuando termina el ciclo, entonces el estado es `cannot_answer` y el campo `error` vale `"execution_failed"`.
- **FR-031 (M) Decisión de estado** — Dadas la cobertura de la selección y el `CodeResult`, cuando se decide el estado, entonces se aplica BR-010 y el resultado queda en `state["status"]` antes de redactar la respuesta.
- **FR-032 (M) Respuesta final** — Dado un estado decidido, cuando se redacta la respuesta, entonces el texto incluye: los resultados numéricos (salvo en `cannot_answer`), las tablas y páginas usadas, una breve explicación del cálculo y las conversiones aplicadas, y, si el estado no es `answered`, qué datos faltan por subpregunta.
- **FR-033 (M) Estado inmutable en la redacción** — Dado un estado decidido, cuando el nodo de respuesta corre, entonces su salida solo actualiza el campo `answer`; `status`, `missing` y `code_result` no se modifican. La redacción recibe los valores de `CodeResult` ya formateados por el sistema y el prompt le prohíbe introducir otros números. Para `cannot_answer`, el texto se arma con una plantilla determinística a partir de `missing` (sin LLM), lo que garantiza BR-015.

### 4.3 Interfaz Streamlit

- **FR-040 (M) Pestaña Subir PDF** — Dado un archivo `.pdf`, cuando el usuario lo sube y confirma, entonces se ejecuta la ingesta mostrando progreso (FR-018) y luego el resumen (FR-017) y los avisos (FR-008, FR-013).
- **FR-041 (M) Pestaña Explorar** — Dado el almacén local, cuando el usuario abre la pestaña, entonces ve la lista de tablas indexadas agrupadas por documento con nombre, descripción, páginas y un expander con los datos completos.
- **FR-042 (M) Pestaña Preguntar** — Dada una pregunta, cuando el usuario la envía, entonces se agrega al historial tipo chat de la sesión junto con: respuesta final, estado (con color distinto para cada uno), datos faltantes si no es `answered`, tablas seleccionadas (expander con datos), código generado (bloque de código), salida de la ejecución y cantidad de reintentos.
- **FR-043 (M) Manejo de errores** — Dada una falla del proxy LiteLLM, de Pinecone o del sandbox (por ejemplo, Docker no disponible), cuando ocurre durante una ejecución, entonces la app no se cae: muestra un `st.error` con el servicio afectado y el mensaje, y la sesión sigue usable.
- **FR-045 (M) Configuración faltante** — Dada una o más variables obligatorias de §7.1 ausentes o vacías, cuando se inicia la app, entonces se muestra la lista de variables faltantes y las pestañas que las necesitan quedan deshabilitadas en lugar de fallar al usarlas.
- **FR-044 (S) Configuración visible** — Dada la app en ejecución, cuando el usuario abre la barra lateral, entonces ve el modelo de chat, el modelo de embeddings, el índice de Pinecone, el backend del sandbox activo y si las trazas de LangSmith están activas (sin mostrar claves).

### 4.4 Sandbox

- **FR-050 (M) Backend Docker** — Dado `SANDBOX_BACKEND=docker`, cuando se ejecuta código, entonces corre en un contenedor de la imagen del proyecto con red deshabilitada, sistema de archivos raíz de solo lectura, las tablas montadas en solo lectura en `/data`, límite de memoria, de CPU y de procesos, y se elimina al terminar.
- **FR-051 (M) Backend subproceso** — Dado `SANDBOX_BACKEND=subprocess`, cuando se ejecuta código, entonces corre en un proceso Python separado en modo aislado, con un directorio temporal como directorio de trabajo que contiene solo copias de las tablas seleccionadas, y un entorno de variables vacío salvo las mínimas para que Python funcione.
- **FR-052 (M) Selección automática** — Dado `SANDBOX_BACKEND=auto` (valor por defecto), cuando se ejecuta código, entonces se usa Docker si el daemon responde y la imagen existe, y si no se usa subproceso; el backend elegido se registra en el estado y se muestra en la UI.
- **FR-053 (M) Filtro estático** — Dado un programa generado, cuando se va a ejecutar con cualquier backend, entonces primero se analiza su AST y se rechaza sin ejecutarlo si importa módulos fuera de la lista permitida (BR-020) o usa `eval`, `exec`, `compile`, `__import__`, `open` en modo escritura, o acceso a atributos dunder; el rechazo cuenta como ejecución inválida con el motivo.
- **FR-054 (M) Timeout** — Dado un programa que excede `SANDBOX_TIMEOUT_S`, cuando vence el plazo, entonces el proceso o contenedor se termina y la ejecución se marca inválida con motivo "timeout".

### 4.5 Infraestructura, observabilidad y evaluación

- **FR-064 (M) Índice Pinecone** — Dado que el índice `PINECONE_INDEX_NAME` no existe, cuando se ejecuta la primera ingesta, entonces se crea un índice serverless con dimensión `EMBEDDING_DIM` y métrica coseno. Si existe con otra dimensión, la ingesta termina con el mensaje "El índice tiene dimensión D1 y el modelo de embeddings D2" sin escribir nada.
- **FR-065 (M) Verificación de dimensión de embeddings** — Dado el modelo `EMBEDDING_MODEL`, cuando se inicializa el servicio de embeddings, entonces se embebe un texto de prueba y, si la longitud del vector no es `EMBEDDING_DIM`, se informa el error con ambos valores.

- **FR-060 (M) Trazas** — Dada cualquier ejecución de Ingesta o del Analista, cuando corre, entonces aparece en LangSmith como una traza en el proyecto `LANGSMITH_PROJECT`, con cada nodo del grafo como span.
- **FR-061 (M) Nombres y metadatos de traza** — Dada una traza, cuando se registra, entonces su `run_name` es `ingest:<nombre del pdf>` o `analyst:<primeros 60 caracteres de la pregunta>`, y sus metadatos incluyen `doc_id` o `question_id` (si viene del set de evaluación), modelo de chat y backend del sandbox.
- **FR-062 (M) Script de evaluación local** — Dado `eval/questions.yaml`, cuando se ejecuta `python -m eval.run_local`, entonces se corre el Analista sobre cada pregunta y se escribe `EVALUATION.md` con, por pregunta: estado esperado y obtenido, respuesta esperada y obtenida, correcta/incorrecta, reintentos y link a la traza.
- **FR-063 (S) Evals en LangSmith (bonus)** — Dado `eval/questions.yaml`, cuando se ejecuta `python -m eval.run_langsmith`, entonces se crea o actualiza un dataset en LangSmith y se corre un experimento con evaluadores automáticos de estado y de valor numérico (BR-030).

## 5. Reglas de negocio

- **BR-001 Columnas consistentes** — `TableMetadata.columns` tiene exactamente una entrada por columna del DataFrame, y cada `columns[i].name` coincide exactamente con el nombre de la columna i. *Motivo:* el generador de código depende de nombres exactos. *Excepciones:* ninguna.
- **BR-002 Columna de encabezados de fila válida** — `row_header_column`, elegida por el LLM, es nula o coincide exactamente con el nombre de una columna de tipo texto del DataFrame. `row_headers` no lo genera el LLM: lo completa el sistema con los valores no nulos de esa columna. *Motivo:* evita entidades inventadas por el LLM. *Excepciones:* si `row_header_column` es nula, `row_headers` es una lista vacía.
- **BR-003 Nombre y descripción útiles** — `name` tiene al menos 3 caracteres y no es genérico (no coincide con "Tabla", "Tabla N", "Table", "Cuadro N" sin más texto); `description` tiene entre 2 y 4 oraciones (contadas como fragmentos no vacíos terminados en `.`, `?` o `!`, sin cortar en números decimales ni abreviaturas de una letra). *Motivo:* la recuperación depende de ellos, y la consigna (§5.2) pide una descripción de 2 a 4 oraciones sobre qué mide la tabla, sus unidades, período y alcance.
- **BR-004 Unidad explícita** — Cada columna numérica tiene `unit` distinto de vacío; si el contexto no permite deducirla, el valor es `"desconocida"` (valor permitido, no error). *Motivo:* BR-012 necesita distinguir unidad conocida de desconocida.
- **BR-005 Identificadores idempotentes** — `doc_id` = primeros 16 caracteres hex del SHA-256 de los bytes del PDF; `table_id` = `{doc_id}-t{NN}`, con NN el orden de la tabla lógica en el documento (01, 02, …). *Motivo:* re-ingerir el mismo contenido produce los mismos IDs aunque cambie el nombre del archivo.
- **BR-006 Reemplazo por documento** — Al indexar un documento, primero se eliminan de Pinecone y del almacén todas las tablas con ese `doc_id`, y luego se escriben las nuevas. *Motivo:* evita tablas obsoletas si la nueva ingesta detecta menos tablas.
- **BR-010 Decisión de estado** — Sea S el conjunto de subpreguntas. Una subpregunta está *resuelta* si está cubierta por la selección (FR-023/FR-024) **y** `CodeResult.results` contiene un valor para ella. Entonces: `answered` si todas están resueltas; `partial` si al menos una está resuelta y al menos una no; `cannot_answer` si ninguna lo está. *Motivo:* el estado lo decide la lógica, no la redacción. *Excepciones:* FR-030.
- **BR-011 Sin datos externos** — No se interpola, extrapola, usa el período más cercano ni se completa con conocimiento del LLM. Un período o entidad faltante deja la subpregunta no cubierta.
- **BR-012 Conversiones** — Se permiten y se informan en la respuesta las conversiones que no requieren datos externos: cambio de escala (miles ↔ millones), porcentaje ↔ fracción, y agregación de valores mensuales a anuales solo si están los 12 meses. Conversión de moneda, ajuste por inflación y per cápita requieren una tabla indexada con el dato; si no existe, la subpregunta no está cubierta.
- **BR-013 Valor de comparación faltante** — Si la pregunta compara contra un valor de referencia (por ejemplo "el promedio nacional") que ninguna tabla informa, la subpregunta no está cubierta; no se reemplaza por un valor calculado salvo que la pregunta defina explícitamente cómo calcularlo.
- **BR-014 Ambigüedad de unidad o significado** — Si una columna necesaria tiene `unit = "desconocida"` o `value_type = "unknown"` y la elección cambia el resultado (por ejemplo, nominal vs. real), la subpregunta no está cubierta y el motivo describe la ambigüedad.
- **BR-015 Sin números en cannot_answer** — Con estado `cannot_answer`, la respuesta y la UI no muestran ningún resultado numérico calculado.
- **BR-020 Módulos permitidos en el código generado** — `pandas`, `numpy`, `math`, `json`, `statistics`, `datetime`, `re`, `decimal`, `fractions`. Cualquier otro import se rechaza (FR-053).
- **BR-030 Corrección en la evaluación** — Una respuesta es correcta si el estado obtenido es igual al esperado y, para `answered`/`partial`, cada valor numérico esperado coincide con el obtenido con tolerancia relativa de 0,5 % (o absoluta de 0,01 si el esperado es 0).

## 6. Requisitos no funcionales

- **NFR-001 Secretos** — Ninguna clave en el repositorio: `.env` en `.gitignore`, `.env.example` versionado con todas las variables y valores vacíos. Umbral: 0 coincidencias al buscar en el historial git patrones de claves (`sk-`, `pcsk_`, `lsv2_`).
- **NFR-002 Aislamiento de secretos en el sandbox** — Umbral: 0 variables de entorno que empiecen con `LITELLM_`, `PINECONE_`, `LANGSMITH_` u `OPENAI_` visibles para el código generado, con cualquier backend.
- **NFR-003 Timeout del sandbox** — `SANDBOX_TIMEOUT_S` por defecto 30 s; ninguna ejecución supera ese valor + 5 s de margen. Docker: memoria ≤ 512 MB, CPU ≤ 1, procesos ≤ 64.
- **NFR-004 Reintentos de ingesta** — `INGEST_MAX_RETRIES` por defecto 2 (hasta 3 llamadas de enriquecimiento por tabla), configurable por variable de entorno.
- **NFR-005 Reintentos del Analista** — `ANALYST_MAX_RETRIES` por defecto 3 (hasta 4 generaciones de código por pregunta), configurable por variable de entorno.
- **NFR-006 Tamaño de metadatos en Pinecone** — Cada registro ≤ 38 KB serializado (margen sobre el límite de ~40 KB); la vista previa se recorta por filas hasta cumplirlo.
- **NFR-007 Reproducibilidad** — Instalación con `uv sync` sobre Python 3.11+ en Windows, macOS y Linux; dependencias fijadas en `uv.lock`; la imagen del sandbox se construye con un único comando documentado.
- **NFR-008 Tiempo de ingesta** — El PDF sintético de ejemplo (≤ 10 páginas, ≤ 8 tablas) se ingiere en ≤ 3 minutos de punta a punta con el modelo del proxy.
- **NFR-009 Uso responsable del proxy** — Con `LLM_CACHE=true`, repetir una ingesta o pregunta idéntica no genera nuevas llamadas al LLM (caché SQLite local) ni al modelo de embeddings (caché de embeddings).
- **NFR-010 Calidad de código** — `mypy` sobre el paquete termina con 0 errores; los estados de los grafos están tipados (TypedDict / Pydantic); `pytest` pasa sin acceso a red (servicios externos simulados en los tests unitarios); `ruff check` termina con 0 errores.

## 7. Datos e interfaces

### 7.1 Variables de entorno (`.env.example`)

`LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` (= `mas-2026s2-tables`), `LANGSMITH_TRACING` (= `true`), `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` (= `mas-2026s2-<legajo>`), `SANDBOX_BACKEND` (`auto`|`docker`|`subprocess`), `SANDBOX_TIMEOUT_S`, `INGEST_MAX_RETRIES`, `ANALYST_MAX_RETRIES`, `RETRIEVAL_K` (por defecto 6), `LLM_CACHE` (`true`|`false`), `DATA_DIR` (por defecto `data/store`), `LLM_STRUCTURED_METHOD` (`function_calling`|`json_schema`|`json_mode`, por defecto `function_calling`).

### 7.2 `TableMetadata` (Pydantic)

Cubre los campos mínimos de la consigna (§5.2: `table_id`, `name`, `description`, `columns` con descripción y tipo/unidad, `row_headers`, `source` con archivo y páginas) y agrega los que necesitan las reglas de respondibilidad (`periods_covered`, `entities_covered`, `value_type`, `scale`).

Los campos marcados **(LLM)** los genera el modelo; los marcados **(sistema)** los completa el código y no se le piden al LLM.

| Campo | Tipo | Origen | Descripción |
|---|---|---|---|
| `table_id` | str | sistema | BR-005 |
| `doc_id` | str | sistema | BR-005 |
| `name` | str | LLM | Nombre descriptivo de la tabla |
| `description` | str | LLM | 2 a 4 oraciones: qué mide la tabla, sus unidades, período y alcance (BR-003) |
| `columns` | list[`ColumnInfo`] | LLM + sistema | Una por columna (BR-001) |
| `row_header_column` | str \| null | LLM | Columna que contiene los encabezados de fila |
| `row_headers` | list[str] | sistema | Valores de `row_header_column` (BR-002) |
| `periods_covered` | list[str] | LLM | Períodos presentes en la tabla (ej. `["2019","2020",…]`) |
| `entities_covered` | list[str] | LLM | Entidades presentes (regiones, productos, rubros) |
| `notes` | str | LLM | Notas al pie y aclaraciones relevantes |
| `source` | `Source` | sistema | `{pdf_name, doc_id, pages: list[int], section_title}` |
| `n_rows`, `n_cols` | int | sistema | Dimensiones del DataFrame |

`ColumnInfo`: `name` (str, nombre exacto), `description` (str, LLM), `dtype` (str, sistema), `unit` (str, LLM; BR-004), `scale` (`"unidades"|"miles"|"millones"|"miles de millones"|"desconocida"`, LLM), `value_type` (`"nominal"|"real"|"porcentaje"|"conteo"|"indice"|"texto"|"unknown"`, LLM).

### 7.3 Registro en Pinecone

- `id` = `table_id`; `values` = embedding del texto definido en FR-015 (dimensión `EMBEDDING_DIM`).
- `metadata`: `doc_id`, `pdf_name`, `pages` (lista de enteros), `name`, `description`, `columns` (lista de nombres), `row_headers` (recortada a 100), `periods_covered`, `entities_covered`, `preview_markdown` (primeras filas, NFR-006), `n_rows`, `n_cols`.

### 7.4 `QueryPlan`

`subquestions: list[{id: "q1"…, text, metrics: list[str], entities: list[str], periods: list[str], operation: str}]`, `search_queries: list[str]` (1 a 4).

### 7.5 Contrato `CodeResult` (última línea de stdout)

```json
{
  "results": [{"subquestion_id": "q1", "value": 12.34, "unit": "%", "label": "Crecimiento promedio 2021-2024"}],
  "missing": [{"subquestion_id": "q2", "reason": "La tabla no tiene 2024"}],
  "conversions": ["Valores en miles convertidos a millones"]
}
```

`value` es número o lista de `{label, value}` para resultados por categoría (por ejemplo, proporción por año).

### 7.6 Estado del grafo del Analista (campos principales)

`question`, `query_plan`, `candidates`, `selection` (cobertura por subpregunta), `code`, `execution` (stdout, stderr, exit_code, duration, backend), `code_result`, `attempts`, `status` (`answered`|`partial`|`cannot_answer`), `missing` (lista por subpregunta), `error` (null | `"execution_failed"` | `"no_tables_indexed"`), `answer`. El estado no contiene DataFrames: solo `table_id`s y rutas.

### 7.7 Grafos

```
Ingesta:   load_pdf ─(archivo inválido o sin capa de texto)→ END con mensaje
           extract_tables ─(0 tablas)→ END con mensaje
           load_pdf → extract_tables → merge_continuations → collect_context → enrich → validate
           validate ─(inválidas y quedan reintentos)→ enrich
           validate ─(resto)→ persist_and_index → END

Analista:  understand → retrieve ─(índice vacío)→ decide_status
           retrieve → select ─(ninguna subpregunta cubierta)→ decide_status
           select → generate_code → execute → validate_output
           validate_output ─(inválida y quedan reintentos)→ generate_code
           validate_output ─(resto)→ decide_status → answer → END
```

## 8. Criterios de verificación

### Ingesta
- VC-001: Ingerir el PDF sintético → el estado contiene el texto de todas sus páginas (cantidad igual a `page_count`). *(FR-001)*
- VC-002: Ingerir un PDF compuesto solo por una imagen → 0 tablas indexadas y la UI muestra el mensaje de FR-002. *(FR-002)*
- VC-002b: Ingerir un PDF con solo texto → 0 llamadas al LLM, 0 tablas indexadas y el mensaje de FR-019. *(FR-019)*
- VC-002c: Ingerir un `.txt` renombrado a `.pdf` y un PDF con contraseña → mensaje de FR-019b en ambos casos, sin excepción no manejada. *(FR-019b)*
- VC-003: Extraer la tabla "simple" del PDF sintético → DataFrame con la cantidad de filas y columnas definidas en el generador del PDF. *(FR-003)*
- VC-004: Extraer la tabla con encabezado de dos niveles del PDF sintético → nombres de columna `"<nivel1> | <nivel2>"`, todos únicos. *(FR-004)*
- VC-005: Normalizar `["", "-", "—", "s/d", "12"]` → `[NaN, NaN, NaN, NaN, 12.0]`. *(FR-005)*
- VC-005b: Normalizar `["-", "12"]` en un documento cuyo texto declara "- Cero absoluto" → `[0.0, 12.0]` y la nota de la tabla menciona la convención; en un documento sin esa declaración → `[NaN, 12.0]`. Normalizar `["///", "...", "1.234*"]` → `[NaN, NaN, 1234.0]`. *(FR-005, FR-006)*
- VC-006: Normalizar la columna `["1.234,56", "(1.500)", "12,5%", "$ 3.000"]` → `[1234.56, -1500, 12.5, 3000]` (formato coma decimal detectado); normalizar la columna `["1,234.56", "(1,500)", "US$ 1,000.50"]` → `[1234.56, -1500, 1000.5]` (formato punto decimal detectado). *(FR-006)*
- VC-006b: Normalizar la columna `["Norte", "Sur", "12"]` (33 % numérico) → queda como texto sin cambios. *(FR-006, borde)*
- VC-007: Extraer la tabla que continúa en la página siguiente del PDF sintético → una sola tabla con `source.pages = [N, N+1]`, la suma de filas de ambas partes y sin la fila de encabezado repetida. *(FR-007)*
- VC-008: Dos tablas consecutivas en páginas distintas con distinta cantidad de columnas → se guardan como dos tablas. *(FR-007, borde)*
- VC-008b: Extraer `indec_ica.pdf` → el Cuadro 9 (página 29) y el Cuadro 10 (página 30) quedan como dos tablas distintas, cada una con `source.pages` de una sola página. *(FR-007, borde)*
- VC-009: PDF de prueba con una tabla como imagen (≥ 10 % del área de la página) y una tabla de texto → se indexa solo la tabla de texto y la UI lista un aviso con la página de la imagen. *(FR-008)*
- VC-009b: PDF de prueba con una imagen pequeña (logo, < 10 % del área) junto a una tabla de texto → se indexa la tabla y no hay aviso. *(FR-008, borde)*
- VC-009c: Extraer `indec_ica.pdf` → se obtienen los Cuadros 1 a 10 (páginas 7, 13, 22, 24, 25, 27, 28, 29 y 30) y ninguna tabla de la tapa (página 1) ni de las páginas de infografías y gráficos (4, 5, 6, 10, 11, 14 a 18); cada descarte genera un aviso de FR-008b. *(FR-008b)*
- VC-009d: Extraer el Cuadro 3 del PDF sintético (solo líneas horizontales) → DataFrame de 4 filas y 4 columnas. *(FR-003)*
- VC-010: Recolectar contexto de una tabla con epígrafe, párrafo anterior y nota al pie conocidos → los tres textos coinciden con los del PDF; los inexistentes quedan vacíos. *(FR-009)*
- VC-011: Enriquecer una tabla con LLM simulado → se obtiene una instancia válida de `TableMetadata`. *(FR-010)*
- VC-012: Validar un `TableMetadata` con una columna de menos → error que nombra BR-001. *(FR-011, BR-001)*
- VC-013: Validar un `TableMetadata` con `row_header_column = "Región"` cuando el DataFrame no tiene esa columna → error que nombra BR-002; con una columna existente → `row_headers` igual a sus valores no nulos. *(BR-002)*
- VC-014: Validar `name = "Tabla 3"` → error que nombra BR-003. *(BR-003)*
- VC-014b: Validar `description` con 1 oración y con 5 oraciones → error que nombra BR-003 en ambos casos; con 2 oraciones que incluyen "12.5 %" → sin error. *(BR-003, borde)*
- VC-015: Validar una columna numérica con `unit = ""` → error; con `unit = "desconocida"` → sin error. *(BR-004)*
- VC-016: LLM simulado que devuelve metadatos inválidos la primera vez y válidos la segunda → la tabla se indexa y la traza muestra 2 llamadas a `enrich`; las tablas que eran válidas desde el inicio se enriquecen 1 sola vez. *(FR-012)*
- VC-017: LLM simulado que siempre devuelve metadatos inválidos → `enrich` se llama `INGEST_MAX_RETRIES + 1` veces, la tabla no se indexa y la UI muestra el aviso con sus errores. *(FR-013, NFR-004)*
- VC-018: Ingerir el PDF sintético → existen un `.parquet` y un `.json` por tabla indexada, y el `.parquet` recargado es igual al DataFrame normalizado. *(FR-014)*
- VC-019: Ingerir el PDF sintético → el índice contiene un vector por tabla con todos los campos de metadatos de §7.3. *(FR-015)*
- VC-020: Ingerir el mismo PDF dos veces, la segunda con otro nombre de archivo → la cantidad de vectores con ese `doc_id` es la misma que tras la primera ingesta y los IDs son idénticos. *(FR-016, BR-005)*
- VC-021: Ingerir un documento, simular que la segunda ingesta detecta una tabla menos → la tabla faltante ya no está en Pinecone ni en el almacén. *(FR-016, BR-006)*
- VC-022: Ingerir desde la UI → por cada tabla se ven los 6 elementos de FR-017. *(FR-017)*
- VC-023: Ingerir desde la UI → aparece una línea de progreso por cada nodo ejecutado, en orden. *(FR-018)*

### Analista
- VC-030: Pregunta con dos partes ("¿Cuál fue X en 2023 y cuál fue Y en 2022?") → `QueryPlan` con 2 subpreguntas. *(FR-020)*
- VC-031: Plan con 2 consultas de búsqueda que devuelven la misma tabla → la tabla aparece una sola vez en `candidates`. *(FR-021)*
- VC-032: Índice vacío → `status = cannot_answer`, `error = "no_tables_indexed"`, `generate_code` no se ejecuta. *(FR-022)*
- VC-033: Pregunta multitabla del set de evaluación → la selección incluye las dos tablas esperadas. *(FR-023)*
- VC-034: Pregunta sobre 2024 con tabla que cubre 2019–2023 → subpregunta no cubierta con motivo que menciona 2024 y el rango 2019–2023. *(FR-024, BR-011)*
- VC-034b: Pregunta por "Córdoba 2023" con tabla cuyo `row_headers` contiene "cordoba" y columna "Año 2023" → la subpregunta sigue cubierta (normalización de FR-024). *(FR-024, borde)*
- VC-034c: Subpregunta cubierta según el LLM que usa una columna con `value_type = "unknown"` y sin justificación de que no afecta → no cubierta con motivo de ambigüedad. *(FR-024b)*
- VC-035: Pregunta sin ninguna tabla relacionada → `generate_code` no se ejecuta y `status = cannot_answer`. *(FR-025)*
- VC-036: Prompt de generación para una tabla → contiene los nombres exactos de columnas, dtypes y la ruta del archivo. *(FR-026)*
- VC-037: Código que imprime `{"results":[...]}` válido → `execution.exit_code = 0` y `code_result` parseado. *(FR-027)*
- VC-038: Para cada caso inválido de FR-028 (exit ≠ 0, timeout, stdout sin JSON, JSON fuera de contrato, NaN) → la ejecución se marca inválida con el motivo correspondiente. *(FR-028)*
- VC-039: Generador simulado que falla en el primer intento y acierta en el segundo → `attempts = 2`, el prompt del segundo intento contiene el stderr del primero. *(FR-029)*
- VC-040: Generador simulado que siempre falla → se generan `ANALYST_MAX_RETRIES + 1` programas, `status = cannot_answer`, `error = "execution_failed"`. *(FR-030, NFR-005)*
- VC-041: Tabla de decisión de BR-010 con las combinaciones {todas, algunas, ninguna} resueltas → `answered`, `partial`, `cannot_answer` respectivamente. *(FR-031, BR-010)*
- VC-042: Pregunta `answered` del set → la respuesta menciona el valor, el nombre de la tabla, las páginas y la operación. *(FR-032)*
- VC-043: Pregunta `partial` del set → la respuesta lista la parte faltante y el dato que falta. *(FR-032)*
- VC-044: Ejecutar el nodo de respuesta con cualquier estado → la actualización que devuelve contiene solo la clave `answer`; para `cannot_answer`, el LLM simulado no recibe ninguna llamada. *(FR-033)*
- VC-045: Pregunta que requiere tipo de cambio sin tabla de tipo de cambio → subpregunta no cubierta con motivo "requiere datos externos". *(BR-012)*
- VC-046: Pregunta con valores en miles pedida en millones → resultado correcto y `conversions` menciona el cambio de escala. *(BR-012)*
- VC-047: Pregunta "¿por cuánto superó al promedio nacional?" sin tabla con promedio nacional → subpregunta no cubierta; no se calcula el promedio de las regiones. *(BR-013)*
- VC-048: Pregunta sobre una columna con `value_type = "unknown"` donde nominal/real cambia el resultado → subpregunta no cubierta y el motivo describe la ambigüedad. *(BR-014)*
- VC-049: Cualquier respuesta `cannot_answer` → ni el texto ni la UI contienen resultados numéricos calculados. *(BR-015)*

### Sandbox
- VC-050: Con Docker disponible y `SANDBOX_BACKEND=docker`, código que intenta `urllib.request.urlopen("https://example.com")` → falla por red no disponible (el filtro AST también lo rechaza; para esta prueba el filtro se desactiva). *(FR-050)*
- VC-051: Con backend Docker, código que intenta escribir en `/data/x.txt` → falla por sistema de archivos de solo lectura. *(FR-050)*
- VC-052: Con backend subproceso, código que lista el directorio de trabajo → solo ve los archivos de las tablas seleccionadas. *(FR-051)*
- VC-053: Con cualquier backend, código que imprime `os.environ` (filtro AST desactivado para la prueba) → ninguna variable con los prefijos de NFR-002. *(NFR-002)*
- VC-054: `SANDBOX_BACKEND=auto` sin Docker disponible → se usa subproceso y la UI muestra "subprocess". *(FR-052)*
- VC-055: Código que importa `os`, `subprocess`, `socket` o llama a `eval` → rechazado antes de ejecutar, con el motivo. *(FR-053, BR-020)*
- VC-056: Código con `while True: pass` y `SANDBOX_TIMEOUT_S=5` → ejecución inválida "timeout" en ≤ 10 s. *(FR-054, NFR-003)*

### UI, observabilidad y evaluación
- VC-060: Subir el PDF sintético desde la UI → se ven progreso, resumen y avisos. *(FR-040)*
- VC-061: Abrir Explorar tras ingerir dos PDFs → dos grupos con sus tablas y datos completos en expanders. *(FR-041)*
- VC-062: Hacer dos preguntas → el historial muestra ambas con los 7 elementos de FR-042. *(FR-042)*
- VC-063: Con `LITELLM_API_KEY` inválida, hacer una pregunta → `st.error` que menciona LiteLLM y la app sigue respondiendo a la interacción siguiente. *(FR-043)*
- VC-064: Con `PINECONE_API_KEY` inválida, subir un PDF → `st.error` que menciona Pinecone, sin caída. *(FR-043)*
- VC-065: Abrir la barra lateral → se ven los 5 datos de FR-044 y ninguna clave. *(FR-044)*
- VC-065b: Iniciar la app sin `PINECONE_API_KEY` → se lista la variable faltante y las pestañas Subir y Preguntar están deshabilitadas; la app no lanza excepción. *(FR-045)*
- VC-065c: Primera ingesta sin índice creado → el índice existe con dimensión `EMBEDDING_DIM`; con un índice de dimensión distinta → mensaje de FR-064 y 0 vectores escritos. *(FR-064)*
- VC-065d: `EMBEDDING_DIM` distinto de la dimensión real del modelo → error que muestra ambos valores al iniciar el servicio. *(FR-065)*
- VC-066: Una ingesta y una pregunta → dos trazas en el proyecto LangSmith con un span por nodo ejecutado. *(FR-060)*
- VC-067: Traza de una pregunta del set → `run_name` empieza con `analyst:` y los metadatos incluyen `question_id`, modelo y backend. *(FR-061)*
- VC-068: `python -m eval.run_local` → `EVALUATION.md` con una fila por pregunta y los 6 campos de FR-062. *(FR-062)*
- VC-069: `python -m eval.run_langsmith` → experimento visible en LangSmith con puntajes de estado y valor por pregunta. *(FR-063, BR-030)*
- VC-070: Fin a fin de NFRs — clonar el repo en una máquina limpia, `uv sync`, completar `.env`, construir la imagen del sandbox, correr `pytest` (pasa sin red), ingerir el PDF sintético (≤ 3 min, NFR-008), repetir la ingesta con `LLM_CACHE=true` (0 llamadas nuevas al LLM en la traza, NFR-009), y buscar patrones de claves en `git log -p` (0 coincidencias, NFR-001). *(NFR-001, 006, 007, 008, 009, 010)*

## 9. Entregables de evaluación

- `data/sample_pdfs/`: PDF sintético (generado por `scripts/make_sample_pdf.py`, con tabla multipágina, encabezado de dos niveles, números con formato argentino, una tabla que no cubre el último año, una tabla regional sin promedio nacional y una columna monetaria sin aclarar nominal/real) y PDF real: informe técnico mensual de INDEC "Intercambio comercial argentino" (ICA), descargado por el alumno desde indec.gob.ar y guardado como `data/sample_pdfs/indec_ica.pdf` (edición con cifras de agosto de 2026, 36 páginas: 10 cuadros numerados —el Cuadro 9 y el 10 son consecutivos con igual estructura— más infografías, gráficos y un glosario de signos convencionales).
- `eval/questions.yaml`: ≥ 10 preguntas con `id`, `question`, `expected_status`, `expected_values` y `notes`; incluye ≥ 2 multitabla, ≥ 1 sin tabla relacionada (`cannot_answer`), ≥ 1 con período faltante, ≥ 1 con valor de comparación faltante, ≥ 1 con conversión de unidad externa y ≥ 2 sobre el PDF real.
- `EVALUATION.md` con resultados y 3 links o capturas de trazas representativas.
- `README.md` con instalación, diagramas Mermaid de ambos grafos (exportados con `draw_mermaid()`), decisiones de diseño, limitaciones y link al video.

## 10. Decisiones de diseño y justificación

| Decisión | Elección | Por qué | Trade-off aceptado |
|---|---|---|---|
| Extracción de PDF | PyMuPDF (`find_tables`, `get_text("dict")`) | Sugerida por la cátedra; una sola librería da tablas y bloques de texto con coordenadas y tamaño de fuente (necesario para títulos de sección); sin dependencias de Java ni modelos de ML | Menor calidad que Docling en tablas sin bordes complejas; se mitiga probando la estrategia `text` cuando `lines` no detecta tablas |
| Almacén de tablas | Parquet + JSON por `table_id` en `DATA_DIR` | Parquet conserva dtypes (no hay que re-tipar); un archivo por tabla hace trivial montar solo las tablas seleccionadas en el sandbox | No es compartido entre máquinas; para el TP el sistema es local |
| Embeddings | Un vector por tabla | La pregunta típica apunta a una tabla por su tema; un vector evita deduplicar y mantiene la recuperación explicable | Menor recall en preguntas que solo nombran una entidad de fila; se mitiga incluyendo `row_headers` y `entities_covered` en el texto embebido |
| Sandbox | Docker (`--network none`, solo lectura, límites) con fallback a subproceso, más filtro AST en ambos | En Windows un subproceso no puede bloquear red ni sistema de archivos; Docker sí. El fallback permite corregir sin Docker | Dos backends que mantener; el fallback tiene aislamiento parcial, documentado como limitación |
| Reintentos agotados | `cannot_answer` + `error="execution_failed"` | Respeta los tres estados de la consigna y distingue "faltan datos" de "falló el código" | El usuario ve `cannot_answer` aunque los datos existan; el campo `error` y la UI lo aclaran |
| Estado de respuesta | Nodo `decide_status` determinístico (BR-010) | La consigna exige que el estado lo decida la lógica y quede en el estado del grafo para testearlo | Menos flexible ante preguntas raras que un LLM juez |
| Unión multipágina | Reglas determinísticas | Testeable y explicable en el oral | No une tablas que cambian de cantidad de columnas entre páginas |
| Stack | Python ≥ 3.11, LangGraph ≥ 1.0, LangChain ≥ 1.0 (`langchain-openai`), `pinecone` SDK, Streamlit, PyMuPDF, pandas + pyarrow; versiones exactas fijadas en `uv.lock` | Requerido por la consigna, salvo PyMuPDF y pyarrow | — |

## 11. Preguntas abiertas

Ninguna. (OQ-1, campos mínimos de metadatos, se resolvió con la consigna completa: §7.2 los cubre y BR-003 incorpora la extensión de la descripción.)

## 12. Supuestos

- A-1: Gestor de dependencias **uv** (la consigna admite uv, poetry o requirements.txt).
- A-2: Identificadores del código en inglés; UI, prompts, README y respuestas en español.
- A-3: El modelo de chat del proxy soporta salida estructurada (tool calling o JSON schema). Se verifica en la primera iteración; si no, se usa modo JSON con validación Pydantic y reintento.
- A-4: La unión multipágina se decide con reglas determinísticas (FR-007), sin LLM.
- A-6: El catálogo de la pestaña Explorar se lee del almacén local (JSON), que es la fuente de verdad junto con Pinecone; ambos se escriben en la misma operación (BR-006).
- A-7: Una tabla que agota los reintentos de validación se saltea (FR-013) en lugar de indexarse con metadatos degradados.
- A-8: El historial del chat vive en `st.session_state` y se pierde al recargar la página.

## Changelog

- **0.3 (2026-10-01)** — Con el PDF real de INDEC: FR-005 interpreta `-` según los signos convencionales del documento (decisión del alumno) y suma `///`, `.`, `…`; FR-006 quita `*`; FR-007 no une tablas separadas por un epígrafe o una "Fuente/Nota"; nueva FR-008b filtra detecciones que no son tablas; FR-003 exige detectar tablas con solo líneas horizontales; el PDF real tiene 36 páginas (el límite de 30 era propio del spec, no de la consigna). VCs nuevos: VC-005b, VC-008b, VC-009c, VC-009d.
- **0.2 (2026-10-01)** — Consigna completa recibida: se resuelve OQ-1; BR-003 exige descripción de 2 a 4 oraciones (VC-014b); §7.2 y FR-015 referencian los mínimos de la consigna §5.2. Se agrega `LLM_STRUCTURED_METHOD` a §7.1 (D-003). Segundo PDF definido: INDEC ICA.
- **0.1 (2026-10-01)** — Borrador inicial aprobado por el alumno.
