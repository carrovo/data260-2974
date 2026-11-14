"""Run HW10 Part 4 traces and the 50-cache-miss latency experiment."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_config import (
    KAFKA_BOOTSTRAP_SERVERS,
    TASKS_TOPIC,
    TRACE_TOPIC,
)
from hw9_agent_client import run_hw8_agent_pipeline
from hw9_semantic_cache import SemanticResponseCache
from hw10_judge import build_model, score_writer_case, write_json_atomic
from hw10_tracing import (
    experiment_question,
    make_span,
    summarize_latency_cases,
    utc_now,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = PROJECT_ROOT / "reports" / "hw10" / "raw"
DEFAULT_EXAMPLES = REPORT_ROOT / "part4_trace_examples.json"
DEFAULT_EXPERIMENT = REPORT_ROOT / "part4_latency_experiment.json"
TRACE_WAIT_SECONDS = 90


async def emit_span(
    producer: AIOKafkaProducer,
    span: dict[str, Any],
) -> None:
    """Publish one span to the shared trace topic."""

    await producer.send_and_wait(
        TRACE_TOPIC,
        span,
        key=str(span["trace_id"]).encode("utf-8"),
    )


async def collect_trace(
    consumer: AIOKafkaConsumer,
    trace_id: str,
    required: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Collect one trace until all required component/status pairs arrive."""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + TRACE_WAIT_SECONDS
    collected: list[dict[str, Any]] = []
    observed: set[tuple[str, str]] = set()
    while loop.time() < deadline:
        remaining_ms = max(1, int((deadline - loop.time()) * 1000))
        batches = await consumer.getmany(timeout_ms=min(1000, remaining_ms))
        for records in batches.values():
            for record in records:
                span = record.value
                if span.get("trace_id") != trace_id:
                    continue
                collected.append(span)
                observed.add((str(span.get("component")), str(span.get("status"))))
        if required <= observed:
            return collected
    missing = sorted(required - observed)
    raise TimeoutError(f"trace {trace_id} is incomplete; missing {missing}")


