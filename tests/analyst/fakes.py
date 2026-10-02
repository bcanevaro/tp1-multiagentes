"""Tablas de prueba (datos del PDF sintético) y fakes de los LLM del Analista."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

from agents.analyst.graph import AnalystServices
from agents.analyst.schemas import (
    GeneratedCode,
    QueryPlan,
    Selection,
    SubQuestion,
    SubquestionCoverage,
)
from agents.ingestion.schemas import ColumnInfo, Source, TableMetadata
from scripts import sample_data as sd
from services.config import Settings
from services.sandbox import run_code
from services.table_store import TableStore
from services.vector_index import InMemoryIndex, VectorRecord, embedding_text
from tests.ingestion.fakes import DIM, HashEmbeddings

DOC = "sint"
PDF = "informe_sintetico.pdf"
FINANCE_ID, UNEMPLOYMENT_ID, WAGES_ID, POPULATION_ID = (f"{DOC}-t0{i}" for i in (1, 2, 3, 5))

Messages = list[BaseMessage]


def _col(
    name: str, unit: str = "", value_type: str = "texto", scale: str = "unidades"
) -> ColumnInfo:
    dtype = "str" if value_type == "texto" else "float64"
    return ColumnInfo(
        name=name,
        description=f"Columna {name}.",
        dtype=dtype,
        unit=unit,
        scale=scale,
        value_type=value_type,
    )


def _meta(
    table_id: str, name: str, columns: list[ColumnInfo], df: pd.DataFrame, page: int, **kw: object
) -> TableMetadata:
    row_col = columns[0].name
    return TableMetadata(
        table_id=table_id,
        doc_id=DOC,
        name=name,
        description=f"{name}. Datos del anuario estadístico de la provincia.",
        columns=columns,
        row_header_column=row_col,
        row_headers=[str(v) for v in df[row_col]],
        periods_covered=kw.get("periods", []),
        entities_covered=[],
        notes="",
        source=Source(pdf_name=PDF, doc_id=DOC, pages=[page]),
        n_rows=len(df),
        n_cols=len(df.columns),
        caption=f"Cuadro. {name}",
    )


def synthetic_tables() -> list[tuple[TableMetadata, pd.DataFrame]]:
    years = [str(y) for y in sd.YEARS_FINANCE]
    finance = pd.DataFrame({"Concepto": list(sd.FINANCE)})
    for i, y in enumerate(years):
        finance[y] = [sd.FINANCE[k][i] for k in sd.FINANCE]
    money = [_col(y, "millones de pesos", "nominal", "millones") for y in years]

    uyears = [str(y) for y in sd.UNEMPLOYMENT_YEARS]
    unemployment = pd.DataFrame({"Departamento": list(sd.UNEMPLOYMENT)})
    for i, y in enumerate(uyears):
        unemployment[y] = [
            float("nan") if (v := sd.UNEMPLOYMENT[d][i]) is None else v for d in sd.UNEMPLOYMENT
        ]

    wyears = [str(y) for y in sd.WAGE_YEARS]
    wages = pd.DataFrame({"Sector": list(sd.WAGES)})
    for i, y in enumerate(wyears):
        wages[y] = [float("nan") if (v := sd.WAGES[s][i]) is None else float(v) for s in sd.WAGES]

    population = pd.DataFrame(
        {
            "Departamento": list(sd.POPULATION),
            "Población": [float(v) for v in sd.POPULATION.values()],
            "Superficie": [float(v) for v in sd.AREA_KM2.values()],
        }
    )
    for df in (finance, unemployment, wages, population):
        df[df.columns[0]] = df[df.columns[0]].astype("str")
    return [
        (
            _meta(
                FINANCE_ID,
                "Finanzas del sector público provincial",
                [_col("Concepto"), *money],
                finance,
                1,
                periods=years,
            ),
            finance,
        ),
        (
            _meta(
                UNEMPLOYMENT_ID,
                "Tasa de desempleo por departamento",
                [_col("Departamento"), *[_col(y, "%", "porcentaje") for y in uyears]],
                unemployment,
                1,
                periods=uyears,
            ),
            unemployment,
        ),
        (
            _meta(
                WAGES_ID,
                "Salario bruto promedio mensual por sector",
                [_col("Sector"), *[_col(y, "pesos", "unknown") for y in wyears]],
                wages,
                2,
                periods=wyears,
            ),
            wages,
        ),
        (
            _meta(
                POPULATION_ID,
                "Población y superficie por departamento",
                [
                    _col("Departamento"),
                    _col("Población", "habitantes", "conteo"),
                    _col("Superficie", "km²", "conteo"),
                ],
                population,
                2,
                periods=["2023"],
            ),
            population,
        ),
    ]


def populate(data_dir: Path) -> tuple[TableStore, InMemoryIndex]:
    store = TableStore(data_dir)
    index = InMemoryIndex(DIM)
    emb = HashEmbeddings()
    records = []
    for meta, df in synthetic_tables():
        store.save(meta, df)
        records.append(VectorRecord(meta.table_id, emb.embed_query(embedding_text(meta)), {}))
    index.upsert(records)
    return store, index


# --------------------------------------------------------------------------------------
# Fakes de los LLM
# --------------------------------------------------------------------------------------


def sub(
    id_: str, text: str, periods: list[str] | None = None, entities: list[str] | None = None
) -> SubQuestion:
    return SubQuestion(
        id=id_,
        text=text,
        metrics=["valor"],
        entities=entities or [],
        periods=periods or [],
        operation="cociente",
    )


def plan(*subs: SubQuestion, queries: list[str] | None = None) -> QueryPlan:
    return QueryPlan(subquestions=list(subs), search_queries=queries or ["tema"])


def cover(
    sub_id: str, tables: list[str], columns: list[str], covered: bool = True, missing: str = ""
) -> SubquestionCoverage:
    return SubquestionCoverage(
        subquestion_id=sub_id,
        covered=covered,
        table_ids=tables,
        columns_used=columns,
        missing=missing,
        related_table="",
    )


class Recorder:
    """Función fake que devuelve respuestas en orden (repite la última) y guarda los mensajes."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[Messages] = []

    def __call__(self, messages: Messages, config: RunnableConfig | None) -> object:
        self.calls.append(messages)
        index = min(len(self.calls), len(self.responses)) - 1
        return self.responses[index]

    def prompt(self, call: int = -1) -> str:
        return "\n".join(str(m.content) for m in self.calls[call])


def code(text: str) -> GeneratedCode:
    return GeneratedCode(code=text, explanation="Divide un valor por otro.")


def make_services(
    store: TableStore,
    index: InMemoryIndex,
    settings: Settings,
    planner: Recorder,
    selector: Recorder,
    coder: Recorder,
    writer: Recorder | None = None,
    max_retries: int = 2,
    run: Callable[..., object] | None = None,
) -> AnalystServices:
    return AnalystServices(
        plan=planner,  # type: ignore[arg-type]
        select=selector,  # type: ignore[arg-type]
        code=coder,  # type: ignore[arg-type]
        write=writer or Recorder("Respuesta redactada."),  # type: ignore[arg-type]
        embeddings_factory=HashEmbeddings,
        index_factory=lambda: index,
        store=store,
        run_code=run or (lambda c, t: run_code(c, t, settings=settings)),  # type: ignore[arg-type]
        max_retries=max_retries,
        retrieval_k=6,
        sandbox_backend="subprocess",
        model="fake-model",
    )


__all__ = ["Selection"]
