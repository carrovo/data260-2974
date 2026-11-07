"""Semantic-cache ingress for the existing HW8 three-agent Q&A pipeline."""

import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from hw9_agent_client import run_hw8_agent_pipeline
from hw9_config import PREFIX
from hw9_semantic_cache import SEMANTIC_THRESHOLD, SemanticResponseCache

PipelineRunner = Callable[[str], Awaitable[str]]


class QuestionRequest(BaseModel):
    """One domain question submitted to the HW9 cache ingress."""

    question: str = Field(min_length=1)


async def handle_question(
    question: str,
    *,
    cache: SemanticResponseCache,
    pipeline_runner: PipelineRunner = run_hw8_agent_pipeline,
) -> dict[str, Any]:
    """Return a semantic hit or run and cache the normal HW8 agent path."""

    started = perf_counter()
    normalized_question = question.strip()
    lookup = await asyncio.to_thread(cache.find, normalized_question)

    if lookup.is_hit:
        latency_ms = (perf_counter() - started) * 1000
        print(
            "[HW9 CACHE HIT] "
            f"similarity={lookup.similarity:.4f} latency_ms={latency_ms:.2f}",
            flush=True,
        )
        return {
            "answer": lookup.answer,
            "is_cached": True,
            "similarity_score": round(lookup.similarity, 4),
            "latency_ms": round(latency_ms, 2),
            "data_version": lookup.data_version,
            "matched_query": lookup.matched_query,
        }

    print(
        "[HW9 CACHE MISS] "
        f"best_similarity={lookup.similarity:.4f}; running HW8 agents",
        flush=True,
    )
    answer = await pipeline_runner(normalized_question)
    _cache_key, data_version = await asyncio.to_thread(
        cache.store,
        normalized_question,
        answer,
    )
    latency_ms = (perf_counter() - started) * 1000
    return {
        "answer": answer,
        "is_cached": False,
        "similarity_score": round(lookup.similarity, 4),
        "latency_ms": round(latency_ms, 2),
        "data_version": data_version,
        "matched_query": lookup.matched_query,
    }


app = FastAPI(
    title="DATA 260 HW9 Semantic Agent Cache",
    version="9.0.0",
)
cache_instance: SemanticResponseCache | None = None


def get_cache() -> SemanticResponseCache:
    """Create one reusable cache and embedding model for the API process."""

    global cache_instance
    if cache_instance is None:
        cache_instance = SemanticResponseCache()
    return cache_instance


@app.get("/health")
async def health() -> dict[str, object]:
    """Return the cache identity and configured starting threshold."""

    cache = await asyncio.to_thread(get_cache)
    return {
        "status": "ok",
        "prefix": PREFIX,
        "semantic_threshold": cache.threshold,
    }


@app.post("/hw9/ask")
async def ask(payload: QuestionRequest) -> dict[str, Any]:
    """Answer one question through the required cache-first ingress."""

    cache = await asyncio.to_thread(get_cache)
    return await handle_question(payload.question, cache=cache)


if not 0 <= SEMANTIC_THRESHOLD <= 1:
    raise ValueError("HW9_SEMANTIC_THRESHOLD must be between 0 and 1")
