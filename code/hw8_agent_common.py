"""Shared Kafka and local-Ollama runtime for the HW8 agents."""

import asyncio
import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_agent_logic import processing_delay_seconds
from hw8_config import (
    AGENT_MAX_ATTEMPTS,
    AGENT_RETRY_BACKOFF_SECONDS,
    DEAD_LETTER_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    SEED,
)

PromptBuilder = Callable[[dict[str, Any]], str]
MessageBuilder = Callable[[dict[str, Any], str], dict[str, Any]]


def decode_json_object(raw_value: bytes) -> dict[str, Any]:
    """Decode one Kafka value and require a JSON object."""

    try:
        value = json.loads(raw_value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("message must be a valid UTF-8 JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("message must be a valid UTF-8 JSON object")
    return value


def build_dead_letter_message(
    *,
    agent_name: str,
    source_topic: str,
    source_partition: int,
    source_offset: int,
    attempts: int,
    error: Exception,
    raw_value: bytes,
    source: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a machine-readable dead-letter record for a failed message."""

    correlation_id = source.get("correlation_id") if source else None
    return {
        "correlation_id": correlation_id,
        "failed_agent": agent_name,
        "source_topic": source_topic,
        "source_partition": source_partition,
        "source_offset": source_offset,
        "attempts": attempts,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "original_message": source,
        "raw_value": raw_value.decode("utf-8", errors="replace"),
    }


def log_json(label: str, value: object) -> None:
    """Print labeled JSON immediately for pipeline evidence."""

    print(f"{label} {json.dumps(value, indent=2, sort_keys=True)}", flush=True)


def call_ollama(system_prompt: str, user_prompt: str) -> str:
    """Call only the configured local Ollama endpoint and return model text."""

    endpoint = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "think": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": 0,
            "seed": SEED,
            "num_predict": 384,
        },
    }
    request = Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Local Ollama request failed: {exc}") from exc

    content = payload.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Local Ollama returned an empty response")
    return content.strip()


async def run_agent(
    *,
    agent_name: str,
    input_topic: str,
    output_topic: str,
    group_id: str,
    system_prompt: str,
    prompt_builder: PromptBuilder,
    message_builder: MessageBuilder,
) -> None:
    """Process with bounded retries, publish or dead-letter, then commit."""

    if AGENT_MAX_ATTEMPTS < 1:
        raise ValueError("HW8_AGENT_MAX_ATTEMPTS must be at least 1")
    if AGENT_RETRY_BACKOFF_SECONDS < 0:
        raise ValueError("HW8_AGENT_RETRY_BACKOFF_SECONDS cannot be negative")

    consumer = AIOKafkaConsumer(
        input_topic,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )

    await consumer.start()
    await producer.start()
    print(
        f"[{agent_name}] READY input={input_topic} output={output_topic} "
        f"model={OLLAMA_MODEL}",
        flush=True,
    )

    try:
        async for record in consumer:
            raw_value = record.value
            source: dict[str, Any] | None = None
            try:
                source = decode_json_object(raw_value)
            except ValueError:
                pass
            correlation_id = source.get("correlation_id") if source else None
            print(
                f"[{agent_name}] RECEIVED topic={record.topic} "
                f"partition={record.partition} offset={record.offset} "
                f"correlation_id={correlation_id}",
                flush=True,
            )
            if source is not None:
                log_json(f"[{agent_name}] INPUT", source)
            else:
                print(
                    f"[{agent_name}] INPUT raw={raw_value!r}",
                    flush=True,
                )

            last_error: Exception | None = None
            for attempt in range(1, AGENT_MAX_ATTEMPTS + 1):
                print(
                    f"[{agent_name}] ATTEMPT {attempt}/{AGENT_MAX_ATTEMPTS} "
                    f"partition={record.partition} offset={record.offset} "
                    f"correlation_id={correlation_id}",
                    flush=True,
                )
                try:
                    source = decode_json_object(raw_value)
                    correlation_id = source.get("correlation_id")
                    delay_seconds = processing_delay_seconds(source)
                    print(
                        f"[{agent_name}] PROCESSING STARTED "
                        f"partition={record.partition} offset={record.offset} "
                        f"correlation_id={correlation_id} "
                        f"delay_seconds={delay_seconds:g}",
                        flush=True,
                    )
                    if delay_seconds:
                        await asyncio.sleep(delay_seconds)
                        print(
                            f"[{agent_name}] DELAY COMPLETE "
                            f"partition={record.partition} offset={record.offset} "
                            f"correlation_id={correlation_id}",
                            flush=True,
                        )

                    prompt = prompt_builder(source)
                    model_output = await asyncio.to_thread(
                        call_ollama,
                        system_prompt,
                        prompt,
                    )
                    outgoing = message_builder(source, model_output)
                    log_json(f"[{agent_name}] OUTPUT", outgoing)

                    key = str(outgoing["correlation_id"]).encode("utf-8")
                    metadata = await producer.send_and_wait(
                        output_topic,
                        outgoing,
                        key=key,
                    )
                    print(
                        f"[{agent_name}] SENT topic={metadata.topic} "
                        f"partition={metadata.partition} offset={metadata.offset} "
                        f"correlation_id={outgoing['correlation_id']}",
                        flush=True,
                    )
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    print(
                        f"[{agent_name}] FAILED attempt={attempt}/"
                        f"{AGENT_MAX_ATTEMPTS} "
                        f"error={type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    if attempt < AGENT_MAX_ATTEMPTS:
                        print(
                            f"[{agent_name}] RETRYING next_attempt={attempt + 1}/"
                            f"{AGENT_MAX_ATTEMPTS}",
                            flush=True,
                        )
                        await asyncio.sleep(AGENT_RETRY_BACKOFF_SECONDS)

            if last_error is not None:
                dead_letter = build_dead_letter_message(
                    agent_name=agent_name,
                    source_topic=record.topic,
                    source_partition=record.partition,
                    source_offset=record.offset,
                    attempts=AGENT_MAX_ATTEMPTS,
                    error=last_error,
                    raw_value=raw_value,
                    source=source,
                )
                dlq_key = str(
                    dead_letter.get("correlation_id")
                    or f"{record.topic}-{record.partition}-{record.offset}"
                ).encode("utf-8")
                metadata = await producer.send_and_wait(
                    DEAD_LETTER_TOPIC,
                    dead_letter,
                    key=dlq_key,
                )
                print(
                    f"[{agent_name}] MOVED TO DLQ topic={metadata.topic} "
                    f"partition={metadata.partition} offset={metadata.offset} "
                    f"attempts={AGENT_MAX_ATTEMPTS} "
                    f"correlation_id={correlation_id}",
                    flush=True,
                )
                log_json(f"[{agent_name}] DLQ", dead_letter)

            await consumer.commit()
            disposition = "dead_letter" if last_error is not None else "success"
            print(
                f"[{agent_name}] COMMITTED input_offset={record.offset} "
                f"disposition={disposition}",
                flush=True,
            )
    finally:
        await consumer.stop()
        await producer.stop()
