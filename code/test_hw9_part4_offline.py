"""Offline tests for the HW9 Part 4 two-agent workflow."""

import json
import tempfile
import unittest
from pathlib import Path

from hw9_part4_agents import (
    LessonStore,
    ReferenceStore,
    TwoAgentSystem,
    load_inputs,
)
from hw9_part4_validation import decide_validation


def fake_model_runner(system_prompt: str, user_prompt: str) -> str:
    """Return deterministic text without requiring Ollama."""

    if "Evaluator Agent" in system_prompt:
        return "The answer was checked against the supplied ground truth."
    if "S2974-000004" in user_prompt:
        return "Listing S2974-000004 has monthly rent of $1,700.00."
    if "S2974-000005" in user_prompt:
        return "Listing S2974-000005 has monthly rent of $1,750.00."
    return "A concise general rental answer."


class Part4AgentTests(unittest.TestCase):
    """Verify split safety, grounded evaluation, and the two-attempt limit."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        lesson_path = Path(self.temporary_directory.name) / "lessons.json"
        lesson_path.write_text('{"lessons": []}\n')
        self.lesson_store = LessonStore(lesson_path)
        self.reference_store = ReferenceStore()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_input_splits_do_not_contain_expected_answers(self) -> None:
        for filename in (
            "training_data.json",
            "validation_data.json",
            "test_data.json",
        ):
            rows = load_inputs(Path(filename))
            self.assertTrue(rows)
            self.assertTrue(
                all(set(row) == {"question_id", "question"} for row in rows)
            )

    def test_controlled_failure_is_repaired_on_second_attempt(self) -> None:
        system = TwoAgentSystem(
            reference_store=self.reference_store,
            lesson_store=self.lesson_store,
            model_runner=fake_model_runner,
        )
        item = load_inputs(Path("training_data.json"))[0]
        result = system.run(
            item,
            allow_revision=True,
            use_lessons=False,
            controlled_incomplete=True,
        )
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["attempts"][0]["evaluation"], "REVISE")
        self.assertEqual(result["final_evaluation"], "PASS")

    def test_system_stops_after_two_failed_attempts(self) -> None:
        def always_incomplete(_system: str, _user: str) -> str:
            return "The exact listing facts are unavailable."

        system = TwoAgentSystem(
            reference_store=self.reference_store,
            lesson_store=self.lesson_store,
            model_runner=always_incomplete,
        )
        item = load_inputs(Path("training_data.json"))[0]
        result = system.run(
            item,
            allow_revision=True,
            use_lessons=False,
        )
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["final_evaluation"], "REVISE")

    def test_relevant_lesson_is_loaded_and_counted(self) -> None:
        lesson = {
            "lesson_id": "lesson_001",
            "failure_pattern": "Listing answers omit exact values.",
            "correction": "Use the exact listing reference facts.",
            "created_at": "2026-11-07",
            "use_count": 0,
            "keywords": ["listing", "rent"],
            "use_reference_facts": True,
        }
        self.lesson_store.save([lesson])
        matched = self.lesson_store.relevant(
            "What is the rent for this listing?",
            increment_use=True,
        )
        self.assertEqual([row["lesson_id"] for row in matched], ["lesson_001"])
        saved = json.loads(self.lesson_store.path.read_text())
        self.assertEqual(saved["lessons"][0]["use_count"], 1)

    def test_validation_gate_keeps_only_safe_improvement(self) -> None:
        before = [
            {
                "question_id": "validation_01",
                "final_evaluation": "REVISE",
                "final_answer": "Missing listing facts.",
            },
            {
                "question_id": "validation_03",
                "final_evaluation": "PASS",
                "final_answer": "Keep written maintenance records.",
            },
        ]
        after = [
            {
                "question_id": "validation_01",
                "final_evaluation": "PASS",
                "final_answer": "S2974-000004 costs $1,700.00.",
            },
            {
                "question_id": "validation_03",
                "final_evaluation": "PASS",
                "final_answer": "Keep written maintenance records.",
            },
        ]
        decision = decide_validation(before, after)
        self.assertTrue(decision["keep_lesson"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
