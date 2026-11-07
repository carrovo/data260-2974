"""Offline metric tests for the HW9 Part 3 threshold sweep."""

import unittest

from hw9_part3_cost import analyze_summaries, calculate_total_cost
from hw9_part3_sweep import calculate_metrics


class ThresholdMetricTests(unittest.TestCase):
    """Verify the required hit and false-hit rate denominators."""

    def test_metric_calculation(self) -> None:
        rows = [
            {
                "expected_hit": True,
                "predicted_hit": True,
                "latency_ms": 10.0,
            },
            {
                "expected_hit": True,
                "predicted_hit": False,
                "latency_ms": 20.0,
            },
            {
                "expected_hit": False,
                "predicted_hit": True,
                "latency_ms": 30.0,
            },
            {
                "expected_hit": False,
                "predicted_hit": False,
                "latency_ms": 40.0,
            },
        ]

        metrics = calculate_metrics(rows)

        self.assertEqual(metrics["case_count"], 4)
        self.assertEqual(metrics["hit_count"], 2)
        self.assertEqual(metrics["hit_rate_pct"], 50.0)
        self.assertEqual(metrics["false_hit_count"], 1)
        self.assertEqual(metrics["false_hit_rate_pct"], 50.0)
        self.assertEqual(metrics["false_miss_count"], 1)
        self.assertEqual(metrics["correct_count"], 2)
        self.assertEqual(metrics["accuracy_pct"], 50.0)
        self.assertEqual(metrics["mean_latency_ms"], 25.0)

    def test_empty_rows_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one"):
            calculate_metrics([])

    def test_cost_model_selects_point_nine(self) -> None:
        summaries = [
            {
                "threshold": 0.90,
                "case_count": 40,
                "hit_count": 12,
                "false_hit_count": 1,
                "accuracy_pct": 75.0,
            },
            {
                "threshold": 0.95,
                "case_count": 40,
                "hit_count": 11,
                "false_hit_count": 1,
                "accuracy_pct": 72.5,
            },
        ]

        analyzed, selected = analyze_summaries(summaries)

        self.assertEqual(analyzed[0]["total_cost_dollars"], 2.56)
        self.assertEqual(analyzed[1]["total_cost_dollars"], 2.58)
        self.assertEqual(selected["threshold"], 0.90)

    def test_invalid_cost_counts_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "hit_count"):
            calculate_total_cost(
                case_count=40,
                hit_count=41,
                false_hit_count=0,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
