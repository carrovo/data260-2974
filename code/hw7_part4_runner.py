import argparse
import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from hw7_part4_agent import (
    MODEL_CONFIG,
    POLICY_SNAPSHOT_PATH,
    Part4AgentError,
    effective_runtime_limits,
    run_part4_agent,
    validate_uploaded_csv,
)
from hw7_part4_data import DEFAULT_MANIFEST_PATH, Part4DataError, verify_outputs
from hw7_part4_tools import PRICING_URL, verify_snapshot_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STUDENT = "Xuanhua Li"
SCENARIO_DIR = PROJECT_ROOT / "reports" / "hw07" / "data" / "part4" / "scenarios"
SUMMARY_PATH = SCENARIO_DIR / "scenario_summary.json"
RAW_OUTPUT = PROJECT_ROOT / "reports" / "hw07" / "raw" / "part4_agent_acceptance.json"
METRICS_PATH = PROJECT_ROOT / "reports" / "hw07" / "METRICS.md"
METRICS_START = "<!-- PART4_AGENT_METRICS_START -->"
METRICS_END = "<!-- PART4_AGENT_METRICS_END -->"


def heading(title: str) -> None:
    print(f"Student: {STUDENT}")
    print(f"===== HW7 Part 4 | {title} =====")


def ollama_models() -> list[str]:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        with urlopen(f"{base}/api/tags", timeout=3) as response:
            payload = json.load(response)
    except (OSError, URLError, ValueError) as exc:
        raise RuntimeError(
            f"Ollama is unavailable at {base}: {type(exc).__name__}"
        ) from exc
    return [str(item.get("name")) for item in payload.get("models", [])]


def preflight() -> bool:
    heading("PREFLIGHT")
    try:
        evidence = verify_outputs(
            snapshot_path=POLICY_SNAPSHOT_PATH,
            manifest_path=DEFAULT_MANIFEST_PATH,
        )
        fixture_verified = all(
            item["winner_matches"] and item["row_count"] == 600
            for item in evidence["scenarios"]
        )
    except Part4DataError as exc:
        print(f"FIXTURE_ERROR: {exc}")
        fixture_verified = False
    try:
        runtime_limits = effective_runtime_limits()
        timeout_valid = True
    except Part4AgentError as exc:
        print(f"TIMEOUT_CONFIG_ERROR: {exc}")
        runtime_limits = None
        timeout_valid = False
    checks: dict[str, bool] = {
        "sanitized_policy_snapshot": verify_snapshot_hash(POLICY_SNAPSHOT_PATH),
        "signed_fixture_manifest": fixture_verified,
        "bounded_ollama_request_timeout": timeout_valid,
        "membership_scenario": validate_uploaded_csv(
            SCENARIO_DIR / "membership_wins.csv"
        )["rows"]
        == 600,
        "pay_per_use_scenario": validate_uploaded_csv(
            SCENARIO_DIR / "pay_per_use_wins.csv"
        )["rows"]
        == 600,
    }
    try:
        names = ollama_models()
        checks["ollama"] = True
        checks["qwen3:8b"] = any(
            name == "qwen3:8b" or name.startswith("qwen3:8b-") for name in names
        )
    except RuntimeError as exc:
        print(f"OLLAMA_ERROR: {exc}")
        checks["ollama"] = False
        checks["qwen3:8b"] = False
    print("MODEL_CONFIG: " + json.dumps(MODEL_CONFIG, sort_keys=True))
    if runtime_limits is not None:
        print(
            "OLLAMA_REQUEST_TIMEOUT_SECONDS: "
            f"{runtime_limits.ollama_request_timeout_seconds:g}"
        )
        print(
            "AGENT_WALL_BUDGET_SECONDS: "
            f"{runtime_limits.wall_budget_seconds:g}"
        )
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} | {name}")
    print(f"READY: {str(all(checks.values())).lower()}")
    return all(checks.values())


def print_result(payload: dict) -> None:
    for event in payload["timeline"]:
        print(
            f"TOOL | {event['tool']} | success={str(event['success']).lower()} "
            f"| source={event.get('source')} | latency_ms={event['latency_ms']}"
        )
        print("SAFE_INPUTS: " + json.dumps(event["inputs"], sort_keys=True))
    print("RESULT: " + json.dumps(payload["result"], ensure_ascii=False, indent=2))
    print(f"TOTAL_TOOL_CALLS: {payload['metrics']['tool_calls']}")
    print(f"PROGRESS_REPAIRS: {payload['metrics']['progress_repair_count']}")
    print(f"TOTAL_TOKENS: {payload['metrics']['total_tokens']}")
    print(f"LATENCY_MS: {payload['metrics']['latency_ms']}")
    print(f"STOP_REASON: {payload['stop_reason']}")


