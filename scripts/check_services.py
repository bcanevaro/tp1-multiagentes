"""Verifica la conexión con los servicios externos y la configuración del `.env`.

Uso:  uv run python scripts/check_services.py

Chequea, en orden: variables obligatorias, proxy LiteLLM (modelos y chat), métodos de salida
estructurada soportados por el modelo de chat, dimensión del modelo de embeddings, Pinecone y
LangSmith. Termina con código 0 si todo está OK y 1 si algo falló.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field  # noqa: E402

from services.config import Settings, get_settings  # noqa: E402


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class _Ping(BaseModel):
    """Respuesta de prueba para verificar la salida estructurada."""

    city: str = Field(description="Nombre de la ciudad")
    year: int = Field(description="Año como número entero")


def check_env(settings: Settings) -> CheckResult:
    missing = settings.missing_required()
    if missing:
        return CheckResult("Variables .env", False, "Faltan: " + ", ".join(missing))
    return CheckResult("Variables .env", True, "Todas las variables obligatorias están definidas")


def check_litellm_models(settings: Settings) -> CheckResult:
    from openai import OpenAI

    client = OpenAI(base_url=settings.LITELLM_BASE_URL, api_key=settings.LITELLM_API_KEY)
    names = sorted(m.id for m in client.models.list())
    detail = f"{len(names)} modelos: {', '.join(names)}"
    problems = [
        f"'{v}' no está en el proxy"
        for v in (settings.LLM_MODEL, settings.EMBEDDING_MODEL)
        if v and v not in names
    ]
    if problems:
        return CheckResult("LiteLLM /models", False, detail + " | " + "; ".join(problems))
    return CheckResult("LiteLLM /models", True, detail)


def check_chat(settings: Settings) -> CheckResult:
    from services.llm import get_chat_model

    llm = get_chat_model(settings.model_copy(update={"LLM_CACHE": False}))
    start = time.perf_counter()
    reply = llm.invoke("Respondé solamente con la palabra OK.")
    elapsed = time.perf_counter() - start
    detail = f"{settings.LLM_MODEL} respondió {reply.content!r} en {elapsed:.1f}s"
    return CheckResult("LiteLLM chat", True, detail)


def check_structured(settings: Settings) -> CheckResult:
    from services.llm import get_chat_model, with_structured

    llm = get_chat_model(settings.model_copy(update={"LLM_CACHE": False}))
    working: list[str] = []
    errors: list[str] = []
    for method in ("function_calling", "json_schema", "json_mode"):
        try:
            s = settings.model_copy(update={"LLM_STRUCTURED_METHOD": method})
            prompt = "Devolvé un JSON con city='Rosario' y year=2024."
            if method == "json_mode":
                prompt += " Claves: city (string), year (entero)."
            out = with_structured(llm, _Ping, s).invoke(prompt)
            if isinstance(out, _Ping) and out.year == 2024:
                working.append(method)
            else:
                errors.append(f"{method}: salida inesperada {out!r}")
        except Exception as exc:  # noqa: BLE001 - queremos reportar cualquier falla
            errors.append(f"{method}: {type(exc).__name__}: {str(exc)[:120]}")
    configured = settings.LLM_STRUCTURED_METHOD
    detail = f"Funcionan: {working or 'ninguno'}; configurado: {configured}"
    if errors:
        detail += " | " + " | ".join(errors)
    ok = configured in working
    if not ok and working:
        detail += f" -> poné LLM_STRUCTURED_METHOD={working[0]} en el .env"
    return CheckResult("Salida estructurada", ok, detail)


def check_embeddings(settings: Settings) -> CheckResult:
    from services.llm import EmbeddingDimensionError, check_embedding_dim, get_embeddings

    emb = get_embeddings(settings.model_copy(update={"LLM_CACHE": False}))
    try:
        dim = check_embedding_dim(emb, settings.EMBEDDING_DIM)
    except EmbeddingDimensionError as exc:
        return CheckResult("Embeddings", False, str(exc))
    return CheckResult("Embeddings", True, f"{settings.EMBEDDING_MODEL}: dimensión {dim}")


def check_pinecone(settings: Settings) -> CheckResult:
    from pinecone import Pinecone

    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    names = list(pc.list_indexes().names())
    index = settings.PINECONE_INDEX_NAME
    if index in names:
        dim = pc.describe_index(index).dimension
        ok = dim == settings.EMBEDDING_DIM
        detail = f"Índice '{index}' existe con dimensión {dim}"
        if not ok:
            detail += f" (EMBEDDING_DIM={settings.EMBEDDING_DIM}: no coinciden)"
        return CheckResult("Pinecone", ok, detail)
    detail = f"Conexión OK. El índice '{index}' no existe todavía: se crea en la primera ingesta"
    return CheckResult("Pinecone", True, detail)


def check_langsmith(settings: Settings) -> CheckResult:
    from langchain_core.tracers.langchain import wait_for_all_tracers
    from langsmith import Client, traceable

    client = Client()
    list(client.list_projects(limit=1))  # valida la API key

    @traceable(name="check_services:ping", project_name=settings.LANGSMITH_PROJECT)
    def ping() -> str:
        return "pong"

    ping()
    wait_for_all_tracers()
    if not settings.LANGSMITH_TRACING:
        return CheckResult("LangSmith", False, "API key válida, pero LANGSMITH_TRACING no es true")
    detail = f"API key válida; traza enviada al proyecto '{settings.LANGSMITH_PROJECT}'"
    return CheckResult("LangSmith", True, detail)


_LITELLM = ("LITELLM_BASE_URL", "LITELLM_API_KEY")


def run_checks(settings: Settings) -> list[CheckResult]:
    results = [check_env(settings)]
    # (nombre, función, variables que necesita para poder correr)
    checks: list[tuple[str, Callable[[Settings], CheckResult], tuple[str, ...]]] = [
        ("LiteLLM /models", check_litellm_models, _LITELLM),
        ("LiteLLM chat", check_chat, _LITELLM + ("LLM_MODEL",)),
        ("Salida estructurada", check_structured, _LITELLM + ("LLM_MODEL",)),
        ("Embeddings", check_embeddings, _LITELLM + ("EMBEDDING_MODEL",)),
        ("Pinecone", check_pinecone, ("PINECONE_API_KEY", "PINECONE_INDEX_NAME")),
        ("LangSmith", check_langsmith, ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT")),
    ]
    missing = set(settings.missing_required())
    for name, fn, needs in checks:
        lacking = [v for v in needs if v in missing]
        if lacking:
            results.append(CheckResult(name, False, "Omitido: falta " + ", ".join(lacking)))
            continue
        try:
            results.append(fn(settings))
        except Exception as exc:  # noqa: BLE001 - el objetivo es reportar, no fallar
            results.append(CheckResult(name, False, f"{type(exc).__name__}: {exc}"))
    return results


def main() -> int:
    settings = get_settings()
    results = run_checks(settings)
    width = max(len(r.name) for r in results)
    print()
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"[{status}] {r.name.ljust(width)}  {r.detail}")
    print()
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
