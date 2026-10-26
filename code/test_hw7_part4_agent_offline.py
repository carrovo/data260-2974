# ruff: noqa: E402

import asyncio
import csv
import io
import json
import os
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Callable

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./tmp/hw7_part4_api_test.db"
os.environ["JWT_SECRET_KEY"] = "part4-offline-test-key-2974-only-not-production"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import Field

import hw7_part4_agent as part4_agent
import hw7_part4_runner as part4_runner
from auth_service import hash_password
from database import Base, SessionLocal, db_session_basede26
from hw7_part4_agent import (
    DEFAULT_WALL_BUDGET_SECONDS,
    MAX_PROGRESS_REPAIRS,
    MAX_TOOL_CALLS,
    MAX_UPLOAD_BYTES,
    OLLAMA_TIMEOUT_ENV,
    POLICY_SNAPSHOT_PATH,
    TARGET_STATS_SQL,
    TOTAL_ROWS_SQL,
    WALL_BUDGET_ENV,
    WEEKLY_SQL,
    AgentBudget,
    Part4AgentError,
    Part4RuntimeLimits,
    create_real_model,
    decode_final_response,
    effective_runtime_limits,
    ollama_timeout_seconds,
    run_part4_agent,
    validate_uploaded_csv,
    verify_agent_result,
    wall_budget_seconds,
)
from hw7_part4_schemas import Part4AdvisorResult
from hw7_part4_tools import PRICING_URL
from jwt_service import create_access_token
from main import app
from models import User, UserRole
from routers.hw7_part4 import get_part4_model

