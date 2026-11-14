"""Pure evidence loading and presentation logic for the HW10 dashboard."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from hw10_tracing import percentile

STAGE_ORDER = {
    "cache_lookup": 0,
    "inbox": 1,
    "tasks": 2,
    "drafts": 3,
    "final": 4,
    "evaluator": 5,
}

PART2_METRIC_PRESENTATION = (
    ("plan_quality", "Planner", "Plan Quality"),
    ("writer_helpfulness", "Writer", "Writer Helpfulness"),
    ("final_answer_helpfulness", "Reviewer", "Final Answer Helpfulness"),
    (
        "final_vs_draft_improvement",
        "Reviewer vs Writer",
        "Final-vs-Draft Improvement",
    ),
)


def read_json(path: Path) -> dict[str, Any]:
    """Read one required JSON object with a source-specific error."""

    if not path.exists():
        raise FileNotFoundError(f"required dashboard evidence is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"dashboard evidence must be a JSON object: {path}")
    return payload


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read one required CSV into plain dictionaries."""

    if not path.exists():
        raise FileNotFoundError(f"required dashboard evidence is missing: {path}")
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO timestamp when one is present."""

    if not isinstance(value, str) or not value.strip():
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("trace timestamps must include a timezone")
    return parsed


def span_envelope_latency_ms(spans: list[dict[str, Any]]) -> float:
    """Derive request latency from the first span start to last span end."""

    starts = [
        parsed
        for span in spans
        if (parsed := parse_timestamp(span.get("start_time"))) is not None
    ]
    ends = [
        parsed
        for span in spans
        if (parsed := parse_timestamp(span.get("end_time"))) is not None
    ]
    if not starts or not ends:
        return 0.0
    return round(max(0.0, (max(ends) - min(starts)).total_seconds() * 1000), 2)


def cache_status_for(record: dict[str, Any]) -> str:
    """Return hit or miss using the explicit cache span when possible."""

    for span in record.get("spans", []):
        status = span.get("cache_status")
        if status in {"hit", "miss"}:
            return str(status)
    return "hit" if record.get("is_cached") is True else "miss"


def request_status_for(record: dict[str, Any]) -> str:
    """Collapse span statuses into one request-level status."""

    return (
        "error"
        if any(span.get("status") == "error" for span in record.get("spans", []))
        else "ok"
    )


def e2e_latency_for(record: dict[str, Any]) -> float:
    """Use the recorded E2E metric or derive a failed-trace envelope."""

    if isinstance(record.get("e2e_latency_ms"), (int, float)):
        return round(float(record["e2e_latency_ms"]), 2)
    if isinstance(record.get("cache_hit_latency_ms"), (int, float)):
        return round(float(record["cache_hit_latency_ms"]), 2)
    return span_envelope_latency_ms(list(record.get("spans", [])))


def normalize_trace_record(
    record: dict[str, Any],
    *,
    source: str,
    trace_kind: str,
) -> dict[str, Any]:
    """Add dashboard metadata without changing the saved raw trace."""

    trace_id = record.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id:
        raise ValueError(f"trace record from {source} is missing trace_id")
    spans = record.get("spans")
    if not isinstance(spans, list) or not spans:
        raise ValueError(f"trace {trace_id} has no spans")
    normalized = dict(record)
    normalized.update(
        {
            "source": source,
            "trace_kind": trace_kind,
            "cache_status": cache_status_for(record),
            "request_status": request_status_for(record),
            "dashboard_e2e_latency_ms": e2e_latency_for(record),
        }
    )
    return normalized


def build_trace_index(
    trace_examples: dict[str, Any],
    latency_experiment: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Index the three required examples plus all 50 latency traces."""

    index: dict[str, dict[str, Any]] = {}
    example_specs = (
        ("cache_hit", "Required cache hit"),
        ("successful_cache_miss", "Required successful cache miss"),
        ("failed_trace", "Required failed trace"),
    )
    for key, label in example_specs:
        raw = trace_examples.get(key)
        if not isinstance(raw, dict):
            raise ValueError(f"trace examples are missing {key}")
        normalized = normalize_trace_record(
            raw,
            source="part4_trace_examples.json",
            trace_kind=label,
        )
        index[normalized["trace_id"]] = normalized

    cases = latency_experiment.get("cases")
    if not isinstance(cases, list):
        raise ValueError("latency experiment cases are missing")
    for position, raw in enumerate(cases, start=1):
        if not isinstance(raw, dict):
            raise ValueError("latency experiment case must be an object")
        normalized = normalize_trace_record(
            raw,
            source="part4_latency_experiment.json",
            trace_kind=f"Latency experiment case {position:02d}",
        )
        trace_id = normalized["trace_id"]
        if trace_id in index:
            raise ValueError(f"duplicate trace_id in dashboard evidence: {trace_id}")
        index[trace_id] = normalized
    return index


