import json
from dataclasses import dataclass
from typing import Any

from langchain_ollama import ChatOllama


@dataclass
class CompletionResult:
    """Standard result returned by the model adapter."""

    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    metadata: dict[str, Any]


class ModelClient:
    """Reusable adapter for local Ollama model calls."""

    def __init__(
        self,
        model_name: str = "qwen3:8b",
        temperature: float = 0.0,
        output_format: str | dict[str, Any] | None = None,
        reasoning: bool = False,
        base_url: str = "http://localhost:11434"
    ) -> None:
        model_options: dict[str, Any] = {
            "model": model_name,
            "temperature": temperature,
            "reasoning": reasoning,
            "base_url": base_url,
            "num_ctx": 2048,
            "num_predict": 1024
        }

        if output_format is not None:
            model_options["format"] = output_format

        self._model = ChatOllama(**model_options)

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[Any] | None = None
    ) -> CompletionResult:
        """
        Send messages to the model through one stable interface.

        The optional tools parameter is included for future homework.
        """
        model = self._model

        if tools:
            model = self._model.bind_tools(tools)

        response = model.invoke(messages)

        if isinstance(response.content, str):
            content = response.content
        else:
            content = json.dumps(
                response.content,
                ensure_ascii=False
            )

        usage = response.usage_metadata or {}
        metadata = response.response_metadata or {}

        input_tokens = int(
            usage.get(
                "input_tokens",
                metadata.get("prompt_eval_count", 0)
            )
        )

        output_tokens = int(
            usage.get(
                "output_tokens",
                metadata.get("eval_count", 0)
            )
        )

        total_tokens = int(
            usage.get(
                "total_tokens",
                input_tokens + output_tokens
            )
        )

        return CompletionResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            metadata=metadata
        )