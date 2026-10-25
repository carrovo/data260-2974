import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STUDENT_NAME = "Xuanhua Li"
ATTEMPTS_PER_TASK = 7
EXPECTED_RUNS = 21
RAW_DIR = PROJECT_ROOT / "reports" / "hw07" / "raw"
METRICS_PATH = PROJECT_ROOT / "reports" / "hw07" / "METRICS.md"
PART2_RELIABILITY = RAW_DIR / "part2_reliability.json"
PART3_DEMOS = RAW_DIR / "part3_reflexion_demos.json"
CONTROLLED_CASE = (
    RAW_DIR / "part3_controlled_offline_reflection_case.json"
)
REFLEXION_RUNS_JSON = RAW_DIR / "part3_reflexion_runs.json"
REFLEXION_RUNS_CSV = RAW_DIR / "part3_reflexion_runs.csv"
COMPARISON_JSON = RAW_DIR / "part3_comparison.json"
COMPARISON_CSV = RAW_DIR / "part3_comparison.csv"


def _real_model_config() -> dict[str, Any]:
    from hw7_part2_runner import MODEL_CONFIG

    return dict(MODEL_CONFIG)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _print_heading(title: str) -> None:
    print(f"Student: {STUDENT_NAME}")
    print(f"===== {title} =====")


