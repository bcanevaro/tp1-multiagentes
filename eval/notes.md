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
