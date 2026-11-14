"""Capture and evaluate one correlated HW10 Planner-Writer-Reviewer run."""

import argparse
import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from deepeval.metrics import GEval
from deepeval.metrics.g_eval import Rubric
from deepeval.models import OllamaModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

from hw8_config import (
    DRAFTS_TOPIC,
    FINAL_TOPIC,
    INBOX_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    PREFIX,
    TASKS_TOPIC,
)
from hw10_judge import (
    JUDGE_CONFIGURATION_VERSION,
    JUDGE_MODEL,
    JUDGE_NUM_PREDICT,
    JUDGE_SEED,
    JUDGE_TEMPERATURE,
    JUDGE_TIMEOUT_SECONDS,
    WRITER_RUBRIC,
    build_model,
    git_head,
    hard_timeout,
    write_json_atomic,
)
from hw10_judge_core import normalized_to_five_point

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "reports" / "hw10" / "raw" / "part2_evaluation.json"
DEFAULT_QUESTION = (
    "What should a renter verify before paying an application fee for an "
    "online rental listing?"
)
PIPELINE_TIMEOUT_SECONDS = int(os.getenv("HW10_PIPELINE_TIMEOUT_SECONDS", "300"))

METRIC_KEYS = (
    "plan_quality",
    "writer_helpfulness",
    "final_answer_helpfulness",
    "final_vs_draft_improvement",
)

PLAN_STEPS = [
    "Check whether the plan directly addresses the rental-housing question.",
    "Check whether it covers the important verification and safety concerns.",
    "Assess whether the steps are logical, practical, and useful to the Writer.",
    "Penalize unsupported assumptions, irrelevant steps, and important omissions.",
    "Apply the supplied 1-5 quality rubric and give a concise reason.",
]

FINAL_STEPS = [
    "Check whether the final answer directly answers the user's question.",
    "Check factual plausibility and penalize invented laws, prices, guarantees, "
    "or unsupported specifics.",
    "Assess completeness, practical usefulness, and actionability.",
    "Assess clarity, organization, and conciseness.",
    "Apply the supplied 1-5 quality rubric and give a concise reason.",
]

IMPROVEMENT_STEPS = [
    "Compare the final answer in Actual Output with the original draft in Context.",
    "Check whether the final answer fixes errors or unsupported claims.",
    "Check whether it improves relevance, completeness, clarity, or actionability.",
    "Penalize changes that remove useful information or make the answer worse.",
    "Apply the supplied 1-5 improvement rubric and give a concise reason.",
]

PLAN_RUBRIC = [
    Rubric(score_range=(1, 1), expected_outcome="Unusable or irrelevant plan."),
    Rubric(
        score_range=(2, 2),
        expected_outcome="Weak plan with major omissions or impractical steps.",
    ),
    Rubric(
        score_range=(3, 3),
        expected_outcome="Adequate plan, but generic or missing important detail.",
    ),
    Rubric(
        score_range=(4, 4),
        expected_outcome="Good, relevant, practical plan with only minor omissions.",
    ),
    Rubric(
        score_range=(5, 5),
        expected_outcome="Excellent, complete, concise, and actionable plan.",
    ),
]

IMPROVEMENT_RUBRIC = [
    Rubric(
        score_range=(1, 1),
        expected_outcome="Final answer is materially worse than the draft.",
    ),
    Rubric(
        score_range=(2, 2),
        expected_outcome="Final answer is slightly worse or introduces new problems.",
    ),
    Rubric(
        score_range=(3, 3),
        expected_outcome="No meaningful improvement; quality is essentially unchanged.",
    ),
    Rubric(
        score_range=(4, 4),
        expected_outcome="Meaningful improvement with clearer or more useful content.",
    ),
    Rubric(
        score_range=(5, 5),
        expected_outcome="Substantial improvement that fixes major draft weaknesses.",
    ),
]


def utc_now() -> str:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC).isoformat()


def required_text(message: dict[str, Any], field: str, label: str) -> str:
    """Return one required message string with a source-specific error."""

    value = message.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}.{field} must be a non-empty string")
    return value.strip()


