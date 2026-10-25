# ruff: noqa: E402

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import HumanMessage, SystemMessage

from hw5_agent import SYSTEM_PROMPT
from hw7_part3_runner import build_comparison
from hw7_reflexion import (
    ReflexionBudgets,
    reflection_security_invariants,
    run_reflexion,
    verify_reflexion_task,
)
from hw7_reflexion_offline import (
    ScriptedReflectionClient,
    _attempt_responses,
    _completion,
    controlled_executor,
    run_controlled_offline_reflection_case,
)
from tool_executor import (
    BLOCKED_HOUSING_SEARCH_PHRASES,
    TOOL_SCHEMAS,
)

STUDENT_NAME = "Xuanhua Li"
SID4 = 2974


def _record_from_attempt(attempt: dict) -> dict:
    return {
        "tool_calls": attempt["tool_calls"],
        "stop_reason": attempt["agent_stop_reason"],
        "final_answer": attempt["final_answer"],
    }


def test_verifier_pass_and_unsupported_failure() -> None:
    payload = run_controlled_offline_reflection_case()
    result = payload["result"]
    first = result["attempts"][0]["verifier"]
    second = result["attempts"][1]["verifier"]

    assert first["passed"] is False
    assert first["unsupported_claim_count"] == 3
    assert {
        claim["type"]
        for claim in first["unsupported_claims"]
    } == {"listing_code", "rent", "manager_name"}
    assert second["passed"] is True
    assert second["unsupported_claim_count"] == 0


def test_real_part2_records_pass_enhanced_verifier() -> None:
    payload = json.loads(
        (
            PROJECT_ROOT
            / "reports/hw07/raw/part2_reliability.json"
        ).read_text(encoding="utf-8")
    )
    results = [
        verify_reflexion_task(run["task_id"], run)
        for run in payload["runs"]
    ]

    assert len(results) == 21
    assert all(result["passed"] for result in results)
    assert all(
        result["unsupported_claim_count"] == 0
        for result in results
    )


def test_controlled_failed_reflection_success() -> None:
    payload = run_controlled_offline_reflection_case()
    result = payload["result"]

    assert payload["case_type"] == (
        "controlled_offline_reflection_case"
    )
    assert payload["real_model_result"] is False
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["task_success"] is False
    assert result["attempts"][1]["task_success"] is True
    assert len(result["reflections"]) == 1
    assert result["reflections"][0]["trigger_attempt"] == 1
    assert result["retry_count"] == 1
    assert result["stop_reason"] == "success"


def test_two_retry_limit() -> None:
    def factory(attempt_index: int, _prompt: str):
        return ScriptedReflectionClient(_attempt_responses(0))

    result = run_reflexion(
        "A",
        budgets=ReflexionBudgets(
            max_retries=2,
            total_tool_calls=12,
            total_tokens=10000,
            wall_clock_seconds=30.0,
        ),
        client_factory=factory,
        execute_fn=controlled_executor,
        model_name="controlled-scripted-fake",
    )

    assert len(result["attempts"]) == 3
    assert len(result["reflections"]) == 2
    assert result["retry_count"] == 2
    assert result["stop_reason"] == "budget_exhausted"


def test_tool_budget_exhaustion() -> None:
    def factory(attempt_index: int, _prompt: str):
        return ScriptedReflectionClient(
            _attempt_responses(attempt_index)
        )

    result = run_reflexion(
        "A",
        budgets=ReflexionBudgets(
            max_retries=2,
            total_tool_calls=1,
            total_tokens=5000,
            wall_clock_seconds=30.0,
        ),
        client_factory=factory,
        execute_fn=controlled_executor,
        model_name="controlled-scripted-fake",
    )

    assert result["total_tool_calls"] == 1
    assert result["stop_reason"] == "budget_exhausted"


def test_token_budget_exhaustion() -> None:
    def factory(_attempt_index: int, _prompt: str):
        return ScriptedReflectionClient(_attempt_responses(0))

    result = run_reflexion(
        "A",
        budgets=ReflexionBudgets(
            max_retries=2,
            total_tool_calls=8,
            total_tokens=50,
            wall_clock_seconds=30.0,
        ),
        client_factory=factory,
        execute_fn=controlled_executor,
        model_name="controlled-scripted-fake",
    )

    assert result["attempts"][0]["agent_stop_reason"] == (
        "token_budget_exhausted"
    )
    assert result["stop_reason"] == "budget_exhausted"


