import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

from sqlalchemy import inspect, text


STUDENT_NAME = "Xuanhua Li"
SID4 = 2974
PORT_BASE = 8274
PREFIX = "s2974"
SEED = 2974
VERIFY_SEED = 262974
DOMAIN_ID = 6
LOCAL_MODEL = "qwen3:8b"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = (
    ROOT / "reports/hw05/verification.json"
)

checks: list[dict] = []


def commit_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


def add_check(name, check_function) -> None:
    try:
        details = check_function()
    except Exception as exc:
        checks.append(
            {
                "name": name,
                "passed": False,
                "details": str(exc),
            }
        )
        print(f"FAIL | {name} | {exc}")
    else:
        checks.append(
            {
                "name": name,
                "passed": True,
                "details": details,
            }
        )
        print(f"PASS | {name} | {details}")


def request_health() -> dict:
    url = f"http://127.0.0.1:{PORT_BASE}/health"

    with urlopen(url, timeout=2) as response:
        if response.status != 200:
            raise AssertionError(
                f"HTTP status was {response.status}"
            )

        payload = json.load(response)

    if payload.get("status") != "ok":
        raise AssertionError(
            f"Unexpected health response: {payload}"
        )

    return payload


def check_fastapi_health() -> str:
    process = None

    try:
        try:
            payload = request_health()

            return (
                f"Existing server returned {payload}"
            )
        except Exception:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "main:app",
                    "--app-dir",
                    "code",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(PORT_BASE),
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )

        deadline = time.monotonic() + 15

        while time.monotonic() < deadline:
            if process.poll() is not None:
                stderr = process.stderr.read()
                raise AssertionError(
                    "FastAPI stopped during startup: "
                    f"{stderr[-500:]}"
                )

            try:
                payload = request_health()

                return (
                    "Started temporary FastAPI server; "
                    f"response={payload}"
                )
            except Exception:
                time.sleep(0.25)

        raise AssertionError(
            "FastAPI health endpoint did not become "
            "ready within 15 seconds"
        )
    finally:
        if process is not None:
            process.terminate()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def check_database_schema() -> str:
    from database import db_session_basede26

    inspector = inspect(db_session_basede26)
    tables = set(inspector.get_table_names())

    required_tables = {
        "users",
        "sessions",
        "property_managers",
        "listings",
        "listing_events",
    }

    missing_tables = required_tables - tables

    if missing_tables:
        raise AssertionError(
            f"Missing tables: {sorted(missing_tables)}"
        )

    listing_columns = {
        column["name"]
        for column in inspector.get_columns(
            "listings"
        )
    }

    required_columns = {
        "listingCode",
        "monthlyRent",
        "availableUnits",
        "propertyManagerId",
        "updated_at",
    }

    missing_columns = (
        required_columns - listing_columns
    )

    if missing_columns:
        raise AssertionError(
            "Missing listing columns: "
            f"{sorted(missing_columns)}"
        )

    with db_session_basede26.connect() as connection:
        listing_count = connection.execute(
            text("SELECT COUNT(*) FROM listings")
        ).scalar_one()

        manager_count = connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM property_managers"
            )
        ).scalar_one()

    if listing_count < 5000:
        raise AssertionError(
            f"Expected at least 5000 listings, "
            f"found {listing_count}"
        )

    if manager_count < 1:
        raise AssertionError(
            "No property managers found"
        )

    return (
        f"{len(required_tables)} required tables; "
        f"{listing_count} listings; "
        f"{manager_count} manager(s)"
    )


def check_redux_client() -> str:
    package_path = ROOT / "frontend/package.json"

    package_data = json.loads(
        package_path.read_text(encoding="utf-8")
    )

    dependencies = package_data.get(
        "dependencies",
        {},
    )

    required_dependencies = {
        "@reduxjs/toolkit",
        "react-redux",
    }

    missing = (
        required_dependencies - set(dependencies)
    )

    if missing:
        raise AssertionError(
            f"Missing Redux packages: {sorted(missing)}"
        )

    required_files = [
        ROOT / (
            "frontend/src/features/listings/"
            "listingsSlice.js"
        ),
        ROOT / "frontend/src/store/store.js",
    ]

    for path in required_files:
        if not path.is_file():
            raise AssertionError(
                f"Missing Redux file: {path}"
            )

    return (
        "Redux Toolkit packages and listing "
        "store files found"
    )


def check_meals_mcp_tool() -> str:
    from meals_server import (
        mcp,
        search_meals_by_name,
    )

    if mcp is None:
        raise AssertionError(
            "TheMealDB FastMCP server was not created"
        )

    results = asyncio.run(
        search_meals_by_name(
            "Arrabiata",
            1,
        )
    )

    if not results:
        raise AssertionError(
            "TheMealDB search returned no results"
        )

    return (
        "TheMealDB MCP server imported; "
        f"tool returned {results[0]['name']}"
    )


def check_domain_mcp_tool() -> str:
    from domain_mcp_server import mcp
    from reliable_domain_tools import (
        search_listings,
    )

    if mcp is None:
        raise AssertionError(
            "Domain FastMCP server was not created"
        )

    result = search_listings(
        "Seed Rental Listing",
        1,
    )

    if result["ok"] is not True:
        raise AssertionError(result["error"])

    if len(result["data"]) != 1:
        raise AssertionError(
            "Domain search did not return one result"
        )

    return (
        "Domain MCP server imported; "
        f"tool returned "
        f"{result['data'][0]['listingCode']}"
    )


