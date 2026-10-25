# ruff: noqa: E402

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Keep imports and every domain-tool call isolated from local MySQL.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from src.model_client import CompletionResult, ModelClient

import domain_tools
from hw5_agent import run_agent
from hw7_agent_tasks import (
    TASK_A,
    TASK_B,
    TASK_C,
    summarize_reliability,
    verify_task,
)
from hw7_part2_runner import (
    FIXTURE_FLAG,
    MODEL_CONFIG,
    PreflightError,
    _database_engine,
    build_summary,
)
from tool_executor import (
    TOOL_SCHEMAS,
    execute_tool,
    validate_tool_inputs,
)

STUDENT_NAME = "Xuanhua Li"
SID4 = 2974


def create_fixture_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE property_managers (
                id INTEGER PRIMARY KEY,
                firstName VARCHAR(100) NOT NULL,
                lastName VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE listings (
                id INTEGER PRIMARY KEY,
                listingCode VARCHAR(30) NOT NULL UNIQUE,
                listingTitle VARCHAR(100) NOT NULL,
                address VARCHAR(200) NOT NULL,
                submitterEmail VARCHAR(200) NOT NULL,
                description TEXT NOT NULL,
                propertyType VARCHAR(30) NOT NULL,
                monthlyRent NUMERIC(10, 2) NOT NULL,
                availableUnits INTEGER NOT NULL,
                termsAccepted INTEGER NOT NULL,
                propertyManagerId INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO property_managers (
                id, firstName, lastName, email
            ) VALUES (
                1, 'Offline', 'Manager',
                'offline.manager@example.com'
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO listings (
                id, listingCode, listingTitle, address,
                submitterEmail, description, propertyType,
                monthlyRent, availableUnits, termsAccepted,
                propertyManagerId, created_at, updated_at
            ) VALUES
                (
                    4, 'S2974-000004', 'Shared Room Fixture',
                    '104 Market Street, San Jose, CA',
                    'owner4@example.com', 'Offline shared-room fixture.',
                    'Shared Room', 1700.00, 1, 1, 1,
                    '2026-10-01 12:00:00',
                    '2026-10-01 12:00:00'
                ),
                (
                    5, 'S2974-000005', 'First Apartment Fixture',
                    '105 Market Street, San Jose, CA',
                    'owner5@example.com', 'Offline apartment fixture.',
                    'Apartment', 1750.00, 2, 1, 1,
                    '2026-10-01 12:00:00',
                    '2026-10-01 12:00:00'
                ),
                (
                    9, 'S2974-000009', 'Second Apartment Fixture',
                    '109 Market Street, San Jose, CA',
                    'owner9@example.com', 'Second offline fixture.',
                    'Apartment', 1950.00, 1, 1, 1,
                    '2026-10-01 12:00:00',
                    '2026-10-01 12:00:00'
                )
            """
        )

    return engine


def tool_call(
    name: str,
    args: dict[str, Any],
    call_id: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "args": args,
        "id": call_id,
        "type": "tool_call",
    }


def completion(
    *,
    content: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
    invalid_tool_calls: list[dict[str, Any]] | None = None,
    input_tokens: int = 2,
    output_tokens: int = 3,
) -> CompletionResult:
    calls = tool_calls or []
    message = AIMessage(
        content=content,
        tool_calls=calls,
    )

    return CompletionResult(
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        metadata={"model": "scripted-offline"},
        message=message,
        tool_calls=calls,
        invalid_tool_calls=invalid_tool_calls or [],
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


class ScriptedClient:
    def __init__(
        self,
        responses: list[CompletionResult],
    ) -> None:
        self.responses = list(responses)
        self.message_snapshots: list[list[Any]] = []
        self.tools_seen: list[list[Any] | None] = []

    def complete(self, messages, tools=None):
        self.message_snapshots.append(list(messages))
        self.tools_seen.append(tools)

        if not self.responses:
            raise AssertionError("scripted responses exhausted")

        return self.responses.pop(0)


def run_scripted(
    prompt: str,
    responses: list[CompletionResult],
    *,
    required_sequence: tuple[str, ...] | None = None,
    max_iterations: int = 6,
    max_tool_calls: int = 8,
) -> tuple[dict[str, Any], ScriptedClient]:
    client = ScriptedClient(responses)
    result = run_agent(
        prompt,
        client=client,
        max_iterations=max_iterations,
        max_tool_calls=max_tool_calls,
        required_tool_sequence=required_sequence,
        log_path=None,
    )

    return result, client


def task_a_responses() -> list[CompletionResult]:
    return [
        completion(
            tool_calls=[
                tool_call(
                    "search_listings",
                    {"query": "Shared Room", "limit": 1},
                    "a-search",
                )
            ]
        ),
        completion(
            tool_calls=[
                tool_call(
                    "listing_details",
                    {"listing_id": 4},
                    "a-detail",
                )
            ]
        ),
        completion(content="Grounded fixture answer for task A."),
    ]


def task_b_responses() -> list[CompletionResult]:
    return [
        completion(
            tool_calls=[
                tool_call(
                    "manager_rent_summary",
                    {"property_manager_id": 1},
                    "b-summary",
                )
            ]
        ),
        completion(
            tool_calls=[
                tool_call(
                    "search_listings",
                    {"query": "S2974-000005", "limit": 1},
                    "b-search",
                )
            ]
        ),
        completion(content="Grounded fixture answer for task B."),
    ]


def task_c_responses() -> list[CompletionResult]:
    return [
        completion(
            tool_calls=[
                tool_call(
                    "search_listings",
                    {"query": "Apartment", "limit": 2},
                    "c-search",
                )
            ]
        ),
        completion(
            tool_calls=[
                tool_call(
                    "listing_details",
                    {"listing_id": 5},
                    "c-detail-1",
                ),
                tool_call(
                    "listing_details",
                    {"listing_id": 9},
                    "c-detail-2",
                ),
            ]
        ),
        completion(content="Grounded fixture comparison for task C."),
    ]


def test_model_client_preserves_native_message() -> None:
    class FakeChatModel:
        def __init__(self) -> None:
            self.bound_tools = None
            self.messages = None

        def bind_tools(self, tools):
            self.bound_tools = tools
            return self

        def invoke(self, messages):
            self.messages = messages
            return AIMessage(
                content="",
                tool_calls=[
                    tool_call(
                        "search_listings",
                        {"query": "Apartment", "limit": 1},
                        "adapter-call",
                    )
                ],
                invalid_tool_calls=[
                    {
                        "name": "search_listings",
                        "args": "{invalid-json",
                        "id": "adapter-invalid-call",
                        "error": "invalid JSON arguments",
                        "type": "invalid_tool_call",
                    }
                ],
                usage_metadata={
                    "input_tokens": 7,
                    "output_tokens": 4,
                    "total_tokens": 11,
                },
                response_metadata={
                    "model": "fake-chat-model",
                },
            )

    fake_model = FakeChatModel()
    client = object.__new__(ModelClient)
    client._model = fake_model
    source_messages = [
        SystemMessage(content="system"),
        HumanMessage(content="user"),
    ]
    result = client.complete(
        source_messages,
        tools=TOOL_SCHEMAS,
    )

    assert result.message is not None
    assert result.message.tool_calls[0]["id"] == "adapter-call"
    assert result.tool_calls == result.message.tool_calls
    assert len(result.invalid_tool_calls) == 1
    assert result.invalid_tool_calls[0]["id"] == (
        "adapter-invalid-call"
    )
    assert result.input_tokens == 7
    assert result.output_tokens == 4
    assert result.total_tokens == 11
    assert result.usage_metadata["total_tokens"] == 11
    assert fake_model.bound_tools == TOOL_SCHEMAS
    assert fake_model.messages == source_messages

    # The original HW1 dict-message input remains accepted.
    client.complete([{"role": "user", "content": "compatible"}])


def test_strict_schema_validation() -> None:
    assert validate_tool_inputs(
        "search_listings",
        {"query": "Apartment"},
    ) == {
        "query": "Apartment",
        "limit": 5,
    }

    invalid_cases = [
        ("search_listings", {"query": "Apartment", "extra": 1}),
        ("search_listings", {"limit": 1}),
        ("search_listings", {"query": "Apartment", "limit": "2"}),
        ("search_listings", {"query": "Apartment", "limit": True}),
        ("search_listings", {"query": "Apartment", "limit": 26}),
        ("listing_details", {"listing_id": True}),
        ("manager_rent_summary", {"property_manager_id": "1"}),
    ]

    for name, inputs in invalid_cases:
        handler_called = False

        def handler(**_inputs):
            nonlocal handler_called
            handler_called = True
            return {"ok": True, "data": {}, "error": None}

        parsed = json.loads(
            execute_tool(
                name,
                inputs,
                handlers={name: handler},
            )
        )
        assert parsed["ok"] is False
        assert parsed["error"]
        assert handler_called is False


def test_task_a_and_message_order() -> None:
    result, client = run_scripted(
        TASK_A.prompt,
        task_a_responses(),
        required_sequence=TASK_A.required_tool_sequence,
    )

    assert verify_task("A", result)["passed"] is True
    assert result["tool_call_count"] == 2
    assert result["tool_call_attempt_count"] == 2
    assert result["model_call_count"] == 3
    assert result["input_tokens"] == 6
    assert result["output_tokens"] == 9
    assert result["total_tokens"] == 15
    assert all(tools == TOOL_SCHEMAS for tools in client.tools_seen)

    second_messages = client.message_snapshots[1]
    assert isinstance(second_messages[0], SystemMessage)
    assert isinstance(second_messages[1], HumanMessage)
    assert isinstance(second_messages[2], AIMessage)
    assert isinstance(second_messages[3], ToolMessage)
    assert second_messages[3].tool_call_id == "a-search"

    third_messages = client.message_snapshots[2]
    assert isinstance(third_messages[-2], AIMessage)
    assert isinstance(third_messages[-1], ToolMessage)
    assert third_messages[-1].tool_call_id == "a-detail"

    assert all(
        "model_message" not in step
        for step in result["steps"]
    )
    assert all(
        call["validation"] == "passed"
        for step in result["steps"]
        for call in step["tool_calls"]
    )
    assert result["steps"][0]["phase"] == "pre_repair"


def test_task_b() -> None:
    result, _client = run_scripted(
        TASK_B.prompt,
        task_b_responses(),
        required_sequence=TASK_B.required_tool_sequence,
    )

    assert verify_task("B", result)["passed"] is True
    assert result["tool_call_count"] == 2


def test_task_c() -> None:
    result, _client = run_scripted(
        TASK_C.prompt,
        task_c_responses(),
        required_sequence=TASK_C.required_tool_sequence,
    )

    assert verify_task("C", result)["passed"] is True
    assert result["tool_call_count"] == 3


def test_one_repair_succeeds() -> None:
    result, client = run_scripted(
        "Search for an apartment.",
        [
            completion(
                tool_calls=[
                    tool_call("invented_tool", {}, "bad-tool")
                ]
            ),
            completion(
                tool_calls=[
                    tool_call(
                        "search_listings",
                        {"query": "Apartment", "limit": 1},
                        "fixed-tool",
                    )
                ]
            ),
            completion(content="Recovered after one repair."),
        ],
        required_sequence=("search_listings",),
    )

    assert result["stop_reason"] == "normal_completion"
    assert result["repair_count"] == 1
    assert result["failure_counts"]["unknown_tool"] == 1
    assert result["tool_call_attempt_count"] == 2
    assert result["tool_call_count"] == 1

    repaired_messages = client.message_snapshots[1]
    assert isinstance(repaired_messages[-2], ToolMessage)
    assert repaired_messages[-2].tool_call_id == "bad-tool"
    assert isinstance(repaired_messages[-1], HumanMessage)
    assert "unknown tool" in str(repaired_messages[-1].content)


def test_second_repair_failure_stops() -> None:
    result, _client = run_scripted(
        "Search for an apartment.",
        [
            completion(
                tool_calls=[
                    tool_call("invented_tool", {}, "bad-tool-1")
                ]
            ),
            completion(
                tool_calls=[
                    tool_call("still_wrong", {}, "bad-tool-2")
                ]
            ),
        ],
        required_sequence=("search_listings",),
    )

    assert result["stop_reason"] == "repair_exhausted"
    assert result["repair_count"] == 1
    assert result["failure_counts"]["unknown_tool"] == 2
    assert result["tool_call_count"] == 0


def test_malformed_arguments_category() -> None:
    result, _client = run_scripted(
        "Search for an apartment.",
        [
            completion(
                tool_calls=[
                    tool_call(
                        "search_listings",
                        {"query": "Apartment", "limit": True},
                        "schema-bad",
                    )
                ]
            ),
            completion(
                tool_calls=[
                    tool_call(
                        "search_listings",
                        {"query": "Apartment", "limit": 1},
                        "schema-fixed",
                    )
                ]
            ),
            completion(content="Recovered schema call."),
        ],
        required_sequence=("search_listings",),
    )

    assert result["stop_reason"] == "normal_completion"
    assert result["failure_counts"]["malformed_arguments"] == 1
    assert result["failures"][0]["subreason"] == (
        "schema_validation_failure"
    )


def test_invalid_native_tool_call_category() -> None:
    result, _client = run_scripted(
        "Search for an apartment.",
        [
            completion(
                invalid_tool_calls=[
                    {
                        "name": "search_listings",
                        "args": "{not-json",
                        "id": "invalid-native",
                        "error": "invalid JSON arguments",
                    }
                ]
            ),
            completion(
                tool_calls=[
                    tool_call(
                        "search_listings",
                        {"query": "Apartment", "limit": 1},
                        "valid-native",
                    )
                ]
            ),
            completion(content="Recovered malformed JSON."),
        ],
        required_sequence=("search_listings",),
    )

    assert result["stop_reason"] == "normal_completion"
    assert result["failure_counts"]["malformed_arguments"] == 1
    assert result["failures"][0]["subreason"] == "invalid_tool_call"


def test_malformed_json_is_not_replaced_with_empty_object() -> None:
    malformed = completion()
    malformed.tool_calls = [
        {
            "name": "search_listings",
            "args": "{not-json",
            "id": "malformed-json",
            "type": "tool_call",
        }
    ]
    result, _client = run_scripted(
        "Search for an apartment.",
        [
            malformed,
            completion(
                tool_calls=[
                    tool_call(
                        "search_listings",
                        {"query": "Apartment", "limit": 1},
                        "malformed-fixed",
                    )
                ]
            ),
            completion(content="Recovered malformed arguments."),
        ],
        required_sequence=("search_listings",),
    )

    assert result["stop_reason"] == "normal_completion"
    assert result["failure_counts"]["malformed_arguments"] == 1
    assert result["failures"][0]["subreason"] == "malformed_tool_call"
    assert result["tool_call_count"] == 1


def test_text_when_tool_required_category() -> None:
    result, _client = run_scripted(
        "Search for an apartment.",
        [
            completion(content="I will answer without a tool."),
            completion(
                tool_calls=[
                    tool_call(
                        "search_listings",
                        {"query": "Apartment", "limit": 1},
                        "text-repair",
                    )
                ]
            ),
            completion(content="Grounded after repair."),
        ],
        required_sequence=("search_listings",),
    )

    assert result["stop_reason"] == "normal_completion"
    assert result["failure_counts"]["text_when_tool_required"] == 1


def test_lost_multi_step_chain_category() -> None:
    result, _client = run_scripted(
        TASK_A.prompt,
        [
            task_a_responses()[0],
            completion(content="Premature answer after search."),
            task_a_responses()[1],
            completion(content="Grounded after finishing detail."),
        ],
        required_sequence=TASK_A.required_tool_sequence,
    )

    assert result["stop_reason"] == "normal_completion"
    assert result["failure_counts"]["lost_multi_step_chain"] == 1
    assert verify_task("A", result)["passed"] is True


def test_iteration_ceiling() -> None:
    responses = [
        completion(
            tool_calls=[
                tool_call(
                    "search_listings",
                    {"query": "Apartment", "limit": 1},
                    f"iteration-{index}",
                )
            ]
        )
        for index in range(2)
    ]
    result, _client = run_scripted(
        "Keep searching.",
        responses,
        max_iterations=2,
        max_tool_calls=5,
    )

    assert result["stop_reason"] == "iteration_ceiling"
    assert result["model_call_count"] == 2
    assert result["tool_call_count"] == 2


def test_tool_call_ceiling() -> None:
    responses = [
        completion(
            tool_calls=[
                tool_call(
                    "search_listings",
                    {"query": "Apartment", "limit": 1},
                    f"budget-{index}",
                )
            ]
        )
        for index in range(2)
    ]
    result, _client = run_scripted(
        "Keep searching.",
        responses,
        max_iterations=4,
        max_tool_calls=1,
    )

    assert result["stop_reason"] == "tool_call_ceiling"
    assert result["tool_call_attempt_count"] == 2
    assert result["tool_call_count"] == 1


def test_nonexistent_id_is_business_error() -> None:
    result, _client = run_scripted(
        "Show listing ID 999999.",
        [
            completion(
                tool_calls=[
                    tool_call(
                        "listing_details",
                        {"listing_id": 999999},
                        "missing-detail",
                    )
                ]
            ),
            completion(
                content="Listing 999999 was not found."
            ),
        ],
        required_sequence=("listing_details",),
    )

    tool_result = result["steps"][0]["tool_calls"][0]["result"]
    assert tool_result["ok"] is False
    assert tool_result["error"] == "listing 999999 was not found"
    assert result["stop_reason"] == "normal_completion"
    assert result["repair_count"] == 0
    assert result["final_answer"] == "Listing 999999 was not found."


def test_reliability_summary_uses_four_categories() -> None:
    runs = []

    scenarios = [
        [
            completion(
                tool_calls=[
                    tool_call(
                        "search_listings",
                        {"query": "Apartment", "limit": True},
                        "summary-malformed-1",
                    )
                ]
            ),
            completion(
                tool_calls=[
                    tool_call(
                        "search_listings",
                        {"query": "Apartment", "limit": True},
                        "summary-malformed-2",
                    )
                ]
            ),
        ],
        [
            completion(
                tool_calls=[
                    tool_call("unknown", {}, "summary-unknown-1")
                ]
            ),
            completion(
                tool_calls=[
                    tool_call("unknown", {}, "summary-unknown-2")
                ]
            ),
        ],
        [
            completion(content="premature"),
            completion(content="premature again"),
        ],
    ]

    for responses in scenarios:
        run, _client = run_scripted(
            "Fixed reliability fixture.",
            responses,
            required_sequence=("search_listings",),
        )
        runs.append(run)

    lost_run, _client = run_scripted(
        TASK_A.prompt,
        [
            task_a_responses()[0],
            completion(content="premature"),
            completion(content="premature again"),
        ],
        required_sequence=TASK_A.required_tool_sequence,
    )
    runs.append(lost_run)

    summary = summarize_reliability(runs)
    assert set(summary["failure_counts"]) == {
        "malformed_arguments",
        "unknown_tool",
        "text_when_tool_required",
        "lost_multi_step_chain",
    }
    assert all(
        count >= 1
        for count in summary["failure_counts"].values()
    )


def test_real_runner_fixture_guard() -> None:
    original_flag = os.environ.get(FIXTURE_FLAG)
    os.environ[FIXTURE_FLAG] = "1"

    try:
        try:
            _database_engine()
        except PreflightError as exc:
            assert "MySQL" in str(exc)
        else:
            raise AssertionError(
                "runner must reject the offline SQLite database"
            )
    finally:
        if original_flag is None:
            os.environ.pop(FIXTURE_FLAG, None)
        else:
            os.environ[FIXTURE_FLAG] = original_flag


def test_real_runner_summary_math() -> None:
    record = {
        "task_success": True,
        "tool_calls": [
            {
                "phase": "pre_repair",
                "validation": "failed",
            },
            {
                "phase": "post_repair",
                "validation": "passed",
            },
        ],
        "failure_categories": ["malformed_arguments"],
    }
    summary = build_summary([record])

    assert MODEL_CONFIG == {
        "model": "qwen3:8b",
        "temperature": 0.0,
        "seed": 2974,
        "reasoning": False,
        "num_ctx": 4096,
        "num_predict": 512,
    }
    assert summary["call_level_well_formed_rate"][
        "all_attempts"
    ]["rate_percent"] == 50.0
    assert summary["call_level_well_formed_rate"][
        "pre_repair"
    ]["rate_percent"] == 0.0
    assert summary["call_level_well_formed_rate"][
        "post_repair"
    ]["rate_percent"] == 100.0
    assert summary["run_level_completion_rate"][
        "rate_percent"
    ] == 100.0
    assert summary["failure_counts"]["malformed_arguments"] == 1


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("model adapter native message", test_model_client_preserves_native_message),
    ("strict schema validation", test_strict_schema_validation),
    ("task A and tool message order", test_task_a_and_message_order),
    ("task B verifier", test_task_b),
    ("task C verifier", test_task_c),
    ("one repair succeeds", test_one_repair_succeeds),
    ("second repair failure stops", test_second_repair_failure_stops),
    ("malformed arguments category", test_malformed_arguments_category),
    ("invalid native tool call", test_invalid_native_tool_call_category),
    (
        "malformed JSON is not silently replaced",
        test_malformed_json_is_not_replaced_with_empty_object,
    ),
    ("text when tool required", test_text_when_tool_required_category),
    ("lost multi-step chain", test_lost_multi_step_chain_category),
    ("iteration ceiling", test_iteration_ceiling),
    ("tool-call ceiling", test_tool_call_ceiling),
    ("nonexistent ID business error", test_nonexistent_id_is_business_error),
    ("four-category summary", test_reliability_summary_uses_four_categories),
    ("real runner fixture guard", test_real_runner_fixture_guard),
    ("real runner summary math", test_real_runner_summary_math),
]


def main() -> None:
    print(f"Student: {STUDENT_NAME} | SID4: {SID4}")
    print("HW7 PART 2 OFFLINE AGENT TESTS")
    print("Database: isolated in-memory SQLite fixture")
    print("Model: scripted fake only; qwen3:8b is not called\n")

    fixture_engine = create_fixture_engine()
    original_engine = domain_tools.db_session_basede26
    domain_tools.db_session_basede26 = fixture_engine
    passed = 0

    try:
        for name, test_function in TESTS:
            try:
                test_function()
            except Exception as exc:
                print(f"FAIL | {name} | {type(exc).__name__}: {exc}")
            else:
                passed += 1
                print(f"PASS | {name}")
    finally:
        domain_tools.db_session_basede26 = original_engine
        fixture_engine.dispose()

    total = len(TESTS)
    print(f"\nFINAL SUMMARY: {passed}/{total} PASS")

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
