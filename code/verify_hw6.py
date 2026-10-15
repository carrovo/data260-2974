import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

STUDENT_NAME = "Xuanhua Li"
SID4 = 2974
PORT_BASE = 8274
PREFIX = "s2974"
SEED = 2974
VERIFY_SEED = 262974
DOMAIN_ID = 6
LOCAL_MODEL = "qwen3:8b"
MONGO_DATABASE = "s2974_doc"

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "reports" / "hw06" / "verification.json"
checks: list[dict[str, Any]] = []


def commit_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def add_check(name: str, function: Callable[[], str]) -> None:
    try:
        details = function()
    except Exception as exc:  # noqa: BLE001 - every check must be recorded
        checks.append(
            {
                "name": name,
                "passed": False,
                "details": f"{type(exc).__name__}: {exc}",
            }
        )
        print(f"FAIL | {name} | {type(exc).__name__}: {exc}")
    else:
        checks.append(
            {
                "name": name,
                "passed": True,
                "details": details,
            }
        )
        print(f"PASS | {name} | {details}")


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    expected_status: int = 200,
) -> tuple[int, Any]:
    request = urllib.request.Request(
        url,
        data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
        headers={"Content-Type": "application/json"},
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            status_code = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read()

    parsed = json.loads(body) if body else None

    if status_code != expected_status:
        raise AssertionError(
            f"Expected HTTP {expected_status}, received {status_code}: {parsed}"
        )

    return status_code, parsed


def check_required_files() -> str:
    required = [
        "AGENT.md",
        "MEMORY.original.md",
        "MEMORY.md",
        "memory_probes.yaml",
        "docker-compose.hw6.yml",
        "code/mongo_database.py",
        "code/hw6_memory.py",
        "code/file_memory.py",
        "code/hw6_memory_experiment.py",
        "reports/hw06/AI_USE.md",
        "reports/hw06/METRICS.md",
        "reports/hw06/RUN_LOG.txt",
    ]
    missing = [name for name in required if not (ROOT / name).is_file()]

    if missing:
        raise AssertionError(f"Missing files: {missing}")

    return f"{len(required)} required HW6 files found"


def check_offline_tests() -> str:
    result = subprocess.run(
        [sys.executable, "code/test_hw6_offline.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise AssertionError(result.stdout[-800:] + result.stderr[-800:])

    if "HW6 OFFLINE TESTS: 6/6 PASS" not in result.stdout:
        raise AssertionError("Expected 6/6 offline-test summary")

    return "Deterministic offline tests: 6/6 PASS"


def check_memory_fixtures() -> str:
    from file_memory import FileMemoryManager

    manager = FileMemoryManager(ROOT)
    final_count = len(manager.non_empty_non_comment_lines())

    original_lines = [
        line.strip()
        for line in (ROOT / "MEMORY.original.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith("<!--")
    ]

    if len(original_lines) != 55:
        raise AssertionError(f"Original memory has {len(original_lines)} lines, not 55")

    if final_count >= 40:
        raise AssertionError(f"Consolidated memory has {final_count} lines")

    return f"MEMORY.md consolidation: 55 -> {final_count} lines"


def check_mongodb() -> str:
    from mongo_database import ensure_hw6_collections, get_mongo_db

    ensure_hw6_collections()
    db = get_mongo_db()
    names = set(db.list_collection_names())
    required = {
        "listings",
        "messages",
        "summaries",
        "episodes",
        "chat_metrics",
    }
    missing = required - names

    if missing:
        raise AssertionError(f"Missing MongoDB collections: {sorted(missing)}")

    return f"MongoDB {MONGO_DATABASE}: five required collections found"


def check_health(base_url: str) -> str:
    _, payload = request_json("GET", f"{base_url}/health")

    if payload != {"status": "ok"}:
        raise AssertionError(f"Unexpected health payload: {payload}")

    return f"FastAPI health returned {payload}"


def check_document_crud(base_url: str) -> str:
    unique = uuid.uuid4().hex[:8]
    _, created = request_json(
        "POST",
        f"{base_url}/api/doc-listings",
        {
            "listingTitle": f"HW6 Verification {unique}",
            "description": "Temporary document used by verify_hw6.py.",
            "status": "active",
            "propertyType": "Apartment",
            "availableFrom": "2026-11-15T12:00:00Z",
        },
        expected_status=201,
    )
    listing_id = created["id"]
    _, fetched = request_json(
        "GET",
        f"{base_url}/api/doc-listings/{listing_id}",
    )

    if fetched["listingTitle"] != created["listingTitle"]:
        raise AssertionError("Created and fetched listing titles differ")

    _, updated = request_json(
        "PUT",
        f"{base_url}/api/doc-listings/{listing_id}",
        {"status": "pending"},
    )

    if updated["status"] != "pending":
        raise AssertionError("Document listing update did not persist")

    request_json(
        "DELETE",
        f"{base_url}/api/doc-listings/{listing_id}",
        expected_status=204,
    )
    return "POST, GET, PUT, and DELETE document checks passed"


def check_validation(base_url: str) -> str:
    _, payload = request_json(
        "POST",
        f"{base_url}/api/doc-listings",
        {
            "listingTitle": "",
            "status": "unknown",
            "propertyType": "Castle",
            "availableFrom": "not-a-date",
        },
        expected_status=422,
    )

    if not payload.get("detail"):
        raise AssertionError("Validation response has no details")

    return "Invalid title, enums, and date returned HTTP 422"


def check_chat_and_memory(base_url: str) -> str:
    user_id = f"verify-{VERIFY_SEED}"
    session_id = f"verify-{uuid.uuid4().hex[:10]}"
    _, chat_payload = request_json(
        "POST",
        f"{base_url}/api/chat",
        {
            "user_id": user_id,
            "session_id": session_id,
            "message": "Remember that my budget is $2,200.",
            "memory_mode": "hybrid",
            "short_term_n": 4,
        },
    )

    if not chat_payload.get("reply"):
        raise AssertionError("Chat response did not contain a reply")

    if "metrics" not in chat_payload:
        raise AssertionError("Chat response did not contain metrics")

    _, memory_payload = request_json(
        "GET",
        f"{base_url}/api/memory/{user_id}?session_id={session_id}",
    )
    _, aggregate_payload = request_json(
        "GET",
        f"{base_url}/api/aggregate/{user_id}",
    )

    if len(memory_payload.get("messages", [])) < 2:
        raise AssertionError("Saved chat messages were not returned")

    if not aggregate_payload.get("daily_message_counts"):
        raise AssertionError("Aggregate returned no daily counts")

    return "Chat, memory retrieval, and aggregation checks passed"


def check_file_command(base_url: str) -> str:
    _, payload = request_json(
        "POST",
        f"{base_url}/api/chat",
        {
            "user_id": "verify-file-memory",
            "session_id": "verify-file-session",
            "message": "/help",
            "memory_mode": "file",
        },
    )

    for command in ("/memory", "/compact", "/dream", "/help"):
        if command not in payload.get("reply", ""):
            raise AssertionError(f"Missing command {command}")

    return "All four file-memory commands are advertised"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify DATA 260 HW6")
    parser.add_argument(
        "--base-url",
        default=f"http://127.0.0.1:{PORT_BASE}",
    )
    parser.add_argument(
        "--offline-only",
        action="store_true",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    add_check("Required repository files", check_required_files)
    add_check("Offline logic tests", check_offline_tests)
    add_check("Memory consolidation fixtures", check_memory_fixtures)

    if not args.offline_only:
        add_check("MongoDB collections", check_mongodb)
        add_check("FastAPI health", lambda: check_health(base_url))
        add_check("MongoDB document CRUD", lambda: check_document_crud(base_url))
        add_check("Pydantic validation", lambda: check_validation(base_url))
        add_check(
            "Chat and MongoDB memory",
            lambda: check_chat_and_memory(base_url),
        )
        add_check(
            "File-memory commands",
            lambda: check_file_command(base_url),
        )

    passed = sum(check["passed"] for check in checks)
    payload = {
        "homework": 6,
        "student": STUDENT_NAME,
        "SID4": SID4,
        "commit_hash": commit_hash(),
        "model": LOCAL_MODEL,
        "configuration": {
            "PORT_BASE": PORT_BASE,
            "PREFIX": PREFIX,
            "DOMAIN_ID": DOMAIN_ID,
            "mongo_database": MONGO_DATABASE,
        },
        "SEED": SEED,
        "VERIFY_SEED": VERIFY_SEED,
        "timestamp": datetime.now().astimezone().isoformat(),
        "mode": ("offline-only" if args.offline_only else "full-smoke-test"),
        "checks": checks,
        "summary": {
            "passed": passed,
            "total": len(checks),
            "all_passed": passed == len(checks),
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    print(f"FINAL SUMMARY: {passed}/{len(checks)} PASS")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")

    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
