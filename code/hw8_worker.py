"""Kafka worker for the HW8 rental-listing request/response service."""

import asyncio
import json
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_config import (
    KAFKA_BOOTSTRAP_SERVERS,
    REQUEST_TOPIC,
    RESPONSE_TOPIC,
    WORKER_GROUP_ID,
)
from hw8_messages import process_request

entities: dict[str, dict[str, Any]] = {}


def log_json(label: str, value: object) -> None:
    """Print one labeled JSON value immediately for screenshot evidence."""

    print(f"{label} {json.dumps(value, indent=2, sort_keys=True)}", flush=True)


async def run_worker() -> None:
    """Consume listing requests, process them, and publish correlated responses."""

    consumer = AIOKafkaConsumer(
        REQUEST_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=WORKER_GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )

    await consumer.start()
    await producer.start()
    print(
        f"Consumer is ready and listening... topic={REQUEST_TOPIC}",
        flush=True,
    )

    try:
        async for message in consumer:
            request = message.value
            operation = request.get("operation") if isinstance(request, dict) else None
            correlation_id = (
                request.get("correlation_id") if isinstance(request, dict) else None
            )
            print(
                "[WORKER] RECEIVED "
                f"topic={message.topic} partition={message.partition} "
                f"offset={message.offset}",
                flush=True,
            )
            log_json("[WORKER] REQUEST", request)

            response = process_request(request, entities)
            print(
                f"[WORKER] PROCESSED operation={operation} "
                f"correlation_id={correlation_id}",
                flush=True,
            )
            log_json("[WORKER] RESPONSE", response)

            metadata = await producer.send_and_wait(RESPONSE_TOPIC, response)
            print(
                "[WORKER] SENT "
                f"topic={metadata.topic} partition={metadata.partition} "
                f"offset={metadata.offset}",
                flush=True,
            )

            await consumer.commit()
            print(
                f"[WORKER] COMMITTED request_offset={message.offset}",
                flush=True,
            )
    finally:
        await consumer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(run_worker())
