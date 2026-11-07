"""Client for sending one question through the existing HW8 agent pipeline."""

import asyncio
import json
from typing import Any
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_config import (
    AGENT_TIMEOUT_SECONDS,
    FINAL_TOPIC,
    INBOX_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    PREFIX,
)


async def _wait_for_result(
    consumer: AIOKafkaConsumer,
    correlation_id: str,
) -> dict[str, Any]:
    """Return the final message matching the submitted correlation ID."""

    async for record in consumer:
        message = record.value
        if message.get("correlation_id") == correlation_id:
            return message
    raise RuntimeError("The HW8 final-topic consumer stopped unexpectedly")


async def run_hw8_agent_pipeline(question: str) -> str:
    """Run the normal Planner/Writer/Reviewer path and return its final answer."""

    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question is required")

    correlation_id = str(uuid4())
    consumer = AIOKafkaConsumer(
        FINAL_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"{PREFIX}_hw9_result_{correlation_id}",
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
        # Force the unique consumer group to join before an answer can be published.
        await consumer.getmany(timeout_ms=1000)
        message = {
            "correlation_id": correlation_id,
            "question": normalized_question,
        }
        metadata = await producer.send_and_wait(
            INBOX_TOPIC,
            message,
            key=correlation_id.encode("utf-8"),
        )
        print(
            "[HW9 AGENT] SENT "
            f"topic={metadata.topic} partition={metadata.partition} "
            f"offset={metadata.offset} correlation_id={correlation_id}",
            flush=True,
        )
        final_message = await asyncio.wait_for(
            _wait_for_result(consumer, correlation_id),
            timeout=AGENT_TIMEOUT_SECONDS,
        )
    finally:
        await consumer.stop()
        await producer.stop()

    if final_message.get("status") != "approved":
        raise RuntimeError(
            "The HW8 Reviewer did not approve the final agent response"
        )
    answer = final_message.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("The HW8 agent pipeline returned an empty answer")
    return answer.strip()
