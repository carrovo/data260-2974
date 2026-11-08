"""Offline tests for the HW9 Part 4 four-variant metrics."""

import unittest

from hw9_part4_variants import summarize_results


class Part4VariantMetricTests(unittest.TestCase):
    """Verify final correctness, attempt, and latency aggregation."""

    def test_summary_metrics(self) -> None:
        rows = [
            {
                "final_evaluation": "PASS",
                "attempt_count": 1,
                "latency_ms": 10.0,
            },
            {
                "final_evaluation": "REVISE",
                "attempt_count": 2,
                "latency_ms": 30.0,
            },
            {
                "final_evaluation": "PASS",
                "attempt_count": 2,
                "latency_ms": 20.0,
            },
        ]

        summary = summarize_results(rows)

        self.assertEqual(summary["correct_answers"], 2)
        self.assertEqual(summary["incorrect_answers"], 1)
        self.assertEqual(summary["average_attempts"], 1.67)
        self.assertEqual(summary["average_latency_ms"], 20.0)

    def test_empty_results_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            summarize_results([])


if __name__ == "__main__":
    unittest.main(verbosity=2)
