import json
import shutil
import tempfile
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from file_memory import FileMemoryManager
from hw6_agent_compliant import normalize_listing_title
from hw6_config import HW6Settings
from hw6_memory import (
    MemoryService,
    allocate_prompt_tokens,
    cosine_similarity,
    extract_episode_facts,
    importance_evict,
)
from hw6_schemas import (
    DocumentListingCreate,
    MemoryMode,
    MemoryPolicy,
)
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
RUN_LOG = ROOT / "reports" / "hw06" / "RUN_LOG.txt"


@dataclass
class FakeResult:
    content: str
    input_tokens: int = 24
    output_tokens: int = 6
    total_tokens: int = 30


class FakeModel:
    def complete(
        self,
        messages: list[dict[str, str]],
        tools=None,
    ) -> FakeResult:
        prompt = messages[-1]["content"]

        if "Create a concise bullet summary" in prompt:
            return FakeResult("- Current durable facts summarized.")

        if "Condense session summaries" in messages[0]["content"]:
            return FakeResult("- Lifetime facts condensed.")

        return FakeResult(f"Remembered response to: {prompt}")


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        return [
            float(len(text)),
            float(sum(ord(character) for character in text) % 101),
        ]


class FakeRepository:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.summaries: list[dict[str, Any]] = []
        self.episodes: list[dict[str, Any]] = []
        self.metrics: list[dict[str, Any]] = []
        self._id = 0

    def _document(self, values: dict[str, Any]) -> dict[str, Any]:
        self._id += 1
        return {
            "_id": str(self._id),
            "created_at": datetime.now(UTC),
            **values,
        }

    def save_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
    ) -> dict[str, Any]:
        item = self._document(
            {
                "user_id": user_id,
                "session_id": session_id,
                "role": role,
                "content": content,
            }
        )
        self.messages.append(item)
        return item

    def recent_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        matching = [
            item
            for item in self.messages
            if item["user_id"] == user_id and item["session_id"] == session_id
        ]
        return matching[-limit:]

    def count_user_messages(
        self,
        user_id: str,
        session_id: str,
    ) -> int:
        return sum(
            item["role"] == "user"
            for item in self.recent_messages(
                user_id,
                session_id,
                1000,
            )
        )

    def latest_summary(
        self,
        user_id: str,
        scope: str,
        session_id: str | None,
    ) -> dict[str, Any] | None:
        matching = [
            item
            for item in self.summaries
            if item["user_id"] == user_id
            and item["scope"] == scope
            and item["session_id"] == session_id
        ]
        return matching[-1] if matching else None

    def save_summary(
        self,
        user_id: str,
        session_id: str | None,
        scope: str,
        text: str,
    ) -> dict[str, Any]:
        item = self._document(
            {
                "user_id": user_id,
                "session_id": session_id,
                "scope": scope,
                "text": text,
            }
        )
        self.summaries.append(item)
        return item

    def recent_summaries(
        self,
        user_id: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        matching = [item for item in self.summaries if item["user_id"] == user_id]
        return list(reversed(matching[-limit:]))

    def session_summary_count(self, user_id: str) -> int:
        return sum(
            item["user_id"] == user_id and item["scope"] == "session"
            for item in self.summaries
        )

    def save_episode(
        self,
        user_id: str,
        session_id: str,
        fact: str,
        importance: float,
        embedding: list[float],
    ) -> dict[str, Any]:
        item = self._document(
            {
                "user_id": user_id,
                "session_id": session_id,
                "fact": fact,
                "importance": importance,
                "embedding": embedding,
            }
        )
        self.episodes.append(item)
        return item

    def recent_episodes(
        self,
        user_id: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        matching = [item for item in self.episodes if item["user_id"] == user_id]
        return list(reversed(matching[-limit:]))

    def save_metric(self, metric: dict[str, Any]) -> None:
        self.metrics.append(metric)


class HW6OfflineTests(unittest.TestCase):
    def test_document_listing_validation(self) -> None:
        valid = DocumentListingCreate(
            listingTitle="Downtown Apartment",
            propertyType="Apartment",
            availableFrom="2026-11-15T12:00:00Z",
        )
        self.assertEqual(valid.status.value, "active")

        with self.assertRaises(ValidationError):
            DocumentListingCreate(
                listingTitle="",
                propertyType="Apartment",
                availableFrom="not-a-date",
            )

        with self.assertRaises(ValidationError):
            DocumentListingCreate(
                listingTitle="Valid title",
                propertyType="Castle",
                availableFrom="2026-11-15T12:00:00Z",
            )

    def test_agent_compliant_function(self) -> None:
        self.assertEqual(
            normalize_listing_title("  Bright   Studio  "),
            "Bright Studio",
        )

        with self.assertRaises(ValueError):
            normalize_listing_title("   ")

        with self.assertRaises(TypeError):
            normalize_listing_title(42)  # type: ignore[arg-type]

        with self.assertRaises(ValueError):
            normalize_listing_title("x" * 101)

    def test_cosine_and_token_allocation(self) -> None:
        self.assertAlmostEqual(
            cosine_similarity([1.0, 0.0], [1.0, 0.0]),
            1.0,
        )
        allocation = allocate_prompt_tokens(
            100,
            {"system": "short", "history": "a much longer history"},
        )
        self.assertEqual(sum(allocation.values()), 100)
        self.assertGreater(allocation["history"], allocation["system"])

    def test_episode_extraction_and_eviction(self) -> None:
        facts = extract_episode_facts(
            "My budget is $2,200. I prefer San Jose. "
            "I must have laundry. I also like sunlight."
        )
        self.assertEqual(len(facts), 3)
        self.assertTrue(all(0 <= item["importance"] <= 1 for item in facts))

        messages = [
            {"role": "user", "content": f"message {index}"} for index in range(12)
        ]
        kept = importance_evict(messages, keep=6)
        self.assertEqual(len(kept), 6)
        self.assertEqual(kept[-1]["content"], "message 11")

    def test_file_consolidation_and_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copy(ROOT / "AGENT.md", root / "AGENT.md")
            shutil.copy(
                ROOT / "MEMORY.original.md",
                root / "MEMORY.md",
            )
            manager = FileMemoryManager(root)
            before = manager.consolidation_status()
            self.assertEqual(before["line_count"], 55)
            self.assertTrue(before["required"])

            result = manager.consolidate()
            self.assertEqual(result["before"], 55)
            self.assertLess(result["after"], 40)
            self.assertGreaterEqual(len(result["contradictions"]), 3)
            self.assertIn("/compact", manager.handle_command("/help", []))

    def test_memory_service_without_external_services(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copy(ROOT / "AGENT.md", root / "AGENT.md")
            shutil.copy(ROOT / "MEMORY.md", root / "MEMORY.md")
            repository = FakeRepository()
            settings = HW6Settings(
                short_term_n=4,
                summarize_every_user_messages=2,
                episodic_top_k=2,
                lifetime_every_session_summaries=2,
            )
            service = MemoryService(
                repository=repository,  # type: ignore[arg-type]
                model=FakeModel(),
                embedder=FakeEmbedder(),
                settings=settings,
                file_memory=FileMemoryManager(root),
                metrics_path=root / "metrics.jsonl",
            )

            for message in (
                "My budget is $2,200.",
                "I prefer San Jose.",
                "I need in-unit laundry.",
                "My move date is November 15, 2026.",
            ):
                result = service.chat(
                    user_id="offline-user",
                    session_id="offline-session",
                    message=message,
                    memory_mode=MemoryMode.mongodb,
                    policy=MemoryPolicy.standard,
                )

            self.assertEqual(result["session_id"], "offline-session")
            self.assertEqual(len(repository.messages), 8)
            self.assertGreaterEqual(len(repository.episodes), 4)
            self.assertEqual(
                sum(item["scope"] == "session" for item in repository.summaries),
                2,
            )
            self.assertEqual(
                sum(item["scope"] == "user" for item in repository.summaries),
                1,
            )
            self.assertEqual(len(repository.metrics), 4)

            command = service.chat(
                user_id="offline-user",
                session_id="offline-session",
                message="/help",
                memory_mode=MemoryMode.file,
                policy=MemoryPolicy.standard,
            )
            self.assertIn("/memory", command["reply"])


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HW6OfflineTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = (
        f"HW6 OFFLINE TESTS: "
        f"{result.testsRun - len(result.failures) - len(result.errors)}"
        f"/{result.testsRun} PASS"
    )
    print(summary)

    with RUN_LOG.open("a", encoding="utf-8") as log:
        log.write(
            "\n[" + datetime.now().astimezone().isoformat() + "] " + summary + "\n"
        )

    if not result.wasSuccessful():
        details = {
            "failures": [name.id() for name, _ in result.failures],
            "errors": [name.id() for name, _ in result.errors],
        }
        print(json.dumps(details, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
