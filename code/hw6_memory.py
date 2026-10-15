import json
import math
import re
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from file_memory import FileMemoryManager
from hw6_config import HW6Settings
from hw6_schemas import MemoryMode, MemoryPolicy

if TYPE_CHECKING:
    from pymongo.database import Database
else:
    Database = Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METRICS_PATH = PROJECT_ROOT / "reports" / "hw06" / "raw" / "chat_turns.jsonl"
METRICS_LOCK = threading.Lock()

SYSTEM_PRIMER = """
You are a concise assistant for a rental-housing-listing project.
Use remembered information only when it is relevant. Do not invent
personal facts. If memories conflict, prefer the newest explicit fact
and mention the conflict when it affects the answer.
""".strip()


class CompletionLike(Protocol):
    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ModelLike(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[Any] | None = None,
    ) -> CompletionLike: ...


class EmbeddingLike(Protocol):
    def embed(self, text: str) -> list[float]: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class LocalEmbeddingProvider:
    """Lazy local embedding wrapper reused from the HW3/HW4 stack."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from llama_index.embeddings.huggingface import (
                        HuggingFaceEmbedding,
                    )

                    self._model = HuggingFaceEmbedding(model_name=self.model_name)

        return self._model

    def embed(self, text: str) -> list[float]:
        values = self._get_model().get_text_embedding(text)
        return [float(value) for value in values]


def cosine_similarity(
    first: list[float],
    second: list[float],
) -> float:
    if not first or not second or len(first) != len(second):
        return 0.0

    dot_product = sum(left * right for left, right in zip(first, second))
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))

    if first_norm == 0 or second_norm == 0:
        return 0.0

    return dot_product / (first_norm * second_norm)


def estimate_text_tokens(text: str) -> int:
    """Deterministic component counter used for token allocation."""

    pieces = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return max(1, len(pieces)) if text else 0


def allocate_prompt_tokens(
    actual_total: int,
    components: dict[str, str],
) -> dict[str, int]:
    """Allocate actual model prompt tokens across prompt components."""

    weights = {name: estimate_text_tokens(text) for name, text in components.items()}
    weight_total = sum(weights.values())

    if actual_total <= 0 or weight_total <= 0:
        return {name: 0 for name in components}

    exact = {
        name: actual_total * weight / weight_total for name, weight in weights.items()
    }
    allocated = {name: int(value) for name, value in exact.items()}
    remaining = actual_total - sum(allocated.values())
    remainder_order = sorted(
        exact,
        key=lambda name: exact[name] - allocated[name],
        reverse=True,
    )

    for name in remainder_order[:remaining]:
        allocated[name] += 1

    return allocated


def extract_episode_facts(message: str) -> list[dict[str, Any]]:
    """Extract up to three explicit user facts without another LLM call."""

    sentences = [
        sentence.strip(" -\t")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", message)
        if sentence.strip()
    ]
    markers = (
        "i ",
        "i'm ",
        "i am ",
        "my ",
        "we ",
        "prefer",
        "need",
        "budget",
        "deadline",
        "move",
        "remember",
        "must",
    )
    results: list[dict[str, Any]] = []

    for sentence in sentences:
        lowered = sentence.casefold()

        if not any(marker in lowered for marker in markers):
            continue

        importance = 0.55

        if re.search(r"\d", sentence):
            importance += 0.15

        if any(
            marker in lowered for marker in ("must", "deadline", "budget", "remember")
        ):
            importance += 0.2

        if any(marker in lowered for marker in ("prefer", "need", "do not", "don't")):
            importance += 0.1

        results.append(
            {
                "fact": sentence[:240],
                "importance": min(1.0, importance),
            }
        )

        if len(results) == 3:
            break

    return results


class MongoMemoryRepository:
    """All MongoDB persistence required by the HW6 memory API."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
    ) -> dict[str, Any]:
        document = {
            "user_id": user_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": utc_now(),
        }
        result = self.db.messages.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    def recent_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        documents = list(
            self.db.messages.find(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                }
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        documents.reverse()
        return documents

    def count_user_messages(
        self,
        user_id: str,
        session_id: str,
    ) -> int:
        return self.db.messages.count_documents(
            {
                "user_id": user_id,
                "session_id": session_id,
                "role": "user",
            }
        )

    def latest_summary(
        self,
        user_id: str,
        scope: str,
        session_id: str | None,
    ) -> dict[str, Any] | None:
        query: dict[str, Any] = {
            "user_id": user_id,
            "scope": scope,
        }

        if scope == "session":
            query["session_id"] = session_id
        else:
            query["session_id"] = None

        return self.db.summaries.find_one(
            query,
            sort=[("created_at", -1)],
        )

    def save_summary(
        self,
        user_id: str,
        session_id: str | None,
        scope: str,
        text: str,
    ) -> dict[str, Any]:
        document = {
            "user_id": user_id,
            "session_id": session_id,
            "scope": scope,
            "text": text,
            "created_at": utc_now(),
        }
        result = self.db.summaries.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    def recent_summaries(
        self,
        user_id: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        return list(
            self.db.summaries.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
        )

    def session_summary_count(self, user_id: str) -> int:
        return self.db.summaries.count_documents(
            {
                "user_id": user_id,
                "scope": "session",
            }
        )

    def save_episode(
        self,
        user_id: str,
        session_id: str,
        fact: str,
        importance: float,
        embedding: list[float],
    ) -> dict[str, Any]:
        document = {
            "user_id": user_id,
            "session_id": session_id,
            "fact": fact,
            "importance": float(importance),
            "embedding": [float(value) for value in embedding],
            "created_at": utc_now(),
        }
        result = self.db.episodes.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    def recent_episodes(
        self,
        user_id: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return list(
            self.db.episodes.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
        )

    def daily_message_counts(
        self,
        user_id: str,
    ) -> list[dict[str, Any]]:
        return list(
            self.db.messages.aggregate(
                [
                    {"$match": {"user_id": user_id}},
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": "%Y-%m-%d",
                                    "date": "$created_at",
                                }
                            },
                            "message_count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ]
            )
        )

    def save_metric(self, metric: dict[str, Any]) -> None:
        self.db.chat_metrics.insert_one(dict(metric))


def serialize_document(document: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}

    for key, value in document.items():
        if key == "_id":
            serialized["id"] = str(value)
        elif isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value

    return serialized


def format_messages(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return "None"

    return "\n".join(f"{message['role']}: {message['content']}" for message in messages)


def importance_evict(
    messages: list[dict[str, Any]],
    keep: int = 6,
) -> list[dict[str, Any]]:
    """Keep recent and information-dense messages under a small budget."""

    if len(messages) <= keep:
        return messages

    scored: list[tuple[float, int, dict[str, Any]]] = []

    for index, message in enumerate(messages):
        content = str(message.get("content", ""))
        recency = (index + 1) / len(messages)
        information = min(len(content) / 250, 1.0)
        fact_bonus = (
            0.5 if re.search(r"\d|prefer|need|must", content, re.IGNORECASE) else 0
        )
        score = recency + information + fact_bonus
        scored.append((score, index, message))

    chosen = sorted(
        sorted(scored, reverse=True)[:keep],
        key=lambda item: item[1],
    )
    return [item[2] for item in chosen]


class MemoryService:
    """Orchestrate short-, long-, episodic, and file memory."""

    def __init__(
        self,
        repository: MongoMemoryRepository,
        model: ModelLike,
        embedder: EmbeddingLike,
        settings: HW6Settings,
        file_memory: FileMemoryManager,
        metrics_path: Path = DEFAULT_METRICS_PATH,
    ) -> None:
        self.repository = repository
        self.model = model
        self.embedder = embedder
        self.settings = settings
        self.file_memory = file_memory
        self.metrics_path = metrics_path

    def retrieve_episodes(
        self,
        user_id: str,
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []

        for episode in self.repository.recent_episodes(user_id):
            similarity = cosine_similarity(
                query_embedding,
                episode.get("embedding", []),
            )
            scored.append(
                {
                    **episode,
                    "similarity": similarity,
                    "retrieval_score": (
                        0.85 * similarity + 0.15 * float(episode.get("importance", 0))
                    ),
                }
            )

        scored.sort(
            key=lambda item: item["retrieval_score"],
            reverse=True,
        )
        return scored[: self.settings.episodic_top_k]

    def _summary_text(
        self,
        user_id: str,
        session_id: str,
    ) -> tuple[str, str]:
        session_summary = self.repository.latest_summary(
            user_id,
            "session",
            session_id,
        )
        lifetime_summary = self.repository.latest_summary(
            user_id,
            "user",
            None,
        )

        return (
            session_summary.get("text", "") if session_summary else "",
            lifetime_summary.get("text", "") if lifetime_summary else "",
        )

    def _create_session_summary(
        self,
        user_id: str,
        session_id: str,
    ) -> CompletionLike:
        messages = self.repository.recent_messages(
            user_id,
            session_id,
            24,
        )
        previous = self.repository.latest_summary(
            user_id,
            "session",
            session_id,
        )
        prompt = (
            "Create a concise bullet summary of durable facts, "
            "preferences, decisions, exact values, and unresolved "
            "items. Correct outdated facts using newer messages.\n\n"
            f"Previous summary:\n{previous.get('text', '') if previous else 'None'}\n\n"
            f"Conversation:\n{format_messages(messages)}"
        )
        result = self.model.complete(
            [
                {
                    "role": "system",
                    "content": "You compress conversation memory accurately.",
                },
                {"role": "user", "content": prompt},
            ]
        )
        self.repository.save_summary(
            user_id,
            session_id,
            "session",
            result.content.strip(),
        )
        return result

    def _maybe_create_lifetime_summary(
        self,
        user_id: str,
    ) -> CompletionLike | None:
        count = self.repository.session_summary_count(user_id)
        interval = self.settings.lifetime_every_session_summaries

        if count == 0 or count % interval != 0:
            return None

        summaries = [
            summary
            for summary in self.repository.recent_summaries(
                user_id,
                12,
            )
            if summary.get("scope") == "session"
        ]

        if len(summaries) < interval:
            return None

        text = "\n\n".join(summary.get("text", "") for summary in summaries)
        result = self.model.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Condense session summaries into one durable "
                        "lifetime summary. Preserve exact constraints."
                    ),
                },
                {"role": "user", "content": text},
            ]
        )
        self.repository.save_summary(
            user_id,
            None,
            "user",
            result.content.strip(),
        )
        return result

    def _write_metric(self, metric: dict[str, Any]) -> None:
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)

        with (
            METRICS_LOCK,
            self.metrics_path.open(
                "a",
                encoding="utf-8",
            ) as output,
        ):
            output.write(
                json.dumps(
                    metric,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

    def chat(
        self,
        *,
        user_id: str,
        session_id: str | None,
        message: str,
        memory_mode: MemoryMode,
        policy: MemoryPolicy,
        short_term_n: int | None = None,
    ) -> dict[str, Any]:
        active_session_id = session_id or uuid.uuid4().hex
        window_size = (
            short_term_n if short_term_n is not None else self.settings.short_term_n
        )

        if message.startswith("/"):
            recent = self.repository.recent_messages(
                user_id,
                active_session_id,
                20,
            )
            reply = self.file_memory.handle_command(
                message,
                recent,
            )
            return {
                "user_id": user_id,
                "session_id": active_session_id,
                "reply": reply,
                "memory_mode": memory_mode,
                "used_memory": {
                    "command": message,
                    "file_memory_status": (self.file_memory.consolidation_status()),
                },
                "metrics": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "latency_ms": 0.0,
                },
            }

        self.repository.save_message(
            user_id,
            active_session_id,
            "user",
            message,
        )

        all_window_messages = self.repository.recent_messages(
            user_id,
            active_session_id,
            window_size + 1,
        )
        prior_messages = all_window_messages[:-1]

        if policy == MemoryPolicy.importance_eviction:
            prior_messages = importance_evict(prior_messages, keep=6)

        session_summary = ""
        lifetime_summary = ""
        query_embedding: list[float] = []
        episodes: list[dict[str, Any]] = []

        if memory_mode in (MemoryMode.mongodb, MemoryMode.hybrid):
            session_summary, lifetime_summary = self._summary_text(
                user_id,
                active_session_id,
            )
            query_embedding = self.embedder.embed(message)
            episodes = self.retrieve_episodes(
                user_id,
                query_embedding,
            )

        file_context = ""
        file_consolidation: dict[str, Any] | None = None

        if memory_mode in (MemoryMode.file, MemoryMode.hybrid):
            if self.file_memory.consolidation_status()["required"]:
                file_consolidation = self.file_memory.consolidate()

            file_context = self.file_memory.load_prompt_context()

        short_term_text = format_messages(prior_messages)
        long_term_text = (
            f"Session summary:\n{session_summary or 'None'}\n\n"
            f"Lifetime summary:\n{lifetime_summary or 'None'}"
        )
        episodic_text = (
            "\n".join(
                "- "
                f"{episode.get('fact', '')} "
                f"(similarity={episode.get('similarity', 0):.3f})"
                for episode in episodes
            )
            or "None"
        )

        system_content = (
            f"{SYSTEM_PRIMER}\n\n"
            f"{file_context}\n\n"
            f"Long-term summaries:\n{long_term_text}\n\n"
            f"Relevant episodic facts:\n{episodic_text}\n\n"
            f"Recent short-term conversation:\n{short_term_text}"
        )
        model_messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": message},
        ]

        started = time.perf_counter()
        result = self.model.complete(model_messages)
        latency_ms = (time.perf_counter() - started) * 1000
        reply = result.content.strip()

        self.repository.save_message(
            user_id,
            active_session_id,
            "assistant",
            reply,
        )

        stored_facts: list[dict[str, Any]] = []

        if memory_mode in (MemoryMode.mongodb, MemoryMode.hybrid):
            for extracted in extract_episode_facts(message):
                embedding = (
                    query_embedding
                    if extracted["fact"] == message.strip()
                    else self.embedder.embed(extracted["fact"])
                )
                stored = self.repository.save_episode(
                    user_id,
                    active_session_id,
                    extracted["fact"],
                    extracted["importance"],
                    embedding,
                )
                stored_facts.append(serialize_document(stored))

        auxiliary_results: list[CompletionLike] = []
        user_message_count = self.repository.count_user_messages(
            user_id,
            active_session_id,
        )

        if (
            memory_mode in (MemoryMode.mongodb, MemoryMode.hybrid)
            and user_message_count % self.settings.summarize_every_user_messages == 0
        ):
            auxiliary_results.append(
                self._create_session_summary(
                    user_id,
                    active_session_id,
                )
            )
            lifetime_result = self._maybe_create_lifetime_summary(user_id)

            if lifetime_result is not None:
                auxiliary_results.append(lifetime_result)

        component_text = {
            "system_primer": SYSTEM_PRIMER,
            "long_term_summary": long_term_text,
            "short_term_window": short_term_text,
            "episodic_facts": episodic_text,
            "file_memory": file_context,
            "current_message": message,
        }
        token_breakdown = allocate_prompt_tokens(
            result.input_tokens,
            component_text,
        )
        auxiliary_input_tokens = sum(item.input_tokens for item in auxiliary_results)
        auxiliary_output_tokens = sum(item.output_tokens for item in auxiliary_results)
        metric = {
            "turn_id": uuid.uuid4().hex,
            "created_at": utc_now(),
            "user_id": user_id,
            "session_id": active_session_id,
            "memory_mode": memory_mode.value,
            "policy": policy.value,
            "short_term_n": window_size,
            "prompt_tokens": result.input_tokens,
            "completion_tokens": result.output_tokens,
            "auxiliary_input_tokens": auxiliary_input_tokens,
            "auxiliary_output_tokens": auxiliary_output_tokens,
            "total_input_tokens": (result.input_tokens + auxiliary_input_tokens),
            "total_output_tokens": (result.output_tokens + auxiliary_output_tokens),
            "token_breakdown": token_breakdown,
            "latency_ms": round(latency_ms, 3),
        }
        self.repository.save_metric(metric)
        self._write_metric(metric)

        return {
            "user_id": user_id,
            "session_id": active_session_id,
            "reply": reply,
            "memory_mode": memory_mode,
            "used_memory": {
                "short_term_message_count": len(prior_messages),
                "short_term_messages": [
                    serialize_document(item) for item in prior_messages
                ],
                "session_summary": session_summary or None,
                "lifetime_summary": lifetime_summary or None,
                "episodic_facts": [
                    {
                        "fact": item.get("fact"),
                        "importance": item.get("importance"),
                        "similarity": round(
                            float(item.get("similarity", 0)),
                            6,
                        ),
                    }
                    for item in episodes
                ],
                "episodes_stored_this_turn": stored_facts,
                "file_memory_loaded": bool(file_context),
                "automatic_file_consolidation": file_consolidation,
            },
            "metrics": serialize_document(metric),
        }
