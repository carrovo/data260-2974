import json
from typing import Any

from langchain_core.messages import AIMessage
from src.model_client import CompletionResult

from hw7_reflexion import (
    ReflexionBudgets,
    reflection_security_invariants,
    run_reflexion,
)


def _tool_call(
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


def _completion(
    *,
    content: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
) -> CompletionResult:
    calls = tool_calls or []
    message = AIMessage(content=content, tool_calls=calls)

    return CompletionResult(
        content=content,
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        metadata={"model": "controlled-scripted-fake"},
        message=message,
        tool_calls=calls,
        invalid_tool_calls=[],
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        },
    )


class ScriptedReflectionClient:
    def __init__(self, responses: list[CompletionResult]) -> None:
        self.responses = list(responses)
        self.message_snapshots: list[list[Any]] = []
        self.tools_seen: list[list[Any] | None] = []

    def complete(self, messages, tools=None):
        self.message_snapshots.append(list(messages))
        self.tools_seen.append(tools)

        if not self.responses:
            raise AssertionError("scripted responses exhausted")

        return self.responses.pop(0)


def _attempt_responses(
    attempt_index: int,
) -> list[CompletionResult]:
    suffix = attempt_index + 1
    final_answer = (
        "Listing Code: S2974-999999; Monthly Rent: $9999.00; "
        "Property Manager: Invented Manager"
        if attempt_index == 0
        else (
            "Listing Code: S2974-000004; Title: Shared Room Fixture; "
            "Address: 104 Market Street, San Jose, CA; "
            "Monthly Rent: $1700.00; Property Manager: "
            "Part2 Fixture Manager"
        )
    )

    return [
        _completion(
            tool_calls=[
                _tool_call(
                    "search_listings",
                    {"query": "Shared Room", "limit": 1},
                    f"offline-{suffix}-search",
                )
            ]
        ),
        _completion(
            tool_calls=[
                _tool_call(
                    "listing_details",
                    {"listing_id": 4},
                    f"offline-{suffix}-detail",
                )
            ]
        ),
        _completion(content=final_answer),
    ]


def controlled_executor(
    name: str,
    inputs: dict[str, Any],
) -> str:
    if name == "search_listings":
        data: Any = [
            {
                "id": 4,
                "listingCode": "S2974-000004",
                "listingTitle": "Shared Room Fixture",
                "address": "104 Market Street, San Jose, CA",
                "propertyType": "Shared Room",
                "monthlyRent": "1700.00",
                "availableUnits": 1,
                "propertyManagerId": 1,
            }
        ]
    elif name == "listing_details" and inputs.get("listing_id") == 4:
        data = {
            "id": 4,
            "listingCode": "S2974-000004",
            "listingTitle": "Shared Room Fixture",
            "address": "104 Market Street, San Jose, CA",
            "propertyType": "Shared Room",
            "monthlyRent": "1700.00",
            "availableUnits": 1,
            "propertyManagerId": 1,
            "propertyManager": {
                "id": 1,
                "firstName": "Part2",
                "lastName": "Fixture Manager",
                "email": "part2-manager@example.com",
            },
        }
    else:
        return json.dumps(
            {
                "ok": False,
                "data": None,
                "error": "unexpected controlled tool call",
            }
        )

    return json.dumps(
        {
            "ok": True,
            "data": data,
            "error": None,
        }
    )


def run_controlled_offline_reflection_case() -> dict[str, Any]:
    clients: list[ScriptedReflectionClient] = []

    def client_factory(
        attempt_index: int,
        _prompt: str,
    ) -> ScriptedReflectionClient:
        client = ScriptedReflectionClient(
            _attempt_responses(attempt_index)
        )
        clients.append(client)
        return client

    result = run_reflexion(
        "A",
        budgets=ReflexionBudgets(
            max_retries=2,
            total_tool_calls=8,
            total_tokens=4000,
            wall_clock_seconds=30.0,
        ),
        client_factory=client_factory,
        execute_fn=controlled_executor,
        model_name="controlled-scripted-fake",
    )

    return {
        "case_type": "controlled_offline_reflection_case",
        "model": "scripted_fake_not_qwen3:8b",
        "real_model_result": False,
        "result": result,
        "security_invariants": reflection_security_invariants(),
        "client_audit": {
            "client_count": len(clients),
            "tool_schema_supplied_each_call": all(
                tools is not None
                for client in clients
                for tools in client.tools_seen
            ),
        },
    }