SCENARIO_DIR = PROJECT_ROOT / "reports" / "hw07" / "data" / "part4" / "scenarios"
MEMBERSHIP_CSV = SCENARIO_DIR / "membership_wins.csv"
PAY_CSV = SCENARIO_DIR / "pay_per_use_wins.csv"
TEST_TMP_ROOT = PROJECT_ROOT / "tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class ScriptedReActModel(BaseChatModel):
    """Deterministic fake that still executes the real LangGraph ReAct graph."""

    loop_forever: bool = False
    structured_mode: bool = False
    structured_encoding: str = "native"
    native_structured_calls: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-part4-react"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedReActModel":
        del tools, kwargs
        return self.model_copy(update={"structured_mode": False})

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        method: str = "json_schema",
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable:
        assert schema is Part4AdvisorResult
        assert method == "json_schema"
        assert include_raw is True
        assert not kwargs
        self.native_structured_calls.append(
            {
                "schema": schema.__name__,
                "method": method,
                "include_raw": include_raw,
            }
        )

        def invoke(messages: list[BaseMessage]) -> dict[str, Any]:
            structured = self.model_copy(update={"structured_mode": True})
            raw = structured.invoke(messages)
            parsed: Part4AdvisorResult | dict[str, Any] | None = None
            parsing_error: Exception | None = None
            if self.structured_encoding in {"native", "parsed_dict"}:
                arguments = raw.tool_calls[0]["args"]
                parsed = (
                    Part4AdvisorResult.model_validate(arguments)
                    if self.structured_encoding == "native"
                    else arguments
                )
            else:
                parsing_error = ValueError("scripted provider parse failure")
            return {
                "raw": raw,
                "parsed": parsed,
                "parsing_error": parsing_error,
            }

        return RunnableLambda(invoke)

    def _message(
        self, *, content: str = "", calls: list[dict] | None = None
    ) -> ChatResult:
        message = AIMessage(
            content=content,
            tool_calls=calls or [],
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _call(self, index: int, name: str, args: dict[str, Any]) -> ChatResult:
        return self._message(
            calls=[
                {
                    "name": name,
                    "args": args,
                    "id": f"part4-call-{index}",
                    "type": "tool_call",
                }
            ]
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        observations = [
            message for message in messages if isinstance(message, ToolMessage)
        ]
        index = len(observations) + 1
        if self.loop_forever and len(observations) >= 3:
            return self._call(
                index, "calculator", {"expression": "1+1", "units": "USD"}
            )
        calls = [
            ("csv_sql", {"sql": TOTAL_ROWS_SQL}),
            ("csv_sql", {"sql": TARGET_STATS_SQL}),
            ("csv_sql", {"sql": WEEKLY_SQL}),
            (
                "policy_retriever",
                {"url": PRICING_URL, "query": "month pass monthly price", "k": 4},
            ),
            (
                "policy_retriever",
                {"url": PRICING_URL, "query": "classic unlock 45 min free", "k": 8},
            ),
            (
                "policy_retriever",
                {"url": PRICING_URL, "query": "ebike free unlock rate", "k": 8},
            ),
        ]
        if len(observations) < len(calls):
            name, args = calls[len(observations)]
            return self._call(index, name, args)

        envelopes = [json.loads(str(message.content)) for message in observations]
        stats = envelopes[1]["data"]["rows"][0]
        membership_expression = (
            f"29 + {stats['classic_overage_minutes']} * 0.17 + "
            f"{stats['ebike_minutes']} * 0.17"
        )
        pay_expression = (
            f"{stats['classic_count']} * 1 + {stats['classic_minutes']} * 0.19 + "
            f"{stats['ebike_count']} * 1 + {stats['ebike_minutes']} * 0.49"
        )
        if len(observations) == 6:
            return self._call(
                index,
                "calculator",
                {"expression": membership_expression, "units": "USD"},
            )
        if len(observations) == 7:
            return self._call(
                index, "calculator", {"expression": pay_expression, "units": "USD"}
            )
        membership = float(envelopes[6]["data"]["value"])
        pay = float(envelopes[7]["data"]["value"])
        if len(observations) == 8:
            return self._call(
                index,
                "calculator",
                {
                    "expression": f"{max(membership, pay)} - {min(membership, pay)}",
                    "units": "USD",
                },
            )

        weekly = envelopes[2]["data"]["rows"]
        passages = [
            passage["text"]
            for envelope in envelopes[3:6]
            for passage in envelope["data"]["passages"]
        ]
        unique_passages = list(dict.fromkeys(passages))
        snapshot = json.loads(POLICY_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        final = {
            "recommendation": (
                "Buy Monthly Membership" if membership < pay else "Pay Per Ride/Minute"
            ),
            "membership_cost": round(membership, 2),
            "pay_per_use_cost": round(pay, 2),
            "dollar_savings": round(abs(pay - membership), 2),
            "target_ride_count": int(stats["target_ride_count"]),
            "target_minutes": float(stats["total_minutes"]),
            "average_target_minutes": float(stats["average_minutes"]),
            "classic_target_count": int(stats["classic_count"]),
            "ebike_target_count": int(stats["ebike_count"]),
            "weekly_table": weekly,
            "assumptions": [
                "Only scenario_target=true rows are costed.",
                "Pricing comes from the committed sanitized official snapshot.",
            ],
            "official_source_url": snapshot["final_url"],
            "citations": unique_passages[:3],
        }
        if not self.structured_mode:
            return self._message(content=json.dumps(final))
        if self.structured_encoding == "plain_json":
            return self._message(content=json.dumps(final))
        if self.structured_encoding == "fenced_json":
            return self._message(content="```json\n" + json.dumps(final) + "\n```")
        if self.structured_encoding == "prose_wrapped_json":
            return self._message(content="Here is the result:\n" + json.dumps(final))
        if self.structured_encoding == "empty":
            return self._message(content="")
        if self.structured_encoding == "malformed_json":
            return self._message(content='{"recommendation":')
        return self._message(
            calls=[
                {
                    "name": Part4AdvisorResult.__name__,
                    "args": final,
                    "id": "part4-structured-response",
                    "type": "tool_call",
                }
            ]
        )


class ProgressRepairModel(ScriptedReActModel):
    """Script early stops and invalid SQL while preserving model-owned calls."""

    premature_points: list[str] = Field(default_factory=list)
    invalid_first_csv: bool = False
    parallel_second_csv: bool = False
    premature_between_calculations: bool = False
    always_premature: bool = False
    correction_messages: list[str] = Field(default_factory=list)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.structured_mode:
            return super()._generate(messages, stop, run_manager, **kwargs)

        observations = [
            message for message in messages if isinstance(message, ToolMessage)
        ]
        correction = (
            messages[-1].content
            if messages
            and isinstance(messages[-1], HumanMessage)
            and "next missing stage" in str(messages[-1].content)
            else None
        )
        if correction is not None:
            self.correction_messages.append(str(correction))

        if self.always_premature:
            return self._message(content="premature model answer must not be exposed")
        if self.invalid_first_csv and not observations and correction is None:
            return self._call(1, "csv_sql", {"sql": TARGET_STATS_SQL})
        if self.parallel_second_csv and len(observations) == 1 and correction is None:
            return self._message(
                calls=[
                    {
                        "name": "csv_sql",
                        "args": {"sql": TARGET_STATS_SQL},
                        "id": "part4-parallel-stage-2",
                        "type": "tool_call",
                    },
                    {
                        "name": "csv_sql",
                        "args": {"sql": WEEKLY_SQL},
                        "id": "part4-parallel-stage-3",
                        "type": "tool_call",
                    },
                ]
            )

        point = {
            0: "before_any_tool",
            3: "after_csv",
            6: "before_calculator",
        }.get(len(observations))
        if point in self.premature_points and correction is None:
            return self._message(content=f"premature at {point}")
        if (
            self.premature_between_calculations
            and 6 <= len(observations) < 9
            and correction is None
        ):
            return self._message(content="premature during calculator evidence")
        if self.premature_between_calculations and correction is not None:
            expression = re.search(
                r"<BEGIN_REQUIRED_EXPRESSION>\n(.+?)\n<END_REQUIRED_EXPRESSION>",
                str(correction),
                re.DOTALL,
            )
            assert expression is not None
            return self._call(
                len(observations) + 1,
                "calculator",
                {"expression": expression.group(1), "units": "USD"},
            )
        return super()._generate(messages, stop, run_manager, **kwargs)


class RepeatedCalculatorRepairModel(ProgressRepairModel):
    """Match the Mac failure shape: one irrelevant value, then early stops."""

    def _without_irrelevant_calculator(
        self, messages: list[BaseMessage]
    ) -> list[BaseMessage]:
        filtered: list[BaseMessage] = []
        for message in messages:
            if isinstance(message, ToolMessage):
                envelope = json.loads(str(message.content))
                expression = envelope.get("data", {}).get("expression")
                if expression == "1 + 1":
                    continue
            filtered.append(message)
        return filtered

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        observations = [
            message for message in messages if isinstance(message, ToolMessage)
        ]
        if self.structured_mode or len(observations) >= 10:
            return ScriptedReActModel._generate(
                self,
                self._without_irrelevant_calculator(messages),
                stop,
                run_manager,
                **kwargs,
            )
        if len(observations) < 6:
            return ScriptedReActModel._generate(
                self, messages, stop, run_manager, **kwargs
            )

        correction = (
            str(messages[-1].content)
            if isinstance(messages[-1], HumanMessage)
            and "next missing stage" in str(messages[-1].content)
            else None
        )
        if len(observations) == 6 and correction is None:
            return self._call(
                7,
                "calculator",
                {"expression": "1 + 1", "units": "USD"},
            )
        if correction is None:
            return self._message(content="premature during calculator evidence")

        self.correction_messages.append(correction)
        expression = re.search(
            r"<BEGIN_REQUIRED_EXPRESSION>\n(.+?)\n<END_REQUIRED_EXPRESSION>",
            correction,
            re.DOTALL,
        )
        assert expression is not None
        return self._call(
            len(observations) + 1,
            "calculator",
            {"expression": expression.group(1), "units": "USD"},
        )


class InvalidFinalProgressModel(ProgressRepairModel):
    """Return schema-valid but unsupported costs to exercise the verifier."""

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        method: str = "json_schema",
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable:
        native = super().with_structured_output(
            schema,
            method=method,
            include_raw=include_raw,
            **kwargs,
        )

        def invoke(messages: list[BaseMessage]) -> dict[str, Any]:
            response = native.invoke(messages)
            parsed = response["parsed"]
            payload = (
                parsed.model_dump(mode="json")
                if isinstance(parsed, Part4AdvisorResult)
                else dict(parsed)
            )
            payload["membership_cost"] = 999.0
            response["parsed"] = payload
            return response

        return RunnableLambda(invoke)


class TimeoutReActModel(ScriptedReActModel):
    """Simulate Ollama's bounded HTTP timeout without using the network."""

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        raise httpx.ReadTimeout("simulated offline timeout")


def _expect_error(function: Callable[[], Any], stop_reason: str | None = None) -> None:
    try:
        function()
    except Part4AgentError as exc:
        if stop_reason is not None:
            assert exc.stop_reason == stop_reason, str(exc)
    else:
        raise AssertionError("expected Part4AgentError")


def _copy_with_rows(source: Path, destination: Path, count: int) -> None:
    with source.open("r", encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)
        rows = list(reader)[:count]
        fields = reader.fieldnames
    with destination.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _valid_final_payload() -> dict[str, Any]:
    return {
        "recommendation": "Buy Monthly Membership",
        "membership_cost": 29.0,
        "pay_per_use_cost": 119.47,
        "dollar_savings": 90.47,
        "target_ride_count": 40,
        "target_minutes": 418.283333,
        "average_target_minutes": 10.457083,
        "classic_target_count": 40,
        "ebike_target_count": 0,
        "weekly_table": [
            {
                "week": "2024-01",
                "target_rides": 40,
                "target_minutes": 418.283333,
            }
        ],
        "assumptions": ["Only scenario_target=true rows are costed."],
        "official_source_url": "https://lyftbikes.com/pricing",
        "citations": ["$29/month"],
    }


def _expect_decode_error(value: Any, classification: str) -> None:
    try:
        decode_final_response(value, source="assistant_content")
    except Part4AgentError as exc:
        assert exc.stop_reason == "invalid_final_response"
        assert exc.diagnostics is not None
        assert exc.diagnostics["classification"] == classification
        assert set(exc.diagnostics) == {
            "source",
            "content_type",
            "character_count",
            "classification",
        }
    else:
        raise AssertionError("expected strict final-response rejection")


def test_strict_final_response_decoder() -> None:
    payload = _valid_final_payload()
    native = Part4AdvisorResult.model_validate(payload)
    decoded_native, native_metadata = decode_final_response(
        native,
        source="structured_response",
    )
    assert decoded_native == native
    assert native_metadata["classification"] == "native_structured"

    plain = json.dumps(payload)
    decoded_plain, plain_metadata = decode_final_response(
        plain,
        source="assistant_content",
    )
    assert decoded_plain.model_dump(mode="json") == payload
    assert plain_metadata["classification"] == "plain_json"

    fenced = "```json\n" + plain + "\n```"
    decoded_fenced, fenced_metadata = decode_final_response(
        fenced,
        source="assistant_content",
    )
    assert decoded_fenced == decoded_plain
    assert fenced_metadata["classification"] == "fenced_json"

    _expect_decode_error("Here is the result: " + plain, "prose_wrapped_json")
    _expect_decode_error(plain + "\n" + plain, "multiple_objects")
    _expect_decode_error('{"recommendation":', "malformed_json")

    non_finite = dict(payload)
    non_finite["membership_cost"] = float("nan")
    _expect_decode_error(json.dumps(non_finite), "malformed_json")
    non_finite["membership_cost"] = float("inf")
    _expect_decode_error(json.dumps(non_finite), "malformed_json")

    missing = dict(payload)
    missing.pop("citations")
    _expect_decode_error(json.dumps(missing), "plain_json")
    extra = {**payload, "unsupported": "field"}
    _expect_decode_error(json.dumps(extra), "plain_json")
    wrong_type = {**payload, "target_ride_count": "40"}
    _expect_decode_error(json.dumps(wrong_type), "plain_json")
    unsupported = {**payload, "recommendation": "Ride a scooter"}
    _expect_decode_error(json.dumps(unsupported), "plain_json")


def test_actual_framework_graph_and_opposite_recommendations() -> None:
    models = [ScriptedReActModel(), ScriptedReActModel()]
    results = [
        run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url=PRICING_URL,
            model=models[0],
            expected_winner="Buy Monthly Membership",
        ),
        run_part4_agent(
            csv_path=PAY_CSV,
            pricing_url=PRICING_URL,
            model=models[1],
            expected_winner="Pay Per Ride/Minute",
        ),
    ]
    assert [result["result"]["recommendation"] for result in results] == [
        "Buy Monthly Membership",
        "Pay Per Ride/Minute",
    ]
    for result in results:
        assert result["framework"].startswith("langgraph.prebuilt.create_react_agent")
        assert result["verification"]["passed"] is True
        assert result["metrics"]["tool_calls"] == 9
        assert result["metrics"]["model_calls"] == 11
        assert result["metrics"]["total_tokens"] == 165
        assert result["metrics"]["progress_repair_count"] == 0
        assert result["metrics"]["structured_response_latency_ms"] >= 0
        assert result["metrics"]["ollama_request_timeout_seconds"] == 60.0
        assert result["metrics"]["wall_budget_seconds"] == 300.0
        assert MAX_TOOL_CALLS == 12
        assert result["final_response_diagnostics"]["source"] == ("structured_response")
        assert result["final_response_diagnostics"]["classification"] == (
            "native_structured"
        )
        assert {event["tool"] for event in result["timeline"]} == {
            "csv_sql",
            "policy_retriever",
            "calculator",
        }
        trace = result["message_trace"]
        for position, item in enumerate(trace):
            if item["role"] != "assistant" or not item["tool_calls"]:
                continue
            tool_message = trace[position + 1]
            assert tool_message["role"] == "tool"
            assert tool_message["tool_call_id"] == item["tool_calls"][0]["id"]

    assert all(
        model.native_structured_calls
        == [
            {
                "schema": "Part4AdvisorResult",
                "method": "json_schema",
                "include_raw": True,
            }
        ]
        for model in models
    )

    compatibility = {
        encoding: run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url=PRICING_URL,
            model=ScriptedReActModel(structured_encoding=encoding),
            expected_winner="Buy Monthly Membership",
        )
        for encoding in ("parsed_dict", "plain_json", "fenced_json")
    }
    assert (
        compatibility["plain_json"]["final_response_diagnostics"]["classification"]
        == "plain_json"
    )
    assert (
        compatibility["fenced_json"]["final_response_diagnostics"]["classification"]
        == "fenced_json"
    )
    assert (
        compatibility["parsed_dict"]["final_response_diagnostics"]["classification"]
        == "native_structured"
    )
    assert (
        compatibility["plain_json"]["final_response_diagnostics"]["parsing_error_type"]
        == "ValueError"
    )
    assert (
        compatibility["fenced_json"]["final_response_diagnostics"]["parsing_error_type"]
        == "ValueError"
    )
    assert all(
        result["verification"]["passed"] is True for result in compatibility.values()
    )

    unsupported_number = dict(results[0]["result"])
    unsupported_number["membership_cost"] = 999
    _expect_error(
        lambda: verify_agent_result(unsupported_number, results[0]["timeline"]),
        "verification_failed",
    )
    unsupported_citation = dict(results[0]["result"])
    unsupported_citation["citations"] = ["Not an official retrieved passage"]
    _expect_error(
        lambda: verify_agent_result(unsupported_citation, results[0]["timeline"]),
        "verification_failed",
    )


def test_native_provider_missing_and_parse_error_fail_closed() -> None:
    cases = {
        "empty": "missing_response",
        "malformed_json": "malformed_json",
    }
    for encoding, classification in cases.items():
        try:
            run_part4_agent(
                csv_path=MEMBERSHIP_CSV,
                pricing_url=PRICING_URL,
                model=ScriptedReActModel(structured_encoding=encoding),
                expected_winner="Buy Monthly Membership",
            )
        except Part4AgentError as exc:
            assert exc.stop_reason == "invalid_final_response"
            assert exc.diagnostics is not None
            assert exc.diagnostics["classification"] == classification
            assert exc.diagnostics["source"] == "assistant_content"
            assert exc.diagnostics["parsing_error_type"] == "ValueError"
            if encoding == "empty":
                assert exc.diagnostics["character_count"] == 0
        else:
            raise AssertionError("provider failure unexpectedly passed")


def test_ollama_timeout_configuration() -> None:
    previous_timeout = os.environ.pop(OLLAMA_TIMEOUT_ENV, None)
    previous_wall = os.environ.pop(WALL_BUDGET_ENV, None)
    try:
        assert wall_budget_seconds() == DEFAULT_WALL_BUDGET_SECONDS == 300.0
        assert ollama_timeout_seconds() == 60.0
        assert create_real_model().sync_client_kwargs["timeout"] == 60.0

        os.environ[WALL_BUDGET_ENV] = "425.5"
        assert wall_budget_seconds() == 425.5
        os.environ[OLLAMA_TIMEOUT_ENV] = "75.5"
        assert ollama_timeout_seconds() == 75.5
        assert create_real_model().sync_client_kwargs["timeout"] == 75.5

        invalid = ("", "not-a-number", "0", "-1", "nan", "inf", "-inf")
        for value in invalid:
            os.environ[OLLAMA_TIMEOUT_ENV] = value
            _expect_error(ollama_timeout_seconds, "validation_error")

        os.environ[OLLAMA_TIMEOUT_ENV] = "90"
        for value in invalid:
            os.environ[WALL_BUDGET_ENV] = value
            _expect_error(effective_runtime_limits, "validation_error")

        os.environ[WALL_BUDGET_ENV] = "999999"
        assert wall_budget_seconds() == 600.0
        os.environ[WALL_BUDGET_ENV] = "45"
        assert effective_runtime_limits() == Part4RuntimeLimits(45.0, 45.0)
        os.environ[WALL_BUDGET_ENV] = "300"
        os.environ[OLLAMA_TIMEOUT_ENV] = "999999"
        assert effective_runtime_limits() == Part4RuntimeLimits(300.0, 300.0)
    finally:
        if previous_timeout is None:
            os.environ.pop(OLLAMA_TIMEOUT_ENV, None)
        else:
            os.environ[OLLAMA_TIMEOUT_ENV] = previous_timeout
        if previous_wall is None:
            os.environ.pop(WALL_BUDGET_ENV, None)
        else:
            os.environ[WALL_BUDGET_ENV] = previous_wall


def test_wall_budget_clock_future_and_safe_diagnostics() -> None:
    now = [100.0]
    budget = AgentBudget(
        wall_budget_seconds=300.0,
        clock=lambda: now[0],
    )
    budget.model_calls = 4
    budget.timeline.append(
        {
            "tool": "calculator",
            "observation": {"unsafe_model_content": "must-not-leak"},
        }
    )
    budget.structured_output_started = True
    now[0] = 401.0
    try:
        budget.check_time()
    except Part4AgentError as exc:
        assert exc.stop_reason == "wall_clock_budget_exhausted"
        assert str(exc) == "Part 4 analysis exceeded 300 seconds"
        assert exc.diagnostics == {
            "elapsed_seconds": 301.0,
            "model_call_count": 4,
            "completed_tool_call_count": 1,
            "last_completed_tool_name": "calculator",
            "structured_output_started": True,
        }
        assert "must-not-leak" not in json.dumps(exc.diagnostics)
    else:
        raise AssertionError("fake clock did not exhaust the wall budget")

    recorded: dict[str, Any] = {}

    class FakeFuture:
        def result(self, *, timeout: float) -> dict[str, Any]:
            recorded["timeout"] = timeout
            return {"messages": []}

        def cancel(self) -> None:
            recorded["cancelled"] = True

    class FakeExecutor:
        def __init__(self, *, max_workers: int):
            recorded["max_workers"] = max_workers

        def submit(self, *_args: Any) -> FakeFuture:
            return FakeFuture()

        def shutdown(self, **kwargs: Any) -> None:
            recorded["shutdown"] = kwargs

    class FakeGraph:
        def invoke(self, *_args: Any) -> dict[str, Any]:
            raise AssertionError("fake executor must not invoke the graph")

    result = part4_agent._invoke_graph_with_budget(
        FakeGraph(),
        {},
        {},
        AgentBudget(wall_budget_seconds=300.0),
        executor_factory=FakeExecutor,
    )
    assert result == {"messages": []}
    assert recorded["timeout"] == 300.0
    assert recorded["max_workers"] == 1

    timeout_recorded: dict[str, Any] = {}

    class TimeoutFuture:
        def result(self, *, timeout: float) -> dict[str, Any]:
            timeout_recorded["timeout"] = timeout
            raise part4_agent.FutureTimeoutError

        def cancel(self) -> None:
            timeout_recorded["cancelled"] = True

    class TimeoutExecutor(FakeExecutor):
        def submit(self, *_args: Any) -> TimeoutFuture:
            return TimeoutFuture()

    future_budget = AgentBudget(wall_budget_seconds=300.0)
    future_budget.model_calls = 2
    try:
        part4_agent._invoke_graph_with_budget(
            FakeGraph(),
            {},
            {},
            future_budget,
            executor_factory=TimeoutExecutor,
        )
    except Part4AgentError as exc:
        assert exc.stop_reason == "wall_clock_budget_exhausted"
        assert exc.diagnostics is not None
        assert exc.diagnostics["model_call_count"] == 2
        assert set(exc.diagnostics) == {
            "elapsed_seconds",
            "model_call_count",
            "completed_tool_call_count",
            "last_completed_tool_name",
            "structured_output_started",
        }
    else:
        raise AssertionError("fake Future timeout was not controlled")
    assert timeout_recorded == {"timeout": 300.0, "cancelled": True}


def test_controlled_cli_timeout_preserves_pending_artifacts() -> None:
    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
        root = Path(temp)
        raw_path = root / "part4_agent_acceptance.json"
        metrics_path = root / "METRICS.md"
        pending = {
            "status": "pending_real_part4_agent_run",
            "model_config": part4_agent.MODEL_CONFIG,
            "runs": [],
        }
        raw_path.write_text(json.dumps(pending) + "\n", encoding="utf-8")
        metrics_path.write_text(
            "before\n<!-- PART4_AGENT_METRICS_START -->\n"
            "pending\n<!-- PART4_AGENT_METRICS_END -->\nafter\n",
            encoding="utf-8",
        )
        raw_before = raw_path.read_bytes()
        metrics_before = metrics_path.read_bytes()
        original_analyze = part4_runner.analyze
        original_raw = part4_runner.RAW_OUTPUT
        original_metrics = part4_runner.METRICS_PATH
        original_argv = sys.argv

        def timed_analyze(
            csv_path: Path,
            url: str,
            expected: str | None = None,
        ) -> dict:
            return run_part4_agent(
                csv_path=csv_path,
                pricing_url=url,
                model=TimeoutReActModel(),
                expected_winner=expected,
            )

        try:
            part4_runner.analyze = timed_analyze
            part4_runner.RAW_OUTPUT = raw_path
            part4_runner.METRICS_PATH = metrics_path
            sys.argv = [
                "hw7_part4_runner.py",
                "acceptance",
                "--scenario",
                "membership_wins",
            ]
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = part4_runner.main()
            pending_unchanged = (
                raw_path.read_bytes() == raw_before
                and metrics_path.read_bytes() == metrics_before
            )

            completed = {
                "status": "completed_real_part4_agent_run",
                "model_config": part4_agent.MODEL_CONFIG,
                "runs": [
                    {"scenario": "membership_wins"},
                    {"scenario": "pay_per_use_wins"},
                ],
            }
            raw_path.write_text(json.dumps(completed) + "\n", encoding="utf-8")
            metrics_path.write_text("verified real metrics\n", encoding="utf-8")
            completed_raw_before = raw_path.read_bytes()
            completed_metrics_before = metrics_path.read_bytes()
            completed_output = io.StringIO()
            with redirect_stdout(completed_output):
                completed_exit_code = part4_runner.main()
            completed_unchanged = (
                raw_path.read_bytes() == completed_raw_before
                and metrics_path.read_bytes() == completed_metrics_before
            )
        finally:
            part4_runner.analyze = original_analyze
            part4_runner.RAW_OUTPUT = original_raw
            part4_runner.METRICS_PATH = original_metrics
            sys.argv = original_argv

        terminal = output.getvalue()
        assert exit_code != 0
        assert "TASK_SUCCESS: false" in terminal
        assert "STOP_REASON: wall_clock_budget_exhausted" in terminal
        assert "ERROR: Ollama model request timed out" in terminal
        assert "FAILURE_DIAGNOSTICS:" in terminal
        assert '"model_call_count": 1' in terminal
        assert '"completed_tool_call_count": 0' in terminal
        assert "model response" not in terminal
        assert "Traceback" not in terminal
        assert pending_unchanged
        assert completed_exit_code != 0
        assert "TASK_SUCCESS: false" in completed_output.getvalue()
        assert completed_unchanged
        assert json.loads(raw_path.read_text(encoding="utf-8"))["status"] == (
            "completed_real_part4_agent_run"
        )


def test_cli_invalid_final_prints_only_safe_diagnostics() -> None:
    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
        raw_path = Path(temp) / "part4_agent_acceptance.json"
        pending = {
            "status": "pending_real_part4_agent_run",
            "model_config": part4_agent.MODEL_CONFIG,
            "runs": [],
        }
        raw_path.write_text(json.dumps(pending) + "\n", encoding="utf-8")
        raw_before = raw_path.read_bytes()
        original_analyze = part4_runner.analyze
        original_raw = part4_runner.RAW_OUTPUT
        original_argv = sys.argv

        def invalid_analyze(
            csv_path: Path,
            url: str,
            expected: str | None = None,
        ) -> dict:
            return run_part4_agent(
                csv_path=csv_path,
                pricing_url=url,
                model=ScriptedReActModel(structured_encoding="prose_wrapped_json"),
                expected_winner=expected,
            )

        try:
            part4_runner.analyze = invalid_analyze
            part4_runner.RAW_OUTPUT = raw_path
            sys.argv = [
                "hw7_part4_runner.py",
                "acceptance",
                "--scenario",
                "membership_wins",
            ]
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = part4_runner.main()
        finally:
            part4_runner.analyze = original_analyze
            part4_runner.RAW_OUTPUT = original_raw
            sys.argv = original_argv

        terminal = output.getvalue()
        assert exit_code != 0
        assert "STOP_REASON: invalid_final_response" in terminal
        assert "FINAL_RESPONSE_DIAGNOSTICS:" in terminal
        assert '"source": "assistant_content"' in terminal
        assert '"classification": "prose_wrapped_json"' in terminal
        assert '"character_count":' in terminal
        assert "Here is the result" not in terminal
        assert raw_path.read_bytes() == raw_before


def test_required_progress_repairs_at_three_early_stops() -> None:
    cases = {
        "before_any_tool": "Stage 1 (TOTAL_ROWS_SQL)",
        "after_csv": "Stage 4 (policy evidence",
        "before_calculator": "Stage 5 (calculator evidence",
    }
    for point, expected_correction in cases.items():
        model = ProgressRepairModel(premature_points=[point])
        result = run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url=PRICING_URL,
            model=model,
            expected_winner="Buy Monthly Membership",
        )
        assert result["verification"]["passed"] is True
        assert result["metrics"]["progress_repair_count"] == 1
        assert result["metrics"]["model_calls"] == 12
        assert result["metrics"]["total_tokens"] == 180
        assert len(model.correction_messages) == 1
        assert expected_correction in model.correction_messages[0]
        assert [event["tool"] for event in result["timeline"][:3]] == [
            "csv_sql",
            "csv_sql",
            "csv_sql",
        ]
        assert [
            event["inputs"]["sql"] for event in result["timeline"][:3]
        ] == [TOTAL_ROWS_SQL, TARGET_STATS_SQL, WEEKLY_SQL]
        assert {event["tool"] for event in result["timeline"]} == {
            "csv_sql",
            "policy_retriever",
            "calculator",
        }


