"""Deterministic offline tests for HW8 Part 2 message transformations."""

import unittest

from hw8_agent_logic import (
    planner_message,
    planner_prompt,
    reviewer_message,
    reviewer_prompt,
    writer_message,
    writer_prompt,
)

CORRELATION_ID = "part2-correlation-2974"


class Part2AgentLogicTests(unittest.TestCase):
    """Verify the three pipeline stages without Kafka or an LLM."""

    def test_complete_pipeline_preserves_correlation_id(self) -> None:
        inbox = {
            "correlation_id": CORRELATION_ID,
            "question": "What should a renter verify?",
        }
        task = planner_message(inbox, "1. Check price. 2. Check terms.")
        draft = writer_message(task, "Verify the price and lease terms.")
        final = reviewer_message(draft, "Verify the price and lease terms.")

        self.assertEqual(task["correlation_id"], CORRELATION_ID)
        self.assertEqual(draft["correlation_id"], CORRELATION_ID)
        self.assertEqual(final["correlation_id"], CORRELATION_ID)
        self.assertEqual(final["status"], "approved")
        self.assertEqual(final["answer"], "Verify the price and lease terms.")

    def test_planner_prompt_contains_question(self) -> None:
        prompt = planner_prompt(
            {
                "correlation_id": CORRELATION_ID,
                "question": "Is the listing available?",
            }
        )
        self.assertIn("Is the listing available?", prompt)

    def test_writer_prompt_contains_question_and_plan(self) -> None:
        prompt = writer_prompt(
            {
                "correlation_id": CORRELATION_ID,
                "question": "Is the listing available?",
                "plan": "Confirm the availability date.",
            }
        )
        self.assertIn("Is the listing available?", prompt)
        self.assertIn("Confirm the availability date.", prompt)

    def test_reviewer_prompt_contains_draft(self) -> None:
        prompt = reviewer_prompt(
            {
                "correlation_id": CORRELATION_ID,
                "question": "Is the listing available?",
                "draft": "Ask the manager about the date.",
            }
        )
        self.assertIn("Ask the manager about the date.", prompt)

    def test_missing_required_field_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "question is required"):
            planner_prompt({"correlation_id": CORRELATION_ID})

    def test_final_json_has_required_fields(self) -> None:
        final = reviewer_message(
            {
                "correlation_id": CORRELATION_ID,
                "question": "Question",
                "draft": "Draft",
            },
            "Final answer",
        )
        self.assertEqual(
            set(final),
            {"correlation_id", "status", "answer"},
        )


if __name__ == "__main__":
    unittest.main()