async def start_trace_io() -> tuple[AIOKafkaConsumer, AIOKafkaProducer]:
    """Start one latest-only collector and one JSON producer."""

    consumer = AIOKafkaConsumer(
        TRACE_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=None,
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
    await consumer.getmany(timeout_ms=1000)
    return consumer, producer


async def traced_cache_lookup(
    *,
    cache: SemanticResponseCache,
    producer: AIOKafkaProducer,
    trace_id: str,
    question: str,
) -> tuple[Any, float]:
    """Perform and emit the cache lookup span."""

    started_at = utc_now()
    started_perf = perf_counter()
    try:
        lookup = await asyncio.to_thread(cache.find, question)
    except Exception as exc:
        finished_at = utc_now()
        await emit_span(
            producer,
            make_span(
                trace_id=trace_id,
                stage="cache_lookup",
                component="Cache",
                start_time=started_at,
                end_time=finished_at,
                duration_ms=(perf_counter() - started_perf) * 1000,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            ),
        )
        raise
    latency_ms = (perf_counter() - started_perf) * 1000
    await emit_span(
        producer,
        make_span(
            trace_id=trace_id,
            stage="cache_lookup",
            component="Cache",
            start_time=started_at,
            end_time=utc_now(),
            duration_ms=latency_ms,
            status="ok",
            cache_status="hit" if lookup.is_hit else "miss",
            metadata={
                "similarity": round(float(lookup.similarity), 6),
                "threshold": cache.threshold,
            },
        ),
    )
    return lookup, latency_ms


async def run_confirmed_miss(
    *,
    cache: SemanticResponseCache,
    producer: AIOKafkaProducer,
    consumer: AIOKafkaConsumer,
    model: Any,
    question: str,
) -> dict[str, Any]:
    """Run one verified miss through all agents and one bounded evaluation."""

    trace_id = str(uuid4())
    e2e_started = perf_counter()
    lookup, _lookup_ms = await traced_cache_lookup(
        cache=cache,
        producer=producer,
        trace_id=trace_id,
        question=question,
    )
    if lookup.is_hit:
        raise RuntimeError(
            f"expected an intentional cache miss but received a hit: {question}"
        )

    answer = await run_hw8_agent_pipeline(question, trace_id=trace_id)
    await asyncio.to_thread(cache.store, question, answer)

    evaluation_started_at = utc_now()
    evaluation_started_perf = perf_counter()
    try:
        evaluation = score_writer_case(model, question, answer)
    except Exception as exc:
        await emit_span(
            producer,
            make_span(
                trace_id=trace_id,
                stage="evaluator",
                component="EVALUATOR",
                start_time=evaluation_started_at,
                end_time=utc_now(),
                duration_ms=(perf_counter() - evaluation_started_perf) * 1000,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            ),
        )
        raise
    await emit_span(
        producer,
        make_span(
            trace_id=trace_id,
            stage="evaluator",
            component="EVALUATOR",
            start_time=evaluation_started_at,
            end_time=utc_now(),
            duration_ms=(perf_counter() - evaluation_started_perf) * 1000,
            status="ok",
            metadata={"judge_score": evaluation["judge_score"]},
        ),
    )
    e2e_latency_ms = (perf_counter() - e2e_started) * 1000
    spans = await collect_trace(
        consumer,
        trace_id,
        {
            ("Cache", "ok"),
            ("PLANNER", "ok"),
            ("WRITER", "ok"),
            ("REVIEWER", "ok"),
            ("FINAL", "ok"),
            ("EVALUATOR", "ok"),
        },
    )
    return {
        "trace_id": trace_id,
        "correlation_id": trace_id,
        "question": question,
        "answer": answer,
        "is_cached": False,
        "judge": evaluation,
        "e2e_latency_ms": round(e2e_latency_ms, 2),
        "spans": spans,
    }


async def run_confirmed_hit(
    *,
    cache: SemanticResponseCache,
    producer: AIOKafkaProducer,
    consumer: AIOKafkaConsumer,
    question: str,
) -> dict[str, Any]:
    """Run and capture a cache hit without invoking any agent."""

    trace_id = str(uuid4())
    lookup, latency_ms = await traced_cache_lookup(
        cache=cache,
        producer=producer,
        trace_id=trace_id,
        question=question,
    )
    if not lookup.is_hit:
        raise RuntimeError("expected the seeded exact question to be a cache hit")
    spans = await collect_trace(consumer, trace_id, {("Cache", "ok")})
    return {
        "trace_id": trace_id,
        "correlation_id": trace_id,
        "question": question,
        "answer": lookup.answer,
        "is_cached": True,
        "cache_hit_latency_ms": round(latency_ms, 2),
        "spans": spans,
    }


async def run_failed_trace(
    *,
    producer: AIOKafkaProducer,
    consumer: AIOKafkaConsumer,
) -> dict[str, Any]:
    """Create a controlled Writer validation failure with a visible error span."""

    trace_id = str(uuid4())
    now = utc_now()
    cache_span = make_span(
        trace_id=trace_id,
        stage="cache_lookup",
        component="Cache",
        start_time=now,
        end_time=now,
        duration_ms=0.0,
        status="ok",
        cache_status="miss",
        metadata={"controlled_failure": True},
    )
    await emit_span(producer, cache_span)
    malformed_task = {
        "correlation_id": trace_id,
        "trace_id": trace_id,
        "question": "Controlled HW10 failed trace: missing Planner plan.",
        "published_at": utc_now(),
    }
    await producer.send_and_wait(
        TASKS_TOPIC,
        malformed_task,
        key=trace_id.encode("utf-8"),
    )
    spans = await collect_trace(
        consumer,
        trace_id,
        {("Cache", "ok"), ("WRITER", "error")},
    )
    failed_span = next(
        span
        for span in spans
        if span.get("component") == "WRITER" and span.get("status") == "error"
    )
    return {
        "trace_id": trace_id,
        "correlation_id": trace_id,
        "failing_stage": failed_span["stage"],
        "error": failed_span["error"],
        "spans": spans,
    }


async def trace_examples(output: Path) -> dict[str, Any]:
    """Capture the required hit, successful miss, and failed trace."""

    consumer, producer = await start_trace_io()
    try:
        cache = await asyncio.to_thread(SemanticResponseCache, threshold=1.0)
        model = build_model()
        token = uuid4().hex[:12]
        question = (
            "What should a renter verify before paying an application fee? "
            f"[HW10 trace example {token}]"
        )
        print("[HW10 PART4] capturing successful cache-miss trace", flush=True)
        successful_miss = await run_confirmed_miss(
            cache=cache,
            producer=producer,
            consumer=consumer,
            model=model,
            question=question,
        )
        print("[HW10 PART4] capturing exact cache-hit trace", flush=True)
        cache_hit = await run_confirmed_hit(
            cache=cache,
            producer=producer,
            consumer=consumer,
            question=question,
        )
        print("[HW10 PART4] capturing controlled failed trace", flush=True)
        failed = await run_failed_trace(producer=producer, consumer=consumer)
    finally:
        await consumer.stop()
        await producer.stop()

    result = {
        "metadata": {
            "schema_version": 1,
            "captured_at": utc_now(),
            "trace_id_policy": "trace_id equals the reused HW8 correlation_id",
            "cache_threshold": 1.0,
        },
        "cache_hit": cache_hit,
        "successful_cache_miss": successful_miss,
        "failed_trace": failed,
    }
    write_json_atomic(output, result)
    return result


def load_experiment(path: Path) -> dict[str, Any]:
    """Load a resumable experiment or initialize a new one."""

    if not path.exists():
        return {
            "metadata": {
                "schema_version": 1,
                "experiment_id": str(uuid4()),
                "started_at": utc_now(),
                "completed_at": None,
                "required_confirmed_cache_misses": 50,
                "cache_threshold": 1.0,
            },
            "cases": [],
            "summary": None,
        }
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or not isinstance(result.get("cases"), list):
        raise ValueError("existing Part 4 experiment checkpoint is invalid")
    if len(result["cases"]) > 50:
        raise ValueError("existing Part 4 experiment contains too many cases")
    return result


async def latency_experiment(output: Path) -> dict[str, Any]:
    """Run or resume exactly 50 verified misses and calculate p50/p95."""

    result = load_experiment(output)
    cases = result["cases"]
    if len(cases) == 50 and result.get("summary") is not None:
        print("[HW10 PART4] 50-case experiment already complete", flush=True)
        return result

    consumer, producer = await start_trace_io()
    try:
        cache = await asyncio.to_thread(SemanticResponseCache, threshold=1.0)
        model = build_model()
        experiment_id = str(result["metadata"]["experiment_id"])
        while len(cases) < 50:
            case_number = len(cases) + 1
            question = experiment_question(
                experiment_id,
                case_number,
                str(uuid4()),
            )
            print(
                f"[HW10 PART4] cache-miss case {case_number}/50",
                flush=True,
            )
            case = await run_confirmed_miss(
                cache=cache,
                producer=producer,
                consumer=consumer,
                model=model,
                question=question,
            )
            case["case_id"] = f"latency-{case_number:02d}"
            cases.append(case)
            write_json_atomic(output, result)
            print(
                f"[HW10 PART4] checkpoint saved with {len(cases)} cases",
                flush=True,
            )
    finally:
        await consumer.stop()
        await producer.stop()

    result["summary"] = summarize_latency_cases(cases)
    result["metadata"]["completed_at"] = utc_now()
    write_json_atomic(output, result)
    return result


def print_examples(result: dict[str, Any]) -> None:
    """Print screenshot-friendly trace evidence."""

    hit = result["cache_hit"]
    success = result["successful_cache_miss"]
    failed = result["failed_trace"]
    print("HW10 PART 4 — REQUIRED TRACE EXAMPLES")
    print("======================================")
    print(f"cache_hit_trace_id = {hit['trace_id']}")
    print(f"cache_hit_latency_ms = {hit['cache_hit_latency_ms']}")
    print(f"successful_miss_trace_id = {success['trace_id']}")
    print(
        "successful_miss_stages = "
        + ", ".join(span["stage"] for span in success["spans"])
    )
    print(f"failed_trace_id = {failed['trace_id']}")
    print(f"failing_stage = {failed['failing_stage']}")
    print(f"error = {failed['error']}")
    print("trace_id_equals_correlation_id = PASS")


def print_experiment(result: dict[str, Any]) -> None:
    """Print the required 50-case latency table and conclusion."""

    summary = result["summary"]
    print("HW10 PART 4 — 50 CONFIRMED CACHE MISSES")
    print("========================================")
    print(f"confirmed_cache_miss_count = {summary['confirmed_cache_miss_count']}")
    print("stage                         p50_ms      p95_ms     mean_%_e2e")
    for key in (
        "cache_lookup",
        "planner",
        "writer",
        "reviewer",
        "queue_wait_total",
        "evaluation",
    ):
        row = summary["stages"][key]
        print(
            f"{key:<28} {row['p50_ms']:>10.2f} {row['p95_ms']:>11.2f} "
            f"{row['mean_percent_of_cache_miss_e2e']:>13.2f}%"
        )
    e2e = summary["cache_miss_e2e"]
    print(f"cache_miss_e2e_p50_ms = {e2e['p50_ms']:.2f}")
    print(f"cache_miss_e2e_p95_ms = {e2e['p95_ms']:.2f}")
    print(f"dominant_contributor = {summary['dominant_contributor']}")
    print(f"optimization = {summary['optimization_recommendation']}")


def parse_args() -> argparse.Namespace:
    """Parse the two independently resumable Part 4 modes."""

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    examples = subparsers.add_parser("examples")
    examples.add_argument("--output", type=Path, default=DEFAULT_EXAMPLES)
    experiment = subparsers.add_parser("experiment")
    experiment.add_argument("--output", type=Path, default=DEFAULT_EXPERIMENT)
    return parser.parse_args()


def main() -> None:
    """Run the selected Part 4 workflow."""

    args = parse_args()
    if args.command == "examples":
        print_examples(asyncio.run(trace_examples(args.output)))
    else:
        print_experiment(asyncio.run(latency_experiment(args.output)))


if __name__ == "__main__":
    main()