def trace_span_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one trace journey in the required logical stage order."""

    rows = []
    for span in record.get("spans", []):
        rows.append(
            {
                "stage": span.get("stage"),
                "component": span.get("component"),
                "start_time": span.get("start_time"),
                "end_time": span.get("end_time"),
                "duration_ms": span.get("duration_ms"),
                "queue_wait_ms": span.get("queue_wait_ms", 0.0),
                "status": span.get("status"),
                "error": span.get("error"),
                "cache_status": span.get("cache_status"),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            STAGE_ORDER.get(str(row["stage"]), 999),
            str(row.get("start_time") or ""),
        ),
    )


def summarize_requests(
    trace_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Calculate the required recent-request operational summary."""

    if not trace_index:
        raise ValueError("at least one trace is required")
    records = list(trace_index.values())
    request_count = len(records)
    hit_count = sum(record["cache_status"] == "hit" for record in records)
    miss_count = request_count - hit_count
    error_count = sum(record["request_status"] == "error" for record in records)
    latencies = [float(record["dashboard_e2e_latency_ms"]) for record in records]

    starts: list[datetime] = []
    ends: list[datetime] = []
    for record in records:
        for span in record["spans"]:
            if (parsed := parse_timestamp(span.get("start_time"))) is not None:
                starts.append(parsed)
            if (parsed := parse_timestamp(span.get("end_time"))) is not None:
                ends.append(parsed)

    return {
        "request_count": request_count,
        "cache_hit_count": hit_count,
        "cache_miss_count": miss_count,
        "cache_hit_rate": hit_count / request_count,
        "error_count": error_count,
        "error_rate": error_count / request_count,
        "e2e_p50_ms": percentile(latencies, 50),
        "e2e_p95_ms": percentile(latencies, 95),
        "window_start": min(starts).isoformat() if starts else None,
        "window_end": max(ends).isoformat() if ends else None,
        "metric_sources": [
            {
                "metric": "Recent request count",
                "time_window": "Earliest to latest saved span",
                "data_source": (
                    "part4_trace_examples.json + part4_latency_experiment.json"
                ),
            },
            {
                "metric": "Cache hit rate",
                "time_window": "All saved Part 4 traces",
                "data_source": "cache_lookup spans (cache_status=hit/miss)",
            },
            {
                "metric": "Error rate",
                "time_window": "All saved Part 4 traces",
                "data_source": "span status and error fields",
            },
            {
                "metric": "End-to-end latency",
                "time_window": "All saved Part 4 traces",
                "data_source": "recorded E2E latency or full span envelope",
            },
        ],
    }


