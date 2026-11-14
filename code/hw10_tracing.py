"""Pure helpers for HW10 distributed tracing and latency analysis."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Iterable

QUESTION_TOPICS = (
    "application fees",
    "security deposits",
    "lease renewal notices",
    "move-in inspections",
    "maintenance requests",
    "roommate agreements",
    "utility charges",
    "parking terms",
    "renter insurance",
    "move-out records",
)
QUESTION_CONTEXTS = (
    "before submitting an application",
    "before signing a lease",
    "during the first week of tenancy",
    "when comparing two rental offers",
    "before ending a tenancy",
)
LATENCY_QUESTIONS = tuple(
    f"What should a renter document about {topic} {context}?"
    for topic in QUESTION_TOPICS
    for context in QUESTION_CONTEXTS
)


def experiment_question(
    experiment_id: str,
    case_number: int,
    attempt_id: str,
) -> str:
    """Return one intentionally uncached but human-readable domain question."""

    if case_number < 1 or case_number > len(LATENCY_QUESTIONS):
        raise ValueError("case_number must be between 1 and 50")
    base = LATENCY_QUESTIONS[case_number - 1]
    return (
        f"{base} [HW10 experiment {experiment_id[:8]}, "
        f"case {case_number:02d}, attempt {attempt_id[:8]}]"
    )


def utc_now() -> str:
    """Return a timezone-aware ISO-8601 UTC timestamp."""

    return datetime.now(UTC).isoformat()


def trace_identity(message: dict[str, Any]) -> str:
    """Return the one request identity and reject a second conflicting ID."""

    correlation_id = message.get("correlation_id")
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise ValueError("correlation_id is required")
    correlation_id = correlation_id.strip()
    trace_id = message.get("trace_id", correlation_id)
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("trace_id is required")
    trace_id = trace_id.strip()
    if trace_id != correlation_id:
        raise ValueError("trace_id must equal correlation_id")
    return trace_id


def parse_timestamp(value: object) -> datetime | None:
    """Parse a timezone-aware ISO timestamp, returning None when absent."""

    if not isinstance(value, str) or not value.strip():
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("published_at must include a timezone")
    return parsed.astimezone(UTC)


def queue_wait_ms(message: dict[str, Any], started_at: str) -> float:
    """Measure time between the previous publish and this stage start."""

    published = parse_timestamp(message.get("published_at"))
    started = parse_timestamp(started_at)
    if published is None or started is None:
        return 0.0
    return round(max(0.0, (started - published).total_seconds() * 1000), 2)


def make_span(
    *,
    trace_id: str,
    stage: str,
    component: str,
    start_time: str,
    end_time: str,
    duration_ms: float,
    status: str,
    error: str | None = None,
    queue_wait: float = 0.0,
    cache_status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one assignment-compliant structured JSON span."""

    if not trace_id.strip():
        raise ValueError("trace_id is required")
    if not stage.strip():
        raise ValueError("stage is required")
    if status not in {"ok", "error"}:
        raise ValueError("status must be ok or error")
    if duration_ms < 0 or queue_wait < 0:
        raise ValueError("span timings cannot be negative")
    span: dict[str, Any] = {
        "trace_id": trace_id,
        "stage": stage,
        "component": component,
        "start_time": start_time,
        "end_time": end_time,
        "duration_ms": round(float(duration_ms), 2),
        "queue_wait_ms": round(float(queue_wait), 2),
        "status": status,
        "error": error,
    }
    if cache_status is not None:
        if cache_status not in {"hit", "miss"}:
            raise ValueError("cache_status must be hit or miss")
        span["cache_status"] = cache_status
    if metadata:
        span["metadata"] = metadata
    return span


def percentile(values: Iterable[float], percent: float) -> float:
    """Return an interpolated percentile without a third-party dependency."""

    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("at least one value is required")
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 2)
    fraction = position - lower
    return round(
        ordered[lower] + (ordered[upper] - ordered[lower]) * fraction,
        2,
    )


def summarize_latency_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize exactly the required Part 4 stage and queue measurements."""

    if len(cases) != 50:
        raise ValueError("latency experiment requires exactly 50 cache misses")

    stage_components = {
        "cache_lookup": "Cache",
        "planner": "PLANNER",
        "writer": "WRITER",
        "reviewer": "REVIEWER",
        "evaluation": "EVALUATOR",
    }
    stage_values: dict[str, list[float]] = {key: [] for key in stage_components}
    queue_values: list[float] = []
    e2e_values: list[float] = []

    for case in cases:
        if case.get("is_cached") is not False:
            raise ValueError("all 50 experiment cases must be confirmed misses")
        spans = case.get("spans")
        if not isinstance(spans, list):
            raise ValueError("each case must contain spans")
        by_component = {
            str(span.get("component")): span
            for span in spans
            if span.get("status") == "ok"
        }
        for key, component in stage_components.items():
            span = by_component.get(component)
            if span is None:
                raise ValueError(f"case is missing successful {component} span")
            stage_values[key].append(float(span["duration_ms"]))
        queue_values.append(
            sum(
                float(span.get("queue_wait_ms", 0.0))
                for span in spans
                if span.get("component") in {"PLANNER", "WRITER", "REVIEWER"}
            )
        )
        e2e_values.append(float(case["e2e_latency_ms"]))

    mean_e2e = sum(e2e_values) / len(e2e_values)
    rows: dict[str, dict[str, float]] = {}
    for key, values in stage_values.items():
        mean_value = sum(values) / len(values)
        rows[key] = {
            "p50_ms": percentile(values, 50),
            "p95_ms": percentile(values, 95),
            "mean_ms": round(mean_value, 2),
            "mean_percent_of_cache_miss_e2e": round(
                mean_value / mean_e2e * 100,
                2,
            ),
        }
    mean_queue = sum(queue_values) / len(queue_values)
    rows["queue_wait_total"] = {
        "p50_ms": percentile(queue_values, 50),
        "p95_ms": percentile(queue_values, 95),
        "mean_ms": round(mean_queue, 2),
        "mean_percent_of_cache_miss_e2e": round(
            mean_queue / mean_e2e * 100,
            2,
        ),
    }
    dominant_key = max(
        ("planner", "writer", "reviewer", "queue_wait_total", "evaluation"),
        key=lambda key: rows[key]["mean_ms"],
    )
    recommendations = {
        "planner": "Shorten the Planner prompt or use a smaller planning model.",
        "writer": "Reduce Writer output tokens or use a faster drafting model.",
        "reviewer": "Use a shorter review prompt or skip review for low-risk drafts.",
        "queue_wait_total": "Scale consumers or rebalance Kafka partitions.",
        "evaluation": "Run evaluation asynchronously or sample production requests.",
    }
    return {
        "confirmed_cache_miss_count": len(cases),
        "cache_miss_e2e": {
            "p50_ms": percentile(e2e_values, 50),
            "p95_ms": percentile(e2e_values, 95),
            "mean_ms": round(mean_e2e, 2),
        },
        "stages": rows,
        "dominant_contributor": dominant_key,
        "optimization_recommendation": recommendations[dominant_key],
    }
