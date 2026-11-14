"""Offline validation for the HW10 Streamlit dashboard data model."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hw10_dashboard_core import load_dashboard_bundle, trace_span_rows

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = PROJECT_ROOT / "reports" / "hw10" / "raw"


class HW10DashboardOfflineTests(unittest.TestCase):
    """Lock dashboard calculations to the committed HW10 evidence."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = load_dashboard_bundle(REPORT_ROOT)

    def test_summary_counts_every_saved_trace(self) -> None:
        summary = self.bundle["request_summary"]
        self.assertEqual(summary["request_count"], 53)
        self.assertEqual(summary["cache_hit_count"], 1)
        self.assertEqual(summary["cache_miss_count"], 52)
        self.assertEqual(summary["error_count"], 1)
        self.assertAlmostEqual(summary["cache_hit_rate"], 1 / 53)
        self.assertAlmostEqual(summary["error_rate"], 1 / 53)
        self.assertIsNotNone(summary["window_start"])
        self.assertIsNotNone(summary["window_end"])
        self.assertEqual(len(summary["metric_sources"]), 4)

    def test_part2_scores_and_coordination_interpretation(self) -> None:
        rows = self.bundle["evaluation_rows"]
        self.assertEqual(
            [row["score_1_to_5"] for row in rows],
            [3, 4, 4, 3],
        )
        interpretation = self.bundle["coordination_interpretation"]
        self.assertIn("no measurable Reviewer refinement", interpretation)
        self.assertIn("approval pass", interpretation)

    def test_part3_validation_metrics_are_preserved(self) -> None:
        judge = self.bundle["judge_summary"]
        agreement = judge["agreement_using_mean_judge_score"]
        repeatability = judge["repeatability"]
        self.assertEqual(judge["case_count"], 20)
        self.assertEqual(judge["run_count"], 3)
        self.assertAlmostEqual(
            agreement["spearman_correlation"],
            0.050251890762960605,
        )
        self.assertAlmostEqual(agreement["mean_absolute_difference"], 0.45)
        self.assertEqual(repeatability["changed_case_count"], 0)
        self.assertFalse(
            judge["deployment_gate_recommendation"][
                "trust_to_gate_deployment"
            ]
        )
        self.assertEqual(len(self.bundle["judge_cases"]), 20)

    def test_required_trace_examples_have_distinct_paths(self) -> None:
        required = self.bundle["required_trace_examples"]
        self.assertEqual(
            [row["example"] for row in required],
            ["Cache hit", "Successful cache miss", "Failed trace"],
        )
        self.assertEqual(required[0]["path"], "cache_lookup")
        self.assertEqual(
            required[1]["path"],
            "cache_lookup → inbox → tasks → drafts → final → evaluator",
        )
        self.assertEqual(required[2]["path"], "cache_lookup → tasks")

    def test_trace_lookup_orders_spans_and_keeps_errors(self) -> None:
        examples = self.bundle["trace_examples"]
        failed_id = examples["failed_trace"]["trace_id"]
        failed = self.bundle["trace_index"][failed_id]
        rows = trace_span_rows(failed)
        self.assertEqual([row["stage"] for row in rows], ["cache_lookup", "tasks"])
        self.assertEqual(failed["cache_status"], "miss")
        self.assertEqual(failed["request_status"], "error")
        self.assertEqual(failed["failing_stage"], "tasks")
        self.assertIn("plan is required", failed["error"])
        self.assertEqual(rows[-1]["status"], "error")

    def test_missing_evidence_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "required dashboard"):
                load_dashboard_bundle(Path(directory))


if __name__ == "__main__":
    unittest.main()
