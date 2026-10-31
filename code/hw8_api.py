"""FastAPI wrapper for the HW8 Kafka listing request/response service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from hw8_config import PORT_BASE, REQUEST_TOPIC, RESPONSE_TOPIC
from hw8_kafka_rpc import KafkaRPC

rpc = KafkaRPC()


class ListingKafkaRequest(BaseModel):
    """HTTP request body that becomes the required Kafka request envelope."""

    correlation_id: str = Field(min_length=1)
    reply_to: str = RESPONSE_TOPIC
    operation: str = Field(min_length=1)
    data: dict[str, Any]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start and stop the Kafka RPC client with the FastAPI application."""

    await rpc.start()
    print(
        f"FastAPI service available at http://127.0.0.1:{PORT_BASE}",
        flush=True,
    )
    yield
    await rpc.stop()


app = FastAPI(
    title="DATA 260 HW8 Rental Listing Kafka API",
    version="8.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, object]:
    """Return the service health and exact Part 1 topic names."""

    return {
        "status": "ok",
        "request_topic": REQUEST_TOPIC,
        "response_topic": RESPONSE_TOPIC,
    }


@app.post("/hw8/listings")
async def listing_operation(payload: ListingKafkaRequest) -> dict[str, Any]:
    """Send one correlated listing operation through Kafka."""

    request = payload.model_dump()
    response = await rpc.make_request(request)
    print(
        "[FASTAPI] RETURNING HTTP RESPONSE "
        f"correlation_id={response.get('correlation_id')}",
        flush=True,
    )
    return response
