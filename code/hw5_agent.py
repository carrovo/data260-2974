# ruff: noqa: E402

import argparse
import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.model_client import CompletionResult, ModelClient

from tool_executor import (
    SAFETY_ERROR_MESSAGE,
    TOOL_CONTRACTS,
    TOOL_SCHEMAS,
    ToolSchemaValidationError,
    UnknownToolError,
    execute_tool,
    validate_tool_inputs,
)

DEFAULT_LOG_PATH = (
    PROJECT_ROOT
    / "reports"
    / "hw07"
    / "raw"
    / "part2_agent_runs.jsonl"
)

DEFAULT_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen3:8b",
)

ToolExecutor = Callable[
    [str, Any],
    str,
]

RELIABILITY_CATEGORIES = (
    "malformed_arguments",
    "unknown_tool",
    "text_when_tool_required",
    "lost_multi_step_chain",
)


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


def build_model(
    model_name: str = DEFAULT_MODEL,
):
    """Create the HW1 model adapter used by the agent loop."""

    return ModelClient(
        model_name=model_name,
        temperature=0.0,
        reasoning=False,
        base_url=os.getenv(
            "OLLAMA_BASE_URL",
            "http://127.0.0.1:11434",
        ),
        seed=2974,
        num_ctx=4096,
        num_predict=512,
    )


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
    """Strictly parse one native tool call without hiding errors."""

    if not isinstance(tool_call, dict):
        raise ValueError("tool call must be an object")

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
        except json.JSONDecodeError as exc:
            raise ValueError(
                "tool arguments are not valid JSON: "
                f"{exc.msg}"
            ) from exc

    if not isinstance(arguments, dict):
        raise ValueError(
            "tool arguments must decode to a JSON object"
        )

    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            "tool name must be a non-empty string"
        )

    if not isinstance(call_id, str) or not call_id:
        call_id = f"call-{uuid.uuid4().hex[:12]}"

    return name.strip(), arguments, call_id


def _completion_from_message(
    message: AIMessage,
) -> CompletionResult:
    """Adapt a legacy injected model response for HW5 compatibility."""

    usage = message.usage_metadata or {}
    metadata = message.response_metadata or {}
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))

    return CompletionResult(
        content=_content_to_text(message.content),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=int(
            usage.get(
                "total_tokens",
                input_tokens + output_tokens,
            )
        ),
        metadata=dict(metadata),
        message=message,
        tool_calls=list(message.tool_calls or []),
        invalid_tool_calls=list(
            message.invalid_tool_calls or []
        ),
        usage_metadata=dict(usage),
    )