def test_stage5_repairs_each_missing_calculation_in_order() -> None:
    model = ProgressRepairModel(premature_between_calculations=True)
    result = run_part4_agent(
        csv_path=MEMBERSHIP_CSV,
        pricing_url=PRICING_URL,
        model=model,
        expected_winner="Buy Monthly Membership",
    )

    assert result["verification"]["passed"] is True
    assert result["metrics"]["progress_repair_count"] == 3
    assert result["metrics"]["model_calls"] == 14
    assert result["metrics"]["total_tokens"] == 210
    assert len(model.correction_messages) == 3
    assert [
        label
        for message in model.correction_messages
        for label in ("membership cost", "pay-per-use cost", "savings")
        if f"next missing evidence is {label}" in message
    ] == ["membership cost", "pay-per-use cost", "savings"]
    assert all(
        message.count("<BEGIN_REQUIRED_EXPRESSION>") == 1
        and message.count("<END_REQUIRED_EXPRESSION>") == 1
        for message in model.correction_messages
    )
    calculator_events = [
        event for event in result["timeline"] if event["tool"] == "calculator"
    ]
    assert len(calculator_events) == 3
    assert all(event["success"] for event in calculator_events)


def test_stage5_repairs_after_irrelevant_calculator_observation() -> None:
    model = RepeatedCalculatorRepairModel()
    result = run_part4_agent(
        csv_path=MEMBERSHIP_CSV,
        pricing_url=PRICING_URL,
        model=model,
        expected_winner="Buy Monthly Membership",
    )

    assert result["verification"]["passed"] is True
    assert result["metrics"]["progress_repair_count"] == 3
    assert result["metrics"]["model_calls"] == 15
    assert result["metrics"]["tool_calls"] == 10
    calculator_events = [
        event for event in result["timeline"] if event["tool"] == "calculator"
    ]
    assert len(calculator_events) == 4
    assert calculator_events[0]["inputs"]["expression"] == "1 + 1"
    assert [
        label
        for message in model.correction_messages
        for label in ("membership cost", "pay-per-use cost", "savings")
        if f"next missing evidence is {label}" in message
    ] == ["membership cost", "pay-per-use cost", "savings"]


