# Iteración 04 — Agente de Ingesta completo

**Estado**: COMPLETA (todos los criterios PASS, incluidos los [usuario]).
**Commit**: lo hace el alumno con el mensaje `Agente de Ingesta: enriquecimiento con LLM, ciclo de validación, almacén Parquet y Pinecone idempotente`. SHA: `1e62f66d82e2a64293adb068a4eb7eeb830a39bf`.

## Resultados de criterios
| Criterio | Test | Resultado |
|---|---|---|
| VC-002b | `tests/ingestion/test_graph.py::test_vc002b_text_only_pdf_does_not_call_llm` | PASS |
| VC-011 | `test_validate.py::test_vc011_annotation_is_valid_table_metadata` | PASS |
| VC-012 | `test_validate.py::test_vc012_missing_column_is_br001`, `test_br001_renamed_column` | PASS |
| VC-013 | `test_validate.py::test_vc013_row_header_column_must_exist` | PASS |
| VC-014, VC-014b | `test_validate.py::test_vc014_generic_name[*]`, `test_vc014b_description_sentences[*]` | PASS |
| VC-015 | `test_validate.py::test_vc015_numeric_column_needs_unit` | PASS |
| VC-016 | `test_graph.py::test_vc016_retry_only_invalid_tables` | PASS |
| VC-017 | `test_graph.py::test_vc017_retries_exhausted_table_is_skipped` | PASS |
| VC-018 | `test_graph.py::test_vc018_parquet_and_json_per_table` | PASS |
| VC-019 | `test_graph.py::test_vc019_one_vector_per_table_with_spec_metadata` | PASS |
| VC-020 | `test_graph.py::test_vc020_reingest_same_content_other_name` | PASS |
| VC-021 | `test_graph.py::test_vc021_stale_tables_are_removed` | PASS |
| VC-065c (lógica) | `test_graph.py::test_vc065c_dimension_mismatch_writes_nothing` | PASS |
| NFR-006 | `test_graph.py::test_nfr006_metadata_size_limit_with_huge_table` | PASS |
| FR-018 (base) | `test_graph.py::test_fr018_stream_reports_each_node_in_order` | PASS |
| FR-002/019b por el grafo | `test_graph.py::test_unreadable_pdfs_end_with_message[*]` | PASS |
| Smoke INDEC con fakes | script ad hoc: 11 tablas indexadas, metadatos ≤ 2,1 KB, 11 s | PASS |
| Suite completa | `uv run pytest -q` | PASS (135 passed, ~24 s) |
| Lint / tipos | `uv run ruff check .`, `uv run mypy agents services` | PASS |
| [usuario] ingesta real del PDF sintético ≤ 3 min (NFR-008) | `uv run python -m agents.ingestion.cli data/sample_pdfs/informe_sintetico.pdf` | PASS: 40,5 s (enrich 9,5 s + 1 reintento 5,3 s; persist 16,5 s incluye crear el índice) |
| [usuario] re-ingesta: mismos IDs y cantidad (VC-020 real) | mismo comando dos veces | PASS: 6 vectores `0ca85a35fc1876be-t01…t06` en ambas |
| [usuario] caché: segunda corrida sin llamadas nuevas (NFR-009) | `enrich` de la segunda corrida | PASS: 0,1 s; corrida total 3,3 s |
| [usuario] traza `ingest:informe_sintetico.pdf` con un span por nodo (VC-066) | LangSmith | PASS (captura: nodos, condicionales y 6 `ChatOpenAI gpt-4.1-mini` dentro de `enrich`) |
| [usuario] ingesta de `indec_ica.pdf` | CLI | PASS: 11 tablas, 1 reintento, 33,2 s, 11 vectores |
| VC-015b (BR-004b, agregado tras la ingesta real) | `test_validate.py::test_vc015b_*` | PASS (137 passed) |
| [usuario] re-ingesta tras BR-004b: el cuadro de salarios ya no dice "corrientes" | CLI | PASS (descripción sin "corrientes"); 137 passed en Windows |

## Archivos
Agregados: `agents/ingestion/{schemas,validate,prompts,graph,cli}.py`, `services/{table_store,vector_index}.py`, `tests/ingestion/{fakes,test_validate,test_graph}.py`, este registro.
Modificados: `services/config.py` y `.env.example` (`PINECONE_CLOUD`, `PINECONE_REGION`), `CONTEXT.md`, `DECISIONS.md`.
Borrados: ninguno.

## Desvíos respecto del plan
- El nodo `collect_context` también normaliza (necesita las tablas ya unidas).
- Variables nuevas `PINECONE_CLOUD`/`PINECONE_REGION` (el plan gratuito de Pinecone solo admite aws/us-east-1).
- El CLI cuenta los vectores del documento en Pinecone al final (para verificar FR-016 sin entrar a la consola).

## Observaciones de la ingesta real
- En las dos corridas, 1 de 6 tablas falló la validación en el primer intento y pasó en el reintento: el ciclo funciona con el LLM real.
- El LLM describió el cuadro de salarios como "pesos corrientes" sin que el PDF lo diga → spec v0.4, BR-004b (decisión del alumno: prompt + regla automática).
- Metadatos de INDEC de buena calidad (detectó la nota metodológica del Cuadro 9). En el Cuadro 6 el LLM eligió `columna_1` (códigos NCM y rubros) como encabezado de fila.

## Problemas encontrados
- Bucle infinito en `pinecone_metadata` al recortar listas de un solo elemento (detectado por el test de NFR-006): ahora achica la lista más pesada con más de un elemento y, si ninguna se puede achicar, lanza error.
- pandas 3 lee los textos del Parquet como dtype `str`; `TableDraft.to_dataframe()` usa el mismo dtype.
- Pinecone solo admite listas de strings en metadatos: `pages` se guarda como `["2", "3"]`.

## For the next iteration
- El Analista lee: `services.vector_index.get_vector_index().query(vector, top_k)` → `Match(id, score, metadata)`; los datos con `TableStore(settings.data_dir).load_df(table_id)` y los metadatos completos con `load_metadata(table_id)` (incluye `columns[].unit/value_type`, `periods_covered`, `entities_covered`, `row_headers`, `notes`).
- Para el sandbox: los Parquet están en `DATA_DIR/tables/{table_id}.parquet`.
