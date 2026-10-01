# Iteración 03 — Extracción determinística

**Estado**: COMPLETA (todos los criterios PASS, incluidos los [usuario]).
**Commit**: lo hace el alumno con el mensaje `Extracción determinística de tablas: normalización, unión multipágina, contexto y avisos`. SHA: `16a5d5c74311898da8180f205f333a22328084ab`.

## Resultados de criterios
| Criterio | Comando / test | Resultado |
|---|---|---|
| VC-001 | `tests/ingestion/test_loader.py::test_vc001_loads_text_of_every_page` | PASS |
| VC-002 | `test_loader.py::test_vc002_image_only_pdf_has_no_text_layer` | PASS |
| VC-002b (base) | `test_extract.py::test_vc002b_text_only_pdf_has_no_tables` | PASS |
| VC-002c | `test_loader.py::test_vc002c_unopenable_files` (error tipado; UI en Iter. 7) | PASS |
| VC-003, VC-004 | `test_extract.py::test_vc003_vc004_shapes_columns_and_values[*]`, `test_vc004_two_level_header` | PASS (6/6 tablas idénticas a `sample_truth.json`, valores incluidos) |
| VC-005, VC-005b | `test_normalize.py::test_vc005_*`, `test_vc005b_*`, `test_extract.py::test_indec_dash_is_zero_and_units_in_header` | PASS |
| VC-006, VC-006b | `test_normalize.py::test_vc006_*`, `test_vc006b_*` | PASS |
| VC-007 | `test_extract.py::test_vc007_multipage_table_is_merged`, `test_continuation_without_header_is_merged` | PASS |
| VC-008, VC-008b | `test_vc008_different_column_counts_are_not_merged`, `test_vc008b_indec_consecutive_tables_are_not_merged` | PASS |
| VC-009, VC-009b | `test_vc009_*`, `test_vc009b_*`, `test_empty_table_is_skipped_with_warning` | PASS |
| VC-009c | `test_vc009c_indec_numbered_tables_are_found`, `test_vc009c_indec_charts_and_infographics_are_discarded` | PASS |
| VC-009d | `test_vc009d_horizontal_rules_only_table` | PASS |
| VC-010 | `tests/ingestion/test_context.py::test_vc010_context_matches_truth[*]` | PASS (6/6) |
| Suite completa | `uv run pytest -q` | PASS (104 passed, ~15 s) |
| Lint / tipos | `uv run ruff check .`, `uv run mypy agents services` | PASS |
| [usuario] diagnóstico INDEC + suite en Windows | `uv run python -m agents.ingestion.extract data/sample_pdfs/indec_ica.pdf`, `uv run pytest -q` | PASS: 11 tablas idénticas a las del contenedor; 104 passed. Diferencia menor: en el Cuadro 5 dos columnas salen sin el sufijo `\| %` en Windows/Python 3.14 (no afecta tests) |

## Archivos
Agregados: `agents/ingestion/{pdf_loader,extract,normalize,merge,context}.py`, `tests/ingestion/{__init__,conftest,test_loader,test_extract,test_normalize,test_context}.py`, `data/sample_pdfs/indec_ica.pdf`, este registro.
Modificados: `pyproject.toml` (mypy `untyped_calls_exclude = ["pymupdf"]`), `docs/SPEC.md` (v0.3), `docs/SPEC-plan.md` (VCs nuevos de la Iteración 3), `CONTEXT.md`, `DECISIONS.md`.
Borrados: ninguno.

## Desvíos respecto del plan
- Spec v0.3 con reglas nuevas que salieron del PDF real (FR-005 convención de "-", FR-007 epígrafe/Fuente, FR-008b, FR-003 tablas con solo líneas horizontales). El "8 % superior/inferior" de un primer borrador de v0.3 se eliminó (D-014).
- Los VCs sobre INDEC (VC-008b, VC-009c) quedaron automatizados en vez de depender solo del criterio [usuario].

## Problemas encontrados
- Las celdas de tabla son bloques de texto cortos y bajaban la "letra del cuerpo"; ahora se calcula con bloques de ≥ 60 caracteres.
- Las líneas del Cuadro 2 (grilla) y del Cuadro 3 (líneas horizontales) tienen el mismo ancho y se agrupaban juntas; ahora se excluyen las líneas que caen dentro de tablas ya detectadas.
- Anclar columnas en el encabezado falla con encabezados alineados a la izquierda y números a la derecha: se usan los blancos de los datos (D-010).
- Ver limitaciones en CONTEXT.md (Cuadro 3 de INDEC).

## For the next iteration
- Pipeline de extracción para el grafo: `read_pdf` → `extract_tables` → `merge_continuations` → por tabla `collect_context(t, loaded, tables)` y `normalize_table(t, loaded)`. Los avisos son `ExtractionWarning` con `message` listo para la UI.
- `normalize_table` devuelve `notes` que deben ir a `TableMetadata.notes` (además de lo que agregue el LLM).
- `RawTable` no es serializable a JSON tal cual (tuplas, `None`); en el estado del grafo conviene guardar dicts (`dataclasses.asdict`) o persistir los DataFrames por `table_id` (decisión de la Iteración 4).
- El orden de las tablas lógicas que devuelve `merge_continuations` es el orden de lectura: úsalo para `table_id = {doc_id}-t{NN}` (BR-005).