def test_invalid_csv_blocked_and_progress_accounting() -> None:
    invalid = ProgressRepairModel(invalid_first_csv=True)
    repaired = run_part4_agent(
        csv_path=MEMBERSHIP_CSV,
        pricing_url=PRICING_URL,
        model=invalid,
        expected_winner="Buy Monthly Membership",
    )
    csv_events = [
        event for event in repaired["timeline"] if event["tool"] == "csv_sql"
    ]
    assert [event["inputs"]["sql"] for event in csv_events] == [
        TOTAL_ROWS_SQL,
        TARGET_STATS_SQL,
        WEEKLY_SQL,
    ]
    assert repaired["metrics"]["tool_calls"] == 9
    assert repaired["metrics"]["progress_repair_count"] == 1
    assert repaired["metrics"]["model_calls"] == 12
    assert repaired["metrics"]["total_tokens"] == 180

    parallel = ProgressRepairModel(parallel_second_csv=True)
    serialized = run_part4_agent(
        csv_path=MEMBERSHIP_CSV,
        pricing_url=PRICING_URL,
        model=parallel,
        expected_winner="Buy Monthly Membership",
    )
    parallel_csv_events = [
        event for event in serialized["timeline"] if event["tool"] == "csv_sql"
    ]
    assert [event["inputs"]["sql"] for event in parallel_csv_events] == [
        TOTAL_ROWS_SQL,
        TARGET_STATS_SQL,
        WEEKLY_SQL,
    ]
    assert serialized["metrics"]["progress_repair_count"] == 1
    assert "Parallel or multiple tool calls are not allowed" in (
        parallel.correction_messages[0]
    )
    assert TARGET_STATS_SQL in parallel.correction_messages[0]

    complete = ProgressRepairModel()
    no_repair = run_part4_agent(
        csv_path=MEMBERSHIP_CSV,
        pricing_url=PRICING_URL,
        model=complete,
        expected_winner="Buy Monthly Membership",
    )
    assert no_repair["metrics"]["progress_repair_count"] == 0
    assert no_repair["metrics"]["model_calls"] == 11
    assert no_repair["metrics"]["total_tokens"] == 165

    maximum = ProgressRepairModel(
        premature_points=["before_any_tool", "after_csv", "before_calculator"]
    )
    maximum_result = run_part4_agent(
        csv_path=MEMBERSHIP_CSV,
        pricing_url=PRICING_URL,
        model=maximum,
        expected_winner="Buy Monthly Membership",
    )
    assert MAX_PROGRESS_REPAIRS == 3
    assert maximum_result["metrics"]["progress_repair_count"] == 3
    assert maximum_result["metrics"]["model_calls"] == 14
    assert maximum_result["metrics"]["total_tokens"] == 210

    instruction = part4_agent._runtime_user_instruction(PRICING_URL)
    assert "Complete these five required stages in order" in instruction
    assert "next action must start with Stage 1 and TOTAL_ROWS_SQL" in instruction
    assert "sequentially, one per model turn" in instruction
    normalized_instruction = " ".join(instruction.split())
    assert (
        "membership cost, pay-per-use cost, and savings, in that order"
        in normalized_instruction
    )
    assert "exactly one calculator call per model turn" in normalized_instruction
    assert (
        "Do not produce a final answer until every stage is complete"
        in normalized_instruction
    )


