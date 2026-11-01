"""Shared Kafka and local-Ollama runtime for the HW8 agents."""

import asyncio
import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from hw8_config import (
    KAFKA_BOOTSTRAP_SERVERS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    SEED,
)

PromptBuilder = Callable[[dict[str, Any]], str]
MessageBuilder = Callable[[dict[str, Any], str], dict[str, Any]]


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
    """Consume, process with local Ollama, publish, then commit one message."""

    consumer = AIOKafkaConsumer(
        input_topic,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
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
        f"[{agent_name}] READY input={input_topic} output={output_topic} "
        f"model={OLLAMA_MODEL}",
        flush=True,
    )

    try:
        async for record in consumer:
            source = record.value
            correlation_id = source.get("correlation_id")
            print(
                f"[{agent_name}] RECEIVED topic={record.topic} "
                f"partition={record.partition} offset={record.offset} "
                f"correlation_id={correlation_id}",
                flush=True,
            )
            log_json(f"[{agent_name}] INPUT", source)

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

            await consumer.commit()
            print(
                f"[{agent_name}] COMMITTED input_offset={record.offset}",
                flush=True,
            )
    finally:
        await consumer.stop()
        await producer.stop()
