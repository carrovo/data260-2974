"""Offline tests for poison-message decoding and dead-letter evidence."""

import json
import unittest

from hw8_agent_common import build_dead_letter_message, decode_json_object


class PoisonMessageTests(unittest.TestCase):
    """Verify bounded-retry inputs and the DLQ record shape."""

    def test_valid_json_object_is_decoded(self) -> None:
        self.assertEqual(decode_json_object(b'{"value": 1}'), {"value": 1})

    def test_malformed_json_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid UTF-8 JSON object"):
            decode_json_object(b'{"value":')

    def test_json_array_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid UTF-8 JSON object"):
            decode_json_object(b"[]")

    def test_dead_letter_preserves_failure_context(self) -> None:
        source = {"correlation_id": "cid-2974", "question": "bad task"}
        raw_value = json.dumps(source).encode("utf-8")
        result = build_dead_letter_message(
            agent_name="WRITER",
            source_topic="s2974_tasks",
            source_partition=1,
            source_offset=7,
            attempts=3,
            error=ValueError("plan is required"),
            raw_value=raw_value,
            source=source,
        )
        self.assertEqual(result["correlation_id"], "cid-2974")
        self.assertEqual(result["failed_agent"], "WRITER")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["source_partition"], 1)
        self.assertEqual(result["source_offset"], 7)
        self.assertEqual(result["error_message"], "plan is required")
        self.assertEqual(result["original_message"], source)


if __name__ == "__main__":
    unittest.main()
