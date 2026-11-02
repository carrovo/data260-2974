"""Run bounded live and recorded-evidence checks for DATA 260 HW8."""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = PROJECT_ROOT / "reports" / "hw08"
DEFAULT_OUTPUT = REPORT_ROOT / "verification.json"
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.hw8.yml"
SID4 = 2974
PORT_BASE = 8274
PREFIX = "s2974"
SEED = 2974
VERIFY_SEED = 262974
DOMAIN_ID = 6
MODEL = "qwen3:8b"
EXPECTED_SCREENSHOTS = {
    f"{number:02d}_{suffix}"
    for number, suffix in (
        (1, "part1_docker_containers.png"),
        (2, "part1_create_listing.png"),
        (3, "part1_get_listing.png"),
        (4, "part1_fastapi_message_flow.png"),
        (5, "part1_worker_message_flow.png"),
        (6, "part2_agent_containers.png"),
        (7, "part2_client_final_json.png"),
        (8, "part2_planner_message_flow.png"),
        (9, "part2_writer_message_flow.png"),
        (10, "part2_reviewer_message_flow.png"),
        (11, "part2_tasks_two_partitions.png"),
        (12, "part3_duplicate_before_fix.png"),
        (13, "part3_duplicate_after_fix.png"),
        (14, "part3_duplicate_worker_idempotency.png"),
        (15, "part3_consumer_killed_mid_work.png"),
        (16, "part3_consumer_redelivered_after_restart.png"),
        (17, "part3_consumer_completed_after_restart.png"),
        (18, "part3_poison_retries_and_dlq.png"),
        (19, "part3_poison_dead_letter_record.png"),
        (20, "part3_later_message_after_poison.png"),
        (21, "part3_ordering_no_key.png"),
        (22, "part3_ordering_entity_key.png"),
        (23, "part3_ordering_two_writers_checks.png"),
    )
}
REQUIRED_RAW = {
    "consumer_death_test.json",
    "duplicate_after_fix.json",
    "duplicate_before_fix.json",
    "ordering_test.json",
    "poison_message_test.json",
}
TEXT_SUFFIXES = {
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".sh",
    ".txt",
    ".ts",
    ".tsx",
    ".yml",
    ".yaml",
}
GOOGLE_KEY_PATTERN = re.compile(rb"AIza[0-9A-Za-z_-]{35}")