def test_progress_repair_exhaustion_preserves_acceptance_files() -> None:
    model = ProgressRepairModel(always_premature=True)
    try:
        run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url=PRICING_URL,
            model=model,
            expected_winner="Buy Monthly Membership",
        )
    except Part4AgentError as exc:
        assert exc.stop_reason == "required_tool_progress_exhausted"
        assert exc.diagnostics == {
            "ordered_completed_tool_names": [],
            "tool_counts": {
                "csv_sql": 0,
                "policy_retriever": 0,
                "calculator": 0,
            },
            "missing_required_stages": [
                "stage_1_total_rows_sql",
                "stage_2_target_stats_sql",
                "stage_3_weekly_sql",
                "stage_4_policy_evidence",
                "stage_5_calculator_evidence",
            ],
            "progress_repair_count": 3,
            "model_call_count": 4,
            "elapsed_seconds": exc.diagnostics["elapsed_seconds"],
        }
        assert "premature model answer" not in json.dumps(exc.diagnostics)
    else:
        raise AssertionError("progress repair exhaustion unexpectedly passed")
    assert len(model.correction_messages) == 3
    assert len(set(model.correction_messages)) == 3
    for attempt, correction in enumerate(model.correction_messages, start=1):
        assert f"Bounded repair {attempt} of 3" in correction
        assert TOTAL_ROWS_SQL in correction

    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
        root = Path(temp)
        raw_path = root / "part4_agent_acceptance.json"
        metrics_path = root / "METRICS.md"
        raw_path.write_text(
            json.dumps(
                {
                    "status": "pending_real_part4_agent_run",
                    "model_config": part4_agent.MODEL_CONFIG,
                    "runs": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        metrics_path.write_text(
            "before\n<!-- PART4_AGENT_METRICS_START -->\n"
            "pending\n<!-- PART4_AGENT_METRICS_END -->\nafter\n",
            encoding="utf-8",
        )
        raw_before = raw_path.read_bytes()
        metrics_before = metrics_path.read_bytes()
        original_analyze = part4_runner.analyze
        original_raw = part4_runner.RAW_OUTPUT
        original_metrics = part4_runner.METRICS_PATH
        original_argv = sys.argv

        def exhausted_analyze(
            csv_path: Path,
            url: str,
            expected: str | None = None,
        ) -> dict:
            return run_part4_agent(
                csv_path=csv_path,
                pricing_url=url,
                model=ProgressRepairModel(always_premature=True),
                expected_winner=expected,
            )

        try:
            part4_runner.analyze = exhausted_analyze
            part4_runner.RAW_OUTPUT = raw_path
            part4_runner.METRICS_PATH = metrics_path
            sys.argv = [
                "hw7_part4_runner.py",
                "acceptance",
                "--scenario",
                "membership_wins",
            ]
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = part4_runner.main()
        finally:
            part4_runner.analyze = original_analyze
            part4_runner.RAW_OUTPUT = original_raw
            part4_runner.METRICS_PATH = original_metrics
            sys.argv = original_argv

        terminal = output.getvalue()
        assert exit_code != 0
        assert "STOP_REASON: required_tool_progress_exhausted" in terminal
        assert "FAILURE_DIAGNOSTICS:" in terminal
        assert "premature model answer" not in terminal
        assert raw_path.read_bytes() == raw_before
        assert metrics_path.read_bytes() == metrics_before


def test_structured_output_bypasses_repair_and_verifier_diagnostics_are_safe() -> None:
    structured_failure = ProgressRepairModel(structured_encoding="empty")
    try:
        run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url=PRICING_URL,
            model=structured_failure,
            expected_winner="Buy Monthly Membership",
        )
    except Part4AgentError as exc:
        assert exc.stop_reason == "invalid_final_response"
    else:
        raise AssertionError("empty structured response unexpectedly passed")
    assert structured_failure.correction_messages == []

    verifier_model = InvalidFinalProgressModel()
    try:
        run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url=PRICING_URL,
            model=verifier_model,
            expected_winner="Buy Monthly Membership",
        )
    except Part4AgentError as exc:
        assert exc.stop_reason == "verification_failed"
        assert exc.diagnostics is not None
        assert exc.diagnostics["ordered_completed_tool_names"] == [
            "csv_sql",
            "csv_sql",
            "csv_sql",
            "policy_retriever",
            "policy_retriever",
            "policy_retriever",
            "calculator",
            "calculator",
            "calculator",
        ]
        assert exc.diagnostics["tool_counts"] == {
            "csv_sql": 3,
            "policy_retriever": 3,
            "calculator": 3,
        }
        assert exc.diagnostics["missing_required_stages"] == []
        assert exc.diagnostics["progress_repair_count"] == 0
        assert exc.diagnostics["model_call_count"] == 11
        assert set(exc.diagnostics) == {
            "ordered_completed_tool_names",
            "tool_counts",
            "missing_required_stages",
            "progress_repair_count",
            "model_call_count",
            "elapsed_seconds",
        }
        assert "999" not in json.dumps(exc.diagnostics)
    else:
        raise AssertionError("independent verifier accepted unsupported cost")

    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
        root = Path(temp)
        raw_path = root / "part4_agent_acceptance.json"
        metrics_path = root / "METRICS.md"
        raw_path.write_text(
            json.dumps(
                {
                    "status": "pending_real_part4_agent_run",
                    "model_config": part4_agent.MODEL_CONFIG,
                    "runs": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        metrics_path.write_text(
            "before\n<!-- PART4_AGENT_METRICS_START -->\n"
            "pending\n<!-- PART4_AGENT_METRICS_END -->\nafter\n",
            encoding="utf-8",
        )
        raw_before = raw_path.read_bytes()
        metrics_before = metrics_path.read_bytes()
        original_analyze = part4_runner.analyze
        original_raw = part4_runner.RAW_OUTPUT
        original_metrics = part4_runner.METRICS_PATH
        original_argv = sys.argv

        def verifier_failure_analyze(
            csv_path: Path,
            url: str,
            expected: str | None = None,
        ) -> dict:
            return run_part4_agent(
                csv_path=csv_path,
                pricing_url=url,
                model=InvalidFinalProgressModel(),
                expected_winner=expected,
            )

        try:
            part4_runner.analyze = verifier_failure_analyze
            part4_runner.RAW_OUTPUT = raw_path
            part4_runner.METRICS_PATH = metrics_path
            sys.argv = [
                "hw7_part4_runner.py",
                "acceptance",
                "--scenario",
                "membership_wins",
            ]
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = part4_runner.main()
        finally:
            part4_runner.analyze = original_analyze
            part4_runner.RAW_OUTPUT = original_raw
            part4_runner.METRICS_PATH = original_metrics
            sys.argv = original_argv

        terminal = output.getvalue()
        assert exit_code != 0
        assert "STOP_REASON: verification_failed" in terminal
        assert "ERROR: Independent Part 4 verification failed" in terminal
        assert "FAILURE_DIAGNOSTICS:" in terminal
        assert '"ordered_completed_tool_names"' in terminal
        assert '"tool_counts"' in terminal
        assert "999" not in terminal
        assert "retrieved page" not in terminal
        assert raw_path.read_bytes() == raw_before
        assert metrics_path.read_bytes() == metrics_before


def test_upload_validation_failures() -> None:
    missing = TEST_TMP_ROOT / "missing-part4.csv"
    _expect_error(lambda: validate_uploaded_csv(missing))
    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
        root = Path(temp)
        short = root / "short.csv"
        _copy_with_rows(MEMBERSHIP_CSV, short, 20)
        _expect_error(lambda: validate_uploaded_csv(short))
        no_target = root / "no-target.csv"
        text = MEMBERSHIP_CSV.read_text(encoding="utf-8").replace(",true\n", ",false\n")
        no_target.write_text(text, encoding="utf-8")
        _expect_error(lambda: validate_uploaded_csv(no_target))
        missing_column = root / "missing-column.csv"
        missing_column.write_text("ride_id,scenario_target\n1,true\n", encoding="utf-8")
        _expect_error(lambda: validate_uploaded_csv(missing_column))
        oversized = root / "oversized.csv"
        with oversized.open("wb") as handle:
            handle.truncate(MAX_UPLOAD_BYTES + 1)
        _expect_error(lambda: validate_uploaded_csv(oversized), "upload_too_large")
    _expect_error(
        lambda: run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url="https://example.com/pricing",
            model=ScriptedReActModel(),
        )
    )


def test_malformed_envelope_and_budgets() -> None:
    _expect_error(
        lambda: run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url=PRICING_URL,
            model=ScriptedReActModel(),
            tool_overrides={"csv_sql": lambda **_kwargs: {"not": "an envelope"}},
        ),
        "malformed_tool_envelope",
    )
    _expect_error(
        lambda: run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url=PRICING_URL,
            model=ScriptedReActModel(loop_forever=True),
        ),
        "tool_call_budget_exhausted",
    )
    _expect_error(
        lambda: run_part4_agent(
            csv_path=MEMBERSHIP_CSV,
            pricing_url=PRICING_URL,
            model=ScriptedReActModel(loop_forever=True),
            recursion_limit=2,
        ),
        "recursion_limit",
    )
    fake_clock = [10.0]
    expired = AgentBudget(wall_budget_seconds=1.0, clock=lambda: fake_clock[0])
    fake_clock[0] = 12.0
    _expect_error(expired.check_time, "wall_clock_budget_exhausted")


def _reader_token() -> str:
    Base.metadata.drop_all(bind=db_session_basede26)
    Base.metadata.create_all(bind=db_session_basede26)
    with SessionLocal() as session:
        user = User(
            name="Part4 Reader",
            username="part4-reader",
            email="part4-reader@example.com",
            password_hash=hash_password("test-only-password"),
            role=UserRole.READER,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        token, _ = create_access_token(user)
        return token


def test_endpoint_auth_reader_upload_and_cleanup() -> None:
    async def exercise() -> tuple[Any, Any, Any, Any, Any]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            missing = await client.post(
                "/api/hw7/part4/analyze",
                data={"pricing_url": PRICING_URL},
                files={
                    "csv_file": (
                        "scenario.csv",
                        MEMBERSHIP_CSV.read_bytes(),
                        "text/csv",
                    )
                },
            )
            invalid = await client.post(
                "/api/hw7/part4/analyze",
                headers={"Authorization": "Bearer invalid"},
                data={"pricing_url": PRICING_URL},
                files={
                    "csv_file": (
                        "scenario.csv",
                        MEMBERSHIP_CSV.read_bytes(),
                        "text/csv",
                    )
                },
            )
            token = _reader_token()
            accepted = await client.post(
                "/api/hw7/part4/analyze",
                headers={"Authorization": f"Bearer {token}"},
                data={"pricing_url": PRICING_URL},
                files={
                    "csv_file": (
                        "scenario.csv",
                        MEMBERSHIP_CSV.read_bytes(),
                        "text/csv",
                    )
                },
            )
            bad_url = await client.post(
                "/api/hw7/part4/analyze",
                headers={"Authorization": f"Bearer {token}"},
                data={"pricing_url": "https://example.com/pricing"},
                files={
                    "csv_file": (
                        "scenario.csv",
                        MEMBERSHIP_CSV.read_bytes(),
                        "text/csv",
                    )
                },
            )
            too_large = await client.post(
                "/api/hw7/part4/analyze",
                headers={"Authorization": f"Bearer {token}"},
                data={"pricing_url": PRICING_URL},
                files={
                    "csv_file": (
                        "scenario.csv",
                        io.BytesIO(b"x" * (MAX_UPLOAD_BYTES + 1)),
                        "text/csv",
                    )
                },
            )
        return missing, invalid, accepted, bad_url, too_large

    app.dependency_overrides[get_part4_model] = lambda: ScriptedReActModel()
    before = set(Path(tempfile.gettempdir()).glob("hw7-part4-*.csv"))
    try:
        missing, invalid, accepted, bad_url, too_large = asyncio.run(exercise())
        assert missing.status_code == 401
        assert invalid.status_code == 401
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["result"]["recommendation"] == "Buy Monthly Membership"
        assert bad_url.status_code == 422
        assert too_large.status_code == 413
        assert set(Path(tempfile.gettempdir()).glob("hw7-part4-*.csv")) == before
    finally:
        app.dependency_overrides.pop(get_part4_model, None)


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("strict final response decoder", test_strict_final_response_decoder),
    (
        "actual framework graph and opposite recommendations",
        test_actual_framework_graph_and_opposite_recommendations,
    ),
    (
        "native provider missing and parsing errors",
        test_native_provider_missing_and_parse_error_fail_closed,
    ),
    ("bounded Ollama timeout configuration", test_ollama_timeout_configuration),
    (
        "bounded wall clock and safe diagnostics",
        test_wall_budget_clock_future_and_safe_diagnostics,
    ),
    (
        "controlled CLI timeout preserves pending artifacts",
        test_controlled_cli_timeout_preserves_pending_artifacts,
    ),
    (
        "invalid final CLI safe diagnostics",
        test_cli_invalid_final_prints_only_safe_diagnostics,
    ),
    (
        "required progress repairs at three early stops",
        test_required_progress_repairs_at_three_early_stops,
    ),
    (
        "stage 5 repairs each missing calculation in order",
        test_stage5_repairs_each_missing_calculation_in_order,
    ),
    (
        "stage 5 repairs after an irrelevant calculator observation",
        test_stage5_repairs_after_irrelevant_calculator_observation,
    ),
    (
        "invalid CSV blocked and progress accounting",
        test_invalid_csv_blocked_and_progress_accounting,
    ),
    (
        "progress repair exhaustion preserves acceptance files",
        test_progress_repair_exhaustion_preserves_acceptance_files,
    ),
    (
        "structured output bypass and safe verifier diagnostics",
        test_structured_output_bypasses_repair_and_verifier_diagnostics_are_safe,
    ),
    ("upload validation failures", test_upload_validation_failures),
    ("malformed envelope and bounded stops", test_malformed_envelope_and_budgets),
    (
        "JWT endpoint, reader access, and cleanup",
        test_endpoint_auth_reader_upload_and_cleanup,
    ),
]


def main() -> None:
    print("HW7 PART 4 PHASE 2 OFFLINE TESTS")
    print("MODEL: deterministic scripted fake through the actual LangGraph graph")
    print("REAL_QWEN_RESULT: false\n")
    passed = 0
    for name, function in TESTS:
        try:
            function()
        except Exception as exc:
            print(f"FAIL | {name} | {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS | {name}")
    print(f"\nFINAL SUMMARY: {passed}/{len(TESTS)} PASS")
    if passed != len(TESTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
