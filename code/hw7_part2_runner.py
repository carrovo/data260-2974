import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STUDENT_NAME = "Xuanhua Li"
SID4 = 2974
MODEL_NAME = "qwen3:8b"
FIXTURE_DATABASE = "hw7_part2_fixture_2974"
FIXTURE_FLAG = "HW7_PART2_ISOLATED"
NONEXISTENT_LISTING_ID = 999999
ATTEMPTS_PER_TASK = 7
EXPECTED_RELIABILITY_RUNS = 21

MODEL_CONFIG = {
    "model": MODEL_NAME,
    "temperature": 0.0,
    "seed": SID4,
    "reasoning": False,
    "num_ctx": 4096,
    "num_predict": 512,
}

RAW_DIR = PROJECT_ROOT / "reports" / "hw07" / "raw"
METRICS_PATH = PROJECT_ROOT / "reports" / "hw07" / "METRICS.md"
RELIABILITY_JSON = RAW_DIR / "part2_reliability.json"
RELIABILITY_CSV = RAW_DIR / "part2_reliability.csv"
SUMMARY_JSON = RAW_DIR / "part2_summary.json"
SUMMARY_CSV = RAW_DIR / "part2_summary.csv"
VERIFICATION_JSON = RAW_DIR / "part2_verification.json"
ERROR_RECOVERY_JSON = RAW_DIR / "part2_error_recovery.json"


class PreflightError(RuntimeError):
    """Raised when the real-model environment is not ready."""


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _database_engine() -> Engine:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise PreflightError("DATABASE_URL is not set")

    if os.getenv(FIXTURE_FLAG) != "1":
        raise PreflightError(
            f"{FIXTURE_FLAG}=1 is required for the isolated fixture"
        )

    parsed = make_url(database_url)

    if not parsed.drivername.startswith("mysql"):
        raise PreflightError(
            "DATABASE_URL must use an isolated MySQL database"
        )

    if parsed.database != FIXTURE_DATABASE:
        raise PreflightError(
            "refusing non-fixture database; expected database name "
            f"{FIXTURE_DATABASE}"
        )

    if parsed.host not in {"127.0.0.1", "localhost"}:
        raise PreflightError(
            "the Part 2 fixture must be hosted on localhost"
        )

    return create_engine(database_url, pool_pre_ping=True)


