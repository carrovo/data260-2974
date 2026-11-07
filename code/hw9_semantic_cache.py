"""Redis vector semantic-response cache for DATA 260 Homework 9."""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

import numpy as np
from redis import Redis
from redis.exceptions import ResponseError

from hw9_config import PREFIX, REDIS_URL

EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
EMBEDDING_DIMENSION = 384
SEMANTIC_THRESHOLD = float(os.getenv("HW9_SEMANTIC_THRESHOLD", "0.85"))
SEMANTIC_INDEX = f"{PREFIX}:semantic:index"
SEMANTIC_KEY_PREFIX = f"{PREFIX}:semantic:entry:"
DATA_VERSION_KEY = f"{PREFIX}:semantic:data_version"


class Encoder(Protocol):
    """Small protocol that also permits deterministic offline test encoders."""

    def encode(
        self,
        sentences: str,
        *,
        normalize_embeddings: bool,
    ) -> Any: ...


@dataclass(frozen=True)
class CacheLookup:
    """Result of one nearest-neighbor cache lookup."""

    answer: str | None
    similarity: float
    matched_query: str | None
    data_version: str | None
    cache_key: str | None

    @property
    def is_hit(self) -> bool:
        return self.answer is not None


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


class SemanticResponseCache:
    """Store and search query embeddings in a Redis cosine vector index."""

    def __init__(
        self,
        redis_client: Redis | None = None,
        encoder: Encoder | None = None,
        threshold: float = SEMANTIC_THRESHOLD,
    ) -> None:
        if threshold < 0 or threshold > 1:
            raise ValueError("threshold must be between 0 and 1")
        self.redis_client = redis_client or Redis.from_url(
            REDIS_URL,
            decode_responses=False,
            protocol=2,
        )
        self._encoder = encoder
        self.threshold = threshold
        self.redis_client.ping()
        self.ensure_index()
        self.redis_client.setnx(DATA_VERSION_KEY, "1")

    @property
    def encoder(self) -> Encoder:
        """Load the local embedding model only when it is first needed."""

        if self._encoder is None:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        return self._encoder

    def ensure_index(self) -> None:
        """Create the Redis HNSW index once and tolerate later restarts."""

        try:
            self.redis_client.execute_command(
                "FT.CREATE",
                SEMANTIC_INDEX,
                "ON",
                "HASH",
                "PREFIX",
                "1",
                SEMANTIC_KEY_PREFIX,
                "SCHEMA",
                "query",
                "TEXT",
                "answer",
                "TEXT",
                "data_version",
                "TAG",
                "created_at",
                "TEXT",
                "embedding",
                "VECTOR",
                "HNSW",
                "6",
                "TYPE",
                "FLOAT32",
                "DIM",
                str(EMBEDDING_DIMENSION),
                "DISTANCE_METRIC",
                "COSINE",
            )
        except ResponseError as exc:
            if "Index already exists" not in str(exc):
                raise

    def _embedding(self, query: str) -> np.ndarray:
        value = self.encoder.encode(
            query,
            normalize_embeddings=True,
        )
        vector = np.asarray(value, dtype=np.float32)
        if vector.shape != (EMBEDDING_DIMENSION,):
            raise ValueError(
                "Expected embedding dimension "
                f"{EMBEDDING_DIMENSION}, received {vector.shape}"
            )
        return vector

    def current_data_version(self) -> str:
        """Return the application-controlled relational-data version marker."""

        value = self.redis_client.get(DATA_VERSION_KEY)
        if value is None:
            self.redis_client.set(DATA_VERSION_KEY, "1")
            return "1"
        return _decode(value)

    def bump_data_version(self) -> str:
        """Increment the marker after a relevant relational-data update."""

        return str(self.redis_client.incr(DATA_VERSION_KEY))

    def find(
        self,
        query: str,
        *,
        enforce_data_version: bool = False,
    ) -> CacheLookup:
        """Return the nearest cached answer when similarity reaches threshold."""

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query is required")
        vector = self._embedding(normalized_query)
        raw = self.redis_client.execute_command(
            "FT.SEARCH",
            SEMANTIC_INDEX,
            "(*)=>[KNN 1 @embedding $query_vector AS vector_distance]",
            "PARAMS",
            "2",
            "query_vector",
            vector.tobytes(),
            "SORTBY",
            "vector_distance",
            "ASC",
            "RETURN",
            "4",
            "query",
            "answer",
            "data_version",
            "vector_distance",
            "DIALECT",
            "2",
        )
        if not raw or int(raw[0]) == 0:
            return CacheLookup(None, 0.0, None, None, None)

        cache_key = _decode(raw[1])
        fields = raw[2]
        values = {
            _decode(fields[index]): _decode(fields[index + 1])
            for index in range(0, len(fields), 2)
        }
        distance = float(values["vector_distance"])
        similarity = max(0.0, min(1.0, 1.0 - distance))
        cached_version = values.get("data_version")

        if enforce_data_version and cached_version != self.current_data_version():
            self.redis_client.delete(cache_key)
            return CacheLookup(
                None,
                similarity,
                values.get("query"),
                cached_version,
                cache_key,
            )
        if similarity < self.threshold:
            return CacheLookup(
                None,
                similarity,
                values.get("query"),
                cached_version,
                cache_key,
            )
        return CacheLookup(
            values.get("answer"),
            similarity,
            values.get("query"),
            cached_version,
            cache_key,
        )

    def store(self, query: str, answer: str) -> tuple[str, str]:
        """Store the query, vector, final answer, and data-version marker."""

        cache_key = f"{SEMANTIC_KEY_PREFIX}{uuid4()}"
        data_version = self.current_data_version()
        self.redis_client.hset(
            cache_key,
            mapping={
                "query": query.strip(),
                "answer": answer.strip(),
                "data_version": data_version,
                "created_at": datetime.now(UTC).isoformat(),
                "embedding": self._embedding(query.strip()).tobytes(),
            },
        )
        return cache_key, data_version

    def clear_entries(self, *, reset_data_version: bool = False) -> int:
        """Delete only HW9 semantic entries, preserving all other Redis keys."""

        keys = list(self.redis_client.scan_iter(f"{SEMANTIC_KEY_PREFIX}*"))
        deleted = int(self.redis_client.delete(*keys)) if keys else 0
        if reset_data_version:
            self.redis_client.set(DATA_VERSION_KEY, "1")
        return deleted
