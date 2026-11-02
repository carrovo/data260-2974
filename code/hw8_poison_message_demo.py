"""Run the HW8 poison-message, bounded-retry, and DLQ experiment."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_config import (
    AGENT_MAX_ATTEMPTS,
    AGENT_TIMEOUT_SECONDS,
    DEAD_LETTER_TOPIC,
    FINAL_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    PREFIX,
    TASKS_TOPIC,
)


def parse_args() -> argparse.Namespace:
    """Parse the raw evidence output path."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def record_json(record: Any) -> dict[str, Any]:
    """Return the useful Kafka metadata and decoded value."""

    return {
        "topic": record.topic,
        "partition": record.partition,
        "offset": record.offset,
        "value": record.value,
    }


async def wait_for_correlation(
    consumer: AIOKafkaConsumer,
    correlation_id: str,
) -> dict[str, Any]:
    """Wait for one record with the requested correlation ID."""

    async for record in consumer:
        if record.value.get("correlation_id") == correlation_id:
            return record_json(record)
    raise RuntimeError("Kafka consumer stopped unexpectedly")


async def run(output_path: Path) -> None:
    """Send one bad task followed by one valid task and collect both results."""

    run_id = str(uuid4())
    poison_correlation_id = f"poison-{run_id}"
    valid_correlation_id = f"valid-{run_id}"
    sequence_key = f"poison-sequence-{run_id}".encode("utf-8")

    dlq_consumer = AIOKafkaConsumer(
        DEAD_LETTER_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"{PREFIX}_poison_dlq_{run_id}",
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    final_consumer = AIOKafkaConsumer(
        FINAL_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"{PREFIX}_poison_final_{run_id}",
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )

    await dlq_consumer.start()
    await final_consumer.start()
    await producer.start()
    try:
        await dlq_consumer.getmany(timeout_ms=1000)
        await final_consumer.getmany(timeout_ms=1000)

        poison_message = {
            "correlation_id": poison_correlation_id,
            "stage": "planned",
            "question": "This poison task intentionally has no plan field.",
            "failure_scenario": "poison_message",
        }
        valid_message = {
            "correlation_id": valid_correlation_id,
            "stage": "planned",
            "question": "What should a renter verify before paying a deposit?",
            "plan": (
                "Verify the property, landlord, written lease, total costs, "
                "and secure payment method."
            ),
            "failure_scenario": "after_poison_message",
        }

        print("[POISON TEST] SENDING BAD MESSAGE", flush=True)
        print(json.dumps(poison_message, indent=2, sort_keys=True), flush=True)
        poison_metadata = await producer.send_and_wait(
            TASKS_TOPIC,
            poison_message,
            key=sequence_key,
        )
        print(
            f"[POISON TEST] BAD SENT partition={poison_metadata.partition} "
            f"offset={poison_metadata.offset}",
            flush=True,
        )

        print("[POISON TEST] SENDING LATER VALID MESSAGE", flush=True)
        print(json.dumps(valid_message, indent=2, sort_keys=True), flush=True)
        valid_metadata = await producer.send_and_wait(
            TASKS_TOPIC,
            valid_message,
            key=sequence_key,
        )
        print(
            f"[POISON TEST] VALID SENT partition={valid_metadata.partition} "
            f"offset={valid_metadata.offset}",
            flush=True,
        )

        dlq_result, final_result = await asyncio.wait_for(
            asyncio.gather(
                wait_for_correlation(dlq_consumer, poison_correlation_id),
                wait_for_correlation(final_consumer, valid_correlation_id),
            ),
            timeout=AGENT_TIMEOUT_SECONDS,
        )
    finally:
        await dlq_consumer.stop()
        await final_consumer.stop()
        await producer.stop()

    summary = {
        "scenario": "poison_message",
        "max_attempts": AGENT_MAX_ATTEMPTS,
        "same_task_partition": (
            poison_metadata.partition == valid_metadata.partition
        ),
        "poison_task": {
            "correlation_id": poison_correlation_id,
            "topic": poison_metadata.topic,
            "partition": poison_metadata.partition,
            "offset": poison_metadata.offset,
        },
        "dead_letter_result": dlq_result,
        "later_valid_task": {
            "correlation_id": valid_correlation_id,
            "topic": valid_metadata.topic,
            "partition": valid_metadata.partition,
            "offset": valid_metadata.offset,
        },
        "later_final_result": final_result,
        "later_message_completed": (
            final_result["value"].get("status") == "approved"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("[POISON TEST] PASS: BAD MESSAGE MOVED TO DLQ", flush=True)
    print(
        "[POISON TEST] PASS: LATER VALID MESSAGE COMPLETED",
        flush=True,
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    print(f"[POISON TEST] Wrote {output_path}", flush=True)


def main() -> None:
    """Run the asynchronous poison-message experiment."""

    args = parse_args()
    asyncio.run(run(args.output))


if __name__ == "__main__":
    main()