def test_human_review_and_false_rejection_audit() -> None:
    vague_responses = _attempt_responses(1)
    vague_responses[-1] = _completion(
        content=(
            "The requested information is available from the verified "
            "tool observations."
        )
    )

    def factory(_attempt_index: int, _prompt: str):
        return ScriptedReflectionClient(vague_responses)

    result = run_reflexion(
        "A",
        client_factory=factory,
        execute_fn=controlled_executor,
        model_name="controlled-scripted-fake",
    )
    audit = result["attempts"][0][
        "verifier_false_rejection_audit"
    ]

    assert result["stop_reason"] == "human_review"
    assert audit == {
        "candidate": True,
        "confirmed_false_rejection": False,
        "status": "pending_human_audit",
        "reason": (
            "tool evidence passed and no unsupported claim was detected, "
            "but final-answer checks failed"
        ),
    }


def test_reflection_isolation_and_security_boundaries() -> None:
    clients: list[ScriptedReflectionClient] = []
    prompts: list[str] = []
    safety_before = BLOCKED_HOUSING_SEARCH_PHRASES

    def factory(attempt_index: int, prompt: str):
        prompts.append(prompt)
        client = ScriptedReflectionClient(
            _attempt_responses(attempt_index)
        )
        clients.append(client)
        return client

    first_run = run_reflexion(
        "A",
        client_factory=factory,
        execute_fn=controlled_executor,
        model_name="controlled-scripted-fake",
    )
    second_run = run_reflexion(
        "A",
        client_factory=lambda attempt, prompt: (
            ScriptedReflectionClient(_attempt_responses(1))
        ),
        execute_fn=controlled_executor,
        model_name="controlled-scripted-fake",
    )
    invariants = reflection_security_invariants()

    assert first_run["run_id"] != second_run["run_id"]
    assert "UNTRUSTED RUN-LOCAL REFLECTION DATA" not in prompts[0]
    assert "UNTRUSTED RUN-LOCAL REFLECTION DATA" in prompts[1]
    assert len(first_run["reflections"]) == 1
    assert second_run["reflections"] == []
    assert BLOCKED_HOUSING_SEARCH_PHRASES == safety_before
    assert invariants["reflection_persistence"] == "none"
    assert invariants["can_modify_system_instructions"] is False
    assert invariants["can_modify_tool_permissions"] is False
    assert invariants["can_modify_safety_gates"] is False
    assert invariants["can_modify_jwt_rbac"] is False

    for client in clients:
        assert all(tools == TOOL_SCHEMAS for tools in client.tools_seen)
        first_messages = client.message_snapshots[0]
        assert isinstance(first_messages[0], SystemMessage)
        assert first_messages[0].content == SYSTEM_PROMPT
        assert isinstance(first_messages[1], HumanMessage)


def test_comparison_table_structure() -> None:
    original = [
        {
            "task_success": True,
            "unsupported_claims": 0,
            "retry_count": 0,
            "total_tool_calls": 2,
            "total_tokens": 100,
            "latency_ms": 10.0,
            "verifier_false_rejection_audit": [],
        }
    ]
    reflexion = [
        {
            "task_success": True,
            "unsupported_claims": 0,
            "retry_count": 1,
            "total_tool_calls": 4,
            "total_tokens": 200,
            "latency_ms": 20.0,
            "verifier_false_rejection_audit": [
                {
                    "candidate": False,
                    "confirmed_false_rejection": False,
                }
            ],
        }
    ]
    comparison = build_comparison(original, reflexion)

    for system in ("original_loop", "reflexion_loop"):
        metrics = comparison[system]
        assert "task_success_rate_percent" in metrics
        assert "unsupported_claims" in metrics
        assert "retry_rate_percent" in metrics
        assert "average_tool_calls" in metrics
        assert "average_tokens" in metrics
        assert "average_latency_ms" in metrics
        assert "verifier_false_rejections" in metrics


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("verifier pass and unsupported failure", test_verifier_pass_and_unsupported_failure),
    ("real Part 2 enhanced verification", test_real_part2_records_pass_enhanced_verifier),
    ("failed reflection success", test_controlled_failed_reflection_success),
    ("two retry limit", test_two_retry_limit),
    ("tool budget exhaustion", test_tool_budget_exhaustion),
    ("token budget exhaustion", test_token_budget_exhaustion),
    ("human review and false rejection", test_human_review_and_false_rejection_audit),
    ("reflection isolation and security", test_reflection_isolation_and_security_boundaries),
    ("comparison table structure", test_comparison_table_structure),
]


def main() -> None:
    print(f"Student: {STUDENT_NAME} | SID4: {SID4}")
    print("HW7 PART 3 OFFLINE REFLEXION TESTS")
    print("Model: scripted fake only; qwen3:8b is not called")
    print("Real Part 2 raw data: verifier read-only audit\n")
    passed = 0

    for name, test_function in TESTS:
        try:
            test_function()
        except Exception as exc:
            print(f"FAIL | {name} | {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS | {name}")

    total = len(TESTS)
    print(f"\nFINAL SUMMARY: {passed}/{total} PASS")

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
