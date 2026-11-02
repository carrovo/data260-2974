"""Run the HW8 no-key versus entity-key Kafka ordering experiment."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_config import (
    AGENT_TIMEOUT_SECONDS,
    KAFKA_BOOTSTRAP_SERVERS,
    ORDERING_RESULTS_TOPIC,
    PREFIX,
    TASKS_TOPIC,
    VERIFY_SEED,
)
from hw8_ordering import (
    ENTITY_KEY_MODE,
    NO_KEY_MODE,
    build_ordering_messages,
    ordering_message_key,
    summarize_ordering_run,
)


def parse_args() -> argparse.Namespace:
    """Parse the raw ordering evidence output path."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


async def collect_run(
    consumer: AIOKafkaConsumer,
    run_id: str,
    count: int,
) -> list[dict[str, Any]]:
    """Collect one run's results in broker append order."""

    results: list[dict[str, Any]] = []
    async for record in consumer:
        if record.value.get("run_id") != run_id:
            continue
        results.append(record.value)
        if len(results) == count:
            return results
    raise RuntimeError("Kafka result consumer stopped unexpectedly")


async def publish_run(
    producer: AIOKafkaProducer,
    run_id: str,
    mode: str,
    count: int,
) -> list[dict[str, Any]]:
    """Publish one deterministic ordering run and record Kafka metadata."""

    sent_records: list[dict[str, Any]] = []
    for message in build_ordering_messages(run_id, mode, count):
        key = ordering_message_key(message, mode)
        metadata = await producer.send_and_wait(TASKS_TOPIC, message, key=key)
        sent_records.append(
            {
                "sequence": message["sequence"],
                "entity_id": message["entity_id"],
                "key": key.decode("utf-8") if key is not None else None,
                "topic": metadata.topic,
                "partition": metadata.partition,
                "offset": metadata.offset,
            }
        )
        print(
            f"[ORDERING TEST] SENT mode={mode} "
            f"sequence={message['sequence']} key={sent_records[-1]['key']} "
            f"partition={metadata.partition} offset={metadata.offset}",
            flush=True,
        )
    return sent_records


async def execute_run(
    producer: AIOKafkaProducer,
    consumer: AIOKafkaConsumer,
    mode: str,
    count: int,
) -> dict[str, Any]:
    """Publish and collect one ordering mode."""

    run_id = f"{mode}-{uuid4()}"
    print(
        f"[ORDERING TEST] START mode={mode} run_id={run_id} "
        f"verify_seed={VERIFY_SEED} count={count}",
        flush=True,
    )
    sent_records = await publish_run(producer, run_id, mode, count)
    processed_records = await asyncio.wait_for(
        collect_run(consumer, run_id, count),
        timeout=AGENT_TIMEOUT_SECONDS,
    )
    summary = summarize_ordering_run(sent_records, processed_records)
    summary["run_id"] = run_id
    summary["mode"] = mode
    print(
        f"[ORDERING TEST] COMPLETE mode={mode} "
        f"partitions={summary['partitions_used']} "
        f"writers={summary['writer_instances_used']} "
        f"order_preserved={summary['global_order_preserved']}",
        flush=True,
    )
    return summary


async def run(output_path: Path) -> None:
    """Run both 20-message experiments and write machine-readable evidence."""

    count = 20
    result_consumer = AIOKafkaConsumer(
        ORDERING_RESULTS_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"{PREFIX}_ordering_demo_{uuid4()}",
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )

    await result_consumer.start()
    await producer.start()
    try:
        await result_consumer.getmany(timeout_ms=1000)
        no_key = await execute_run(
            producer, result_consumer, NO_KEY_MODE, count
        )
        entity_key = await execute_run(
            producer, result_consumer, ENTITY_KEY_MODE, count
        )
    finally:
        await result_consumer.stop()
        await producer.stop()

    checks = {
        "no_key_used_two_partitions": no_key["partition_count_used"] == 2,
        "no_key_used_two_writers": no_key["writer_instance_count_used"] == 2,
        "no_key_global_order_changed": not no_key["global_order_preserved"],
        "per_partition_order_preserved": no_key[
            "per_partition_order_preserved"
        ],
        "entity_key_used_one_partition": (
            entity_key["partition_count_used"] == 1
        ),
        "entity_key_preserved_order": entity_key[
            "global_order_preserved"
        ],
    }
    summary = {
        "scenario": "two_partitions_two_writers",
        "verify_seed": VERIFY_SEED,
        "message_count_per_run": count,
        "checks": checks,
        "pass": all(checks.values()),
        "no_key": no_key,
        "entity_key": entity_key,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("[ORDERING TEST] COMPARISON", flush=True)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    print(f"[ORDERING TEST] Wrote {output_path}", flush=True)
    if not summary["pass"]:
        raise RuntimeError(f"ordering checks failed: {checks}")
    print("[ORDERING TEST] PASS", flush=True)


def main() -> None:
    """Run the asynchronous ordering experiment."""

    args = parse_args()
    asyncio.run(run(args.output))


if __name__ == "__main__":
    main()
