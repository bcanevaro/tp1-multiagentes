"""Agente de Ingesta: StateGraph de LangGraph (spec §7.7).

    load_pdf ─(archivo inválido o sin texto)→ END
    load_pdf → extract_tables ─(0 tablas)→ END
    extract_tables → merge_continuations → collect_context → enrich → validate
    validate ─(tablas inválidas con reintentos disponibles)→ enrich
    validate ─(resto)→ persist_and_index → END

El estado es JSON (modelos Pydantic y tipos simples): se ve completo en LangSmith y no lleva
DataFrames (decisión D-015). Los servicios externos (LLM, embeddings, índice, almacén) se
inyectan con `IngestionServices`, así los tests usan fakes.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.embeddings import Embeddings
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from agents.ingestion.context import collect_context
from agents.ingestion.extract import RawTable, extract_tables
from agents.ingestion.merge import merge_continuations
from agents.ingestion.normalize import normalize_table
from agents.ingestion.pdf_loader import (
    LoadedPdf,
    NoTextLayerError,
    PdfOpenError,
    compute_doc_id,
    load_pdf,
    open_pdf,
)
from agents.ingestion.prompts import build_messages
from agents.ingestion.schemas import (
    TableAnnotation,
    TableContextData,
    TableDraft,
    TableMetadata,
)
from agents.ingestion.validate import build_metadata, table_id_for, validate_annotation
from services.config import Settings, get_settings
from services.table_store import TableStore
from services.tracing import run_config
from services.vector_index import (
    IndexDimensionError,
    VectorIndex,
    VectorRecord,
    embedding_text,
    get_vector_index,
    pinecone_metadata,
)

NO_TABLES_MESSAGE = "No se detectaron tablas en el PDF"
NONE_VALID_MESSAGE = "Ninguna tabla pasó la validación de metadatos; no se indexó nada"

# (tabla, errores del intento anterior) -> anotación o excepción, en el mismo orden.
Annotator = Callable[
    [list[tuple[TableDraft, list[str]]], str, RunnableConfig | None],
    list[TableAnnotation | Exception],
]


@dataclass
class IngestionServices:
    annotate: Annotator
    embeddings_factory: Callable[[], Embeddings]
    index_factory: Callable[[], VectorIndex]
    store: TableStore
    max_retries: int = 2
    index_name: str = ""


_SERVICE_PACKAGES = ("openai", "httpx", "httpcore")


def is_service_error(exc: BaseException) -> bool:
    """Error del proxy (conexión, autenticación, modelo caído…), no de formato de la respuesta.

    Se mira toda la jerarquía de la clase: langchain-openai envuelve los errores de `openai` en
    sus propias clases (p. ej. `OpenAIInvalidRequestError`, subclase de `openai.BadRequestError`).
    """
    return any(cls.__module__.split(".")[0] in _SERVICE_PACKAGES for cls in type(exc).__mro__)


def llm_annotator(settings: Settings) -> Annotator:
    """Anotador real: una llamada con salida estructurada por tabla, en paralelo."""

    def annotate(
        jobs: list[tuple[TableDraft, list[str]]], pdf_name: str, config: RunnableConfig | None
    ) -> list[TableAnnotation | Exception]:
        from services.llm import get_chat_model, with_structured

        model = with_structured(get_chat_model(settings), TableAnnotation, settings)
        inputs = [build_messages(draft, pdf_name, errors) for draft, errors in jobs]
        batch_config: RunnableConfig = {**(config or {}), "max_concurrency": 4}
        results = model.batch(inputs, config=batch_config, return_exceptions=True)
        return [
            r if isinstance(r, TableAnnotation | Exception) else TypeError(repr(r)) for r in results
        ]

    return annotate


def default_services(settings: Settings | None = None) -> IngestionServices:
    settings = settings or get_settings()
    from services.llm import get_embeddings

    return IngestionServices(
        annotate=llm_annotator(settings),
        embeddings_factory=lambda: get_embeddings(settings),
        index_factory=lambda: get_vector_index(settings),
        store=TableStore(settings.data_dir),
        max_retries=settings.INGEST_MAX_RETRIES,
        index_name=settings.PINECONE_INDEX_NAME or "",
    )


# --------------------------------------------------------------------------------------
# Estado
# --------------------------------------------------------------------------------------


class RawTableData(BaseModel):
    """`RawTable` en versión JSON."""

    pages: list[int]
    bbox: list[float]
    last_bbox: list[float]
    header_rows: list[list[str | None]]
    rows: list[list[str]]
    strategy: str

    @classmethod
    def from_raw(cls, t: RawTable) -> RawTableData:
        return cls(pages=t.pages, bbox=list(t.bbox), last_bbox=list(t.last_bbox),
                   header_rows=t.header_rows, rows=t.rows, strategy=t.strategy)  # fmt: skip

    def to_raw(self) -> RawTable:
        b, lb = self.bbox, self.last_bbox
        return RawTable(pages=self.pages, bbox=(b[0], b[1], b[2], b[3]),
                        last_bbox=(lb[0], lb[1], lb[2], lb[3]), header_rows=self.header_rows,
                        rows=self.rows, strategy=self.strategy)  # fmt: skip


class IngestionState(TypedDict, total=False):
    pdf_path: str
    pdf_name: str
    doc_id: str
    page_count: int
    raw_tables: list[RawTableData]
    drafts: list[TableDraft]
    candidates: dict[int, TableAnnotation]  # última respuesta del LLM por tabla (sin validar)
    annotations: dict[int, TableAnnotation]  # anotaciones válidas
    pending_errors: dict[int, list[str]]  # errores del último intento de cada tabla pendiente
    attempts: dict[int, int]  # llamadas al LLM por tabla
    failed: list[int]  # tablas que agotaron los reintentos (FR-013)
    indexed: list[TableMetadata]
    warnings: Annotated[list[str], operator.add]  # avisos para la UI
    log: Annotated[list[str], operator.add]  # una línea por nodo (FR-018)
    error: str | None  # error que corta la ingesta


@lru_cache(maxsize=4)
def _loaded_pdf(path: str, mtime: float, name: str) -> LoadedPdf:
    data = Path(path).read_bytes()
    doc = open_pdf(data)
    try:
        return load_pdf(doc, name, data)
    finally:
        doc.close()


def _loaded(state: IngestionState) -> LoadedPdf:
    path = Path(state["pdf_path"])
    return _loaded_pdf(str(path), path.stat().st_mtime, state["pdf_name"])


def _pending(state: IngestionState) -> list[int]:
    done = set(state.get("annotations", {})) | set(state.get("failed", []))
    return [d.index for d in state.get("drafts", []) if d.index not in done]


# --------------------------------------------------------------------------------------
# Grafo
# --------------------------------------------------------------------------------------


def build_ingestion_graph(services: IngestionServices) -> Any:
    def load_pdf_node(state: IngestionState) -> IngestionState:
        try:
            loaded = _loaded(state)
        except (PdfOpenError, NoTextLayerError) as exc:
            return {"error": str(exc), "log": [f"load_pdf: {exc}"]}
        return {
            "doc_id": loaded.doc_id,
            "page_count": loaded.page_count,
            "log": [f"load_pdf: {loaded.page_count} páginas leídas (doc_id {loaded.doc_id})"],
        }

    def extract_tables_node(state: IngestionState) -> IngestionState:
        loaded = _loaded(state)
        doc = open_pdf(Path(state["pdf_path"]))
        try:
            raw, warnings = extract_tables(doc, loaded)
        finally:
            doc.close()
        update: IngestionState = {
            "raw_tables": [RawTableData.from_raw(t) for t in raw],
            "warnings": [w.message for w in warnings],
            "log": [f"extract_tables: {len(raw)} tablas detectadas en {loaded.page_count} páginas"],
        }
        if not raw:
            update["error"] = NO_TABLES_MESSAGE
        return update

    def merge_node(state: IngestionState) -> IngestionState:
        raw = [t.to_raw() for t in state["raw_tables"]]
        merged = merge_continuations(raw, _loaded(state))
        joined = len(raw) - len(merged)
        return {
            "raw_tables": [RawTableData.from_raw(t) for t in merged],
            "log": [
                f"merge_continuations: {len(merged)} tablas lógicas "
                f"({joined} uniones entre páginas)"
            ],
        }

    def collect_context_node(state: IngestionState) -> IngestionState:
        loaded = _loaded(state)
        tables = [t.to_raw() for t in state["raw_tables"]]
        drafts: list[TableDraft] = []
        warnings: list[str] = []
        for i, table in enumerate(tables):
            ctx = collect_context(table, loaded, tables)
            df, notes, problems = normalize_table(table, loaded)
            warnings += [w.message for w in problems]
            drafts.append(
                TableDraft.from_dataframe(
                    i, table.pages, table.strategy, df,
                    TableContextData(caption=ctx.caption, paragraph_before=ctx.paragraph_before,
                                     paragraph_after=ctx.paragraph_after,
                                     section_title=ctx.section_title, footnotes=ctx.footnotes),
                    notes,
                )
            )  # fmt: skip
        with_caption = sum(1 for d in drafts if d.context.caption)
        return {
            "drafts": drafts,
            "annotations": {},
            "attempts": {},
            "failed": [],
            "pending_errors": {},
            "warnings": warnings,
            "log": [
                f"collect_context: contexto de {len(drafts)} tablas ({with_caption} con epígrafe)"
            ],
        }

    def enrich_node(state: IngestionState, config: RunnableConfig) -> IngestionState:
        pending = _pending(state)
        drafts = {d.index: d for d in state["drafts"]}
        errors = state.get("pending_errors", {})
        jobs = [(drafts[i], errors.get(i, [])) for i in pending]
        results = services.annotate(jobs, state["pdf_name"], config)
        service_errors = [r for r in results if isinstance(r, Exception) and is_service_error(r)]
        if results and len(service_errors) == len(results):
            # Todas las llamadas fallaron por el servicio (clave inválida, proxy caído…): no es un
            # problema de los metadatos, así que no se reintenta; la UI lo muestra (FR-043).
            raise service_errors[0]
        attempts = dict(state.get("attempts", {}))
        candidates: dict[int, TableAnnotation] = {}
        call_errors: dict[int, list[str]] = {}
        for i, result in zip(pending, results, strict=True):
            attempts[i] = attempts.get(i, 0) + 1
            if isinstance(result, TableAnnotation):
                candidates[i] = result
            else:
                call_errors[i] = [f"Error al llamar al LLM: {type(result).__name__}: {result}"]
        retry = any(n > 1 for n in attempts.values() if n)
        label = "reintento" if retry else "intento 1"
        return {
            "candidates": candidates,
            "pending_errors": call_errors,
            "attempts": attempts,
            "log": [f"enrich: {len(jobs)} tablas anotadas con el LLM ({label})"],
        }

    def validate_node(state: IngestionState) -> IngestionState:
        drafts = {d.index: d for d in state["drafts"]}
        annotations = dict(state.get("annotations", {}))
        failed = list(state.get("failed", []))
        errors: dict[int, list[str]] = dict(state.get("pending_errors", {}))
        warnings: list[str] = []
        for i, candidate in state.get("candidates", {}).items():
            problems = validate_annotation(candidate, drafts[i])
            if problems:
                errors[i] = problems
            else:
                annotations[i] = candidate
                errors.pop(i, None)
        for i in list(errors):
            if state["attempts"].get(i, 0) > services.max_retries:
                failed.append(i)
                d = drafts[i]
                name = d.context.caption or f"tabla {i + 1}"
                warnings.append(
                    f"Página {d.pages[0]}: no se indexó «{name[:80]}» porque sus metadatos "
                    f"no pasaron la validación tras {state['attempts'][i]} intentos: "
                    + "; ".join(errors.pop(i))
                )
        return {
            "annotations": annotations,
            "failed": failed,
            "pending_errors": errors,
            "candidates": {},
            "warnings": warnings,
            "log": [
                f"validate: {len(annotations)} válidas, {len(errors)} a reintentar, "
                f"{len(failed)} descartadas"
            ],
        }

    def persist_and_index_node(state: IngestionState) -> IngestionState:
        annotations = state.get("annotations", {})
        if not annotations:
            return {
                "error": NONE_VALID_MESSAGE,
                "log": [f"persist_and_index: {NONE_VALID_MESSAGE}"],
            }
        try:
            index = services.index_factory()
        except IndexDimensionError as exc:
            return {"error": str(exc), "log": [f"persist_and_index: {exc}"]}
        doc_id, pdf_name = state["doc_id"], state["pdf_name"]
        drafts = {d.index: d for d in state["drafts"]}
        items: list[tuple[TableMetadata, Any]] = []
        for i in sorted(annotations):
            meta = build_metadata(annotations[i], drafts[i], table_id=table_id_for(doc_id, i),
                                  doc_id=doc_id, pdf_name=pdf_name)  # fmt: skip
            items.append((meta, drafts[i].to_dataframe()))
        vectors = services.embeddings_factory().embed_documents(
            [embedding_text(m) for m, _ in items]
        )
        records = [
            VectorRecord(meta.table_id, list(vec), pinecone_metadata(meta, df))
            for (meta, df), vec in zip(items, vectors, strict=True)
        ]
        # BR-006: se reemplaza todo lo del documento (sin duplicados ni tablas obsoletas).
        index.delete_ids(index.list_ids(f"{doc_id}-t"))
        services.store.delete_doc(doc_id)
        services.store.save_pdf(doc_id, Path(state["pdf_path"]).read_bytes())
        for meta, df in items:
            services.store.save(meta, df)
        index.upsert(records)
        where = f" «{services.index_name}»" if services.index_name else ""
        return {
            "indexed": [m for m, _ in items],
            "log": [
                f"persist_and_index: {len(items)} tablas guardadas e indexadas en Pinecone{where}"
            ],
        }

    def after_load(state: IngestionState) -> Literal["extract_tables", "__end__"]:
        return "__end__" if state.get("error") else "extract_tables"

    def after_extract(state: IngestionState) -> Literal["merge_continuations", "__end__"]:
        return "__end__" if state.get("error") else "merge_continuations"

    def after_validate(state: IngestionState) -> Literal["enrich", "persist_and_index"]:
        return "enrich" if _pending(state) else "persist_and_index"

    graph = StateGraph(IngestionState)
    graph.add_node("load_pdf", load_pdf_node)
    graph.add_node("extract_tables", extract_tables_node)
    graph.add_node("merge_continuations", merge_node)
    graph.add_node("collect_context", collect_context_node)
    graph.add_node("enrich", enrich_node)
    graph.add_node("validate", validate_node)
    graph.add_node("persist_and_index", persist_and_index_node)
    graph.add_edge(START, "load_pdf")
    graph.add_conditional_edges("load_pdf", after_load)
    graph.add_conditional_edges("extract_tables", after_extract)
    graph.add_edge("merge_continuations", "collect_context")
    graph.add_edge("collect_context", "enrich")
    graph.add_edge("enrich", "validate")
    graph.add_conditional_edges("validate", after_validate)
    graph.add_edge("persist_and_index", END)
    return graph.compile()


# --------------------------------------------------------------------------------------
# Puntos de entrada
# --------------------------------------------------------------------------------------


def _initial_state(pdf_path: Path, pdf_name: str | None) -> IngestionState:
    return {
        "pdf_path": str(pdf_path),
        "pdf_name": pdf_name or pdf_path.name,
        "warnings": [],
        "log": [],
    }


def _config(pdf_path: Path, pdf_name: str | None, settings: Settings | None) -> RunnableConfig:
    name = pdf_name or pdf_path.name
    try:
        doc_id: str | None = compute_doc_id(pdf_path.read_bytes())
    except OSError:
        doc_id = None
    model = settings.LLM_MODEL if settings else None
    return run_config("ingest", name, doc_id=doc_id, model=model)


def ingest_pdf(
    pdf_path: Path,
    pdf_name: str | None = None,
    services: IngestionServices | None = None,
    settings: Settings | None = None,
) -> IngestionState:
    """Corre la ingesta completa y devuelve el estado final."""
    settings = settings or (get_settings() if services is None else None)
    graph = build_ingestion_graph(services or default_services(settings))
    result: IngestionState = graph.invoke(
        _initial_state(pdf_path, pdf_name), config=_config(pdf_path, pdf_name, settings)
    )
    return result


def stream_ingest(
    pdf_path: Path,
    pdf_name: str | None = None,
    services: IngestionServices | None = None,
    settings: Settings | None = None,
) -> Iterator[tuple[str, IngestionState]]:
    """Ejecuta la ingesta emitiendo `(nodo, actualización)` al terminar cada nodo (FR-018)."""
    settings = settings or (get_settings() if services is None else None)
    graph = build_ingestion_graph(services or default_services(settings))
    for chunk in graph.stream(
        _initial_state(pdf_path, pdf_name),
        config=_config(pdf_path, pdf_name, settings),
        stream_mode="updates",
    ):
        for node, update in chunk.items():
            yield str(node), cast(IngestionState, update or {})
