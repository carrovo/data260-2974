"""Streamlit operations and evidence dashboard for DATA 260 HW10."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from hw10_dashboard_core import load_dashboard_bundle, trace_span_rows

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = PROJECT_ROOT / "reports" / "hw10" / "raw"


@st.cache_data(show_spinner="Loading committed HW10 evidence...")
def load_evidence() -> dict[str, Any]:
    """Cache deterministic file parsing across Streamlit reruns."""

    return load_dashboard_bundle(REPORT_ROOT)


def format_ms(value: float) -> str:
    """Format milliseconds compactly for metric cards."""

    return f"{value:,.2f} ms"


def render_summary(bundle: dict[str, Any]) -> None:
    """Render system health and evidence-source summary metrics."""

    summary = bundle["request_summary"]
    experiment = bundle["latency_experiment"]["summary"]
    examples = bundle["trace_examples"]

    st.title("HW10 Operations Summary")
    st.caption(
        "Recent metrics are calculated from committed Part 4 trace artifacts. "
        "They are reproducible evidence, not live production estimates."
    )

    first = st.columns(4)
    first[0].metric("Recent requests", summary["request_count"])
    first[1].metric(
        "Semantic-cache hit rate",
        f"{summary['cache_hit_rate'] * 100:.2f}%",
        f"{summary['cache_hit_count']} hit / {summary['cache_miss_count']} miss",
    )
    first[2].metric(
        "Error rate",
        f"{summary['error_rate'] * 100:.2f}%",
        f"{summary['error_count']} failed trace",
        delta_color="inverse",
    )
    first[3].metric("E2E latency p50", format_ms(summary["e2e_p50_ms"]))

    second = st.columns(4)
    second[0].metric("E2E latency p95", format_ms(summary["e2e_p95_ms"]))
    second[1].metric(
        "Cache-hit latency",
        format_ms(float(examples["cache_hit"]["cache_hit_latency_ms"])),
        "reported separately",
    )
    second[2].metric(
        "Cache-miss E2E p50",
        format_ms(float(experiment["cache_miss_e2e"]["p50_ms"])),
    )
    second[3].metric(
        "Cache-miss E2E p95",
        format_ms(float(experiment["cache_miss_e2e"]["p95_ms"])),
    )

    st.subheader("Metric window and provenance")
    st.write(
        f"**Window:** `{summary['window_start']}` through "
        f"`{summary['window_end']}`"
    )
    st.dataframe(summary["metric_sources"], width="stretch", hide_index=True)

    st.subheader("50 confirmed cache-miss stage latency")
    stage_rows = []
    for key in (
        "cache_lookup",
        "planner",
        "writer",
        "reviewer",
        "queue_wait_total",
        "evaluation",
    ):
        row = experiment["stages"][key]
        stage_rows.append(
            {
                "stage": key,
                "p50_ms": row["p50_ms"],
                "p95_ms": row["p95_ms"],
                "mean_%_cache_miss_e2e": row[
                    "mean_percent_of_cache_miss_e2e"
                ],
            }
        )
    st.dataframe(stage_rows, width="stretch", hide_index=True)
    st.warning(
        f"Dominant contributor: **{experiment['dominant_contributor']}**. "
        f"Recommended first optimization: "
        f"{experiment['optimization_recommendation']}"
    )


def render_evaluation(bundle: dict[str, Any]) -> None:
    """Render Part 2 coordination and Part 3 judge-validation evidence."""

    rows = bundle["evaluation_rows"]
    judge = bundle["judge_summary"]
    agreement = judge["agreement_using_mean_judge_score"]
    repeatability = judge["repeatability"]
    gate = judge["deployment_gate_recommendation"]

    st.title("Evaluation Evidence")
    st.caption("Scores use the assignment's consistent 1–5 scale.")

    score_by_criterion = {
        row["criterion"]: int(row["score_1_to_5"]) for row in rows
    }
    cards = st.columns(4)
    cards[0].metric("Planner plan", f"{score_by_criterion['Plan Quality']}/5")
    cards[1].metric(
        "Writer draft",
        f"{score_by_criterion['Writer Helpfulness']}/5",
    )
    cards[2].metric(
        "Reviewer final",
        f"{score_by_criterion['Final Answer Helpfulness']}/5",
    )
    cards[3].metric(
        "Final vs draft",
        f"{score_by_criterion['Final-vs-Draft Improvement']}/5",
    )

    st.subheader("Part 2: scores by pipeline stage and case")
    st.dataframe(rows, width="stretch", hide_index=True)
    st.info(bundle["coordination_interpretation"])

    with st.expander("Inspect the evaluated Planner, Writer, and Reviewer content"):
        pipeline = bundle["part2"]["pipeline"]
        st.markdown("**Question**")
        st.write(bundle["part2"]["question"])
        st.markdown("**Planner plan**")
        st.code(pipeline["plan"], language=None)
        st.markdown("**Writer draft**")
        st.write(pipeline["draft"])
        st.markdown("**Reviewer final answer**")
        st.write(pipeline["final_answer"])

    st.subheader("Part 3: automated-judge validation")
    validation_cards = st.columns(4)
    validation_cards[0].metric(
        "Spearman correlation",
        f"{agreement['spearman_correlation']:.4f}",
    )
    validation_cards[1].metric(
        "Mean absolute difference",
        f"{agreement['mean_absolute_difference']:.2f}",
    )
    validation_cards[2].metric(
        "Changed cases",
        f"{repeatability['changed_case_count']} / {judge['case_count']}",
    )
    validation_cards[3].metric(
        "Maximum repeat change",
        f"{repeatability['maximum_absolute_score_change']:.2f}",
    )

    st.dataframe(bundle["judge_cases"], width="stretch", hide_index=True)
    if gate["trust_to_gate_deployment"]:
        st.success("The saved decision recommends trusting the judge as a gate.")
    else:
        st.error(
            "Do not trust this judge to gate deployment yet. It was perfectly "
            "repeatable here, but its ranking alignment with human labels was weak."
        )
    st.write(f"**Decision rule:** {gate['decision_rule']}")
    st.write("**Additional evidence required:**")
    for item in gate["additional_evidence_required"]:
        st.write(f"- {item}")


def trace_label(trace_id: str, record: dict[str, Any]) -> str:
    """Create an informative selectbox label without hiding the trace ID."""

    return (
        f"{record['trace_kind']} | {record['cache_status']} | "
        f"{record['request_status']} | {trace_id}"
    )


def render_trace_lookup(bundle: dict[str, Any]) -> None:
    """Render exact trace lookup and the full ordered request journey."""

    index = bundle["trace_index"]
    required = bundle["required_trace_examples"]
    default_id = required[1]["trace_id"]

    st.title("Trace Lookup")
    st.caption(
        "Lookup uses the HW8 correlation_id reused as trace_id. No second request "
        "identifier is created."
    )

    st.subheader("Required report trace IDs")
    st.dataframe(required, width="stretch", hide_index=True)

    if "hw10_trace_query" not in st.session_state:
        st.session_state["hw10_trace_query"] = default_id
    selected = st.selectbox(
        "Available saved traces",
        options=list(index),
        format_func=lambda trace_id: trace_label(trace_id, index[trace_id]),
    )
    if st.button("Load selected trace", type="primary"):
        st.session_state["hw10_trace_query"] = selected

    trace_id = st.text_input("trace_id", key="hw10_trace_query").strip()
    if not trace_id:
        st.info("Enter a trace_id to inspect a request journey.")
        return
    record = index.get(trace_id)
    if record is None:
        st.error("No saved trace matches that trace_id.")
        return

    if record["request_status"] == "error":
        st.error(
            f"Failed cache-{record['cache_status']} path. "
            f"Failing stage: {record.get('failing_stage', 'see journey')}. "
            f"Error: {record.get('error', 'see span error column')}"
        )
    elif record["cache_status"] == "hit":
        st.success("Cache hit: the Planner–Writer–Reviewer path was bypassed.")
    else:
        st.info("Cache miss: request completed the Kafka agent and evaluator path.")

    cards = st.columns(4)
    cards[0].metric("Cache path", record["cache_status"])
    cards[1].metric("Request status", record["request_status"])
    cards[2].metric(
        "E2E latency",
        format_ms(float(record["dashboard_e2e_latency_ms"])),
    )
    cards[3].metric("Span count", len(record["spans"]))
    st.caption(f"Source: {record['source']} | Type: {record['trace_kind']}")

    if record.get("question"):
        st.markdown("**Question**")
        st.write(record["question"])
    if record.get("answer"):
        with st.expander("Final answer"):
            st.write(record["answer"])

    st.subheader("Full request journey")
    st.dataframe(trace_span_rows(record), width="stretch", hide_index=True)
    with st.expander("Raw saved trace JSON"):
        st.json(record)


def main() -> None:
    """Configure and render one of the three required dashboard pages."""

    st.set_page_config(
        page_title="DATA 260 HW10 Operations",
        page_icon="📊",
        layout="wide",
    )
    st.sidebar.title("DATA 260 HW10")
    st.sidebar.caption("Rental-housing multi-agent operations evidence")
    page = st.sidebar.radio(
        "Page",
        ("Summary", "Evaluation", "Trace Lookup"),
    )
    try:
        bundle = load_evidence()
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        st.error(f"Dashboard evidence could not be loaded: {exc}")
        st.stop()

    if page == "Summary":
        render_summary(bundle)
    elif page == "Evaluation":
        render_evaluation(bundle)
    else:
        render_trace_lookup(bundle)


if __name__ == "__main__":
    main()