def analyze(csv_path: Path, url: str, expected: str | None = None) -> dict:
    heading(f"ANALYZE {csv_path.name}")
    payload = run_part4_agent(
        csv_path=csv_path,
        pricing_url=url,
        expected_winner=expected,
    )
    print_result(payload)
    return payload


def _update_metrics(runs: dict[str, dict]) -> None:
    complete = all(name in runs for name in ("membership_wins", "pay_per_use_wins"))
    status = (
        "completed_real_part4_agent_run" if complete else "partial_real_part4_agent_run"
    )
    rows = []
    for name in ("membership_wins", "pay_per_use_wins"):
        run = runs.get(name)
        if run is None:
            rows.append(f"| `{name}` | pending | pending | pending | pending |")
            continue
        analysis = run["analysis"]
        rows.append(
            f"| `{name}` | {analysis['result']['recommendation']} | "
            f"{analysis['metrics']['tool_calls']} | "
            f"{analysis['metrics']['total_tokens']} | "
            f"{analysis['metrics']['latency_ms']} |"
        )
    block = "\n".join(
        [
            METRICS_START,
            "## Part 4 — Framework ReAct Bike Membership Advisor",
            "",
            f"Status: `{status}`",
            "",
            'Framework: `langgraph.prebuilt.create_react_agent(version="v2")`',
            "",
            "Model configuration: `qwen3:8b`, temperature `0.0`, seed `2974`, "
            "reasoning disabled, `num_ctx=4096`, `num_predict=1024`.",
            "",
            "| Acceptance scenario | Recommendation | Tool calls | Tokens | Latency (ms) |",
            "|---|---|---:|---:|---:|",
            *rows,
            "",
            "Only real local qwen3:8b acceptance runs are included above.",
            METRICS_END,
        ]
    )
    text = METRICS_PATH.read_text(encoding="utf-8")
    before, remainder = text.split(METRICS_START, 1)
    _, after = remainder.split(METRICS_END, 1)
    METRICS_PATH.write_text(before + block + after, encoding="utf-8")


def acceptance(scenario: str) -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    definitions = {item["scenario"]: item for item in summary["scenarios"]}
    names = ["membership_wins", "pay_per_use_wins"] if scenario == "all" else [scenario]
    stored: dict[str, dict] = {}
    if RAW_OUTPUT.exists():
        existing = json.loads(RAW_OUTPUT.read_text(encoding="utf-8"))
        if existing.get("status") in {
            "partial_real_part4_agent_run",
            "completed_real_part4_agent_run",
        }:
            stored = {run["scenario"]: run for run in existing.get("runs", [])}
    for name in names:
        item = definitions[name]
        expected = {
            "membership": "Buy Monthly Membership",
            "pay_per_use": "Pay Per Ride/Minute",
        }[item["expected_winning_option"]]
        stored[name] = {
            "scenario": name,
            "expected_winner_used_by_verifier_only": expected,
            "analysis": analyze(SCENARIO_DIR / f"{name}.csv", PRICING_URL, expected),
        }
    complete = all(name in stored for name in ("membership_wins", "pay_per_use_wins"))
    status = (
        "completed_real_part4_agent_run" if complete else "partial_real_part4_agent_run"
    )
    ordered = [
        stored[name]
        for name in ("membership_wins", "pay_per_use_wins")
        if name in stored
    ]
    RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    RAW_OUTPUT.write_text(
        json.dumps(
            {
                "status": status,
                "model_config": MODEL_CONFIG,
                "runs": ordered,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _update_metrics(stored)
    print(f"RAW_OUTPUT: {RAW_OUTPUT.relative_to(PROJECT_ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HW7 Part 4 real-model runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--csv", type=Path, required=True)
    analyze_parser.add_argument("--url", default=PRICING_URL)
    acceptance_parser = subparsers.add_parser("acceptance")
    acceptance_parser.add_argument(
        "--scenario",
        choices=["membership_wins", "pay_per_use_wins", "all"],
        required=True,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "preflight":
            return 0 if preflight() else 1
        if args.command == "analyze":
            analyze(args.csv, args.url)
        else:
            acceptance(args.scenario)
    except Part4AgentError as exc:
        print("TASK_SUCCESS: false")
        print(f"STOP_REASON: {exc.stop_reason}")
        error = (
            "Independent Part 4 verification failed"
            if exc.stop_reason == "verification_failed"
            else str(exc)
        )
        print(f"ERROR: {error}")
        if exc.diagnostics is not None:
            label = (
                "FINAL_RESPONSE_DIAGNOSTICS"
                if exc.stop_reason == "invalid_final_response"
                else "FAILURE_DIAGNOSTICS"
            )
            print(
                f"{label}: " + json.dumps(exc.diagnostics, sort_keys=True)
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