def check_tool_safety() -> str:
    from tool_executor import execute_tool

    raw_result = execute_tool(
        "search_listings",
        {
            "query": (
                "no families with children"
            ),
            "limit": 5,
        },
    )

    result = json.loads(raw_result)

    expected_error = (
        "Safety rule blocked a discriminatory "
        "housing search."
    )

    if result != {
        "ok": False,
        "data": None,
        "error": expected_error,
    }:
        raise AssertionError(
            f"Unexpected safety result: {result}"
        )

    return (
        "Discriminatory housing search blocked "
        "before handler execution"
    )


def check_offline_tests() -> str:
    result = subprocess.run(
        [
            sys.executable,
            "code/test_hw5_offline.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise AssertionError(
            result.stdout[-500:]
            + result.stderr[-500:]
        )

    if "FINAL SUMMARY: 10/10 PASS" not in (
        result.stdout
    ):
        raise AssertionError(
            "Expected 10/10 offline-test summary"
        )

    return "Part 4 + Part 5 offline tests: 10/10"


def check_ollama_model() -> str:
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise AssertionError(
            result.stderr.strip()
        )

    if LOCAL_MODEL not in result.stdout:
        raise AssertionError(
            f"{LOCAL_MODEL} is not installed"
        )

    return f"Local model installed: {LOCAL_MODEL}"


def check_failure_records() -> str:
    json_path = (
        ROOT
        / "reports/hw05/raw/"
        / "failure_injection_calls.json"
    )

    csv_path = (
        ROOT
        / "reports/hw05/raw/"
        / "failure_injection_calls.csv"
    )

    payload = json.loads(
        json_path.read_text(encoding="utf-8")
    )

    records = payload["records"]

    if len(records) != 150:
        raise AssertionError(
            f"Expected 150 records, "
            f"found {len(records)}"
        )

    csv_line_count = len(
        csv_path.read_text(
            encoding="utf-8"
        ).splitlines()
    )

    if csv_line_count != 151:
        raise AssertionError(
            "Expected one CSV header plus "
            "150 records"
        )

    if payload["verify_seed"] != VERIFY_SEED:
        raise AssertionError(
            "Unexpected VERIFY_SEED"
        )

    return (
        "150 JSON records and 150 CSV records; "
        f"VERIFY_SEED={VERIFY_SEED}"
    )


def check_agent_logs() -> str:
    log_path = (
        ROOT
        / "reports/hw05/raw/"
        / "agent_runs.jsonl"
    )

    runs = [
        json.loads(line)
        for line in log_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    if len(runs) < 4:
        raise AssertionError(
            f"Expected at least 4 runs, "
            f"found {len(runs)}"
        )

    normal_count = sum(
        run["stop_reason"]
        == "normal_completion"
        for run in runs
    )

    safety_count = sum(
        run["stop_reason"] == "safety_block"
        for run in runs
    )

    total_tool_calls = sum(
        run["tool_call_count"]
        for run in runs
    )

    if normal_count < 3:
        raise AssertionError(
            "Expected at least 3 normal completions"
        )

    if safety_count < 1:
        raise AssertionError(
            "Expected at least 1 safety block"
        )

    if total_tool_calls < 4:
        raise AssertionError(
            "Expected at least 4 tool calls"
        )

    return (
        f"{len(runs)} logged runs; "
        f"{normal_count} normal; "
        f"{safety_count} safety-blocked"
    )


def main() -> None:
    print(
        f"Student: {STUDENT_NAME} | SID4: {SID4}"
    )
    print("HW5 FINAL SELF-CHECK\n")

    add_check(
        "FastAPI health endpoint",
        check_fastapi_health,
    )
    add_check(
        "MySQL relational schema",
        check_database_schema,
    )
    add_check(
        "Redux client",
        check_redux_client,
    )
    add_check(
        "TheMealDB MCP tool",
        check_meals_mcp_tool,
    )
    add_check(
        "Rental domain MCP tool",
        check_domain_mcp_tool,
    )
    add_check(
        "Tool safety rule",
        check_tool_safety,
    )
    add_check(
        "Offline tool tests",
        check_offline_tests,
    )
    add_check(
        "Ollama local model",
        check_ollama_model,
    )
    add_check(
        "Failure-injection raw records",
        check_failure_records,
    )
    add_check(
        "Agent JSONL logs",
        check_agent_logs,
    )

    passed_count = sum(
        check["passed"]
        for check in checks
    )
    total_count = len(checks)

    verification = {
        "homework": "HW5",
        "student": STUDENT_NAME,
        "sid4": SID4,
        "commit_hash": commit_hash(),
        "timestamp": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),
        "model": {
            "provider": "Ollama",
            "name": LOCAL_MODEL,
        },
        "configuration": {
            "PORT_BASE": PORT_BASE,
            "PREFIX": PREFIX,
            "SEED": SEED,
            "VERIFY_SEED": VERIFY_SEED,
            "DOMAIN_ID": DOMAIN_ID,
            "DOMAIN": "rental housing",
        },
        "checks": checks,
        "summary": {
            "passed": passed_count,
            "total": total_count,
            "all_passed": (
                passed_count == total_count
            ),
        },
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            verification,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"\nFINAL SUMMARY: "
        f"{passed_count}/{total_count} PASS"
    )
    print(
        f"Verification written to: "
        f"{OUTPUT_PATH.relative_to(ROOT)}"
    )

    if passed_count != total_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()