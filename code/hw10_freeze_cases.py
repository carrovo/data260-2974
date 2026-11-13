"""Freeze 20 Writer drafts before any HW10 judge scores are produced."""

import argparse
import asyncio
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_config import (
    AGENT_TIMEOUT_SECONDS,
    DRAFTS_TOPIC,
    INBOX_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    OLLAMA_MODEL,
    PREFIX,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = PROJECT_ROOT / "hw10_eval_questions.json"
DEFAULT_CASES = PROJECT_ROOT / "eval_cases.json"
DEFAULT_LABELS = PROJECT_ROOT / "human_labels.csv"
EXPECTED_CASE_COUNT = 20


def utc_now() -> str:
    """Return one reproducible UTC timestamp string."""

    return datetime.now(UTC).isoformat()


def load_questions(path: Path) -> list[dict[str, str]]:
    """Load and validate the fixed 20-question domain case bank."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != EXPECTED_CASE_COUNT:
        raise ValueError(
            f"{path} must contain exactly {EXPECTED_CASE_COUNT} questions"
        )

    questions: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"question {index} must be a JSON object")
        case_id = item.get("case_id")
        question = item.get("question")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"question {index} has an invalid case_id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate case_id: {case_id}")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{case_id} has an invalid question")
        seen_ids.add(case_id)
        questions.append(
            {"case_id": case_id.strip(), "question": question.strip()}
        )
    return questions


def load_existing_cases(path: Path) -> list[dict[str, Any]]:
    """Load a partial case file so an interrupted run can resume safely."""

    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON array")
    case_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"{path} contains a non-object case")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{path} contains a case without case_id")
        if case_id in case_ids:
            raise ValueError(f"{path} contains duplicate case_id {case_id}")
        case_ids.add(case_id)
    return payload


def write_json_atomic(path: Path, payload: object) -> None:
    """Write JSON through a sibling temporary file to preserve checkpoints."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_label_template(path: Path, case_ids: list[str]) -> None:
    """Create a blank human-only label sheet without overwriting prior work."""

    if path.exists():
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["case_id", "human_score", "notes"],
        )
        writer.writeheader()
        for case_id in case_ids:
            writer.writerow(
                {"case_id": case_id, "human_score": "", "notes": ""}
            )


async def wait_for_draft(
    consumer: AIOKafkaConsumer,
    correlation_id: str,
) -> dict[str, Any]:
    """Return the Writer message matching one submitted correlation ID."""

    async for record in consumer:
        value = record.value
        if value.get("correlation_id") == correlation_id:
            return value
    raise RuntimeError("Draft-topic consumer stopped unexpectedly")


async def collect_writer_draft(
    case_id: str,
    question: str,
) -> dict[str, Any]:
    """Send one question through Planner and Writer and capture the draft."""

    correlation_id = str(uuid4())
    consumer = AIOKafkaConsumer(
        DRAFTS_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"{PREFIX}_hw10_freeze_{correlation_id}",
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
        # Ensure the unique group is assigned before the Writer can reply.
        await consumer.getmany(timeout_ms=1000)
        submitted_at = utc_now()
        message = {
            "correlation_id": correlation_id,
            "question": question,
        }
        await producer.send_and_wait(
            INBOX_TOPIC,
            message,
            key=correlation_id.encode("utf-8"),
        )
        draft_message = await asyncio.wait_for(
            wait_for_draft(consumer, correlation_id),
            timeout=AGENT_TIMEOUT_SECONDS,
        )
    finally:
        await consumer.stop()
        await producer.stop()

    plan = draft_message.get("plan")
    draft = draft_message.get("draft")
    if not isinstance(plan, str) or not plan.strip():
        raise RuntimeError(f"{case_id} returned an empty Planner plan")
    if not isinstance(draft, str) or not draft.strip():
        raise RuntimeError(f"{case_id} returned an empty Writer draft")
    return {
        "case_id": case_id,
        "correlation_id": correlation_id,
        "question": question,
        "plan": plan.strip(),
        "draft": draft.strip(),
        "metadata": {
            "domain": "rental housing listings",
            "pipeline": "HW8 Planner-Writer",
            "planner_model": OLLAMA_MODEL,
            "writer_model": OLLAMA_MODEL,
            "temperature": 0,
            "seed": 2974,
            "submitted_at": submitted_at,
            "captured_at": utc_now(),
        },
    }


async def freeze_cases(
    questions_path: Path,
    cases_path: Path,
    labels_path: Path,
) -> None:
    """Capture missing cases, checkpoint each result, and make label sheet."""

    questions = load_questions(questions_path)
    existing = load_existing_cases(cases_path)
    allowed_ids = {item["case_id"] for item in questions}
    unexpected_ids = {
        str(item["case_id"]) for item in existing
    } - allowed_ids
    if unexpected_ids:
        raise ValueError(
            "existing eval_cases.json contains unexpected IDs: "
            + ", ".join(sorted(unexpected_ids))
        )

    cases_by_id = {str(item["case_id"]): item for item in existing}
    for position, item in enumerate(questions, start=1):
        case_id = item["case_id"]
        if case_id in cases_by_id:
            print(
                f"[HW10 FREEZE] {position}/{EXPECTED_CASE_COUNT} "
                f"{case_id} already captured",
                flush=True,
            )
            continue
        print(
            f"[HW10 FREEZE] {position}/{EXPECTED_CASE_COUNT} "
            f"capturing {case_id}",
            flush=True,
        )
        captured = await collect_writer_draft(case_id, item["question"])
        cases_by_id[case_id] = captured
        ordered = [
            cases_by_id[question["case_id"]]
            for question in questions
            if question["case_id"] in cases_by_id
        ]
        write_json_atomic(cases_path, ordered)
        print(
            f"[HW10 FREEZE] saved checkpoint with {len(ordered)} cases",
            flush=True,
        )

    ordered = [cases_by_id[item["case_id"]] for item in questions]
    write_json_atomic(cases_path, ordered)
    write_label_template(
        labels_path,
        [item["case_id"] for item in questions],
    )
    print(
        f"[HW10 FREEZE] complete: {len(ordered)} drafts saved to {cases_path}",
        flush=True,
    )
    print(
        f"[HW10 FREEZE] manually assign 1-5 labels in {labels_path} "
        "before any judge run",
        flush=True,
    )


def parse_args() -> argparse.Namespace:
    """Parse optional file locations for reproducible local runs."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    return parser.parse_args()


def main() -> None:
    """Run the bounded asynchronous case-freezing workflow."""

    args = parse_args()
    asyncio.run(freeze_cases(args.questions, args.cases, args.labels))


if __name__ == "__main__":
    main()
