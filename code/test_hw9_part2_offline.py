"""Offline tests for HW9 Part 2 cache-first query-handler behavior."""

import asyncio
import os
import unittest
from typing import Any

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from hw9_part2_api import handle_question  # noqa: E402
from hw9_semantic_cache import CacheLookup  # noqa: E402


class FakeSemanticCache:
    """Minimal deterministic cache used without Redis or an embedding model."""

    def __init__(self) -> None:
        self.entries: dict[str, str] = {}

    def find(self, query: str) -> CacheLookup:
        answer = self.entries.get(query)
        if answer is None:
            return CacheLookup(None, 0.25, None, None, None)
        return CacheLookup(answer, 1.0, query, "1", "fake-key")

    def store(self, query: str, answer: str) -> tuple[str, str]:
        self.entries[query] = answer
        return "fake-key", "1"


class Part2HandlerTests(unittest.TestCase):
    """Verify that hits bypass and misses run the HW8 pipeline callable."""

    def test_miss_runs_pipeline_and_exact_hit_bypasses_it(self) -> None:
        cache = FakeSemanticCache()
        pipeline_calls: list[str] = []

        async def fake_pipeline(question: str) -> str:
            pipeline_calls.append(question)
            return "Reviewer-approved answer"

        async def scenario() -> tuple[dict[str, Any], dict[str, Any]]:
            first = await handle_question(
                "How should a renter verify a listing?",
                cache=cache,  # type: ignore[arg-type]
                pipeline_runner=fake_pipeline,
            )
            second = await handle_question(
                "How should a renter verify a listing?",
                cache=cache,  # type: ignore[arg-type]
                pipeline_runner=fake_pipeline,
            )
            return first, second

        first, second = asyncio.run(scenario())
        self.assertFalse(first["is_cached"])
        self.assertTrue(second["is_cached"])
        self.assertEqual(first["answer"], second["answer"])
        self.assertEqual(len(pipeline_calls), 1)
        self.assertEqual(second["similarity_score"], 1.0)

    def test_different_question_is_a_cache_miss(self) -> None:
        cache = FakeSemanticCache()
        pipeline_calls = 0

        async def fake_pipeline(question: str) -> str:
            nonlocal pipeline_calls
            pipeline_calls += 1
            return f"Answer for: {question}"

        async def scenario() -> tuple[dict[str, Any], dict[str, Any]]:
            first = await handle_question(
                "Question A",
                cache=cache,  # type: ignore[arg-type]
                pipeline_runner=fake_pipeline,
            )
            second = await handle_question(
                "Question B",
                cache=cache,  # type: ignore[arg-type]
                pipeline_runner=fake_pipeline,
            )
            return first, second

        first, second = asyncio.run(scenario())
        self.assertFalse(first["is_cached"])
        self.assertFalse(second["is_cached"])
        self.assertEqual(pipeline_calls, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
