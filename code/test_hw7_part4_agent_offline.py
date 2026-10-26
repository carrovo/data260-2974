# ruff: noqa: E402

import asyncio
import csv
import io
import json
import os
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
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import Field

import hw7_part4_agent as part4_agent
import hw7_part4_runner as part4_runner
from auth_service import hash_password
from database import Base, SessionLocal, db_session_basede26
from hw7_part4_agent import (
    MAX_UPLOAD_BYTES,
    OLLAMA_TIMEOUT_ENV,
    POLICY_SNAPSHOT_PATH,
    TARGET_STATS_SQL,
    TOTAL_ROWS_SQL,
    WEEKLY_SQL,
    Part4AgentError,
    create_real_model,
    decode_final_response,
    ollama_timeout_seconds,
    run_part4_agent,
    validate_uploaded_csv,
    verify_agent_result,
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
        if self.loop_forever:
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
        assert result["metrics"]["structured_response_latency_ms"] >= 0
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
    previous = os.environ.pop(OLLAMA_TIMEOUT_ENV, None)
    try:
        assert ollama_timeout_seconds() == 60.0
        assert create_real_model().sync_client_kwargs["timeout"] == 60.0

        os.environ[OLLAMA_TIMEOUT_ENV] = "75.5"
        assert ollama_timeout_seconds() == 75.5
        assert create_real_model().sync_client_kwargs["timeout"] == 75.5

        for value in ("", "not-a-number", "0", "-1", "nan", "inf", "-inf"):
            os.environ[OLLAMA_TIMEOUT_ENV] = value
            _expect_error(ollama_timeout_seconds, "validation_error")

        for value in ("120", "120.01", "999999"):
            os.environ[OLLAMA_TIMEOUT_ENV] = value
            assert ollama_timeout_seconds() == 120.0
    finally:
        if previous is None:
            os.environ.pop(OLLAMA_TIMEOUT_ENV, None)
        else:
            os.environ[OLLAMA_TIMEOUT_ENV] = previous


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
    original_wall_budget = part4_agent.MAX_WALL_SECONDS
    part4_agent.MAX_WALL_SECONDS = -1
    try:
        _expect_error(
            lambda: run_part4_agent(
                csv_path=MEMBERSHIP_CSV,
                pricing_url=PRICING_URL,
                model=ScriptedReActModel(),
            ),
            "wall_clock_budget_exhausted",
        )
    finally:
        part4_agent.MAX_WALL_SECONDS = original_wall_budget


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
        "controlled CLI timeout preserves pending artifacts",
        test_controlled_cli_timeout_preserves_pending_artifacts,
    ),
    (
        "invalid final CLI safe diagnostics",
        test_cli_invalid_final_prints_only_safe_diagnostics,
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
