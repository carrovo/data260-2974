"""Send and collect the HW8 Writer consumer-death failure experiment."""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_config import (
    AGENT_TIMEOUT_SECONDS,
    FINAL_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    PREFIX,
    TASKS_TOPIC,
)


def parse_args() -> argparse.Namespace:
    """Parse send or collect mode and its evidence-file options."""

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    send_parser = subparsers.add_parser("send")
    send_parser.add_argument("--state", type=Path, required=True)
    send_parser.add_argument("--delay-seconds", type=float, default=45)

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--state", type=Path, required=True)
    return parser.parse_args()


def write_state(path: Path, state: dict[str, Any]) -> None:
    """Write the machine-readable experiment state."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


async def send_test_message(state_path: Path, delay_seconds: float) -> None:
    """Send one planned task that pauses inside Writer before processing."""

    if delay_seconds <= 0 or delay_seconds > 120:
        raise ValueError("delay-seconds must be greater than 0 and at most 120")

    correlation_id = str(uuid4())
    message = {
        "correlation_id": correlation_id,
        "stage": "planned",
        "question": "What should a renter verify before signing a lease?",
        "plan": (
            "Explain how to verify the listing, costs, lease terms, and landlord."
        ),
        "processing_delay_seconds": delay_seconds,
        "failure_scenario": "consumer_death",
    }
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )
    await producer.start()
    try:
        metadata = await producer.send_and_wait(
            TASKS_TOPIC,
            message,
            key=correlation_id.encode("utf-8"),
        )
    finally:
        await producer.stop()

    state = {
        "scenario": "consumer_killed_mid_work",
        "correlation_id": correlation_id,
        "task_topic": metadata.topic,
        "task_partition": metadata.partition,
        "task_offset": metadata.offset,
        "processing_delay_seconds": delay_seconds,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "completed_after_restart": False,
        "final_message": None,
    }
    write_state(state_path, state)
    print("[CONSUMER DEATH TEST] SENT", flush=True)
    print(json.dumps(state, indent=2, sort_keys=True), flush=True)
    print(
        "[CONSUMER DEATH TEST] Wait for Writer PROCESSING STARTED, "
        "then kill Writer before DELAY COMPLETE.",
        flush=True,
    )


async def find_final_message(correlation_id: str) -> dict[str, Any]:
    """Find the correlated final message, including one produced before collection."""

    consumer = AIOKafkaConsumer(
        FINAL_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"{PREFIX}_death_result_{correlation_id}",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    await consumer.start()
    try:
        async for record in consumer:
            message = record.value
            if message.get("correlation_id") == correlation_id:
                return {
                    "topic": record.topic,
                    "partition": record.partition,
                    "offset": record.offset,
                    "value": message,
                }
    finally:
        await consumer.stop()
    raise RuntimeError("Final-topic consumer stopped unexpectedly")


async def collect_result(state_path: Path) -> None:
    """Collect the final message after Writer has been restarted."""

    state = json.loads(state_path.read_text(encoding="utf-8"))
    correlation_id = state["correlation_id"]
    final_message = await asyncio.wait_for(
        find_final_message(correlation_id),
        timeout=AGENT_TIMEOUT_SECONDS,
    )
    state["completed_after_restart"] = True
    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    state["final_message"] = final_message
    write_state(state_path, state)
    print("[CONSUMER DEATH TEST] COMPLETED AFTER RESTART", flush=True)
    print(json.dumps(state, indent=2, sort_keys=True), flush=True)


def main() -> None:
    """Run the selected phase of the consumer-death experiment."""

    args = parse_args()
    if args.command == "send":
        asyncio.run(send_test_message(args.state, args.delay_seconds))
    else:
        asyncio.run(collect_result(args.state))


if __name__ == "__main__":
    main()
