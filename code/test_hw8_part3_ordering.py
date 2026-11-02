"""Offline tests for the HW8 partition-key ordering experiment."""

import unittest

from hw8_config import VERIFY_SEED
from hw8_ordering import (
    ENTITY_KEY_MODE,
    NO_KEY_MODE,
    build_ordering_messages,
    ordering_message_key,
    summarize_ordering_run,
)


class OrderingTests(unittest.TestCase):
    """Verify deterministic messages, key choice, and order metrics."""

    def test_messages_are_deterministic_from_verify_seed(self) -> None:
        first = build_ordering_messages("run-1", NO_KEY_MODE)
        second = build_ordering_messages("run-1", NO_KEY_MODE)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 20)
        self.assertEqual(first[0]["verify_seed"], VERIFY_SEED)
        self.assertEqual(len({item["entity_id"] for item in first}), 1)

    def test_no_key_mode_has_no_message_key(self) -> None:
        message = build_ordering_messages("run-1", NO_KEY_MODE, 1)[0]
        self.assertIsNone(ordering_message_key(message, NO_KEY_MODE))

    def test_entity_key_is_stable_for_related_messages(self) -> None:
        messages = build_ordering_messages("run-1", ENTITY_KEY_MODE, 3)
        keys = {
            ordering_message_key(message, ENTITY_KEY_MODE)
            for message in messages
        }
        self.assertEqual(keys, {messages[0]["entity_id"].encode("utf-8")})

    def test_summary_detects_cross_partition_reordering(self) -> None:
        sent = [
            {"sequence": 1, "entity_id": "p1", "key": None, "partition": 0},
            {"sequence": 2, "entity_id": "p1", "key": None, "partition": 1},
            {"sequence": 3, "entity_id": "p1", "key": None, "partition": 0},
        ]
        processed = [
            {"sequence": 2, "source_partition": 1, "writer_instance": "b"},
            {"sequence": 1, "source_partition": 0, "writer_instance": "a"},
            {"sequence": 3, "source_partition": 0, "writer_instance": "a"},
        ]
        result = summarize_ordering_run(sent, processed)
        self.assertEqual(result["partitions_used"], [0, 1])
        self.assertEqual(result["writer_instance_count_used"], 2)
        self.assertFalse(result["global_order_preserved"])
        self.assertTrue(result["per_partition_order_preserved"])

    def test_summary_detects_entity_key_order(self) -> None:
        sent = [
            {"sequence": value, "entity_id": "p1", "key": "p1", "partition": 1}
            for value in (1, 2, 3)
        ]
        processed = [
            {
                "sequence": value,
                "source_partition": 1,
                "writer_instance": "a",
            }
            for value in (1, 2, 3)
        ]
        result = summarize_ordering_run(sent, processed)
        self.assertEqual(result["partition_count_used"], 1)
        self.assertTrue(result["global_order_preserved"])


if __name__ == "__main__":
    unittest.main()
