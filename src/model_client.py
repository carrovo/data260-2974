import json
from dataclasses import dataclass, field
from typing import Any, Sequence

from langchain_core.messages import AIMessage, BaseMessage
from langchain_ollama import ChatOllama


@dataclass
class CompletionResult:
    """Standard result returned by the model adapter."""

    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    metadata: dict[str, Any]
    message: AIMessage | None = None
    tool_calls: list[dict[str, Any]] = field(
        default_factory=list
    )
    invalid_tool_calls: list[dict[str, Any]] = field(
        default_factory=list
    )
    usage_metadata: dict[str, Any] = field(
        default_factory=dict
    )


class ModelClient:
    """Reusable adapter for local Ollama model calls."""

    def __init__(
        self,
        model_name: str = "qwen3:8b",
        temperature: float = 0.0,
        output_format: str | dict[str, Any] | None = None,
        reasoning: bool = False,
        base_url: str = "http://localhost:11434",
        seed: int | None = None,
        num_ctx: int = 2048,
        num_predict: int = 1024,
    ) -> None:
        model_options: dict[str, Any] = {
            "model": model_name,
            "temperature": temperature,
            "reasoning": reasoning,
            "base_url": base_url,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        }

        if output_format is not None:
            model_options["format"] = output_format # Set the output format to the output format.
        if seed is not None:
            model_options["seed"] = seed # Set the seed to the seed.

        self._model = ChatOllama(**model_options)

    def complete(
        self,
        messages: Sequence[
            BaseMessage | dict[str, Any]
        ],
        tools: list[Any] | None = None,
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
            metadata=dict(metadata),
            message=response,
            tool_calls=list(
                getattr(response, "tool_calls", None)
                or []
            ),
            invalid_tool_calls=list(
                getattr(
                    response,
                    "invalid_tool_calls",
                    None,
                )
                or []
            ),
            usage_metadata=dict(usage),
        )