def validate_pipeline_capture(
    correlation_id: str,
    question: str,
    messages: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Validate and flatten the three correlated Kafka stage messages."""

    expected_topics = {TASKS_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC}
    if set(messages) != expected_topics:
        missing = sorted(expected_topics - set(messages))
        raise ValueError(f"pipeline capture is incomplete; missing topics: {missing}")

    for topic, message in messages.items():
        observed = required_text(message, "correlation_id", topic)
        if observed != correlation_id:
            raise ValueError(f"{topic} has a different correlation_id")

    task = messages[TASKS_TOPIC]
    draft_message = messages[DRAFTS_TOPIC]
    final_message = messages[FINAL_TOPIC]
    task_question = required_text(task, "question", TASKS_TOPIC)
    draft_question = required_text(draft_message, "question", DRAFTS_TOPIC)
    if task_question != question or draft_question != question:
        raise ValueError("captured question does not match the submitted question")

    plan = required_text(task, "plan", TASKS_TOPIC)
    if required_text(draft_message, "plan", DRAFTS_TOPIC) != plan:
        raise ValueError("Writer did not preserve the Planner plan")
    if final_message.get("status") != "approved":
        raise ValueError("Reviewer final message is not approved")

    return {
        "correlation_id": correlation_id,
        "question": question,
        "plan": plan,
        "draft": required_text(draft_message, "draft", DRAFTS_TOPIC),
        "final_answer": required_text(final_message, "answer", FINAL_TOPIC),
        "raw_messages": messages,
    }


async def wait_for_pipeline(
    consumer: AIOKafkaConsumer,
    correlation_id: str,
) -> dict[str, dict[str, Any]]:
    """Collect matching tasks, drafts, and final records from one consumer."""

    expected_topics = {TASKS_TOPIC, DRAFTS_TOPIC, FINAL_TOPIC}
    captured: dict[str, dict[str, Any]] = {}
    async for record in consumer:
        message = record.value
        if message.get("correlation_id") != correlation_id:
            continue
        captured[record.topic] = message
        print(
            f"[HW10 PART2] captured topic={record.topic} "
            f"partition={record.partition} offset={record.offset}",
            flush=True,
        )
        if set(captured) == expected_topics:
            return captured
    raise RuntimeError("pipeline-topic consumer stopped unexpectedly")


async def collect_pipeline(question: str) -> dict[str, Any]:
    """Send one question and capture all three correlated agent outputs."""

    correlation_id = str(uuid4())
    consumer = AIOKafkaConsumer(
        TASKS_TOPIC,
        DRAFTS_TOPIC,
        FINAL_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"{PREFIX}_hw10_part2_{correlation_id}",
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )

    await consumer.start()
    await producer.start()
    try:
        await consumer.getmany(timeout_ms=1000)
        message = {"correlation_id": correlation_id, "question": question}
        metadata = await producer.send_and_wait(
            INBOX_TOPIC,
            message,
            key=correlation_id.encode("utf-8"),
        )
        print(
            f"[HW10 PART2] submitted topic={INBOX_TOPIC} "
            f"partition={metadata.partition} offset={metadata.offset} "
            f"correlation_id={correlation_id}",
            flush=True,
        )
        messages = await asyncio.wait_for(
            wait_for_pipeline(consumer, correlation_id),
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
    finally:
        await consumer.stop()
        await producer.stop()

    capture = validate_pipeline_capture(correlation_id, question, messages)
    capture["captured_at"] = utc_now()
    return capture


def build_metric(
    *,
    name: str,
    criteria: str,
    steps: list[str],
    params: list[SingleTurnParams],
    rubric: list[Rubric],
    model: OllamaModel,
) -> GEval:
    """Create one deterministic bounded G-Eval metric."""

    return GEval(
        name=name,
        criteria=criteria,
        evaluation_steps=steps,
        evaluation_params=params,
        rubric=rubric,
        model=model,
        threshold=0,
        async_mode=False,
        strict_mode=False,
    )


def metric_and_case(
    key: str,
    pipeline: dict[str, Any],
    model: OllamaModel,
) -> tuple[GEval, LLMTestCase]:
    """Build the requested metric and its correctly shaped test case."""

    question = str(pipeline["question"])
    if key == "plan_quality":
        return (
            build_metric(
                name="Plan Quality",
                criteria=(
                    "Evaluate whether the Planner plan is relevant, complete, "
                    "practical, concise, and safe for answering the question."
                ),
                steps=PLAN_STEPS,
                params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
                rubric=PLAN_RUBRIC,
                model=model,
            ),
            LLMTestCase(input=question, actual_output=str(pipeline["plan"])),
        )
    if key == "writer_helpfulness":
        return (
            build_metric(
                name="Writer Helpfulness",
                criteria=(
                    "Evaluate whether the Writer draft is accurate, directly "
                    "relevant, practically useful, complete enough, clear, concise, "
                    "and free of unsupported claims."
                ),
                steps=FINAL_STEPS,
                params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
                rubric=WRITER_RUBRIC,
                model=model,
            ),
            LLMTestCase(input=question, actual_output=str(pipeline["draft"])),
        )
    if key == "final_answer_helpfulness":
        return (
            build_metric(
                name="Final Answer Helpfulness",
                criteria=(
                    "Evaluate whether the Reviewer final answer is accurate, "
                    "directly relevant, practically useful, complete enough, clear, "
                    "concise, and free of unsupported claims."
                ),
                steps=FINAL_STEPS,
                params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
                rubric=WRITER_RUBRIC,
                model=model,
            ),
            LLMTestCase(
                input=question,
                actual_output=str(pipeline["final_answer"]),
            ),
        )
    if key == "final_vs_draft_improvement":
        return (
            build_metric(
                name="Final-vs-Draft Improvement",
                criteria=(
                    "Evaluate how much the Reviewer final answer in Actual Output "
                    "improves over the original Writer draft supplied in Context."
                ),
                steps=IMPROVEMENT_STEPS,
                params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                    SingleTurnParams.CONTEXT,
                ],
                rubric=IMPROVEMENT_RUBRIC,
                model=model,
            ),
            LLMTestCase(
                input=question,
                actual_output=str(pipeline["final_answer"]),
                context=[f"Original Writer draft:\n{pipeline['draft']}"],
            ),
        )
    raise ValueError(f"unknown Part 2 metric: {key}")


def score_metric(
    key: str,
    pipeline: dict[str, Any],
    model: OllamaModel,
) -> dict[str, Any]:
    """Run one metric with the shared hard timeout and return raw evidence."""

    metric, test_case = metric_and_case(key, pipeline, model)
    started = time.perf_counter()
    with hard_timeout(JUDGE_TIMEOUT_SECONDS):
        normalized = float(metric.measure(test_case, _show_indicator=False))
    latency_ms = (time.perf_counter() - started) * 1000
    return {
        "metric_name": metric.name,
        "score": normalized_to_five_point(normalized),
        "deepeval_normalized_score": normalized,
        "reason": metric.reason,
        "latency_ms": round(latency_ms, 2),
    }


def initialize_result(question: str, pipeline: dict[str, Any]) -> dict[str, Any]:
    """Create the resumable Part 2 result envelope."""

    return {
        "metadata": {
            "schema_version": 1,
            "evaluation_code_commit": git_head(),
            "judge_framework": "DeepEval GEval",
            "judge_configuration_version": JUDGE_CONFIGURATION_VERSION,
            "judge_model": JUDGE_MODEL,
            "temperature": JUDGE_TEMPERATURE,
            "seed": JUDGE_SEED,
            "thinking_enabled": False,
            "num_predict": JUDGE_NUM_PREDICT,
            "judge_timeout_seconds_per_metric": JUDGE_TIMEOUT_SECONDS,
            "pipeline_timeout_seconds": PIPELINE_TIMEOUT_SECONDS,
            "score_scale": {"minimum": 1, "maximum": 5},
        },
        "question": question,
        "pipeline": pipeline,
        "metrics": {},
        "started_at": utc_now(),
        "completed_at": None,
    }


def load_result(path: Path, question: str) -> dict[str, Any] | None:
    """Load a compatible checkpoint so failed metric calls can resume."""

    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("question") != question:
        raise ValueError("existing Part 2 output uses a different question")
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("existing Part 2 output has invalid metrics")
    return payload


def print_summary(result: dict[str, Any]) -> None:
    """Print a screenshot-friendly Part 2 score summary."""

    metrics = result["metrics"]
    print("HW10 PART 2 — END-TO-END EVALUATION")
    print("=====================================")
    print(f"correlation_id = {result['pipeline']['correlation_id']}")
    print("stages_collected = Planner, Writer, Reviewer")
    for key in METRIC_KEYS:
        item = metrics[key]
        print(f"{key} = {item['score']}/5")
        print(f"  reason = {item['reason']}")
    delta = (
        metrics["final_answer_helpfulness"]["score"]
        - metrics["writer_helpfulness"]["score"]
    )
    print(f"final_minus_writer_score = {delta:+d}")
    print("bounded_timeouts = PASS")


def parse_args() -> argparse.Namespace:
    """Parse the question and resumable output path."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    """Capture one E2E run, resume four judge metrics, and save evidence."""

    args = parse_args()
    question = args.question.strip()
    if not question:
        raise ValueError("question must not be empty")

    result = load_result(args.output, question)
    if result is None:
        print("[HW10 PART2] capturing correlated pipeline outputs", flush=True)
        pipeline = asyncio.run(collect_pipeline(question))
        result = initialize_result(question, pipeline)
        write_json_atomic(args.output, result)
    else:
        print("[HW10 PART2] resuming saved pipeline capture", flush=True)

    model = build_model()
    for key in METRIC_KEYS:
        if key in result["metrics"]:
            print(f"[HW10 PART2] {key} already complete", flush=True)
            continue
        print(f"[HW10 PART2] scoring {key}", flush=True)
        result["metrics"][key] = score_metric(key, result["pipeline"], model)
        write_json_atomic(args.output, result)

    result["completed_at"] = utc_now()
    write_json_atomic(args.output, result)
    print("[HW10 PART2] evaluation complete", flush=True)
    print_summary(result)


if __name__ == "__main__":
    main()
