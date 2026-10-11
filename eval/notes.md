## Trazas representativas

Links públicos de LangSmith (se abren sin cuenta):

- **Respuesta completa con dos tablas del PDF real** (`ind-03`, peso del sector automotriz en las exportaciones de agosto de 2026): https://smith.langchain.com/public/2183c165-d3cf-4e3b-9412-a88335229d5a/r/8c6c0931-9f58-49dc-8e36-35e389bf9951
- **Respuesta parcial** (`syn-04`: responde qué departamento tuvo más desempleo y explica que ninguna tabla informa el promedio provincial, sin calcularlo): https://smith.langchain.com/public/4ade60ee-1d51-48d7-8b55-30f9750d0151/r/50298fd4-00bd-4e28-8fcd-1797ff0d8ce0
- **Ingesta completa del PDF real** (`indec_ica.pdf`: cada nodo del grafo de Ingesta aparece como un span —carga, extracción, unión entre páginas, contexto, enriquecimiento con el LLM (una llamada por tabla, en paralelo), validación e indexación en Pinecone—; 11 tablas indexadas): https://smith.langchain.com/public/6745c41c-325b-4c47-a6e2-f46ed862311b/r
- **Con reintentos:** en la corrida final ninguna pregunta necesitó reintentar el código, así que no hay traza de este tipo en el reporte. Durante el desarrollo sí hubo reintentos reales: el filtro de seguridad rechazó un programa que usaba `exit()` y otro que llamaba a `.rename` (que se parecía a una operación de archivos), y en un tercer caso el código devolvió un texto donde iba un número; en los tres el segundo programa, generado con el error del primero, respondió bien. Los tests del grafo verifican ese ciclo (un fallo seguido de un acierto, y fallos hasta agotar los reintentos).

## Análisis

**Resultado final: 16/16.** Todas las preguntas obtienen el estado esperado y, cuando hay números, el valor esperado con tolerancia de 0,5 %. Las 6 preguntas que no se pueden responder explican qué dato falta y qué cubre la tabla más parecida, sin dar números calculados.

**Cómo se llegó.** El set se corrió varias veces durante el desarrollo y cada falla se corrigió en el sistema, no en las preguntas (salvo una, ver abajo):

- Primeras corridas sobre el PDF sintético (8/11 estados correctos): el chequeo automático de cobertura buscaba textual períodos como "todos los años disponibles" y entidades como "provincia", y descartaba preguntas que sí tenían datos; y en `syn-04` el modelo reemplazó el promedio provincial por el promedio simple de los departamentos. Se acotó el chequeo y se agregó uno específico para valores de comparación.
- Después, con los estados bien, aparecieron errores de valor: proporciones devueltas como fracción (0,0113 en vez de 1,13 %) y una parte sin datos que el código calculó igual dentro de otra subpregunta. Se exigió porcentaje y se dejó de pasarle al generador de código la pregunta completa: solo recibe las partes que tiene que calcular y, aparte, las que no.
- `syn-01` decía "crecimiento interanual promedio", que el modelo leyó como tasa compuesta (78,55 %) y no como promedio de las variaciones (84,88 %). Las dos lecturas son válidas, así que se reformuló la pregunta.
- Primera corrida con las preguntas de INDEC: 14/16. `ind-01` e `ind-02` dieron "no se puede responder" porque el chequeo de períodos buscaba "enero 2026" como frase, cuando en el cuadro de INDEC el mes es una fila y el año una columna. Ahora el mes y el año se verifican por separado.

**Qué tener en cuenta al leer el 16/16.**

- Son 16 preguntas y el sistema se ajustó mirándolas, así que el resultado mide sobre todo que los casos previstos funcionan; no estima la tasa de acierto sobre preguntas nuevas. Las 5 preguntas de INDEC se escribieron después de cerrar el Analista y fallaron 2 en su primera corrida, lo que da una idea más realista.
- La corrida final reutilizó muchas respuestas del modelo guardadas en la caché local (por eso tardó 68 s). Con temperatura 0 las respuestas son casi siempre iguales, pero una corrida sin caché puede variar en algún caso.
- Los chequeos automáticos de cobertura se basan en palabras (años, meses, nombres de filas, "promedio provincial"). Una pregunta que exprese lo mismo con otras palabras depende solo del criterio del modelo.
