"""Send one question to the HW8 Kafka pipeline and read its final result."""

import argparse
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

DEFAULT_QUESTION = (
    "What information should a renter verify before applying for a rental listing?"
)


def parse_args() -> argparse.Namespace:
    """Parse an optional question from the command line."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    return parser.parse_args()


async def wait_for_result(
    consumer: AIOKafkaConsumer,
    correlation_id: str,
) -> dict[str, Any]:
    """Read final messages until the matching correlation ID arrives."""

    async for record in consumer:
        message = record.value
        if message.get("correlation_id") == correlation_id:
            print(
                f"[CLIENT] RECEIVED FINAL topic={record.topic} "
                f"partition={record.partition} offset={record.offset}",
                flush=True,
            )
            return message
    raise RuntimeError("Final-topic consumer stopped unexpectedly")


async def run(question: str) -> None:
    """Publish a question and display its correlated final JSON result."""

    correlation_id = str(uuid4())
    consumer = AIOKafkaConsumer(
        FINAL_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"{PREFIX}_result_{correlation_id}",
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
        # Join the final-topic consumer group before the pipeline can reply.
        await consumer.getmany(timeout_ms=1000)
        message = {
            "correlation_id": correlation_id,
            "question": question.strip(),
        }
        print(f"[CLIENT] SENDING topic={INBOX_TOPIC}", flush=True)
        print(json.dumps(message, indent=2, sort_keys=True), flush=True)
        metadata = await producer.send_and_wait(
            INBOX_TOPIC,
            message,
            key=correlation_id.encode("utf-8"),
        )
        print(
            f"[CLIENT] SENT partition={metadata.partition} offset={metadata.offset}",
            flush=True,
        )

        final_message = await asyncio.wait_for(
            wait_for_result(consumer, correlation_id),
            timeout=AGENT_TIMEOUT_SECONDS,
        )
        print("[CLIENT] FINAL JSON", flush=True)
        print(json.dumps(final_message, indent=2, sort_keys=True), flush=True)
        if final_message.get("status") != "approved":
            raise RuntimeError("Reviewer did not approve the final message")
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    """Run the asynchronous question sender."""

    args = parse_args()
    asyncio.run(run(args.question))


if __name__ == "__main__":
    main()
