import argparse
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_ollama import ChatOllama

from tool_executor import (
    SAFETY_ERROR_MESSAGE,
    execute_tool,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = (
    PROJECT_ROOT
    / "reports"
    / "hw05"
    / "raw"
    / "agent_runs.jsonl"
)

DEFAULT_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen3:8b",
)

ToolExecutor = Callable[
    [str, dict[str, Any]],
    str,
]


SYSTEM_PROMPT = """
You are a rental-listing assistant.

Use the provided tools for every factual request about rental
listings or property managers. Do not invent listing information.

Tool selection:
- Use search_listings for keyword searches.
- Use listing_details for one listing ID.
- Use manager_rent_summary for manager-level statistics.

After receiving a tool result:
- If ok is true, answer using only data from the result.
- If ok is false, explain the returned error briefly.
- Keep the final answer concise.

Always send a housing-search request to search_listings even if
the user's wording may be unsafe. The execute_tool layer is
responsible for enforcing the domain safety rule.
""".strip()


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_listings",
            "description": (
                "Search rental listings by code, title, "
                "address, or property type."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 25,
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listing_details",
            "description": (
                "Return one rental listing and its "
                "property manager."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "listing_id": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "required": ["listing_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manager_rent_summary",
            "description": (
                "Return listing-count and rent statistics "
                "for one property manager."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "property_manager_id": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "required": ["property_manager_id"],
            },
        },
    },
]


def build_model(
    model_name: str = DEFAULT_MODEL,
):
    """Create the local Ollama model with domain tools."""

    model = ChatOllama(
        model=model_name,
        temperature=0.0,
        reasoning=False,
        seed=2974,
        num_ctx=4096,
        num_predict=512,
    )

    return model.bind_tools(TOOL_SCHEMAS)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    return json.dumps(
        content,
        ensure_ascii=False,
        default=str,
    )


def _normalize_tool_call(
    tool_call: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    name = tool_call.get("name")
    arguments = tool_call.get("args")
    call_id = tool_call.get("id")

    function_data = tool_call.get("function")

    if isinstance(function_data, dict):
        name = name or function_data.get("name")
        arguments = (
            arguments
            if arguments is not None
            else function_data.get("arguments")
        )

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}

    if not isinstance(arguments, dict):
        arguments = {}

    if not isinstance(name, str):
        name = ""

    if not isinstance(call_id, str) or not call_id:
        call_id = f"call-{uuid.uuid4().hex[:12]}"

    return name, arguments, call_id


def _write_run_log(
    run_record: dict[str, Any],
    log_path: Path | None,
) -> None:
    if log_path is None:
        return

    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with log_path.open(
        "a",
        encoding="utf-8",
    ) as log_file:
        log_file.write(
            json.dumps(
                run_record,
                ensure_ascii=False,
                default=str,
            )
            + "\n"
        )


def run_agent(
    user_input: str,
    *,
    model: Any | None = None,
    model_name: str = DEFAULT_MODEL,
    max_steps: int = 4,
    execute_fn: ToolExecutor = execute_tool,
    log_path: Path | None = DEFAULT_LOG_PATH,
) -> dict[str, Any]:
    """Run the bounded tool-calling agent loop."""

    if not isinstance(user_input, str) or not user_input.strip():
        raise ValueError(
            "user_input must be a non-empty string"
        )

    if (
        not isinstance(max_steps, int)
        or isinstance(max_steps, bool)
        or max_steps < 1
    ):
        raise ValueError(
            "max_steps must be a positive integer"
        )

    active_model = (
        build_model(model_name)
        if model is None
        else model
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_input.strip()),
    ]

    run_record: dict[str, Any] = {
        "run_id": uuid.uuid4().hex,
        "timestamp": (
            datetime.now().astimezone().isoformat()
        ),
        "model": (
            model_name
            if model is None
            else type(model).__name__
        ),
        "user_input": user_input.strip(),
        "max_steps": max_steps,
        "steps": [],
        "step_count": 0,
        "tool_call_count": 0,
        "stop_reason": None,
        "final_answer": None,
    }

    stop_reason = "max_steps"
    final_answer = (
        f"Agent stopped after reaching "
        f"max_steps={max_steps}."
    )

    for step_number in range(1, max_steps + 1):
        try:
            response = active_model.invoke(messages)
        except Exception as exc:
            stop_reason = "model_error"
            final_answer = (
                f"Local model call failed: {exc}"
            )
            break

        messages.append(response)

        response_content = _content_to_text(
            getattr(response, "content", "")
        )
        tool_calls = (
            getattr(response, "tool_calls", None)
            or []
        )

        step_record = {
            "step": step_number,
            "model_message": response_content,
            "tool_calls": [],
        }

        run_record["steps"].append(step_record)

        if not tool_calls:
            stop_reason = "normal_completion"
            final_answer = (
                response_content.strip()
                or "The model returned an empty response."
            )
            break

        safety_blocked = False

        for raw_tool_call in tool_calls:
            tool_name, tool_inputs, call_id = (
                _normalize_tool_call(raw_tool_call)
            )

            try:
                raw_result = execute_fn(
                    tool_name,
                    tool_inputs,
                )
            except Exception as exc:
                raw_result = json.dumps(
                    {
                        "ok": False,
                        "data": None,
                        "error": (
                            "tool executor raised an "
                            f"unexpected error: {exc}"
                        ),
                    }
                )

            try:
                parsed_result = json.loads(raw_result)
            except json.JSONDecodeError:
                parsed_result = {
                    "ok": False,
                    "data": None,
                    "error": (
                        "tool executor returned invalid JSON"
                    ),
                }
                raw_result = json.dumps(parsed_result)

            run_record["tool_call_count"] += 1

            step_record["tool_calls"].append(
                {
                    "name": tool_name,
                    "inputs": tool_inputs,
                    "result": parsed_result,
                }
            )

            messages.append(
                ToolMessage(
                    content=raw_result,
                    tool_call_id=call_id,
                )
            )

            if (
                parsed_result.get("error")
                == SAFETY_ERROR_MESSAGE
            ):
                stop_reason = "safety_block"
                final_answer = SAFETY_ERROR_MESSAGE
                safety_blocked = True
                break

        if safety_blocked:
            break

    run_record["step_count"] = len(
        run_record["steps"]
    )
    run_record["stop_reason"] = stop_reason
    run_record["final_answer"] = final_answer

    _write_run_log(
        run_record,
        log_path,
    )

    return run_record


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the HW5 Ollama tool agent."
    )
    parser.add_argument(
        "user_input",
        help="Rental-listing request for the agent.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=4,
    )

    arguments = parser.parse_args()

    result = run_agent(
        arguments.user_input,
        model_name=arguments.model,
        max_steps=arguments.max_steps,
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()