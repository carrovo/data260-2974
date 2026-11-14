"""Deterministic offline tests for HW10 judge-validation statistics."""

import csv
import tempfile
import unittest
from pathlib import Path

from hw10_judge import NonThinkingOllamaClient
from hw10_judge_core import (
    build_case_rows,
    load_human_labels,
    normalized_to_five_point,
    rank_with_ties,
    spearman_correlation,
    summarize_judge_runs,
)


class HW10JudgeCoreTests(unittest.TestCase):
    """Verify agreement, ties, repeatability, and label validation."""

    def test_ollama_wrapper_disables_thinking(self) -> None:
        class FakeClient:
            def chat(self, *args: object, **kwargs: object) -> dict[str, object]:
                return {"args": args, **kwargs}

        wrapped = NonThinkingOllamaClient(FakeClient())
        result = wrapped.chat(
            model="qwen3:8b",
            messages=[],
            think=True,
        )
        self.assertEqual(result["think"], False)

    def test_rank_with_ties_uses_average_rank(self) -> None:
        self.assertEqual(rank_with_ties([4, 4, 5, 5]), [1.5, 1.5, 3.5, 3.5])

    def test_normalized_geval_score_recovers_five_point_rubric(self) -> None:
        self.assertEqual(normalized_to_five_point(0.0), 1)
        self.assertEqual(normalized_to_five_point(0.25), 2)
        self.assertEqual(normalized_to_five_point(0.5), 3)
        self.assertEqual(normalized_to_five_point(0.75), 4)
        self.assertEqual(normalized_to_five_point(1.0), 5)
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            normalized_to_five_point(1.1)

    def test_spearman_is_one_for_identical_tied_rankings(self) -> None:
        self.assertAlmostEqual(
            spearman_correlation([4, 4, 5, 5], [4, 4, 5, 5]) or 0,
            1.0,
        )

    def test_repeatability_summary_counts_score_changes(self) -> None:
        case_ids = ["case-01", "case-02"]
        labels = {"case-01": 4, "case-02": 5}
        runs = [
            {"case-01": 4, "case-02": 5},
            {"case-01": 4, "case-02": 5},
            {"case-01": 5, "case-02": 5},
        ]
        summary = summarize_judge_runs(case_ids, labels, runs)
        repeatability = summary["repeatability"]
        self.assertEqual(repeatability["changed_case_count"], 1)
        self.assertEqual(repeatability["changed_case_rate"], 0.5)
        self.assertEqual(
            repeatability["changed_pairwise_comparison_count"],
            2,
        )
        self.assertAlmostEqual(
            repeatability["mean_absolute_score_change"],
            1 / 3,
        )
        self.assertEqual(repeatability["maximum_absolute_score_change"], 1)

    def test_case_rows_retain_all_raw_scores(self) -> None:
        rows = build_case_rows(
            ["case-01"],
            {"case-01": 5},
            [
                {"case-01": 4},
                {"case-01": 5},
                {"case-01": 5},
            ],
        )
        self.assertEqual(rows[0]["judge_run_1"], 4)
        self.assertEqual(rows[0]["judge_run_2"], 5)
        self.assertEqual(rows[0]["judge_run_3"], 5)
        self.assertTrue(rows[0]["score_changed"])
        self.assertAlmostEqual(rows[0]["judge_mean"], 14 / 3)

    def test_out_of_range_human_label_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["case_id", "human_score", "notes"],
                )
                writer.writeheader()
                writer.writerow({"case_id": "case-01", "human_score": 6, "notes": ""})
            with self.assertRaisesRegex(ValueError, "between 1 and 5"):
                load_human_labels(path, ["case-01"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
