# Evaluación del Agente Analista

Generado por `uv run python -m eval.run_local`. Una respuesta es correcta si el estado coincide con el esperado y, para `answered`/`partial`, cada valor esperado tiene que aparecer entre los resultados del código con tolerancia relativa de 0,5 % (absoluta de 0,01 si el esperado es 0).

- **Fecha:** 2026-10-11 21:31
- **Modelo:** `openai/gpt-4.1-mini`
- **Embeddings:** `text-embedding-3-small`
- **Sandbox:** subprocess
- **Preguntas:** 22
- **Duración total:** 249 s

## Resumen

- **Correctas:** 20/22 (91%)
- **Estado correcto:** 20/22 (91%)
- **Valores correctos** (preguntas `answered`/`partial`): 12/14 (86%)
- **Reintentos de código:** 1 en total

| Grupo | Correctas |
|---|---|
| PDF: `informe_sintetico.pdf` | 11/11 (100%) |
| PDF: `indec_ica.pdf` | 4/5 (80%) |
| PDF: `indec_ipc.pdf` | 5/6 (83%) |
| Estado esperado: `answered` | 9/11 (82%) |
| Estado esperado: `cannot_answer` | 8/8 (100%) |
| Estado esperado: `partial` | 3/3 (100%) |

## Trazas representativas

Links públicos de LangSmith (se abren sin cuenta):

- **Respuesta completa con dos tablas del PDF real** (`ind-03`, peso del sector automotriz en las exportaciones de agosto de 2026; corrida del 5/10, en la que respondió bien): https://smith.langchain.com/public/2183c165-d3cf-4e3b-9412-a88335229d5a/r/8c6c0931-9f58-49dc-8e36-35e389bf9951
- **Respuesta parcial** (`syn-04`: responde qué departamento tuvo más desempleo y explica que ninguna tabla informa el promedio provincial, sin calcularlo): https://smith.langchain.com/public/4ade60ee-1d51-48d7-8b55-30f9750d0151/r/50298fd4-00bd-4e28-8fcd-1797ff0d8ce0
- **Ingesta completa del PDF real** (`indec_ica.pdf`: cada nodo del grafo de Ingesta aparece como un span —carga, extracción, unión entre páginas, contexto, enriquecimiento con el LLM (una llamada por tabla, en paralelo), validación e indexación en Pinecone—; 11 tablas indexadas): https://smith.langchain.com/public/6745c41c-325b-4c47-a6e2-f46ed862311b/r
- **Con reintento** (`ipc-03`, corrida final: el filtro de seguridad rechazó el primer programa porque usaba `locals()`; el segundo, generado con ese error, respondió bien con dos tablas): https://smith.langchain.com/public/d7787069-bd24-4ebe-a28e-37604775e653/r

## Análisis

**Resultado final: 20/22** (corrida del 11/10, modelo `openai/gpt-4.1-mini`, sin caché). Las 11 preguntas del PDF sintético, las 8 `cannot_answer` y las 3 `partial` dan lo esperado. Fallan dos preguntas `answered`, y las dos **fallan de forma conservadora**: el sistema dice que le falta un dato en lugar de dar un número equivocado. En toda la corrida no hay ningún resultado numérico incorrecto.

- `ind-03` (participación del sector automotriz en las exportaciones del mes): el selector eligió el Cuadro 3 como fuente del total de exportaciones en lugar del Cuadro 1; el código no encontró la fila del total y lo informó como faltante → `cannot_answer`. En la corrida del 5/10 respondió bien.
- `ipc-02` (región con mayor variación en Vivienda y diferencia con el dato nacional): respondió la región (Noreste, 4,0 %), pero el código no tomó la columna "Nacional" de la misma tabla y declaró faltante la segunda parte → `partial`. En otras dos corridas dio la diferencia correcta (1,2 puntos).

**Cómo se llegó.** El set se corrió varias veces y cada falla se corrigió en el sistema, no en las preguntas (salvo `syn-01`, ver abajo):

