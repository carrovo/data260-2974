"""Kafka ordering experiment helpers and Writer observation mode."""

import asyncio
import json
import os
import random
from collections import defaultdict
from typing import Any

from hw8_config import (
    DOMAIN_ID,
    KAFKA_BOOTSTRAP_SERVERS,
    ORDERING_RESULTS_TOPIC,
    TASKS_TOPIC,
    VERIFY_SEED,
    WRITER_GROUP_ID,
)

NO_KEY_MODE = "no_key"
ENTITY_KEY_MODE = "entity_key"
ORDERING_MODES = {NO_KEY_MODE, ENTITY_KEY_MODE}


def build_ordering_messages(
    run_id: str,
    mode: str,
    count: int = 20,
) -> list[dict[str, Any]]:
    """Create deterministic related messages from VERIFY_SEED."""

    if mode not in ORDERING_MODES:
        raise ValueError(f"unsupported ordering mode: {mode}")
    if count < 1:
        raise ValueError("count must be at least 1")

    rng = random.Random(VERIFY_SEED)
    entity_id = f"property-{DOMAIN_ID}-{VERIFY_SEED}"
    seeded_values = rng.sample(range(1000, 10000), count)
    return [
        {
            "correlation_id": f"ordering-{run_id}-{sequence:02d}",
            "stage": "planned",
            "question": (
                f"Apply related update {sequence} to {entity_id}."
            ),
            "plan": "Record the ordered update for the same rental entity.",
            "failure_scenario": "ordering",
            "ordering_mode": mode,
            "run_id": run_id,
            "entity_id": entity_id,
            "sequence": sequence,
            "seeded_value": seeded_values[sequence - 1],
            "verify_seed": VERIFY_SEED,
            # Earlier messages wait longer so two partitions visibly interleave.
            "ordering_delay_seconds": round((count - sequence) * 0.03, 2),
        }
        for sequence in range(1, count + 1)
    ]


def ordering_message_key(message: dict[str, Any], mode: str) -> bytes | None:
    """Return no key for the baseline or the related entity key for the fix."""

    if mode == NO_KEY_MODE:
        return None
    if mode == ENTITY_KEY_MODE:
        return str(message["entity_id"]).encode("utf-8")
    raise ValueError(f"unsupported ordering mode: {mode}")


def summarize_ordering_run(
    sent_records: list[dict[str, Any]],
    processed_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize partition placement and observed processing order."""

    sent_sequence = [int(record["sequence"]) for record in sent_records]
    processed_sequence = [
        int(record["sequence"]) for record in processed_records
    ]
    per_partition: dict[int, list[int]] = defaultdict(list)
    for record in processed_records:
        per_partition[int(record["source_partition"])].append(
            int(record["sequence"])
        )

    partitions_used = sorted(
        {int(record["partition"]) for record in sent_records}
    )
    workers_used = sorted(
        {str(record["writer_instance"]) for record in processed_records}
    )
    return {
        "message_count": len(sent_records),
        "entity_id": sent_records[0]["entity_id"] if sent_records else None,
        "keys": sorted(
            {record["key"] for record in sent_records},
            key=lambda value: "" if value is None else str(value),
        ),
        "partitions_used": partitions_used,
        "partition_count_used": len(partitions_used),
        "writer_instances_used": workers_used,
        "writer_instance_count_used": len(workers_used),
        "sent_sequence": sent_sequence,
        "processed_sequence": processed_sequence,
        "global_order_preserved": processed_sequence == sent_sequence,
        "per_partition_sequences": {
            str(partition): sequence
            for partition, sequence in sorted(per_partition.items())
        },
        "per_partition_order_preserved": all(
            sequence == sorted(sequence) for sequence in per_partition.values()
        ),
        "sent_records": sent_records,
        "processed_records": processed_records,
    }


async def run_ordering_writer() -> None:
    """Run Writer in a model-free mode that records actual Kafka order."""

    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

    writer_instance = os.getenv("HOSTNAME", "ordering-writer-local")
    consumer = AIOKafkaConsumer(
        TASKS_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=WRITER_GROUP_ID,
        auto_offset_reset="latest",
        enable_auto_commit=False,
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )

    await consumer.start()
    await producer.start()
    print(
        f"[ORDERING-WRITER] READY instance={writer_instance} "
        f"group={WRITER_GROUP_ID} input={TASKS_TOPIC} "
        f"output={ORDERING_RESULTS_TOPIC}",
        flush=True,
    )
    try:
        async for record in consumer:
            source = json.loads(record.value.decode("utf-8"))
            if not isinstance(source, dict):
                raise ValueError("ordering message must be a JSON object")
            if source.get("failure_scenario") != "ordering":
                print(
                    f"[ORDERING-WRITER] SKIPPED instance={writer_instance} "
                    f"partition={record.partition} offset={record.offset}",
                    flush=True,
                )
                await consumer.commit()
                continue

            delay_seconds = float(source["ordering_delay_seconds"])
            if delay_seconds < 0:
                raise ValueError("ordering_delay_seconds cannot be negative")
            await asyncio.sleep(delay_seconds)
            result = {
                "run_id": source["run_id"],
                "ordering_mode": source["ordering_mode"],
                "entity_id": source["entity_id"],
                "sequence": source["sequence"],
                "verify_seed": source["verify_seed"],
                "writer_instance": writer_instance,
                "source_topic": record.topic,
                "source_partition": record.partition,
                "source_offset": record.offset,
            }
            metadata = await producer.send_and_wait(
                ORDERING_RESULTS_TOPIC,
                result,
                key=str(source["run_id"]).encode("utf-8"),
            )
            print(
                f"[ORDERING-WRITER] PROCESSED instance={writer_instance} "
                f"mode={source['ordering_mode']} sequence={source['sequence']} "
                f"entity={source['entity_id']} "
                f"source_partition={record.partition} "
                f"source_offset={record.offset} "
                f"result_offset={metadata.offset}",
                flush=True,
            )
            await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()
