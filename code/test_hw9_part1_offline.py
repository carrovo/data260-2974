"""Offline unit test for the HW9 Part 1 counter algorithm."""

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault(
    "DATABASE_URL",
    "sqlite+pysqlite:///:memory:",
)

from hw9_cache import DatabaseCache  # noqa: E402


class FakeRedis:
    """Minimal Redis substitute for deterministic offline testing."""

    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def set(
        self,
        key: str,
        value: int,
        *,
        nx: bool = False,
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = int(value)
        return True

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]


class FakeSession:
    """Track database syncs without requiring MySQL."""

    def __init__(self) -> None:
        self.listing = SimpleNamespace(id=1, viewCount=0)
        self.commit_count = 0
        self.persisted_counts: list[int] = []

    def get(self, model, listing_id: int):
        del model
        if listing_id != self.listing.id:
            return None
        return self.listing

    def commit(self) -> None:
        self.commit_count += 1
        self.persisted_counts.append(self.listing.viewCount)

    def refresh(self, listing) -> None:
        del listing


class Part1CounterTests(unittest.TestCase):
    def test_twenty_five_accesses_sync_at_ten_and_twenty(self) -> None:
        db = FakeSession()
        redis_client = FakeRedis()
        cache = DatabaseCache(db, redis_client)

        observed = [
            cache.increment_listing_views(1)
            for _ in range(25)
        ]

        self.assertEqual(observed, list(range(1, 26)))
        self.assertEqual(db.commit_count, 2)
        self.assertEqual(db.persisted_counts, [10, 20])
        self.assertEqual(db.listing.viewCount, 20)
        self.assertEqual(
            redis_client.values["s2974:views:listing:1"],
            25,
        )

    def test_missing_listing_is_rejected(self) -> None:
        db = FakeSession()
        cache = DatabaseCache(db, FakeRedis())

        with self.assertRaises(LookupError):
            cache.increment_listing_views(999)


if __name__ == "__main__":
    unittest.main(verbosity=2)