- *Desarrollo (hasta el 5/10), 16 preguntas sobre el PDF sintético y el de comercio exterior de INDEC:*
  - Primeras corridas sobre el PDF sintético (8/11 estados correctos): el chequeo automático de cobertura buscaba textual períodos como "todos los años disponibles" y entidades como "provincia", y descartaba preguntas que sí tenían datos; y en `syn-04` el modelo reemplazó el promedio provincial por el promedio simple de los departamentos. Se acotó el chequeo y se agregó uno específico para valores de comparación.
  - Errores de valor: proporciones devueltas como fracción (0,0113 en vez de 1,13 %) y una parte sin datos que el código calculó igual dentro de otra subpregunta. Se exigió porcentaje y el generador de código dejó de recibir la pregunta completa: solo las partes que tiene que calcular y, aparte, las que no.
  - `syn-01` decía "crecimiento interanual promedio", que el modelo leyó como tasa compuesta (78,55 %) y no como promedio de las variaciones (84,88 %). Las dos lecturas son válidas, así que se reformuló la pregunta.
  - Primera corrida con INDEC: 14/16. El chequeo de períodos buscaba "enero 2026" como frase, cuando en el cuadro el mes es una fila y el año una columna; ahora se verifican por separado. Resultado: 16/16, pero en una corrida que reutilizó respuestas guardadas en la caché local.
- *11/10: corrida sin caché y un PDF nuevo.* El proxy dejó de atender el alias `gpt-4.1-mini` y el mismo modelo pasó a llamarse `openai/gpt-4.1-mini`; con el nombre nuevo la caché no aplica, así que desde acá todas las llamadas son reales. Se sumó el IPC de agosto de 2026 de INDEC (26 cuadros) con 6 preguntas escritas **antes** de correrlas:
  - Primera corrida de las 6: 3/6. El chequeo de entidades exigía la frase exacta, y el plan del LLM anotaba entidades compuestas ("IPC nivel general nacional", "nivel nacional", "dato nacional") que en la tabla están separadas (fila "Nivel general", columna "Nacional"). Ahora una entidad está presente si cada palabra que la identifica aparece en las tablas (sin contar artículos ni palabras genéricas); "Córdoba" y "Río Seco" siguen sin pasar.
  - Corrida completa de las 22: 19/22. `ind-01` falló porque el plan escribió el período "enero-agosto 2026" y el cuadro dice "acumulado hasta agosto de 2026": ahora un rango que empieza en enero acepta una tabla con el acumulado hasta ese mes. Además el selector de tablas no veía el epígrafe original del PDF (solo el nombre que generó el LLM en la ingesta); ahora lo ve, y su prompt pide buscar en otra tabla el total o denominador que falte y explica equivalencias de períodos ("acumulado del año" = "respecto a diciembre").
  - Corrida final: 20/22. **Después de esta corrida no se hicieron más ajustes.**

**Qué tener en cuenta al leer el 20/22.**

- **El resultado varía entre corridas.** Temperatura 0 no hace determinístico al modelo: la misma pregunta puede elegir otras tablas o anotar otras entidades. En dos corridas seguidas de las 6 preguntas del IPC el resultado fue 10/12, con fallas distintas en cada una, y `ind-03`/`ipc-02` respondieron bien en otras corridas. Conviene leer el número como "alrededor de 9 de cada 10" y no como exacto.
- **El sistema se ajustó mirando estas preguntas**, así que el número sobreestima el acierto en documentos nuevos. La mejor estimación para un PDF desconocido es la primera corrida de las preguntas del IPC (3/6) y de las de comercio exterior (14/16 en su momento): los fallos iniciales vinieron de chequeos demasiado literales, ya corregidos, pero puede haber otros.
- **Los chequeos automáticos de cobertura se basan en palabras** (años, meses, nombres de filas, "promedio provincial"). Ahora toleran entidades y rangos redactados de otra forma, pero una pregunta que exprese algo con palabras muy distintas depende solo del criterio del modelo.
- **Cuando falla, falla hacia "no puedo responder".** En las corridas observadas los errores del selector terminan en `partial` o `cannot_answer` con el dato faltante explicado, no en números inventados: el código informa lo que no encuentra y el estado lo deciden reglas.

