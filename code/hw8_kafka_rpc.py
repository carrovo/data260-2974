"""Asynchronous Kafka request/response client used by the HW8 FastAPI service."""

import asyncio
import json
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_config import (
    API_RESPONSE_GROUP_ID,
    KAFKA_BOOTSTRAP_SERVERS,
    REQUEST_TOPIC,
    RESPONSE_TOPIC,
    RPC_TIMEOUT_SECONDS,
)


class KafkaRPC:
    """Match Kafka responses to waiting FastAPI requests by correlation ID."""

    def __init__(self) -> None:
        self.producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        )
        self.consumer = AIOKafkaConsumer(
            RESPONSE_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=API_RESPONSE_GROUP_ID,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        self.pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.consumer_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the Kafka producer and background response consumer."""

        await self.producer.start()
        await self.consumer.start()
        self.consumer_task = asyncio.create_task(self.consume_responses())
        print(f"[FASTAPI] Kafka RPC started; request_topic={REQUEST_TOPIC}", flush=True)
        print(f"[FASTAPI] Listening on response_topic={RESPONSE_TOPIC}", flush=True)

    async def stop(self) -> None:
        """Stop the background response consumer and Kafka clients."""

        if self.consumer_task is not None:
            self.consumer_task.cancel()
            try:
                await self.consumer_task
            except asyncio.CancelledError:
                pass
        await self.consumer.stop()
        await self.producer.stop()

    async def consume_responses(self) -> None:
        """Resolve the pending Future whose correlation ID matches each response."""

        async for message in self.consumer:
            response = message.value
            correlation_id = response.get("correlation_id")
            print(
                "[FASTAPI] RECEIVED RESPONSE "
                f"topic={message.topic} partition={message.partition} "
                f"offset={message.offset} correlation_id={correlation_id}",
                flush=True,
            )
            print(
                f"[FASTAPI] RESPONSE {json.dumps(response, indent=2, sort_keys=True)}",
                flush=True,
            )

            if isinstance(correlation_id, str):
                future = self.pending.pop(correlation_id, None)
                if future is not None and not future.done():
                    future.set_result(response)
                else:
                    print(
                        "[FASTAPI] No pending request for "
                        f"correlation_id={correlation_id}",
                        flush=True,
                    )

    async def make_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Publish one request and wait for its matching Kafka response."""

        correlation_id = request.get("correlation_id")
        if not isinstance(correlation_id, str) or not correlation_id:
            raise ValueError("correlation_id is required")
        if correlation_id in self.pending:
            raise ValueError("correlation_id is already pending")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.pending[correlation_id] = future

        print(
            "[FASTAPI] SENDING REQUEST "
            f"topic={REQUEST_TOPIC} correlation_id={correlation_id}",
            flush=True,
        )
        print(
            f"[FASTAPI] REQUEST {json.dumps(request, indent=2, sort_keys=True)}",
            flush=True,
        )

        try:
            metadata = await self.producer.send_and_wait(REQUEST_TOPIC, request)
            print(
                "[FASTAPI] SENT REQUEST "
                f"topic={metadata.topic} partition={metadata.partition} "
                f"offset={metadata.offset}",
                flush=True,
            )
            return await asyncio.wait_for(future, timeout=RPC_TIMEOUT_SECONDS)
        except TimeoutError:
            return {
                "correlation_id": correlation_id,
                "success": False,
                "error": "Kafka worker response timed out",
            }
        finally:
            self.pending.pop(correlation_id, None)
