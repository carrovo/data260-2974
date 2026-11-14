"""Deterministic offline tests for HW10 Part 4 observability."""

import unittest

from hw8_agent_logic import planner_message, reviewer_message, writer_message
from hw10_tracing import (
    LATENCY_QUESTIONS,
    experiment_question,
    make_span,
    percentile,
    summarize_latency_cases,
    trace_identity,
)

TRACE_ID = "trace-2974"


def fake_span(component: str, duration_ms: float, queue_ms: float = 0) -> dict:
    """Build one minimal successful span used by summary tests."""

    return make_span(
        trace_id=TRACE_ID,
        stage=component.lower(),
        component=component,
        start_time="2026-11-14T00:00:00+00:00",
        end_time="2026-11-14T00:00:01+00:00",
        duration_ms=duration_ms,
        queue_wait=queue_ms,
        status="ok",
    )


class HW10Part4OfflineTests(unittest.TestCase):
    """Verify trace identity, propagation, and latency calculations offline."""

    def test_trace_id_must_reuse_correlation_id(self) -> None:
        self.assertEqual(
            trace_identity({"correlation_id": TRACE_ID, "trace_id": TRACE_ID}),
            TRACE_ID,
        )
        with self.assertRaisesRegex(ValueError, "must equal"):
            trace_identity(
                {"correlation_id": TRACE_ID, "trace_id": "second-request-id"}
            )

    def test_all_three_agents_propagate_one_trace_id(self) -> None:
        inbox = {
            "correlation_id": TRACE_ID,
            "trace_id": TRACE_ID,
            "question": "What should a renter verify?",
        }
        task = planner_message(inbox, "Check the listing and written terms.")
        draft = writer_message(task, "Verify the listing and written terms.")
        final = reviewer_message(draft, "Verify the listing and written terms.")
        self.assertEqual(
            [task["trace_id"], draft["trace_id"], final["trace_id"]],
            [TRACE_ID, TRACE_ID, TRACE_ID],
        )

    def test_span_contains_assignment_required_fields(self) -> None:
        span = fake_span("PLANNER", 12.5, 3.25)
        self.assertEqual(
            {
                "trace_id",
                "stage",
                "component",
                "start_time",
                "end_time",
                "duration_ms",
                "queue_wait_ms",
                "status",
                "error",
            },
            set(span),
        )

    def test_question_bank_has_exactly_50_unique_domain_questions(self) -> None:
        self.assertEqual(len(LATENCY_QUESTIONS), 50)
        self.assertEqual(len(set(LATENCY_QUESTIONS)), 50)
        rendered = [
            experiment_question("experiment-2974", index, f"attempt-{index}")
            for index in range(1, 51)
        ]
        self.assertEqual(len(set(rendered)), 50)

    def test_percentile_uses_linear_interpolation(self) -> None:
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(percentile([1, 2, 3, 4], 95), 3.85)

    def test_summary_requires_and_reports_50_confirmed_misses(self) -> None:
        cases = []
        for index in range(50):
            spans = [
                fake_span("Cache", 10 + index),
                fake_span("PLANNER", 100 + index, 1),
                fake_span("WRITER", 200 + index, 2),
                fake_span("REVIEWER", 300 + index, 3),
                fake_span("EVALUATOR", 400 + index),
            ]
            cases.append(
                {
                    "is_cached": False,
                    "e2e_latency_ms": 1200 + index,
                    "spans": spans,
                }
            )
        summary = summarize_latency_cases(cases)
        self.assertEqual(summary["confirmed_cache_miss_count"], 50)
        self.assertEqual(summary["stages"]["planner"]["p50_ms"], 124.5)
        self.assertEqual(summary["stages"]["queue_wait_total"]["p95_ms"], 6.0)
        self.assertEqual(summary["dominant_contributor"], "evaluation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