## Resultados por pregunta

| ID | Estado esperado | Estado obtenido | Respuesta esperada | Respuesta obtenida | Correcta | Reintentos | Traza |
|---|---|---|---|---|---|---|---|
| syn-01 | `answered` | `answered` | Promedio de las variaciones interanuales de los ingresos totales 2019-2023: 84,88 % | [q1] Promedio simple de las variaciones interanuales de los ingresos totales del sector público entre 2019 y 2023: 84,88 % | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/81436115-2acd-469a-a4f0-472b48082e11?poll=true) |
| syn-02 | `answered` | `answered` | Gasto en ciencia y tecnología / gastos totales: 2019: 1,13 %; 2020: 1,07 %; 2021: 1,17 %; 2022: 1,23 %; 2023: 1,15 % | [q1] Proporción del gasto en ciencia y tecnología respecto al gasto total por año: 2019: 1,13 %; 2020: 1,07 %; 2021: 1,17 %; 2022: 1,23 %; 2023: 1,15 % | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/27c3dbfb-2cc5-436f-88d6-195a3a6936a8?poll=true) |
| syn-03 | `cannot_answer` | `cannot_answer` | Falta: La tabla de finanzas públicas cubre 2019-2023; 2024 no está disponible. | Falta: Dato para el año 2024 | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/a11bebdc-d0a3-40bc-a2fd-0fe792fcec13?poll=true) |
| syn-04 | `partial` | `partial` | Departamento con mayor desempleo en 2023 (Norte): 9,8 % · Falta: Ninguna tabla informa un promedio provincial de desempleo; no se reemplaza por el promedio de los departamentos. | [q1] Departamento con la tasa de desempleo más alta en 2023: Norte: 9,8 % · Falta: Promedio provincial de tasa de desempleo en 2023 | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/86d968fa-b86b-4b19-9fd8-a1255a85c9b9?poll=true) |
| syn-05 | `answered` | `answered` | Producción de soja 2023 por habitante: Capital: 0,0165 toneladas por habitante; Norte: 3,81 toneladas por habitante; Valle Alto: 2,03 toneladas por habitante; Llanura: 7,57 toneladas por habitante; Costa Sur: 1,2 tonela… | [q1] Producción de soja por habitante en cada departamento en 2023: Capital: 0,0165 toneladas por habitante; Norte: 3,81 toneladas por habitante; Valle Alto: 2,03 toneladas por habitante; Llanura: 7,57 toneladas por hab… | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/f28c9a3d-a4fa-4faa-ab8c-5c48022e3ca6?poll=true) |
| syn-06 | `answered` | `answered` | Desempleo 2023 ponderado por población: 7,49 % | [q1] Tasa de desempleo provincial ponderada por población, 2023: 7,49 % | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/454eb3dd-cd4b-430b-afc2-05fb0c286bee?poll=true) |
| syn-07 | `cannot_answer` | `cannot_answer` | Falta: Las exportaciones están en US$ y los ingresos en pesos; no hay ninguna tabla con el tipo de cambio. | Falta: Valor de exportaciones en pesos para 2023 (solo se tiene en miles de dólares) | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/f67718a5-fe4a-4237-969e-f62ce1fc84bb?poll=true) |
| syn-08 | `answered` | `answered` | Exportaciones totales 2023: 956,69 millones de US$ | [q1] Total de exportaciones de la provincia en 2023: 956,69 millones de dólares | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/cc1853c8-1864-474f-84e9-6605d2f7ef67?poll=true) |
| syn-09 | `cannot_answer` | `cannot_answer` | Falta: La tabla de salarios no indica si los valores son nominales o reales y no hay un índice de precios para deflactar. | Falta: No hay datos de inflación para 2021-2023, solo para 2025-2026. No se puede calcular salario real entre 2021 y 2023. | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/5c316629-331f-4035-a703-f49784cd0f2e?poll=true) |
| syn-10 | `cannot_answer` | `cannot_answer` | Falta: Ninguna tabla indexada tiene datos de turismo. | Falta: Número de turistas que visitaron la provincia en 2023 | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/79bc6688-44d0-459b-b042-07cf285983b7?poll=true) |
| syn-11 | `cannot_answer` | `cannot_answer` | Falta: La tabla de desempleo incluye Capital, Norte, Valle Alto, Llanura y Costa Sur; Río Seco no está. | Falta: No hay datos para el departamento Río Seco en la tabla de tasa de desempleo por departamento. | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/940e15e7-d33d-47c1-bc35-18da040b66ca?poll=true) |
| ind-01 | `answered` | `answered` | Participación de Santa Fe en las exportaciones acumuladas a agosto de 2026: 20,44 % | [q1] Porcentaje de exportaciones argentinas acumuladas hasta agosto de 2026 originadas en Santa Fe: 20,44 % | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/639d0f8f-9528-4312-8bf3-25a29aa66a5f?poll=true) |
| ind-02 | `answered` | `answered` | Saldo comercial promedio mensual enero-agosto 2026: 2.281,25 millones de USD | [q1] Saldo comercial promedio mensual entre enero y agosto de 2026: 2.281,25 millones de USD | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/d2ef81f7-5016-4ecd-a1cc-df5d9a944e36?poll=true) |
| ind-03 | `answered` | `cannot_answer` | Exportaciones del sector automotriz / exportaciones totales, agosto de 2026: 9,88 % | Falta: No se encontró fila total de exportaciones en tabla 18d7b83789e2f178-t03 | ❌ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/c27482be-7b62-4ecb-89ce-9319dea3beb1?poll=true) |
| ind-04 | `cannot_answer` | `cannot_answer` | Falta: El informe llega hasta agosto de 2026; septiembre solo tiene datos de 2025. | Falta: Dato de exportaciones para septiembre de 2026 | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/97873d7c-39cf-444b-be11-f8b576d10952?poll=true) |
| ind-05 | `partial` | `partial` | Exportaciones de la región Patagonia, agosto de 2026: 1.469 millones de USD · Falta: El origen de las exportaciones por región solo se publica para 2026; no hay dato de Patagonia en agosto de 2025. | [q1] Exportaciones región Patagonia agosto 2026: 1.469 millones de USD · Falta: Falta el dato de exportaciones de la región Patagonia en agosto de 2025 para calcular el crecimiento. | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/24c5b047-2b8c-4e90-a020-61bfd37d83bc?poll=true) |
| ipc-01 | `answered` | `answered` | Variación mensual del IPC nivel general nacional, agosto de 2026: 1,7 % | [q1] Variación mensual del IPC nivel general a nivel nacional en agosto de 2026: 1,7 % | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/12d8efc3-9bcb-4873-b66f-d46a9ca4178b?poll=true) |
| ipc-02 | `answered` | `partial` | Mayor variación mensual en Vivienda, agua, electricidad, gas y otros combustibles (Noreste): 4 % · Diferencia con la variación nacional (2,8 %): 1,2 puntos porcentuales | [q1] Noreste: 4 % · Falta: No se puede calcular diferencia porque falta dato nacional. | ❌ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/a86f1573-dc50-4878-b3e7-616ca43fd740?poll=true) |
| ipc-03 | `answered` | `answered` | Variación interanual (33,5 %) menos variación acumulada desde diciembre de 2025 (21,3 %): 12,2 puntos porcentuales | [q1] Variación interanual IPC nivel general nacional agosto 2026: 33,5 % · [q2] Variación acumulada del año IPC nivel general nacional agosto 2026: 21,3 % · [q3] Diferencia variación interanual − variación acumulada del… | ✅ | 1 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/0c997181-6d4c-4a6d-a7af-a0489f2378d5?poll=true) |
| ipc-04 | `cannot_answer` | `cannot_answer` | Falta: El informe llega hasta agosto de 2026; no hay datos de septiembre. | Falta: No hay datos para septiembre de 2026, solo agosto de 2026 | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/3b250d9d-dae3-4da7-aee8-051e232eb985?poll=true) |
| ipc-05 | `cannot_answer` | `cannot_answer` | Falta: El IPC se publica por regiones (GBA, Pampeana, Noreste, Noroeste, Cuyo, Patagonia), no por provincia; no se reemplaza por la región Pampeana. | Falta: No hay datos para la provincia de Córdoba, solo para regiones geográficas más amplias como Cuyo o Noroeste. | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/b3c0f747-8673-46f5-8b64-6c0ba0fa0680?poll=true) |
| ipc-06 | `partial` | `partial` | Variación mensual del IPC nivel general nacional, agosto de 2026: 1,7 % · Falta: No hay datos de septiembre de 2026. | [q1] Variación mensual del IPC nivel general nacional en agosto de 2026: 1,7 % · Falta: Datos de variación mensual del IPC nivel general nacional para septiembre de 2026 | ✅ | 0 | [ver](https://smith.langchain.com/o/f77ee408-f756-4ed9-a57a-ab9c0c8e5426/projects/p/ed1144b8-92a1-4679-9b91-36eaa85d3578/r/d315253a-9131-4c2d-8a4c-9e9e37f5b2ca?poll=true) |

## Detalle

### syn-01 — ¿Cuál fue el promedio simple de las variaciones interanuales de los ingresos totales del sector público entre 2019 y 2023?

- **Caso:** una tabla; promedio de variaciones interanuales (2020, 2021, 2022 y 2023)
- **Tablas usadas:** Cuadro 1 (esperadas: Cuadro 1) ✅
- **Tiempo:** 16.6 s

Respuesta del agente:

> El promedio simple de las variaciones interanuales de los ingresos totales del sector público entre 2019 y 2023 fue 84,88 %. Este dato se obtuvo de la tabla «Ingresos y gastos del sector público provincial, 2019-2023» en la página 1 del informe_sintetico.pdf, calculando las variaciones interanuales y luego su promedio simple.

### syn-02 — ¿Qué proporción de los gastos totales representó el gasto en ciencia y tecnología en cada año?

- **Caso:** una tabla; resultado por categoría
- **Tablas usadas:** Cuadro 1 (esperadas: Cuadro 1) ✅
- **Tiempo:** 13.9 s

Respuesta del agente:

> La proporción del gasto en ciencia y tecnología respecto al gasto total fue: 2019: 1,13 %; 2020: 1,07 %; 2021: 1,17 %; 2022: 1,23 %; 2023: 1,15 %. Estos datos se obtuvieron de la tabla «Ingresos y gastos del sector público provincial, 2019-2023» (informe_sintetico.pdf, página 1), calculando la relación entre el gasto en ciencia y tecnología y el gasto total para cada año.

### syn-03 — ¿Cuál fue el resultado financiero del sector público provincial en 2024?

- **Caso:** falta un período
- **Tiempo:** 4.6 s

Respuesta del agente:

> No puedo responder esta pregunta con las tablas indexadas.
>
> - ¿Cuál fue el resultado financiero del sector público provincial en 2024?: Dato para el año 2024 (La tabla Ingresos y gastos del sector público provincial cubre 2019-2023)

### syn-04 — ¿Qué departamento tuvo la tasa de desempleo más alta en 2023, y por cuánto superó al promedio provincial?

- **Caso:** falta un valor de comparación
- **Tablas usadas:** Cuadro 2 (esperadas: Cuadro 2) ✅
- **Tiempo:** 11.7 s

Respuesta del agente:

> El departamento con la tasa de desempleo más alta en 2023 fue Norte, con un 9,8 %, según la tabla «Tasa de desempleo por departamento, 2021-2023» (página 1 del informe_sintetico.pdf). No se pudo responder cuánto superó esta tasa al promedio provincial, ya que ese dato no está disponible en la tabla.

### syn-05 — ¿Cuál fue la producción de soja por habitante en cada departamento en 2023?

- **Caso:** multitabla; cambio de escala (miles de toneladas -> toneladas)
- **Tablas usadas:** Cuadro 4, Cuadro 5 (esperadas: Cuadro 4, Cuadro 5) ✅
- **Tiempo:** 14.4 s

Respuesta del agente:

> La producción de soja por habitante en 2023 fue: Capital 0,0165 t/hab; Norte 3,81 t/hab; Valle Alto 2,03 t/hab; Llanura 7,57 t/hab; Costa Sur 1,2 t/hab. Estos datos se obtuvieron usando las tablas «Producción de soja y maíz por departamento, campañas 2022 y 2023» y «Población y superficie por departamento, 2023» (ambas en página 2 del informe_sintetico.pdf), calculando el cociente entre producción total y población por departamento.

### syn-06 — ¿Cuál fue la tasa de desempleo de la provincia en 2023 calculada como el promedio de los departamentos ponderado por su población?

- **Caso:** multitabla; la pregunta define explícitamente cómo calcular el promedio (excepción a la regla del valor de comparación)
- **Tablas usadas:** Cuadro 2, Cuadro 5 (esperadas: Cuadro 2, Cuadro 5) ✅
- **Tiempo:** 13.1 s

Respuesta del agente:

> La tasa de desempleo de la provincia en 2023, calculada como el promedio ponderado por población de los departamentos, fue 7,49 %. Se usaron las tablas «Tasa de desempleo por departamento, 2021-2023» (página 1) y «Población y superficie por departamento, 2023» (página 2) del informe_sintetico.pdf para realizar el cálculo.

### syn-07 — ¿Qué porcentaje de los ingresos totales del sector público de 2023 representaron las exportaciones de ese año expresadas en pesos?

- **Caso:** conversión de unidades que requiere datos externos
- **Tiempo:** 5.4 s

Respuesta del agente:

> No puedo responder esta pregunta con las tablas indexadas.
>
> - Porcentaje que representaron las exportaciones de 2023 sobre los ingresos totales del sector público de 2023 expresados en pesos: Valor de exportaciones en pesos para 2023 (solo se tiene en miles de dólares) (La tabla Ingresos y gastos del sector público provincial cubre ingresos totales en millones de pesos para 2023. La tabla Exportaciones mensuales por grandes rubros cubre exportaciones en miles de dólares para 2023.)

### syn-08 — ¿Cuál fue el total de exportaciones de la provincia en 2023, en millones de dólares?

- **Caso:** tabla multipágina; suma de los 12 meses y cambio de escala (miles -> millones)
- **Tablas usadas:** Cuadro 6 (esperadas: Cuadro 6) ✅
- **Tiempo:** 10.8 s

Respuesta del agente:

> El total de exportaciones de la provincia en 2023 fue de 956,69 millones de dólares, según la tabla «Exportaciones mensuales por grandes rubros, 2022-2023» del informe_sintetico.pdf, páginas 2 y 3. Se sumaron los valores mensuales en miles de dólares y se convirtieron a millones para obtener este resultado.

### syn-09 — ¿Cuánto creció el salario real promedio del sector industria entre 2021 y 2023?

- **Caso:** ambigüedad nominal/real
- **Tiempo:** 4.7 s

Respuesta del agente:

> No puedo responder esta pregunta con las tablas indexadas.
>
> - Cuánto creció el salario real promedio del sector industria entre 2021 y 2023: No hay datos de inflación para 2021-2023, solo para 2025-2026. No se puede calcular salario real entre 2021 y 2023. (La tabla Variaciones del Índice de Precios al Consumidor por divisiones y regiones, agosto 2026 cubre variaciones IPC entre diciembre 2025 y agosto 2026.)

### syn-10 — ¿Cuántos turistas visitaron la provincia en 2023?

- **Caso:** ninguna tabla relacionada
- **Tiempo:** 4.2 s

Respuesta del agente:

> No puedo responder esta pregunta con las tablas indexadas.
>
> - Número total de turistas que visitaron la provincia en 2023: Número de turistas que visitaron la provincia en 2023 (No hay tabla con datos de turismo o visitantes en 2023)

### syn-11 — ¿Cuál fue la tasa de desempleo del departamento Río Seco en 2023?

- **Caso:** falta una entidad
- **Tiempo:** 4.6 s

Respuesta del agente:

> No puedo responder esta pregunta con las tablas indexadas.
>
> - Cuál fue la tasa de desempleo del departamento Río Seco en 2023: No hay datos para el departamento Río Seco en la tabla de tasa de desempleo por departamento. (La tabla Tasa de desempleo por departamento cubre 2021-2023 para los departamentos Capital, Norte, Valle Alto, Llanura y Costa Sur.)

### ind-01 — ¿Qué porcentaje de las exportaciones argentinas acumuladas hasta agosto de 2026 se originó en la provincia de Santa Fe?

- **Caso:** una tabla real; cociente entre una fila y el total (13.746 / 67.248)
- **Tablas usadas:** Cuadro 1, Cuadro 10 (esperadas: Cuadro 10) ✅
- **Tiempo:** 13.9 s

Respuesta del agente:

> El porcentaje de las exportaciones argentinas acumuladas hasta agosto de 2026 que se originó en la provincia de Santa Fe es 20,44 %. Este dato se obtuvo de las tablas «Intercambio comercial argentino de bienes, enero-agosto 2026 y año 2025» (página 7) y «Origen de las exportaciones por regiones económicas y grandes rubros, acumulado hasta agosto de 2026» (página 30), calculando la proporción de las exportaciones de Santa Fe respecto al total nacional.

### ind-02 — ¿Cuál fue el saldo comercial promedio mensual entre enero y agosto de 2026?

- **Caso:** una tabla real; promedio de 8 meses
- **Tablas usadas:** Cuadro 1 (esperadas: Cuadro 1) ✅
- **Tiempo:** 11.6 s

Respuesta del agente:

> El saldo comercial promedio mensual entre enero y agosto de 2026 fue de 2.281,25 millones de USD, según la tabla «Intercambio comercial argentino de bienes, enero-agosto 2026 y año 2025» (indec_ica.pdf, página 7). Este valor se obtuvo calculando el promedio mensual del saldo comercial para esos meses.

### ind-03 — ¿Qué porcentaje de las exportaciones totales de agosto de 2026 correspondió al sector automotriz?

- **Caso:** multitabla real; exportaciones automotrices (878) sobre el total del mes (8.883)
- **Tablas usadas:** Cuadro 3, Cuadro 7
- **Qué falló:** estado `cannot_answer`; falta Exportaciones del sector automotriz / exportaciones totales, agosto de 2026 = 9.884
- **Tiempo:** 12.0 s

Respuesta del agente:

> No puedo responder esta pregunta con las tablas indexadas.
>
> - Porcentaje de las exportaciones totales de agosto de 2026 que correspondió al sector automotriz: No se encontró fila total de exportaciones en tabla 18d7b83789e2f178-t03

### ind-04 — ¿Cuánto exportó la Argentina en septiembre de 2026?

- **Caso:** falta un período (la fila existe, pero sin dato para 2026)
- **Tiempo:** 4.8 s

Respuesta del agente:

> No puedo responder esta pregunta con las tablas indexadas.
>
> - Cuánto exportó la Argentina en septiembre de 2026: Dato de exportaciones para septiembre de 2026 (La tabla Intercambio comercial argentino de bienes, enero-agosto 2026 y año 2025 cubre hasta agosto de 2026 y el año 2025, no incluye septiembre de 2026.)

### ind-05 — ¿Cuánto exportó la región Patagonia en agosto de 2026 y cuánto creció respecto de agosto de 2025?

- **Caso:** falta un período para una parte de la pregunta
- **Tablas usadas:** Cuadro 9 (esperadas: Cuadro 9) ✅
- **Tiempo:** 12.4 s

Respuesta del agente:

> En agosto de 2026, la región Patagonia exportó 1.469 millones de USD, según la tabla «Origen de las exportaciones por regiones y provincias, agosto 2026» (indec_ica.pdf, página 29). No se pudo calcular el crecimiento respecto de agosto de 2025 porque falta el dato de exportaciones de Patagonia en ese mes.

### ipc-01 — ¿Cuál fue la variación mensual del IPC nivel general a nivel nacional en agosto de 2026?

- **Caso:** una tabla real; dato directo
- **Tablas usadas:** Cuadro 1 (esperadas: Cuadro 1) ✅
- **Tiempo:** 11.2 s

Respuesta del agente:

> La variación mensual del IPC nivel general a nivel nacional en agosto de 2026 fue de 1,7 %. Este dato se obtuvo de la tabla «Variación mensual del IPC por divisiones y regiones, agosto 2026» en la página 5 del documento indec_ipc.pdf, extrayendo directamente el valor correspondiente a ese mes y nivel.

### ipc-02 — En agosto de 2026, ¿qué región tuvo la mayor variación mensual en Vivienda, agua, electricidad, gas y otros combustibles, y por cuántos puntos superó al dato nacional?

- **Caso:** una tabla real; máximo entre regiones y diferencia con un valor de comparación que sí está en la tabla
- **Tablas usadas:** Cuadro 1 (esperadas: Cuadro 1) ✅
- **Qué falló:** estado `partial`; falta Diferencia con la variación nacional (2,8 %) = 1.2
- **Tiempo:** 17.6 s

Respuesta del agente:

> En agosto de 2026, la región Noreste tuvo la mayor variación mensual en Vivienda, agua, electricidad, gas y otros combustibles, con un 4 %, según la tabla «Variación mensual del IPC por divisiones y regiones, agosto 2026» (página 5). No se puede determinar cuántos puntos superó esta variación al dato nacional porque falta el dato nacional.

### ipc-03 — ¿Cuántos puntos porcentuales de diferencia hubo entre la variación interanual y la variación acumulada del año del IPC nivel general nacional en agosto de 2026?

- **Caso:** multitabla real; cada medida está en un cuadro distinto
- **Tablas usadas:** Cuadro 3, Cuadro 14 (esperadas: Cuadro 3, Cuadro 2) ❌
- **Tiempo:** 23.2 s

Respuesta del agente:

> La diferencia entre la variación interanual (33,5 %) y la variación acumulada del año (21,3 %) del IPC nivel general nacional en agosto de 2026 fue de 12,2 puntos porcentuales. Esta información se obtuvo de las tablas «Variación anual del Índice de Precios al Consumidor por divisiones y regiones, agosto 2026» (página 6) y «Variaciones del IPC agosto 2026 respecto a diciembre 2025 por región y categoría» (página 10) del documento indec_ipc.pdf, calculando la resta directa entre ambos valores.

### ipc-04 — ¿Cuál fue la variación mensual del IPC en septiembre de 2026?

- **Caso:** falta un período
- **Tiempo:** 5.1 s

Respuesta del agente:

> No puedo responder esta pregunta con las tablas indexadas.
>
> - Cuál fue la variación mensual del IPC en septiembre de 2026: No hay datos para septiembre de 2026, solo agosto de 2026 (La tabla Variación mensual del IPC por divisiones y regiones, agosto 2026 cubre agosto de 2026.)

### ipc-05 — ¿Cuál fue la variación mensual del IPC en la provincia de Córdoba en agosto de 2026?

- **Caso:** falta una entidad (existe una entidad cercana que no se debe usar)
- **Tiempo:** 6.7 s

Respuesta del agente:

> No puedo responder esta pregunta con las tablas indexadas.
>
> - Cuál fue la variación mensual del IPC en la provincia de Córdoba en agosto de 2026: No hay datos para la provincia de Córdoba, solo para regiones geográficas más amplias como Cuyo o Noroeste. (Las tablas cubren regiones geográficas amplias (Cuyo, Noroeste) pero no la provincia de Córdoba específicamente.)

### ipc-06 — ¿Cuál fue la variación mensual del IPC nivel general nacional en agosto y en septiembre de 2026?

- **Caso:** falta un período para una parte de la pregunta
- **Tablas usadas:** Cuadro 1 (esperadas: Cuadro 1) ✅
- **Tiempo:** 12.8 s

Respuesta del agente:

> La variación mensual del IPC nivel general nacional en agosto de 2026 fue 1,7 % (según la tabla «Variación mensual del IPC por divisiones y regiones, agosto 2026», página 5). No se pudo responder la variación para septiembre de 2026 porque no se dispone de datos para ese mes.

