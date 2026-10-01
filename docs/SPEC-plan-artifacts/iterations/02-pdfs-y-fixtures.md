# Iteración 02 — PDF sintético, fixtures de prueba y preguntas del PDF sintético

**Estado**: código completo y verificado en el contenedor; **pendiente el criterio [usuario]** (el alumno abre el PDF y corre los tests en Windows).
**Commit**: lo hace el alumno con el mensaje `PDF sintético reproducible, fixtures de borde y preguntas de evaluación del PDF sintético`. SHA: _pendiente_.

## Resultados de criterios
| Criterio | Comando | Resultado |
|---|---|---|
| Generación de PDF y fixtures | `uv run python scripts/make_sample_pdf.py && uv run python scripts/make_test_fixtures.py /tmp/fx` | PASS |
| Reproducibilidad | `tests/test_sample_pdf.py::test_generation_is_reproducible` (y md5 idéntico en dos corridas en Linux) | PASS |
| Todas las páginas con texto; tabla larga en 2 páginas | `test_every_page_has_text`, `test_has_multipage_table` (exportaciones en [2, 3]) | PASS |
| Cobertura de la consigna §9.2 en las preguntas | `tests/test_questions.py::test_covers_assignment_minimums` | PASS |
| Valores esperados == cálculo desde `sample_data.py` | `tests/test_questions.py::test_syn0*` | PASS |
| Propiedades de cada PDF de borde | `tests/test_edge_pdfs.py` | PASS |
| Suite completa | `uv run pytest -q` | PASS (46 passed) |
| Lint / tipos | `uv run ruff check .`, `uv run mypy agents services` | PASS |
| [usuario] PDF legible y razonable para la demo | el alumno lo abre | _pendiente_ |

## Archivos
Agregados: `scripts/sample_data.py`, `scripts/make_sample_pdf.py`, `scripts/make_test_fixtures.py`, `data/sample_pdfs/informe_sintetico.pdf`, `tests/fixtures/sample_truth.json`, `tests/test_sample_pdf.py`, `tests/test_edge_pdfs.py`, `tests/test_questions.py`, `eval/questions.yaml`, `docs/SPEC-plan-artifacts/iterations/02-pdfs-y-fixtures.md`.
Modificados: `tests/conftest.py` (fixture `edge_pdfs`), `.gitignore` (`tests/fixtures/generated/`), `.env.example` (modelos, D-007), `services/config.py`, `scripts/check_services.py`, `tests/test_config.py` (arreglos de la iteración 1), `docs/SPEC-plan-artifacts/{CONTEXT,DECISIONS}.md`.
Borrados: ninguno.

## Desvíos respecto del plan
- El PDF quedó en 3 páginas (el plan permitía ≤ 10).
- Los PDFs de borde no se versionan (D-008); el plan decía "genera en tests/fixtures/".
- Se agregaron dos fixtures no listadas en el plan: `continuacion_sin_encabezado.pdf` (segunda variante de FR-007) y `tabla_vacia.pdf` (tabla > 90 % vacía de FR-008).

## Problemas encontrados
- `Path.relative_to(ROOT)` fallaba al generar en un tmp: el truth guarda la ruta relativa solo si está dentro del repo.
- PyMuPDF sugiere instalar `pymupdf_layout`; no se usa (no es necesario por ahora).

## For the next iteration
- Usá `tests/fixtures/sample_truth.json` como verdad: `columns` son los nombres aplanados esperados (encabezado de 2 niveles → `"Soja | 2022"`), `values` los valores ya normalizados (`null` = s/d; porcentajes en escala 0–100; `$` sin símbolo).
- Ojo con lo que ya se observó de `find_tables()` (ver Known gaps en CONTEXT.md): epígrafe tomado como encabezado externo, el Cuadro 3 sin bordes verticales no se detecta con la estrategia por defecto, encabezados con `\n`.
- Las fixtures de borde están en `edge_pdfs[nombre]`; `FIXTURES` en `scripts/make_test_fixtures.py` dice qué espera cada una. La contraseña del PDF protegido es `secreta`.