def print_reflexion_run(result: dict[str, Any]) -> None:
    _print_heading(f"HW7 Part 3 Reflexion Task {result['task_id']}")

    for attempt in result["attempts"]:
        print(f"ATTEMPT: {attempt['attempt_number']}")

        for call in attempt["tool_calls"]:
            print(
                "TOOL_CALL: "
                f"{call.get('name')} "
                + json.dumps(
                    call.get("inputs"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            print(
                "TOOL_OBSERVATION: "
                + json.dumps(
                    call.get("result"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )

        verifier = attempt["verifier"]
        print(f"VERIFIER_PASS: {str(verifier['passed']).lower()}")
        print(
            "UNSUPPORTED_CLAIMS: "
            f"{verifier['unsupported_claim_count']}"
        )
        print("FINAL_ANSWER:")
        print(attempt["final_answer"])

        reflection = next(
            (
                item
                for item in result["reflections"]
                if item["trigger_attempt"]
                == attempt["attempt_number"]
            ),
            None,
        )

        if reflection is not None:
            print(
                "REFLECTION: "
                + json.dumps(
                    {
                        "failure_explanation": reflection[
                            "failure_explanation"
                        ],
                        "evidence": reflection["evidence"],
                        "revised_strategy": reflection[
                            "revised_strategy"
                        ],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )

    print(f"RETRY_COUNT: {result['retry_count']}")
    print(f"TOTAL_TOOL_CALLS: {result['total_tool_calls']}")
    print(f"TOTAL_TOKENS: {result['total_tokens']}")
    print(f"STOP_REASON: {result['stop_reason']}")
    print(f"TASK_SUCCESS: {str(result['task_success']).lower()}")


def _run_real_demo(task_key: str) -> dict[str, Any]:
    from hw7_reflexion import ReflexionBudgets, run_reflexion

    result = run_reflexion(
        task_key,
        budgets=ReflexionBudgets(
            max_retries=2,
            total_tool_calls=12,
            total_tokens=24000,
            wall_clock_seconds=300.0,
        ),
    )
    result["model_config"] = _real_model_config()

    return result


def run_demo(task_key: str) -> list[dict[str, Any]]:
    task_keys = ["A", "B", "C"] if task_key == "all" else [task_key]
    results = []

    for key in task_keys:
        result = _run_real_demo(key)
        print_reflexion_run(result)
        print()
        results.append(result)

    stored_results = {
        result["task_id"]: result
        for result in results
    }

    if task_key != "all" and PART3_DEMOS.exists():
        try:
            existing = json.loads(
                PART3_DEMOS.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            existing = {}

        if existing.get("status") == "completed_real_model_run":
            for item in existing.get("runs", []):
                if item.get("task_id") not in stored_results:
                    stored_results[item["task_id"]] = item

    ordered = [
        stored_results[key]
        for key in ("A", "B", "C")
        if key in stored_results
    ]
    _write_json(
        PART3_DEMOS,
        {
            "status": "completed_real_model_run",
            "model": "qwen3:8b",
            "runs": ordered,
        },
    )

    return results


def run_controlled_offline() -> dict[str, Any]:
    from hw7_reflexion_offline import (
        run_controlled_offline_reflection_case,
    )

    payload = run_controlled_offline_reflection_case()
    result = payload["result"]
    _print_heading("CONTROLLED OFFLINE REFLECTION CASE")
    print("MODEL: scripted_fake_not_qwen3:8b")
    print("REAL_MODEL_RESULT: false")
    print_reflexion_run(result)
    _write_json(CONTROLLED_CASE, payload)

    return payload


def _load_original_runs() -> list[dict[str, Any]]:
    if not PART2_RELIABILITY.exists():
        raise RuntimeError(
            "Part 2 real reliability JSON is missing"
        )

    payload = json.loads(
        PART2_RELIABILITY.read_text(encoding="utf-8")
    )
    runs = payload.get("runs", [])

    if (
        payload.get("status") != "completed_real_model_run"
        or len(runs) != EXPECTED_RUNS
    ):
        raise RuntimeError(
            "Part 2 comparison input must contain 21 real runs"
        )

    return runs


def _system_metrics(
    system_name: str,
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    run_count = len(runs)
    successful = sum(bool(run["task_success"]) for run in runs)
    retries = sum(int(run.get("retry_count", 0)) > 0 for run in runs)
    unsupported = sum(
        int(run.get("unsupported_claims", 0))
        for run in runs
    )
    tool_calls = sum(int(run.get("total_tool_calls", 0)) for run in runs)
    tokens = sum(int(run.get("total_tokens", 0)) for run in runs)
    latency = sum(float(run.get("latency_ms", 0.0)) for run in runs)
    false_rejections = sum(
        any(
            audit.get("confirmed_false_rejection") is True
            for audit in run.get(
                "verifier_false_rejection_audit",
                [],
            )
        )
        for run in runs
    )
    false_rejection_candidates = sum(
        any(
            audit.get("candidate") is True
            for audit in run.get(
                "verifier_false_rejection_audit",
                [],
            )
        )
        for run in runs
    )

    return {
        "system": system_name,
        "run_count": run_count,
        "task_success_count": successful,
        "task_success_rate_percent": round(
            successful / run_count * 100,
            2,
        ),
        "unsupported_claims": unsupported,
        "retry_run_count": retries,
        "retry_rate_percent": round(retries / run_count * 100, 2),
        "total_tool_calls": tool_calls,
        "average_tool_calls": round(tool_calls / run_count, 3),
        "total_tokens": tokens,
        "average_tokens": round(tokens / run_count, 3),
        "average_latency_ms": round(latency / run_count, 3),
        "verifier_false_rejections": false_rejections,
        "verifier_false_rejection_candidates": (
            false_rejection_candidates
        ),
    }


def build_comparison(
    original_runs: list[dict[str, Any]],
    reflexion_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "completed_real_model_comparison",
        "model_config": _real_model_config(),
        "original_loop": _system_metrics(
            "original_loop",
            original_runs,
        ),
        "reflexion_loop": _system_metrics(
            "reflexion_loop",
            reflexion_runs,
        ),
    }


def _original_comparison_records(
    original_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from hw7_reflexion import verify_reflexion_task

    records = []

    for original in original_runs:
        verifier = verify_reflexion_task(
            original["task_id"],
            original,
        )
        records.append(
            {
                "run_id": original["attempt_id"],
                "task_id": original["task_id"],
                "task_success": verifier["passed"],
                "unsupported_claims": verifier[
                    "unsupported_claim_count"
                ],
                "retry_count": 0,
                "total_tool_calls": original["tool_call_count"],
                "total_tokens": original["total_tokens"],
                "latency_ms": original["latency_ms"],
                "stop_reason": (
                    "success"
                    if verifier["passed"]
                    else "human_review"
                ),
                "verifier": verifier,
                "verifier_false_rejection_audit": [
                    verifier["false_rejection_audit"]
                ],
            }
        )

    return records


def _write_reflexion_csv(
    records: list[dict[str, Any]],
) -> None:
    fieldnames = [
        "run_id",
        "task_id",
        "retry_count",
        "task_success",
        "unsupported_claims",
        "total_tool_calls",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "stop_reason",
        "attempts",
        "reflections",
        "verifier_false_rejection_audit",
    ]
    REFLEXION_RUNS_CSV.parent.mkdir(parents=True, exist_ok=True)

    with REFLEXION_RUNS_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()

        for record in records:
            row = {
                field: record.get(field)
                for field in fieldnames
            }

            for field in (
                "attempts",
                "reflections",
                "verifier_false_rejection_audit",
            ):
                row[field] = json.dumps(
                    row[field],
                    ensure_ascii=False,
                    sort_keys=True,
                )

            writer.writerow(row)


def _write_comparison_csv(comparison: dict[str, Any]) -> None:
    rows = [
        comparison["original_loop"],
        comparison["reflexion_loop"],
    ]
    fieldnames = list(rows[0])

    with COMPARISON_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _part3_metrics_section(comparison: dict[str, Any]) -> str:
    original = comparison["original_loop"]
    reflexion = comparison["reflexion_loop"]

    def row(label: str, key: str, suffix: str = "") -> str:
        return (
            f"| {label} | {original[key]}{suffix} | "
            f"{reflexion[key]}{suffix} |"
        )

    return "\n".join(
        [
            "<!-- PART3_METRICS_START -->",
            "## Part 3 — Reflexion and Bounded Self-Correction",
            "",
            "Status: `completed_real_model_comparison`",
            "",
            "| Metric | Original loop | Reflexion loop |",
            "|---|---:|---:|",
            row("Task success (%)", "task_success_rate_percent", "%"),
            row("Unsupported claims", "unsupported_claims"),
            row("Retry rate (%)", "retry_rate_percent", "%"),
            row("Average tool calls", "average_tool_calls"),
            row("Average tokens", "average_tokens"),
            row("Latency (ms)", "average_latency_ms"),
            row(
                "Verifier false rejections",
                "verifier_false_rejections",
            ),
            "<!-- PART3_METRICS_END -->",
        ]
    )


def update_metrics(comparison: dict[str, Any]) -> None:
    start_marker = "<!-- PART3_METRICS_START -->"
    end_marker = "<!-- PART3_METRICS_END -->"
    section = _part3_metrics_section(comparison)
    existing = METRICS_PATH.read_text(encoding="utf-8")

    if start_marker in existing and end_marker in existing:
        prefix = existing.split(start_marker, 1)[0].rstrip()
        suffix = existing.split(end_marker, 1)[1].lstrip()
        updated = prefix + "\n\n" + section + "\n"

        if suffix:
            updated += "\n" + suffix
    else:
        updated = existing.rstrip() + "\n\n" + section + "\n"

    METRICS_PATH.write_text(updated, encoding="utf-8")


def run_comparison() -> dict[str, Any]:
    original_source = _load_original_runs()
    original_records = _original_comparison_records(original_source)
    reflexion_records = []

    _print_heading("HW7 Part 3 Real Comparison - 21 Reflexion Runs")
    print("RUN_PLAN: A x 7, B x 7, C x 7")

    for task_key in ("A", "B", "C"):
        for attempt in range(1, ATTEMPTS_PER_TASK + 1):
            result = _run_real_demo(task_key)
            result["comparison_attempt_id"] = (
                f"{task_key}-R-{attempt:02d}"
            )
            reflexion_records.append(result)
            print(
                f"RUN {result['comparison_attempt_id']} | "
                f"success={str(result['task_success']).lower()} | "
                f"retries={result['retry_count']} | "
                f"stop={result['stop_reason']}"
            )

    if len(reflexion_records) != EXPECTED_RUNS:
        raise RuntimeError("Reflexion comparison requires exactly 21 runs")

    comparison = build_comparison(
        original_records,
        reflexion_records,
    )
    _write_json(
        REFLEXION_RUNS_JSON,
        {
            "status": "completed_real_model_run",
            "runs": reflexion_records,
        },
    )
    _write_reflexion_csv(reflexion_records)
    _write_json(
        COMPARISON_JSON,
        {
            **comparison,
            "original_run_audit": original_records,
        },
    )
    _write_comparison_csv(comparison)
    update_metrics(comparison)
    print("COMPARISON_JSON: reports/hw07/raw/part3_comparison.json")
    print("COMPARISON_CSV: reports/hw07/raw/part3_comparison.csv")

    return comparison


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run HW7 Part 3 bounded Reflexion workflows.",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--reset-fixture", action="store_true")
    demo = subparsers.add_parser("demo")
    demo.add_argument(
        "--task",
        choices=["A", "B", "C", "all"],
        default="all",
    )
    subparsers.add_parser("controlled-offline")
    subparsers.add_parser("comparison")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.mode == "controlled-offline":
        os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
        run_controlled_offline()
        return

    from hw7_part2_runner import (
        PreflightError,
        print_preflight,
        run_preflight,
    )

    try:
        preflight = run_preflight(
            reset=(
                args.mode == "preflight"
                and args.reset_fixture
            )
        )
    except PreflightError as exc:
        _print_heading("HW7 Part 3 Preflight")
        print("PREFLIGHT_STATUS: blocked")
        print(f"STOP_REASON: {exc}")
        raise SystemExit(2) from exc

    if args.mode == "preflight":
        print_preflight(preflight)
    elif args.mode == "demo":
        run_demo(args.task)
    elif args.mode == "comparison":
        run_comparison()


if __name__ == "__main__":
    main()