def reset_fixture(engine: Engine) -> None:
    """Reset only the guarded, dedicated Part 2 fixture database."""

    with engine.begin() as connection:
        active_database = connection.execute(
            text("SELECT DATABASE()")
        ).scalar_one()

        if active_database != FIXTURE_DATABASE:
            raise PreflightError(
                "fixture reset guard rejected the active database"
            )

        connection.exec_driver_sql("DROP TABLE IF EXISTS listings")
        connection.exec_driver_sql(
            "DROP TABLE IF EXISTS property_managers"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE property_managers (
                id INTEGER PRIMARY KEY,
                firstName VARCHAR(100) NOT NULL,
                lastName VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE
            ) ENGINE=InnoDB
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
                monthlyRent DECIMAL(10, 2) NOT NULL,
                availableUnits INTEGER NOT NULL,
                termsAccepted BOOLEAN NOT NULL,
                propertyManagerId INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT fk_part2_manager
                    FOREIGN KEY (propertyManagerId)
                    REFERENCES property_managers(id)
            ) ENGINE=InnoDB
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO property_managers (
                id, firstName, lastName, email
            ) VALUES (
                1, 'Part2', 'Fixture Manager',
                'part2-manager@example.com'
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
                    'owner4@example.com',
                    'Deterministic Shared Room fixture for HW7 Part 2.',
                    'Shared Room', 1700.00, 1, TRUE, 1,
                    '2026-10-01 12:00:00',
                    '2026-10-01 12:00:00'
                ),
                (
                    5, 'S2974-000005', 'First Apartment Fixture',
                    '105 Market Street, San Jose, CA',
                    'owner5@example.com',
                    'Deterministic supporting example for HW7 Part 2.',
                    'Apartment', 1750.00, 2, TRUE, 1,
                    '2026-10-01 12:00:00',
                    '2026-10-01 12:00:00'
                ),
                (
                    9, 'S2974-000009', 'Second Apartment Fixture',
                    '109 Market Street, San Jose, CA',
                    'owner9@example.com',
                    'Second deterministic apartment for comparison.',
                    'Apartment', 1950.00, 1, TRUE, 1,
                    '2026-10-01 12:00:00',
                    '2026-10-01 12:00:00'
                )
            """
        )


def fixture_status(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        mysql_version = str(
            connection.execute(text("SELECT VERSION()"))
            .scalar_one()
        )
        active_database = str(
            connection.execute(text("SELECT DATABASE()"))
            .scalar_one()
        )
        shared_room_count = int(
            connection.execute(
                text(
                    "SELECT COUNT(*) FROM listings "
                    "WHERE propertyType = 'Shared Room'"
                )
            ).scalar_one()
        )
        apartment_count = int(
            connection.execute(
                text(
                    "SELECT COUNT(*) FROM listings "
                    "WHERE propertyType = 'Apartment'"
                )
            ).scalar_one()
        )
        support_manager = connection.execute(
            text(
                "SELECT propertyManagerId FROM listings "
                "WHERE listingCode = 'S2974-000005'"
            )
        ).scalar_one_or_none()

    checks = {
        "fixture_database": active_database == FIXTURE_DATABASE,
        "shared_room_available": shared_room_count >= 1,
        "supporting_example_manager_1": support_manager == 1,
        "two_apartments_available": apartment_count >= 2,
    }

    return {
        "mysql_version": mysql_version,
        "database": active_database,
        "shared_room_count": shared_room_count,
        "supporting_example_manager_id": support_manager,
        "apartment_count": apartment_count,
        "checks": checks,
        "ready": all(checks.values()),
    }


def ollama_status() -> dict[str, Any]:
    base_url = os.getenv(
        "OLLAMA_BASE_URL",
        "http://127.0.0.1:11434",
    ).rstrip("/")

    try:
        with urlopen(
            f"{base_url}/api/version",
            timeout=4,
        ) as response:
            version_payload = json.load(response)

        with urlopen(
            f"{base_url}/api/tags",
            timeout=4,
        ) as response:
            tags_payload = json.load(response)
    except (OSError, URLError, ValueError) as exc:
        raise PreflightError(
            "Ollama is unavailable at the configured local URL: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    installed_models = sorted(
        {
            str(item.get("name") or item.get("model"))
            for item in tags_payload.get("models", [])
            if item.get("name") or item.get("model")
        }
    )
    model_available = MODEL_NAME in installed_models

    return {
        "base_url": base_url,
        "version": version_payload.get("version"),
        "required_model": MODEL_NAME,
        "installed_models": installed_models,
        "model_available": model_available,
    }


def run_preflight(*, reset: bool = False) -> dict[str, Any]:
    engine = _database_engine()

    try:
        if reset:
            reset_fixture(engine)

        fixture = fixture_status(engine)
    except Exception as exc:
        if isinstance(exc, PreflightError):
            raise

        raise PreflightError(
            "fixture_setup_failure: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    finally:
        engine.dispose()

    if not fixture["ready"]:
        failed = [
            name
            for name, passed in fixture["checks"].items()
            if not passed
        ]
        raise PreflightError(
            "fixture_setup_failure: " + ", ".join(failed)
        )

    ollama = ollama_status()

    if not ollama["model_available"]:
        raise PreflightError(
            f"required model {MODEL_NAME} is not installed; "
            "no download was attempted"
        )

    return {
        "status": "ready",
        "checked_at": _now(),
        "model_config": MODEL_CONFIG,
        "ollama": ollama,
        "fixture": fixture,
    }


def _flatten_tool_calls(
    run_record: dict[str, Any],
) -> list[dict[str, Any]]:
    flattened = []

    for step in run_record.get("steps", []):
        for call in step.get("tool_calls", []):
            flattened.append(
                {
                    "iteration": step.get("iteration"),
                    "phase": step.get("phase"),
                    "call_id": call.get("call_id"),
                    "name": call.get("name"),
                    "inputs": call.get("inputs"),
                    "validation": call.get("validation"),
                    "validation_subreason": call.get(
                        "validation_subreason"
                    ),
                    "executed": call.get("executed"),
                    "result": call.get("result"),
                }
            )

    return flattened


def _well_formed_state(
    calls: list[dict[str, Any]],
    phase: str,
) -> dict[str, Any]:
    phase_calls = [
        call
        for call in calls
        if call.get("phase") == phase
    ]
    well_formed = sum(
        call.get("validation") == "passed"
        for call in phase_calls
    )
    attempts = len(phase_calls)

    return {
        "attempts": attempts,
        "well_formed_calls": well_formed,
        "all_well_formed": (
            well_formed == attempts
            if attempts
            else None
        ),
        "rate_percent": (
            round(well_formed / attempts * 100, 2)
            if attempts
            else None
        ),
    }


def _recognized_failures(
    run_record: dict[str, Any],
    *,
    task_success: bool,
) -> list[dict[str, Any]]:
    from hw5_agent import RELIABILITY_CATEGORIES

    failures = [
        dict(failure)
        for failure in run_record.get("failures", [])
        if failure.get("category") in RELIABILITY_CATEGORIES
    ]

    if not task_success and not failures:
        failures.append(
            {
                "category": "lost_multi_step_chain",
                "subreason": (
                    "deterministic_verifier_failed_or_agent_stopped:"
                    f"{run_record.get('stop_reason')}"
                ),
                "reason": (
                    "the fixed task did not satisfy its deterministic "
                    "tool-chain verifier"
                ),
                "repair_attempted": False,
            }
        )

    return failures


def run_fixed_task(
    task_key: str,
    *,
    attempt_id: str,
) -> dict[str, Any]:
    from hw5_agent import run_agent
    from hw7_agent_tasks import TASK_SPECS, verify_task

    spec = TASK_SPECS[task_key]
    started = time.perf_counter()
    run_record = run_agent(
        spec.prompt,
        model_name=MODEL_NAME,
        max_iterations=6,
        max_tool_calls=8,
        required_tool_sequence=spec.required_tool_sequence,
        log_path=None,
    )
    latency_ms = round(
        (time.perf_counter() - started) * 1000,
        3,
    )
    verification = verify_task(task_key, run_record)
    task_success = bool(verification["passed"])
    calls = _flatten_tool_calls(run_record)
    failures = _recognized_failures(
        run_record,
        task_success=task_success,
    )

    return {
        "attempt_id": attempt_id,
        "task_id": task_key,
        "prompt": spec.prompt,
        "model_config": MODEL_CONFIG,
        "started_at": run_record["timestamp"],
        "latency_ms": latency_ms,
        "stop_reason": run_record["stop_reason"],
        "task_success": task_success,
        "verification": verification,
        "model_call_count": run_record["model_call_count"],
        "tool_call_attempt_count": run_record[
            "tool_call_attempt_count"
        ],
        "tool_call_count": run_record["tool_call_count"],
        "repair_count": run_record["repair_count"],
        "input_tokens": run_record["input_tokens"],
        "output_tokens": run_record["output_tokens"],
        "total_tokens": run_record["total_tokens"],
        "tool_calls": calls,
        "pre_repair_well_formed": _well_formed_state(
            calls,
            "pre_repair",
        ),
        "post_repair_well_formed": _well_formed_state(
            calls,
            "post_repair",
        ),
        "failure_categories": [
            failure["category"]
            for failure in failures
        ],
        "failure_subreasons": [
            failure.get("subreason")
            for failure in failures
        ],
        "failures": failures,
        "final_answer": run_record["final_answer"],
    }


def _print_heading(title: str) -> None:
    print(f"Student: {STUDENT_NAME}")
    print(f"===== {title} =====")


def print_run(result: dict[str, Any]) -> None:
    _print_heading(
        f"HW7 Part 2 Task {result['task_id']} - {result['attempt_id']}"
    )
    print(
        "MODEL_CONFIG: "
        + json.dumps(result["model_config"], sort_keys=True)
    )

    for call in result["tool_calls"]:
        print(
            "TOOL_CALL: "
            f"{call['name']} "
            + json.dumps(
                call["inputs"],
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        print(
            "TOOL_OBSERVATION: "
            + json.dumps(
                call["result"],
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    print("FINAL_ANSWER:")
    print(result["final_answer"])
    print(f"TOTAL_TOOL_CALLS: {result['tool_call_count']}")
    print(
        "TOTAL_TOOL_CALL_ATTEMPTS: "
        f"{result['tool_call_attempt_count']}"
    )
    print(f"STOP_REASON: {result['stop_reason']}")
    print(f"TASK_SUCCESS: {str(result['task_success']).lower()}")


def _rate_summary(
    calls: list[dict[str, Any]],
) -> dict[str, Any]:
    well_formed = sum(
        call.get("validation") == "passed"
        for call in calls
    )
    attempts = len(calls)

    return {
        "attempts": attempts,
        "well_formed_calls": well_formed,
        "rate_percent": (
            round(well_formed / attempts * 100, 2)
            if attempts
            else None
        ),
    }


def build_summary(
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    from hw5_agent import RELIABILITY_CATEGORIES

    all_calls = [
        call
        for run_record in run_records
        for call in run_record["tool_calls"]
    ]
    pre_calls = [
        call
        for call in all_calls
        if call.get("phase") == "pre_repair"
    ]
    post_calls = [
        call
        for call in all_calls
        if call.get("phase") == "post_repair"
    ]
    successful_runs = sum(
        run_record["task_success"]
        for run_record in run_records
    )
    failure_counts = {
        category: 0
        for category in RELIABILITY_CATEGORIES
    }

    for run_record in run_records:
        for category in run_record["failure_categories"]:
            failure_counts[category] += 1

    return {
        "status": "completed_real_model_run",
        "generated_at": _now(),
        "student": STUDENT_NAME,
        "sid4": SID4,
        "model_config": MODEL_CONFIG,
        "expected_run_count": EXPECTED_RELIABILITY_RUNS,
        "actual_run_count": len(run_records),
        "call_level_well_formed_rate": {
            "all_attempts": _rate_summary(all_calls),
            "pre_repair": _rate_summary(pre_calls),
            "post_repair": _rate_summary(post_calls),
        },
        "run_level_completion_rate": {
            "completed_runs": successful_runs,
            "total_runs": len(run_records),
            "rate_percent": round(
                successful_runs / len(run_records) * 100,
                2,
            ),
        },
        "failure_counts": failure_counts,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_reliability_csv(
    path: Path,
    records: list[dict[str, Any]],
) -> None:
    fieldnames = [
        "attempt_id",
        "task_id",
        "prompt",
        "model_config",
        "stop_reason",
        "task_success",
        "model_call_count",
        "tool_call_attempt_count",
        "tool_call_count",
        "repair_count",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "pre_repair_well_formed",
        "post_repair_well_formed",
        "failure_categories",
        "failure_subreasons",
        "tool_calls",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            row = {
                name: record.get(name)
                for name in fieldnames
            }

            for name in (
                "model_config",
                "pre_repair_well_formed",
                "post_repair_well_formed",
                "failure_categories",
                "failure_subreasons",
                "tool_calls",
            ):
                row[name] = json.dumps(
                    row[name],
                    ensure_ascii=False,
                    sort_keys=True,
                )

            writer.writerow(row)


def _write_summary_csv(
    path: Path,
    summary: dict[str, Any],
) -> None:
    call_rates = summary["call_level_well_formed_rate"]
    run_rate = summary["run_level_completion_rate"]
    failure_counts = summary["failure_counts"]
    row = {
        "status": summary["status"],
        "model": MODEL_NAME,
        "expected_runs": summary["expected_run_count"],
        "actual_runs": summary["actual_run_count"],
        "call_attempts": call_rates["all_attempts"]["attempts"],
        "call_well_formed": call_rates["all_attempts"][
            "well_formed_calls"
        ],
        "call_well_formed_rate_percent": call_rates[
            "all_attempts"
        ]["rate_percent"],
        "pre_repair_rate_percent": call_rates["pre_repair"][
            "rate_percent"
        ],
        "post_repair_rate_percent": call_rates["post_repair"][
            "rate_percent"
        ],
        "completed_runs": run_rate["completed_runs"],
        "run_completion_rate_percent": run_rate["rate_percent"],
        **failure_counts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def _metrics_section(summary: dict[str, Any]) -> str:
    call_rates = summary["call_level_well_formed_rate"]
    run_rate = summary["run_level_completion_rate"]
    failures = summary["failure_counts"]

    def display_rate(value: float | None) -> str:
        return "N/A" if value is None else f"{value}%"

    return "\n".join(
        [
            "<!-- PART2_METRICS_START -->",
            "## Part 2 — Hand-written Agent Loop",
            "",
            f"Status: `{summary['status']}`",
            f"Model: `{MODEL_NAME}`",
            (
                "Configuration: `temperature=0.0`, `seed=2974`, "
                "`num_ctx=4096`, `num_predict=512`"
            ),
            "",
            "| Metric | Result |",
            "|---|---:|",
            (
                "| Call-level well-formed rate (all attempts) | "
                f"{display_rate(call_rates['all_attempts']['rate_percent'])} "
                f"({call_rates['all_attempts']['well_formed_calls']}/"
                f"{call_rates['all_attempts']['attempts']}) |"
            ),
            (
                "| Call-level pre-repair rate | "
                f"{display_rate(call_rates['pre_repair']['rate_percent'])} |"
            ),
            (
                "| Call-level post-repair rate | "
                f"{display_rate(call_rates['post_repair']['rate_percent'])} |"
            ),
            (
                "| Run-level completion rate | "
                f"{run_rate['rate_percent']}% "
                f"({run_rate['completed_runs']}/{run_rate['total_runs']}) |"
            ),
            "",
            "| Failure category | Count |",
            "|---|---:|",
            *[
                f"| `{category}` | {count} |"
                for category, count in failures.items()
            ],
            "<!-- PART2_METRICS_END -->",
        ]
    )


def update_metrics(summary: dict[str, Any]) -> None:
    start_marker = "<!-- PART2_METRICS_START -->"
    end_marker = "<!-- PART2_METRICS_END -->"
    section = _metrics_section(summary)
    existing = (
        METRICS_PATH.read_text(encoding="utf-8")
        if METRICS_PATH.exists()
        else "# HW7 Metrics\n"
    )

    if start_marker in existing and end_marker in existing:
        prefix = existing.split(start_marker, 1)[0].rstrip()
        suffix = existing.split(end_marker, 1)[1].lstrip()
        updated = prefix + "\n\n" + section + "\n"

        if suffix:
            updated += "\n" + suffix
    else:
        updated = existing.rstrip() + "\n\n" + section + "\n"

    METRICS_PATH.write_text(updated, encoding="utf-8")


def run_verification(task_key: str) -> list[dict[str, Any]]:
    task_keys = ["A", "B", "C"] if task_key == "all" else [task_key]
    results = []

    for key in task_keys:
        result = run_fixed_task(
            key,
            attempt_id=f"verification-{key}",
        )
        print_run(result)
        print()
        results.append(result)

    stored_results = {
        result["task_id"]: result
        for result in results
    }

    if task_key != "all" and VERIFICATION_JSON.exists():
        try:
            existing_payload = json.loads(
                VERIFICATION_JSON.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            existing_payload = {}

        if existing_payload.get("status") == (
            "completed_real_model_run"
        ):
            for existing_result in existing_payload.get("runs", []):
                existing_key = existing_result.get("task_id")

                if existing_key not in stored_results:
                    stored_results[existing_key] = existing_result

    ordered_results = [
        stored_results[key]
        for key in ("A", "B", "C")
        if key in stored_results
    ]

    _write_json(
        VERIFICATION_JSON,
        {
            "status": "completed_real_model_run",
            "generated_at": _now(),
            "runs": ordered_results,
        },
    )

    return results


def run_error_recovery() -> dict[str, Any]:
    from hw5_agent import run_agent

    prompt = (
        "Look up full details for rental listing ID 999999. Use the "
        "listing_details tool, then explain the returned result without "
        "inventing a listing."
    )
    started = time.perf_counter()
    run_record = run_agent(
        prompt,
        model_name=MODEL_NAME,
        max_iterations=4,
        max_tool_calls=3,
        required_tool_sequence=("listing_details",),
        log_path=None,
    )
    calls = _flatten_tool_calls(run_record)
    latency_ms = round(
        (time.perf_counter() - started) * 1000,
        3,
    )
    expected_error = (
        f"listing {NONEXISTENT_LISTING_ID} was not found"
    )
    useful_message = any(
        call.get("result", {}).get("error") == expected_error
        for call in calls
    )
    task_success = (
        useful_message
        and run_record["stop_reason"] == "normal_completion"
        and bool(run_record["final_answer"])
    )
    result = {
        "attempt_id": "error-recovery-001",
        "task_id": "error-recovery",
        "prompt": prompt,
        "model_config": MODEL_CONFIG,
        "latency_ms": latency_ms,
        "stop_reason": run_record["stop_reason"],
        "task_success": task_success,
        "model_call_count": run_record["model_call_count"],
        "tool_call_attempt_count": run_record[
            "tool_call_attempt_count"
        ],
        "tool_call_count": run_record["tool_call_count"],
        "repair_count": run_record["repair_count"],
        "input_tokens": run_record["input_tokens"],
        "output_tokens": run_record["output_tokens"],
        "total_tokens": run_record["total_tokens"],
        "tool_calls": calls,
        "pre_repair_well_formed": _well_formed_state(
            calls,
            "pre_repair",
        ),
        "post_repair_well_formed": _well_formed_state(
            calls,
            "post_repair",
        ),
        "failure_categories": [
            failure["category"]
            for failure in run_record["failures"]
        ],
        "failure_subreasons": [
            failure["subreason"]
            for failure in run_record["failures"]
        ],
        "final_answer": run_record["final_answer"],
    }
    print_run(result)
    _write_json(
        ERROR_RECOVERY_JSON,
        {
            "status": "completed_real_model_run",
            "generated_at": _now(),
            "run": result,
        },
    )

    return result


def run_reliability() -> dict[str, Any]:
    records = []

    _print_heading("HW7 Part 2 Reliability - 21 Real Runs")
    print("RUN_PLAN: A x 7, B x 7, C x 7")
    print("MODEL_CONFIG: " + json.dumps(MODEL_CONFIG, sort_keys=True))

    for task_key in ("A", "B", "C"):
        for attempt in range(1, ATTEMPTS_PER_TASK + 1):
            attempt_id = f"{task_key}-{attempt:02d}"
            result = run_fixed_task(
                task_key,
                attempt_id=attempt_id,
            )
            records.append(result)
            print(
                f"RUN {attempt_id} | success="
                f"{str(result['task_success']).lower()} | "
                f"calls={result['tool_call_count']} | "
                f"repairs={result['repair_count']} | "
                f"stop={result['stop_reason']}"
            )

    if len(records) != EXPECTED_RELIABILITY_RUNS:
        raise RuntimeError(
            "reliability runner did not produce exactly 21 runs"
        )

    summary = build_summary(records)
    _write_json(
        RELIABILITY_JSON,
        {
            "status": "completed_real_model_run",
            "generated_at": _now(),
            "runs": records,
        },
    )
    _write_reliability_csv(RELIABILITY_CSV, records)
    _write_json(SUMMARY_JSON, summary)
    _write_summary_csv(SUMMARY_CSV, summary)
    update_metrics(summary)

    print("SUMMARY_JSON: reports/hw07/raw/part2_summary.json")
    print("SUMMARY_CSV: reports/hw07/raw/part2_summary.csv")
    print(
        "CALL_LEVEL_WELL_FORMED_RATE: "
        f"{summary['call_level_well_formed_rate']['all_attempts']['rate_percent']}%"
    )
    print(
        "RUN_LEVEL_COMPLETION_RATE: "
        f"{summary['run_level_completion_rate']['rate_percent']}%"
    )

    return summary


def print_preflight(payload: dict[str, Any]) -> None:
    _print_heading("HW7 Part 2 Preflight")
    print(f"OLLAMA_VERSION: {payload['ollama']['version']}")
    print(f"MODEL: {MODEL_NAME} available")
    print(f"MYSQL_VERSION: {payload['fixture']['mysql_version']}")
    print(f"DATABASE: {payload['fixture']['database']}")
    print(
        "SEED_CHECK: Shared Room="
        f"{payload['fixture']['shared_room_count']}, "
        "S2974-000005.manager="
        f"{payload['fixture']['supporting_example_manager_id']}, "
        "Apartment="
        f"{payload['fixture']['apartment_count']}"
    )
    print("MODEL_CONFIG: " + json.dumps(MODEL_CONFIG, sort_keys=True))
    print("PREFLIGHT_STATUS: ready")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run HW7 Part 2 real-model experiments.",
    )
    subparsers = parser.add_subparsers(
        dest="mode",
        required=True,
    )
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument(
        "--reset-fixture",
        action="store_true",
        help=(
            "Recreate only the guarded hw7_part2_fixture_2974 database "
            "tables before checking them."
        ),
    )
    verification_parser = subparsers.add_parser("verification")
    verification_parser.add_argument(
        "--task",
        choices=["A", "B", "C", "all"],
        default="all",
    )
    subparsers.add_parser("error-recovery")
    subparsers.add_parser("reliability")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        preflight = run_preflight(
            reset=(
                args.mode == "preflight"
                and args.reset_fixture
            )
        )
    except PreflightError as exc:
        _print_heading("HW7 Part 2 Preflight")
        print("PREFLIGHT_STATUS: blocked")
        print(f"STOP_REASON: {exc}")
        raise SystemExit(2) from exc

    if args.mode == "preflight":
        print_preflight(preflight)
    elif args.mode == "verification":
        run_verification(args.task)
    elif args.mode == "error-recovery":
        run_error_recovery()
    elif args.mode == "reliability":
        run_reliability()


if __name__ == "__main__":
    main()
