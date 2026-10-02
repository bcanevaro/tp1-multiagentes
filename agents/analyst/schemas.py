"""Modelos del Agente Analista (spec §7.4–§7.6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agents.ingestion.schemas import TableMetadata
from services.sandbox.result import CodeResult

Status = Literal["answered", "partial", "cannot_answer"]
AnalystError = Literal["execution_failed", "no_tables_indexed"]

# --------------------------------------------------------------------------------------
# Salidas estructuradas del LLM
# --------------------------------------------------------------------------------------


class SubQuestion(BaseModel):
    id: str = Field(description="Identificador: q1, q2, …")
    text: str = Field(description="La parte de la pregunta, autocontenida")
    metrics: list[str] = Field(description="Métricas o variables que hay que obtener")
    entities: list[str] = Field(
        description="SOLO nombres propios específicos que tienen que aparecer en los datos "
        "(p. ej. 'Norte', 'Córdoba', 'Industria'). Nada genérico ('provincia', 'departamentos')"
    )
    periods: list[str] = Field(description="Períodos pedidos, p. ej. ['2023'] o ['2019', '2023']")
    operation: str = Field(description="Operación: suma, promedio, variación, cociente, máximo…")


class QueryPlan(BaseModel):
    subquestions: list[SubQuestion] = Field(description="Una por cada parte que pide un dato")
    search_queries: list[str] = Field(
        description="De 1 a 4 consultas para buscar las tablas, en español, por tema",
        min_length=1,
        max_length=4,
    )


class SubquestionCoverage(BaseModel):
    subquestion_id: str
    covered: bool = Field(description="true solo si las tablas elegidas tienen TODO lo necesario")
    table_ids: list[str] = Field(description="table_id de las tablas necesarias (0, 1 o varias)")
    columns_used: list[str] = Field(description="Nombres exactos de las columnas que se usarían")
    missing: str = Field(description="Si no está cubierta: qué dato falta. Vacío si está cubierta")
    related_table: str = Field(
        description="Si no está cubierta y hay una tabla relacionada: qué contiene "
        "(p. ej. 'La tabla Ingresos por año cubre 2019-2023'). Vacío si no hay"
    )
    ambiguity_ok: str = Field(
        default="",
        description="Solo si una columna usada tiene unidad 'desconocida' o tipo 'unknown' y aun "
        "así el resultado no depende de eso: por qué. Vacío en otro caso",
    )


class Selection(BaseModel):
    coverage: list[SubquestionCoverage] = Field(description="Una entrada por subpregunta")


class GeneratedCode(BaseModel):
    code: str = Field(description="Programa Python completo, sin bloques ``` ni explicación")
    explanation: str = Field(description="Una o dos oraciones: qué calcula el programa y cómo")


# --------------------------------------------------------------------------------------
# Estado
# --------------------------------------------------------------------------------------


class Candidate(BaseModel):
    table_id: str
    score: float
    metadata: TableMetadata
    preview_markdown: str


class MissingInfo(BaseModel):
    subquestion_id: str
    text: str
    reason: str
    related_table: str = ""


class ExecutionSummary(BaseModel):
    """Lo que se guarda de cada ejecución del sandbox (JSON, sin el objeto original)."""

    attempt: int
    code: str
    stdout: str
    stderr: str
    exit_code: int | None
    duration_s: float
    backend: str
    timed_out: bool = False
    rejected: str | None = None
    error: str | None = None  # motivo de invalidez (FR-028), None si fue válida


class UsedTable(BaseModel):
    table_id: str
    name: str
    pages: list[int]
    pdf_name: str


class AnalystOutcome(BaseModel):
    """Resumen final pensado para la UI y la evaluación."""

    question: str
    status: Status
    error: AnalystError | None
    answer: str
    code_result: CodeResult | None
    missing: list[MissingInfo]
    tables: list[UsedTable]
    code: str
    executions: list[ExecutionSummary]
    retries: int