class _LegacyModelClient:
    """Keep the old injectable `.invoke()` test seam working."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def complete(
        self,
        messages: Sequence[BaseMessage],
        tools: list[Any] | None = None,
    ) -> CompletionResult:
        del tools
        response = self.model.invoke(messages)

        if not isinstance(response, AIMessage):
            raise TypeError(
                "injected model must return an AIMessage"
            )

        return _completion_from_message(response)


def _assistant_message(
    completion: CompletionResult,
) -> AIMessage:
    if completion.message is not None:
        return completion.message

    return AIMessage(
        content=completion.content,
        tool_calls=completion.tool_calls,
        invalid_tool_calls=(
            completion.invalid_tool_calls
        ),
    )


def _error_result(message: str) -> str:
    return json.dumps(
        {
            "ok": False,
            "data": None,
            "error": message,
        },
        ensure_ascii=False,
    )


def _repair_message(
    category: str,
    reason: str,
    expected_tool: str | None,
) -> HumanMessage:
    expectation = (
        f" The next required tool is {expected_tool}."
        if expected_tool is not None
        else ""
    )

    return HumanMessage(
        content=(
            "Tool-call correction required "
            f"({category}): {reason}."
            f"{expectation} Return a valid tool call only; "
            "do not provide analysis or a final answer yet."
        )
    )


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
    client: Any | None = None,
    model: Any | None = None,
    model_name: str = DEFAULT_MODEL,
    max_steps: int | None = None,
    max_iterations: int = 6,
    max_tool_calls: int = 8,
    required_tool_sequence: tuple[str, ...] | None = None,
    execute_fn: ToolExecutor = execute_tool,
    log_path: Path | None = DEFAULT_LOG_PATH,
) -> dict[str, Any]:
    """Run a bounded hand-written tool-calling agent loop."""

    if not isinstance(user_input, str) or not user_input.strip():
        raise ValueError(
            "user_input must be a non-empty string"
        )

    if client is not None and model is not None:
        raise ValueError(
            "provide either client or model, not both"
        )

    # Preserve the HW5 `max_steps` keyword while using clearer HW7 naming.
    legacy_max_steps = max_steps is not None

    if max_steps is not None:
        max_iterations = max_steps

    if (
        not isinstance(max_iterations, int)
        or isinstance(max_iterations, bool)
        or max_iterations < 1
    ):
        raise ValueError(
            "max_iterations must be a positive integer"
        )

    if (
        not isinstance(max_tool_calls, int)
        or isinstance(max_tool_calls, bool)
        or max_tool_calls < 1
    ):
        raise ValueError(
            "max_tool_calls must be a positive integer"
        )

    if required_tool_sequence is not None:
        if not isinstance(required_tool_sequence, tuple):
            raise ValueError(
                "required_tool_sequence must be a tuple"
            )

        unknown_required = [
            name
            for name in required_tool_sequence
            if name not in TOOL_CONTRACTS
        ]

        if unknown_required:
            raise ValueError(
                "required_tool_sequence contains unknown tool: "
                + unknown_required[0]
            )

    if client is not None:
        active_client = client
        recorded_model = type(client).__name__
    elif model is not None:
        active_client = _LegacyModelClient(model)
        recorded_model = type(model).__name__
    else:
        active_client = build_model(model_name)
        recorded_model = model_name

    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_input.strip()),
    ]

    run_record: dict[str, Any] = {
        "run_id": uuid.uuid4().hex,
        "timestamp": (
            datetime.now().astimezone().isoformat()
        ),
        "model": recorded_model,
        "user_input": user_input.strip(),
        "max_iterations": max_iterations,
        "max_tool_calls": max_tool_calls,
        "required_tool_sequence": list(
            required_tool_sequence or ()
        ),
        "steps": [],
        "step_count": 0,
        "model_call_count": 0,
        "tool_call_attempt_count": 0,
        "tool_call_count": 0,
        "repair_count": 0,
        "failures": [],
        "failure_counts": {
            category: 0
            for category in RELIABILITY_CATEGORIES
        },
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "stop_reason": None,
        "final_answer": None,
    }

    executed_names: list[str] = []
    failure_counter: Counter[str] = Counter()
    repair_used = False
    stop_reason: str | None = None
    final_answer: str | None = None

    def expected_next_tool() -> str | None:
        if required_tool_sequence is None:
            return None

        position = len(executed_names)

        if position >= len(required_tool_sequence):
            return None

        return required_tool_sequence[position]

    def task_tools_complete() -> bool:
        if required_tool_sequence is None:
            return bool(executed_names)

        return tuple(executed_names) == required_tool_sequence

    def record_failure(
        *,
        category: str,
        reason: str,
        subreason: str,
        iteration: int,
        step_record: dict[str, Any],
    ) -> bool:
        """Record a bounded repair; return true when retrying."""

        nonlocal repair_used, stop_reason, final_answer

        if category not in RELIABILITY_CATEGORIES:
            raise ValueError(
                f"unsupported reliability category: {category}"
            )

        failure = {
            "iteration": iteration,
            "category": category,
            "subreason": subreason,
            "reason": reason,
            "repair_attempted": not repair_used,
        }
        run_record["failures"].append(failure)
        step_record["failure"] = failure
        failure_counter[category] += 1

        if repair_used:
            stop_reason = "repair_exhausted"
            final_answer = (
                "Agent stopped after one unsuccessful "
                f"tool-call repair: {reason}"
            )
            return False

        repair_used = True
        run_record["repair_count"] = 1
        messages.append(
            _repair_message(
                category,
                reason,
                expected_next_tool(),
            )
        )
        return True

    for iteration in range(1, max_iterations + 1):
        step_record: dict[str, Any] = {
            "iteration": iteration,
            "phase": (
                "post_repair"
                if repair_used
                else "pre_repair"
            ),
            "tool_calls": [],
        }
        run_record["steps"].append(step_record)

        try:
            completion = active_client.complete(
                messages,
                tools=TOOL_SCHEMAS,
            )
        except Exception as exc:
            stop_reason = "model_error"
            final_answer = (
                "Local model call failed: "
                f"{type(exc).__name__}: {exc}"
            )
            break

        run_record["model_call_count"] += 1
        run_record["input_tokens"] += completion.input_tokens
        run_record["output_tokens"] += completion.output_tokens
        run_record["total_tokens"] += completion.total_tokens

        assistant_message = _assistant_message(completion)
        messages.append(assistant_message)
        response_content = completion.content.strip()
        tool_calls = list(completion.tool_calls or [])
        invalid_tool_calls = list(
            completion.invalid_tool_calls or []
        )
        run_record["tool_call_attempt_count"] += (
            len(tool_calls) + len(invalid_tool_calls)
        )

        if invalid_tool_calls:
            invalid = invalid_tool_calls[0]
            invalid_error = invalid.get("error")
            reason = (
                str(invalid_error)
                if invalid_error
                else "tool arguments were malformed"
            )
            step_record["tool_calls"].extend(
                {
                    "call_id": item.get("id"),
                    "name": item.get("name"),
                    "inputs": item.get("args"),
                    "validation": "failed",
                    "validation_subreason": "invalid_tool_call",
                    "executed": False,
                    "result": json.loads(
                        _error_result(reason)
                    ),
                }
                for item in invalid_tool_calls
            )

            if record_failure(
                category="malformed_arguments",
                reason=reason,
                subreason="invalid_tool_call",
                iteration=iteration,
                step_record=step_record,
            ):
                continue

            break

        if not tool_calls:
            if not task_tools_complete():
                category = (
                    "text_when_tool_required"
                    if not executed_names
                    else "lost_multi_step_chain"
                )
                reason = (
                    "the model answered before calling a tool"
                    if not executed_names
                    else (
                        "the model answered before completing "
                        "the required tool sequence"
                    )
                )

                if record_failure(
                    category=category,
                    reason=reason,
                    subreason="premature_text_response",
                    iteration=iteration,
                    step_record=step_record,
                ):
                    continue

                break

            if not response_content:
                if record_failure(
                    category="lost_multi_step_chain",
                    reason=(
                        "the model returned no final answer after "
                        "completing the tools"
                    ),
                    subreason="empty_final_answer",
                    iteration=iteration,
                    step_record=step_record,
                ):
                    continue

                break

            stop_reason = "normal_completion"
            final_answer = response_content
            break

        prepared_calls: list[
            tuple[str, dict[str, Any], str]
        ] = []
        validation_failure: tuple[
            str,
            str,
            str,
        ] | None = None

        for raw_tool_call in tool_calls:
            try:
                tool_name, raw_inputs, call_id = (
                    _normalize_tool_call(raw_tool_call)
                )
            except ValueError as exc:
                raw_call_data = (
                    raw_tool_call
                    if isinstance(raw_tool_call, dict)
                    else {}
                )
                step_record["tool_calls"].append(
                    {
                        "call_id": raw_call_data.get("id"),
                        "name": raw_call_data.get("name"),
                        "inputs": raw_call_data.get(
                            "args",
                            raw_tool_call,
                        ),
                        "validation": "failed",
                        "validation_subreason": (
                            "malformed_tool_call"
                        ),
                        "executed": False,
                        "result": json.loads(
                            _error_result(str(exc))
                        ),
                    }
                )
                validation_failure = (
                    "malformed_arguments",
                    "malformed_tool_call",
                    str(exc),
                )
                break

            try:
                tool_inputs = validate_tool_inputs(
                    tool_name,
                    raw_inputs,
                )
            except UnknownToolError as exc:
                validation_failure = (
                    "unknown_tool",
                    "unknown_tool_name",
                    str(exc),
                )
                step_record["tool_calls"].append(
                    {
                        "call_id": call_id,
                        "name": tool_name,
                        "inputs": raw_inputs,
                        "validation": "failed",
                        "validation_subreason": (
                            "unknown_tool_name"
                        ),
                        "executed": False,
                        "result": json.loads(
                            _error_result(str(exc))
                        ),
                    }
                )
                messages.append(
                    ToolMessage(
                        content=_error_result(str(exc)),
                        tool_call_id=call_id,
                        name=tool_name,
                    )
                )
                break
            except ToolSchemaValidationError as exc:
                validation_failure = (
                    "malformed_arguments",
                    "schema_validation_failure",
                    str(exc),
                )
                step_record["tool_calls"].append(
                    {
                        "call_id": call_id,
                        "name": tool_name,
                        "inputs": raw_inputs,
                        "validation": "failed",
                        "validation_subreason": (
                            "schema_validation_failure"
                        ),
                        "executed": False,
                        "result": json.loads(
                            _error_result(str(exc))
                        ),
                    }
                )
                messages.append(
                    ToolMessage(
                        content=_error_result(str(exc)),
                        tool_call_id=call_id,
                        name=tool_name,
                    )
                )
                break

            prepared_calls.append(
                (tool_name, tool_inputs, call_id)
            )

        if validation_failure is not None:
            category, subreason, reason = validation_failure

            if record_failure(
                category=category,
                reason=reason,
                subreason=subreason,
                iteration=iteration,
                step_record=step_record,
            ):
                continue

            break

        stop_for_budget = False
        safety_blocked = False

        for tool_name, tool_inputs, call_id in prepared_calls:
            if run_record["tool_call_count"] >= max_tool_calls:
                budget_error = (
                    "tool-call ceiling reached before execution"
                )
                raw_result = _error_result(budget_error)
                step_record["tool_calls"].append(
                    {
                        "call_id": call_id,
                        "name": tool_name,
                        "inputs": tool_inputs,
                        "validation": "passed",
                        "validation_subreason": None,
                        "executed": False,
                        "result": json.loads(raw_result),
                    }
                )
                messages.append(
                    ToolMessage(
                        content=raw_result,
                        tool_call_id=call_id,
                        name=tool_name,
                    )
                )
                stop_reason = "tool_call_ceiling"
                final_answer = (
                    "Agent stopped after reaching "
                    f"max_tool_calls={max_tool_calls}."
                )
                stop_for_budget = True
                break

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
            except (json.JSONDecodeError, TypeError):
                parsed_result = {
                    "ok": False,
                    "data": None,
                    "error": (
                        "tool executor returned invalid JSON"
                    ),
                }
                raw_result = json.dumps(parsed_result)

            run_record["tool_call_count"] += 1
            executed_names.append(tool_name)

            step_record["tool_calls"].append(
                {
                    "call_id": call_id,
                    "name": tool_name,
                    "inputs": tool_inputs,
                    "validation": "passed",
                    "validation_subreason": None,
                    "executed": True,
                    "result": parsed_result,
                }
            )

            messages.append(
                ToolMessage(
                    content=raw_result,
                    tool_call_id=call_id,
                    name=tool_name,
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

        if stop_for_budget or safety_blocked:
            break

        if required_tool_sequence is not None:
            actual_sequence = tuple(executed_names)
            expected_prefix = required_tool_sequence[
                : len(actual_sequence)
            ]

            if (
                len(actual_sequence)
                > len(required_tool_sequence)
                or actual_sequence != expected_prefix
            ):
                if record_failure(
                    category="lost_multi_step_chain",
                    reason=(
                        "tool sequence diverged from the fixed task; "
                        f"expected {list(required_tool_sequence)}, "
                        f"received {list(actual_sequence)}"
                    ),
                    subreason="wrong_tool_sequence",
                    iteration=iteration,
                    step_record=step_record,
                ):
                    continue

                break

    if stop_reason is None:
        stop_reason = (
            "max_steps"
            if legacy_max_steps
            else "iteration_ceiling"
        )
        final_answer = (
            "Agent stopped after reaching "
            + (
                f"max_steps={max_iterations}."
                if legacy_max_steps
                else f"max_iterations={max_iterations}."
            )
        )

    run_record["step_count"] = len(
        run_record["steps"]
    )
    run_record["failure_counts"] = {
        category: failure_counter.get(category, 0)
        for category in RELIABILITY_CATEGORIES
    }
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