def part2_evaluation_rows(part2: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the one required E2E case into stage/criterion score rows."""

    pipeline = part2.get("pipeline")
    metrics = part2.get("metrics")
    if not isinstance(pipeline, dict) or not isinstance(metrics, dict):
        raise ValueError("Part 2 evidence is incomplete")
    case_id = str(pipeline.get("correlation_id", "unknown"))
    rows = []
    for key, stage, criterion in PART2_METRIC_PRESENTATION:
        metric = metrics.get(key)
        if not isinstance(metric, dict):
            raise ValueError(f"Part 2 metric is missing: {key}")
        rows.append(
            {
                "case_id": case_id,
                "stage": stage,
                "criterion": criterion,
                "score_1_to_5": int(metric["score"]),
                "reason": metric.get("reason"),
                "latency_ms": metric.get("latency_ms"),
            }
        )
    return rows


def coordination_interpretation(rows: list[dict[str, Any]]) -> str:
    """Create a short honest Planner/Writer/Reviewer coordination reading."""

    scores = {str(row["criterion"]): int(row["score_1_to_5"]) for row in rows}
    plan = scores["Plan Quality"]
    writer = scores["Writer Helpfulness"]
    final = scores["Final Answer Helpfulness"]
    improvement = scores["Final-vs-Draft Improvement"]
    if final == writer and improvement <= 3:
        return (
            f"Planner quality was {plan}/5 and the Writer raised the usable answer "
            f"quality to {writer}/5. The Reviewer final remained {final}/5, while "
            f"the improvement score was {improvement}/5, so this run shows a useful "
            "Writer output but no measurable Reviewer refinement. The Reviewer acted "
            "as an approval pass rather than a quality-improvement stage."
        )
    direction = "improved" if final > writer else "reduced"
    return (
        f"Planner scored {plan}/5 and Writer scored {writer}/5. Reviewer {direction} "
        f"the final score to {final}/5; improvement was rated {improvement}/5."
    )


def parse_judge_case_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Convert judge comparison CSV values for Streamlit display."""

    parsed = []
    for row in rows:
        parsed.append(
            {
                "case_id": row["case_id"],
                "human_score": int(row["human_score"]),
                "judge_run_1": int(row["judge_run_1"]),
                "judge_run_2": int(row["judge_run_2"]),
                "judge_run_3": int(row["judge_run_3"]),
                "judge_mean": float(row["judge_mean"]),
                "absolute_difference": float(
                    row["absolute_difference_from_human"]
                ),
                "score_changed": row["score_changed"].strip().lower() == "true",
            }
        )
    return parsed


def required_trace_examples(trace_examples: dict[str, Any]) -> list[dict[str, str]]:
    """Return the three report-required IDs and their path descriptions."""

    rows = []
    for key, label in (
        ("cache_hit", "Cache hit"),
        ("successful_cache_miss", "Successful cache miss"),
        ("failed_trace", "Failed trace"),
    ):
        record = trace_examples[key]
        rows.append(
            {
                "example": label,
                "trace_id": str(record["trace_id"]),
                "path": " → ".join(
                    row["stage"] for row in trace_span_rows(record)
                ),
            }
        )
    return rows


def load_dashboard_bundle(report_root: Path) -> dict[str, Any]:
    """Load and validate all evidence required by the three dashboard pages."""

    part2 = read_json(report_root / "part2_evaluation.json")
    judge_summary = read_json(report_root / "judge_validation_summary.json")
    judge_cases = parse_judge_case_rows(
        read_csv_rows(report_root / "judge_validation_cases.csv")
    )
    trace_examples = read_json(report_root / "part4_trace_examples.json")
    latency_experiment = read_json(report_root / "part4_latency_experiment.json")
    trace_index = build_trace_index(trace_examples, latency_experiment)
    evaluation_rows = part2_evaluation_rows(part2)
    return {
        "part2": part2,
        "evaluation_rows": evaluation_rows,
        "coordination_interpretation": coordination_interpretation(evaluation_rows),
        "judge_summary": judge_summary,
        "judge_cases": judge_cases,
        "trace_examples": trace_examples,
        "latency_experiment": latency_experiment,
        "trace_index": trace_index,
        "request_summary": summarize_requests(trace_index),
        "required_trace_examples": required_trace_examples(trace_examples),
    }