def git_output(*arguments: str) -> str:
    """Return stripped output from one Git command."""

    completed = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def load_json(path: Path) -> dict[str, Any]:
    """Load one required JSON object."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    """Build one verification result."""

    return {"name": name, "passed": bool(passed), "detail": detail}


def compose_up() -> tuple[bool, str]:
    """Start the bounded Part 1 stack needed for a live round trip."""

    command = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "up",
        "-d",
        "--build",
        "kafka",
        "kafka-init",
        "worker",
        "api",
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    detail = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, detail[-2000:]


def request_json(path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    """Send one local HTTP request and decode its JSON response."""

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{PORT_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urlopen(request, timeout=15) as response:
        value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("HTTP response must be a JSON object")
        return response.status, value


def wait_for_health() -> dict[str, Any]:
    """Wait up to 60 seconds for the FastAPI health endpoint."""

    deadline = time.monotonic() + 60
    last_error = "health endpoint did not respond"
    while time.monotonic() < deadline:
        try:
            status, payload = request_json("/health")
            if status == 200 and payload.get("status") == "ok":
                return payload
            last_error = f"unexpected health response: {status} {payload}"
        except (OSError, URLError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(last_error)


def live_round_trip() -> list[dict[str, Any]]:
    """Start the stack and verify CREATE then GET through Kafka."""

    started, startup_detail = compose_up()
    results = [
        check(
            "compose_stack_started",
            started,
            "Kafka, kafka-init, Worker, and FastAPI compose services started",
        )
    ]
    if not started:
        results[0]["detail"] += f": {startup_detail}"
        return results

    try:
        health = wait_for_health()
        run_id = str(uuid4())
        create_id = f"verify-create-{run_id}"
        create_status, created = request_json(
            "/hw8/listings",
            {
                "correlation_id": create_id,
                "reply_to": f"{PREFIX}_entity_responses",
                "operation": "CREATE_LISTING",
                "data": {
                    "listingTitle": "HW8 Verification Studio",
                    "address": "100 Verification Way, San Jose, CA",
                    "description": (
                        "A deterministic listing created by the HW8 self-check."
                    ),
                    "propertyType": "Studio",
                    "monthlyRent": 1800,
                    "availableUnits": 1,
                },
            },
        )
        entity_id = created.get("entity_id")
        get_id = f"verify-get-{run_id}"
        get_status, fetched = request_json(
            "/hw8/listings",
            {
                "correlation_id": get_id,
                "reply_to": f"{PREFIX}_entity_responses",
                "operation": "GET_LISTING",
                "data": {"entity_id": entity_id},
            },
        )
        results.extend(
            [
                check(
                    "api_health",
                    health.get("request_topic") == f"{PREFIX}_entity_requests"
                    and health.get("response_topic")
                    == f"{PREFIX}_entity_responses",
                    "HTTP 200 health response reported both required topics",
                ),
                check(
                    "live_create_listing",
                    create_status == 200
                    and created.get("success") is True
                    and created.get("correlation_id") == create_id
                    and isinstance(entity_id, str),
                    "CREATE_LISTING completed through FastAPI and Kafka",
                ),
                check(
                    "live_get_listing",
                    get_status == 200
                    and fetched.get("success") is True
                    and fetched.get("correlation_id") == get_id
                    and fetched.get("entity", {}).get("entity_id") == entity_id,
                    "GET_LISTING returned the entity created in the same live run",
                ),
            ]
        )
    except Exception as exc:
        results.append(check("live_round_trip", False, f"{type(exc).__name__}: {exc}"))
    return results


def offline_test_checks() -> list[dict[str, Any]]:
    """Run all deterministic HW8 offline test suites."""

    suites = [
        "code/test_hw8_part1_offline.py",
        "code/test_hw8_part2_offline.py",
        "code/test_hw8_part3_idempotency.py",
        "code/test_hw8_part3_consumer_death.py",
        "code/test_hw8_part3_poison_dlq.py",
        "code/test_hw8_part3_ordering.py",
    ]
    results = []
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "code")
    for suite in suites:
        completed = subprocess.run(
            [sys.executable, suite, "-v"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (completed.stdout + completed.stderr).strip()
        results.append(
            check(
                f"offline_{Path(suite).stem}",
                completed.returncode == 0,
                output[-800:],
            )
        )
    return results


def evidence_checks() -> list[dict[str, Any]]:
    """Validate the recorded Part 3 failure evidence."""

    raw = REPORT_ROOT / "raw"
    before = load_json(raw / "duplicate_before_fix.json")
    after = load_json(raw / "duplicate_after_fix.json")
    death = load_json(raw / "consumer_death_test.json")
    poison = load_json(raw / "poison_message_test.json")
    ordering = load_json(raw / "ordering_test.json")
    return [
        check(
            "duplicate_before_and_after",
            before.get("extra_side_effect") is True
            and after.get("extra_side_effect") is False
            and after.get("same_entity_id") is True,
            "replay created a second entity before the fix and reused one after it",
        ),
        check(
            "consumer_death_redelivery",
            death.get("completed_after_restart") is True
            and death.get("task_partition") == 1
            and death.get("task_offset") == 0
            and death.get("final_message", {}).get("value", {}).get("status")
            == "approved",
            "partition 1 offset 0 completed with approved status after restart",
        ),
        check(
            "poison_message_dlq",
            poison.get("max_attempts") == 3
            and poison.get("later_message_completed") is True
            and poison.get("dead_letter_result", {}).get("value", {}).get("attempts")
            == 3,
            "poison task moved to DLQ after 3 attempts and later task completed",
        ),
        check(
            "partition_key_ordering",
            ordering.get("pass") is True
            and ordering.get("verify_seed") == VERIFY_SEED
            and ordering.get("message_count_per_run") == 20
            and all(ordering.get("checks", {}).values()),
            "20-message no-key and entity-key runs passed all six checks",
        ),
    ]


def tracked(relative_path: str) -> bool:
    """Return whether Git tracks one repository-relative path."""

    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative_path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def secret_pattern_count() -> int:
    """Count Google-style API key patterns without printing file contents."""

    count = 0
    for root in (PROJECT_ROOT / "code", REPORT_ROOT):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            count += len(GOOGLE_KEY_PATTERN.findall(path.read_bytes()))
    return count


def artifact_checks() -> list[dict[str, Any]]:
    """Check required evidence, documentation, and tracked state."""

    screenshots = {path.name for path in (REPORT_ROOT / "screenshots").glob("*.png")}
    raw_files = {path.name for path in (REPORT_ROOT / "raw").glob("*.json")}
    docs = {
        "reports/hw08/AI_USE.md",
        "reports/hw08/METRICS.md",
        "reports/hw08/RUN_LOG.txt",
    }
    evidence = {
        *(f"reports/hw08/raw/{name}" for name in REQUIRED_RAW),
        *(f"reports/hw08/screenshots/{name}" for name in EXPECTED_SCREENSHOTS),
    }
    ai_use = (REPORT_ROOT / "AI_USE.md").read_text(encoding="utf-8")
    return [
        check(
            "required_screenshots",
            EXPECTED_SCREENSHOTS <= screenshots,
            "all 23 labeled screenshots are present",
        ),
        check(
            "required_raw_evidence",
            REQUIRED_RAW <= raw_files,
            "all 5 machine-readable failure files are present",
        ),
        check(
            "required_documentation",
            all((PROJECT_ROOT / path).is_file() for path in docs),
            "AI use, metrics, and run log documents are present",
        ),
        check(
            "required_files_tracked",
            all(tracked(path) for path in docs | evidence),
            "required documentation and evidence are tracked by Git",
        ),
        check(
            "ai_use_four_questions",
            all(f"## {number}." in ai_use for number in range(1, 5)),
            "AI_USE.md answers all four required questions",
        ),
        check(
            "secret_pattern_scan",
            secret_pattern_count() == 0,
            "count-only Google API key pattern scan found zero matches",
        ),
    ]


def build_verification() -> dict[str, Any]:
    """Run all HW8 checks and build the verification document."""

    checks = [
        *live_round_trip(),
        *offline_test_checks(),
        *evidence_checks(),
        *artifact_checks(),
    ]
    return {
        "homework": 8,
        "student": "Xuanhua Li",
        "sid4": SID4,
        "commit_hash": git_output("rev-parse", "HEAD"),
        "branch": git_output("branch", "--show-current"),
        "model": MODEL,
        "configuration": {
            "port_base": PORT_BASE,
            "prefix": PREFIX,
            "seed": SEED,
            "verify_seed": VERIFY_SEED,
            "domain_id": DOMAIN_ID,
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": (
            "live Kafka CREATE/GET round trip, deterministic offline suites, "
            "recorded Part 3 evidence, and required tracked artifacts"
        ),
        "checks": checks,
        "passed": all(item["passed"] for item in checks),
    }


def main() -> None:
    """Write verification.json and exit nonzero if any check fails."""

    result = build_verification()
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for item in result["checks"]:
        status = "PASS" if item["passed"] else "FAIL"
        print(f"{status}: {item['name']} - {item['detail']}")
    print(f"VERIFICATION_JSON={DEFAULT_OUTPUT}")
    print(f"FINAL_STATUS={'PASS' if result['passed'] else 'FAIL'}")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
