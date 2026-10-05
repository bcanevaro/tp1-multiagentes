# Iteración 09 — Documentación final y verificación de punta a punta

**Estado**: PENDIENTE de los criterios [usuario].
**Commit**: lo hace el alumno con el mensaje `Documentación final: README, evaluación y arquitectura`. SHA: _pendiente_.

## Resultados de criterios
| Criterio | Verificación | Resultado |
|---|---|---|
| `README.md`, `EVALUATION.md` y `docs/ARCHITECTURE.md` existen y no referencian spec, plan, VCs, FRs ni iteraciones | `tests/test_docs.py::test_docs_do_not_reference_internal_artifacts[*]` (patrón `SPEC\|plan-artifacts\|VC-\|FR-\|BR-\|Iteration`) | PASS |
| Diagramas Mermaid exportados con `draw_mermaid()` y al día | `scripts/export_graphs.py` → `docs/graphs/*.mmd`; `tests/test_docs.py::test_readme_diagrams_match_the_graphs` | PASS |
| Todas las variables de `.env.example` documentadas | `tests/test_docs.py::test_readme_documents_every_env_variable` | PASS |
| Cada decisión de `DECISIONS.md` reflejada o marcada interna | tabla «Decisiones» abajo | PASS |
| Suite completa | `uv run pytest -q` | PASS (275 passed, 5 skipped = tests Docker, en el contenedor) |
| Lint / tipos | `uv run ruff check .`, `uv run mypy agents services ui eval app.py` | PASS |
| [usuario] VC-070: repo limpio siguiendo el README (`uv sync`, `.env`, imagen del sandbox, `pytest`, `streamlit run`, ingesta del sintético) y búsqueda de claves en el historial | — | _pendiente_ |
| [usuario] link del video en el README | — | _pendiente_ |

## Decisiones
| Decisión | Dónde quedó documentada |
|---|---|
| D-001 layout en la raíz | README «Estructura del repositorio» |
| D-002 cachés propias | README «Servicios y configuración»; ARCHITECTURE §4 |
| D-003 `LLM_STRUCTURED_METHOD` | README (tabla del `.env` y «Servicios y configuración») |
| D-004 `.env` al entorno | ARCHITECTURE §4 |
| D-005 commits del alumno | Interna (proceso) |
| D-006 implementación en la sesión principal | Interna (proceso) |
| D-007 modelos | README «Servicios y configuración» y tabla del `.env` |
| D-008, D-009 PDF sintético | README «Evaluación»; ARCHITECTURE §6 |
| D-010 a D-014 extracción | README «Extracción» |
| D-015 a D-019 ingesta | README «Ingesta»; ARCHITECTURE §1 |
| D-020 a D-022 sandbox | README «El código generado corre aislado»; ARCHITECTURE §3 |
| D-023 servicios inyectados | ARCHITECTURE (introducción) |
| D-024, D-025 modelo de código, formato argentino | README «Analista» |
| D-026, D-029, D-039 chequeos de cobertura | README «Analista»; ARCHITECTURE §2; EVALUATION «Análisis» |
| D-027 salida completa por subpregunta | ARCHITECTURE §2 |
| D-028 recuperación y almacén local | README «Limitaciones» y «Solución de problemas»; ARCHITECTURE §2 |
| D-030 porcentajes y partes sin datos fuera del código | README «Analista»; EVALUATION «Análisis» |
| D-031, D-032 extras y pestañas bloqueadas | README «Uso» |
| D-033, D-034 acceso a servicios y errores | README «Servicios y configuración» y «Ingesta»; ARCHITECTURE §1 y §4 |
| D-035 a D-038 evaluación | README «Evaluación»; ARCHITECTURE §5; EVALUATION |

## Archivos
Agregados: `docs/ARCHITECTURE.md`, `docs/graphs/{ingestion,analyst}.mmd`, `scripts/export_graphs.py`, `eval/notes.md`, `tests/test_docs.py`, este registro.
Modificados: `README.md` (completo), `EVALUATION.md` (corrida final del alumno + trazas y análisis desde `eval/notes.md`, sin referencias internas), `eval/run_local.py` (incluye `eval/notes.md` en el reporte; encabezado sin referencias internas), `eval/questions.yaml` (textos de `syn-01` y `syn-06` sin referencias internas), `tests/eval/test_run_local.py`, `CONTEXT.md`, `iterations/08-evaluacion.md` (COMPLETA con SHA).
Borrados: ninguno.

## Desvíos respecto del plan
- `EVALUATION.md` lo genera `eval.run_local`; la parte escrita a mano (trazas y análisis) vive en `eval/notes.md` y el script la copia en cada reporte, así una nueva corrida no la pierde.
- Se agregó `tests/test_docs.py` para que la regla «sin referencias internas» y los diagramas se verifiquen solos.
