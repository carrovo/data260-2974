"""Offline tests for the HW10 Part 2 correlated evaluator."""

import tempfile
import unittest
from pathlib import Path

from hw10_part2_evaluator import (
    DRAFTS_TOPIC,
    FINAL_TOPIC,
    METRIC_KEYS,
    TASKS_TOPIC,
    load_result,
    validate_pipeline_capture,
)

CORRELATION_ID = "hw10-part2-test-2974"
QUESTION = "What should a renter verify before paying a fee?"


def sample_messages() -> dict[str, dict[str, str]]:
    """Return one valid correlated three-stage capture."""

    return {
        TASKS_TOPIC: {
            "correlation_id": CORRELATION_ID,
            "stage": "planned",
            "question": QUESTION,
            "plan": "Verify the listing, fee terms, and payment recipient.",
        },
        DRAFTS_TOPIC: {
            "correlation_id": CORRELATION_ID,
            "stage": "drafted",
            "question": QUESTION,
            "plan": "Verify the listing, fee terms, and payment recipient.",
            "draft": "Confirm the listing and written fee terms first.",
        },
        FINAL_TOPIC: {
            "correlation_id": CORRELATION_ID,
            "status": "approved",
            "answer": "Confirm the listing, recipient, amount, and refund policy.",
        },
    }


class HW10Part2OfflineTests(unittest.TestCase):
    """Verify correlation, field preservation, metrics, and checkpoints."""

    def test_capture_extracts_all_three_stages(self) -> None:
        capture = validate_pipeline_capture(
            CORRELATION_ID,
            QUESTION,
            sample_messages(),
        )
        self.assertEqual(capture["correlation_id"], CORRELATION_ID)
        self.assertIn("Verify the listing", capture["plan"])
        self.assertIn("written fee terms", capture["draft"])
        self.assertIn("refund policy", capture["final_answer"])
        self.assertEqual(len(capture["raw_messages"]), 3)

    def test_mismatched_correlation_id_is_rejected(self) -> None:
        messages = sample_messages()
        messages[FINAL_TOPIC]["correlation_id"] = "different-id"
        with self.assertRaisesRegex(ValueError, "different correlation_id"):
            validate_pipeline_capture(CORRELATION_ID, QUESTION, messages)

    def test_changed_plan_is_rejected(self) -> None:
        messages = sample_messages()
        messages[DRAFTS_TOPIC]["plan"] = "A different plan"
        with self.assertRaisesRegex(ValueError, "preserve the Planner plan"):
            validate_pipeline_capture(CORRELATION_ID, QUESTION, messages)

    def test_required_metric_names_are_exact(self) -> None:
        self.assertEqual(
            METRIC_KEYS,
            (
                "plan_quality",
                "writer_helpfulness",
                "final_answer_helpfulness",
                "final_vs_draft_improvement",
            ),
        )

    def test_checkpoint_with_different_question_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(
                '{"question":"other","metrics":{}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "different question"):
                load_result(path, QUESTION)


if __name__ == "__main__":
    unittest.main(verbosity=2)
