"""Deterministic offline tests for the HW10 Part 3.1 freeze workflow."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from hw10_freeze_cases import (
    EXPECTED_CASE_COUNT,
    load_existing_cases,
    load_questions,
    write_json_atomic,
    write_label_template,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HW10FreezeOfflineTests(unittest.TestCase):
    """Verify case-bank validation and human-label template behavior."""

    def test_question_bank_contains_20_unique_domain_cases(self) -> None:
        questions = load_questions(
            PROJECT_ROOT / "hw10_eval_questions.json"
        )
        self.assertEqual(len(questions), EXPECTED_CASE_COUNT)
        self.assertEqual(
            len({item["case_id"] for item in questions}),
            EXPECTED_CASE_COUNT,
        )
        self.assertTrue(
            all(item["question"].endswith("?") for item in questions)
        )

    def test_atomic_json_checkpoint_can_be_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eval_cases.json"
            payload = [
                {
                    "case_id": "case-01",
                    "question": "Question?",
                    "draft": "Draft",
                }
            ]
            write_json_atomic(path, payload)
            self.assertEqual(load_existing_cases(path), payload)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_label_template_is_blank_and_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "human_labels.csv"
            case_ids = ["case-01", "case-02"]
            write_label_template(path, case_ids)
            first_text = path.read_text(encoding="utf-8")

            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(
                [row["case_id"] for row in rows],
                case_ids,
            )
            self.assertTrue(all(row["human_score"] == "" for row in rows))

            path.write_text(
                first_text.replace("case-01,,", "case-01,5,manual"),
                encoding="utf-8",
            )
            write_label_template(path, case_ids)
            self.assertIn("case-01,5,manual", path.read_text(encoding="utf-8"))

    def test_duplicate_case_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(
                json.dumps(
                    [
                        {"case_id": "case-01"},
                        {"case_id": "case-01"},
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate case_id"):
                load_existing_cases(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
