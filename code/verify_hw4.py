from __future__ import annotations

import asyncio
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
REPORT_DIR = ROOT / "reports" / "hw04"
RAW_DIR = REPORT_DIR / "raw"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"
OUTPUT_FILE = REPORT_DIR / "verification.json"

SID4 = 2974
DOMAIN_ID = 6
PORT_BASE = 8274
PREFIX = "s2974"
SEED = 2974
VERIFY_SEED = 262974

EXPECTED_CONFIGURATIONS = [
    "A_no_rag",
    "B_basic_rag",
    "C_context_engineered_rag",
]

EXPECTED_QUESTION_TYPES = [
    "one_chunk",
    "two_chunks",
    "similar_across_documents",
    "ambiguous",
    "not_in_documents",
    "unrelated",
]

REFUSAL_TEXT = (
    "I cannot answer this question from the provided documents."
)

checks: list[dict[str, Any]] = []


def record(
    name: str,
    passed: bool,
    details: Any,
) -> None:
    """Record one verification result."""
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "details": details,
        }
    )


def run_check(
    name: str,
    function: Callable[[], tuple[bool, dict[str, Any]]],
) -> None:
    """Run one check and record unexpected failures."""
    try:
        passed, details = function()
        record(name, passed, details)
    except Exception as error:
        record(
            name,
            False,
            {
                "error_type": type(error).__name__,
                "message": str(error),
            },
        )


def git_output(*arguments: str) -> str:
    """Return output from a read-only Git command."""
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load non-empty JSON Lines records."""
    return [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def check_project_files() -> tuple[bool, dict[str, Any]]:
    """Check required source and documentation files."""
    required_files = [
        CODE_DIR / "main.py",
        CODE_DIR / "database.py",
        CODE_DIR / "models.py",
        CODE_DIR / "schemas.py",
        CODE_DIR / "crud.py",
        CODE_DIR / "auth_service.py",
        CODE_DIR / "init_db.py",
        CODE_DIR / "seed_hw4.py",
        CODE_DIR / "hw4_n_plus_one_experiment.py",
        CODE_DIR / "hw4_rag_experiment.py",
        CODE_DIR / "hw4_compute_rag_metrics.py",
        ROOT / "frontend" / "package.json",
        ROOT / "frontend" / "src" / "App.jsx",
        ROOT / "frontend" / "src" / "pages" / "Login.jsx",
        ROOT / "frontend" / "src" / "pages" / "Home.jsx",
        ROOT / "frontend" / "src" / "pages" / "CreateRecord.jsx",
        ROOT / "frontend" / "src" / "pages" / "UpdateRecord.jsx",
        ROOT / "frontend" / "src" / "pages" / "DeleteRecord.jsx",
        ROOT / "questions_hw4.yaml",
        ROOT / "SOURCES.md",
        REPORT_DIR / "METRICS.md",
        REPORT_DIR / "RUN_LOG.txt",
        REPORT_DIR / "AI_USE.md",
    ]

    missing_files = [
        str(path.relative_to(ROOT))
        for path in required_files
        if not path.exists()
    ]

    return (
        not missing_files,
        {
            "required_file_count": len(required_files),
            "missing_files": missing_files,
        },
    )


def check_application() -> tuple[bool, dict[str, Any]]:
    """Run an authenticated smoke test against the FastAPI app."""
    import httpx
    from sqlalchemy import text

    if str(CODE_DIR) not in sys.path:
        sys.path.insert(0, str(CODE_DIR))

    from database import db_session_basede26
    from main import app

    verify_email = (
        f"verify-hw4-{VERIFY_SEED}@example.com"
    )
    verify_password = "VerifyOnly262974!"

    # Remove an old verification user before the test.
    with db_session_basede26.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM users "
                "WHERE email = :email"
            ),
            {
                "email": verify_email,
            },
        )

    async def exercise_application() -> dict[str, Any]:
        results: dict[str, Any] = {}

        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            health_response = await client.get(
                "/health"
            )

            results["health_status"] = (
                health_response.status_code
            )
            results["health_body"] = (
                health_response.json()
            )

            register_response = await client.post(
                "/api/auth/register",
                json={
                    "name": "HW4 Verification User",
                    "email": verify_email,
                    "password": verify_password,
                },
            )

            results["register_status"] = (
                register_response.status_code
            )

            login_response = await client.post(
                "/api/auth/login",
                json={
                    "email": verify_email,
                    "password": verify_password,
                },
            )

            cookie_header = login_response.headers.get(
                "set-cookie",
                "",
            )
            cookie_lower = cookie_header.lower()

            results["login_status"] = (
                login_response.status_code
            )
            results["cookie_httponly"] = (
                "httponly" in cookie_lower
            )
            results["cookie_samesite_lax"] = (
                "samesite=lax" in cookie_lower
            )
            results["cookie_max_age_1800"] = (
                "max-age=1800" in cookie_lower
            )

            me_response = await client.get(
                "/api/auth/me"
            )

            results["me_status"] = (
                me_response.status_code
            )
            results["me_email"] = (
                me_response.json().get("email")
                if me_response.status_code == 200
                else None
            )

            naive_response = await client.get(
                "/api/listings/naive",
                params={
                    "page_size": 10,
                },
            )

            fixed_response = await client.get(
                "/api/listings/fixed",
                params={
                    "page_size": 10,
                },
            )

            results["naive_status"] = (
                naive_response.status_code
            )
            results["fixed_status"] = (
                fixed_response.status_code
            )

            results["naive_records"] = (
                len(naive_response.json())
                if naive_response.status_code == 200
                else 0
            )
            results["fixed_records"] = (
                len(fixed_response.json())
                if fixed_response.status_code == 200
                else 0
            )

            results["naive_sql_statements"] = (
                naive_response.headers.get(
                    "x-sql-statements"
                )
            )
            results["fixed_sql_statements"] = (
                fixed_response.headers.get(
                    "x-sql-statements"
                )
            )

        return results

    try:
        results = asyncio.run(
            exercise_application()
        )
    finally:
        # Delete the temporary user and its sessions.
        with db_session_basede26.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM users "
                    "WHERE email = :email"
                ),
                {
                    "email": verify_email,
                },
            )

    required_results = [
        results["health_status"] == 200,
        results["health_body"] == {
            "status": "ok",
        },
        results["register_status"] == 201,
        results["login_status"] == 200,
        results["cookie_httponly"],
        results["cookie_samesite_lax"],
        results["cookie_max_age_1800"],
        results["me_status"] == 200,
        results["me_email"] == verify_email,
        results["naive_status"] == 200,
        results["fixed_status"] == 200,
        results["naive_records"] == 10,
        results["fixed_records"] == 10,
        results["naive_sql_statements"] == "11",
        results["fixed_sql_statements"] == "2",
    ]

    return all(required_results), results


def check_questions() -> tuple[bool, dict[str, Any]]:
    """Check the six required question categories."""
    data = yaml.safe_load(
        (ROOT / "questions_hw4.yaml").read_text(
            encoding="utf-8"
        )
    )

    questions = data.get("questions", [])

    question_ids = [
        question.get("id")
        for question in questions
    ]

    question_types = [
        question.get("type")
        for question in questions
    ]

    answerability_values = [
        question.get("answerability")
        for question in questions
    ]

    passed = (
        data.get("question_count") == 6
        and question_ids == [
            "q1",
            "q2",
            "q3",
            "q4",
            "q5",
            "q6",
        ]
        and question_types
        == EXPECTED_QUESTION_TYPES
        and answerability_values.count(
            "answerable"
        ) == 4
        and answerability_values.count(
            "unsupported"
        ) == 1
        and answerability_values.count(
            "out_of_domain"
        ) == 1
    )

    return (
        passed,
        {
            "declared_question_count": data.get(
                "question_count"
            ),
            "actual_question_count": len(questions),
            "question_ids": question_ids,
            "question_types": question_types,
            "answerability": answerability_values,
        },
    )


def check_database() -> tuple[bool, dict[str, Any]]:
    """Check seed counts, foreign keys, and the added index."""
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text

    load_dotenv()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        return (
            False,
            {
                "error": "DATABASE_URL is missing.",
            },
        )

    engine = create_engine(database_url)

    with engine.connect() as connection:
        listing_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM listings"
            )
        ).scalar_one()

        event_count = connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM listing_events"
            )
        ).scalar_one()

        listings_with_events = connection.execute(
            text(
                "SELECT COUNT(DISTINCT listing_id) "
                "FROM listing_events"
            )
        ).scalar_one()

        index_count = connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'listing_events' "
                "AND index_name = "
                "'idx_listing_events_event_type' "
                "AND column_name = 'event_type'"
            )
        ).scalar_one()

    details = {
        "seed": SEED,
        "listing_count": listing_count,
        "event_count": event_count,
        "listings_with_events": listings_with_events,
        "event_type_index_count": index_count,
    }

    passed = (
        listing_count == 5000
        and event_count == 200
        and listings_with_events == 199
        and index_count == 1
    )

    return passed, details


def check_n_plus_one_outputs() -> tuple[bool, dict[str, Any]]:
    """Check all 180 N+1 request records."""
    csv_path = (
        RAW_DIR / "n_plus_one_requests.csv"
    )
    summary_path = (
        RAW_DIR / "n_plus_one_summary.json"
    )

    with csv_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        csv_rows = list(csv.DictReader(file))

    summary_data = json.loads(
        summary_path.read_text(
            encoding="utf-8"
        )
    )
    summary_rows = summary_data.get(
        "summary",
        []
    )

    expected_sql_counts = {
        ("naive", 10): 11,
        ("naive", 50): 51,
        ("naive", 200): 201,
        ("fixed", 10): 2,
        ("fixed", 50): 2,
        ("fixed", 200): 2,
    }

    combination_counts: dict[
        tuple[str, int],
        int,
    ] = {}

    invalid_rows: list[dict[str, Any]] = []

    for row in csv_rows:
        key = (
            row["mode"],
            int(row["page_size"]),
        )

        combination_counts[key] = (
            combination_counts.get(key, 0) + 1
        )

        expected_sql = expected_sql_counts.get(
            key
        )

        if (
            row["status_code"] != "200"
            or int(row["sql_statements"])
            != expected_sql
        ):
            invalid_rows.append(row)

    correct_repetitions = all(
        combination_counts.get(key) == 30
        for key in expected_sql_counts
    )

    details = {
        "csv_request_rows": len(csv_rows),
        "summary_rows": len(summary_rows),
        "combination_counts": {
            f"{mode}_{page_size}": count
            for (
                mode,
                page_size,
            ), count in combination_counts.items()
        },
        "invalid_row_count": len(invalid_rows),
    }

    passed = (
        len(csv_rows) == 180
        and len(summary_rows) == 6
        and correct_repetitions
        and not invalid_rows
    )

    return passed, details


def check_rag_outputs() -> tuple[bool, dict[str, Any]]:
    """Check the corrected 54-run RAG experiment."""
    run_summary = json.loads(
        (
            RAW_DIR / "rag_run_summary.json"
        ).read_text(encoding="utf-8")
    )

    output_rows = load_jsonl(
        RAW_DIR / "rag_outputs.jsonl"
    )

    metric_rows = load_jsonl(
        RAW_DIR / "rag_per_run_metrics.jsonl"
    )

    metrics_summary = json.loads(
        (
            RAW_DIR / "rag_metrics_summary.json"
        ).read_text(encoding="utf-8")
    )

    with (
        RAW_DIR / "rag_outputs.csv"
    ).open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        csv_rows = list(csv.DictReader(file))

    configurations = sorted(
        {
            row.get("configuration")
            for row in output_rows
        }
    )

    refusal_rows = [
        row
        for row in output_rows
        if (
            row.get("configuration")
            == "C_context_engineered_rag"
            and row.get("query_id")
            in {"q5", "q6"}
        )
    ]

    valid_refusals = [
        row
        for row in refusal_rows
        if row.get("answer", "").strip()
        == REFUSAL_TEXT
    ]

    retrieval_printout_path = (
        RAW_DIR / "rag_retrieval_printouts.txt"
    )

    details = {
        "reported_total_runs": run_summary.get(
            "total_runs"
        ),
        "reported_configurations": (
            run_summary.get("configurations")
        ),
        "jsonl_records": len(output_rows),
        "csv_records": len(csv_rows),
        "per_run_metric_records": len(metric_rows),
        "metric_summary_rows": len(
            metrics_summary.get("summary", [])
        ),
        "configurations_found": configurations,
        "required_refusal_rows": len(
            refusal_rows
        ),
        "valid_refusal_rows": len(
            valid_refusals
        ),
        "retrieval_printout_exists": (
            retrieval_printout_path.exists()
        ),
    }

    passed = (
        run_summary.get("total_runs") == 54
        and run_summary.get("configurations")
        == EXPECTED_CONFIGURATIONS
        and run_summary.get("k_values")
        == [1, 3, 5]
        and len(output_rows) == 54
        and len(csv_rows) == 54
        and len(metric_rows) == 54
        and len(
            metrics_summary.get("summary", [])
        ) == 9
        and configurations
        == sorted(EXPECTED_CONFIGURATIONS)
        and len(refusal_rows) == 6
        and len(valid_refusals) == 6
        and retrieval_printout_path.exists()
    )

    return passed, details


def check_documentation() -> tuple[bool, dict[str, Any]]:
    """Check final documentation content."""
    metrics_text = (
        REPORT_DIR / "METRICS.md"
    ).read_text(encoding="utf-8")

    run_log_text = (
        REPORT_DIR / "RUN_LOG.txt"
    ).read_text(encoding="utf-8")

    ai_use_text = (
        REPORT_DIR / "AI_USE.md"
    ).read_text(encoding="utf-8")

    sources_text = (
        ROOT / "SOURCES.md"
    ).read_text(encoding="utf-8")

    required_metrics_terms = [
        "A_no_rag",
        "B_basic_rag",
        "C_context_engineered_rag",
        "SQL statements/request",
        "idx_listing_events_event_type",
        "Format compliance",
    ]

    required_run_log_terms = [
        "VERIFY_SEED: 262974",
        "sql= 201.0",
        "C_context_engineered_rag",
        "Total RAG runs: 54",
    ]

    required_ai_sections = [
        "## 1.",
        "## 2.",
        "## 3.",
        "## 4.",
    ]

    required_sources = [
        "hud_assistance_animal_notice.pdf",
        "hud_fair_housing_guide_2025.pdf",
    ]

    missing_metrics_terms = [
        term
        for term in required_metrics_terms
        if term not in metrics_text
    ]

    missing_run_log_terms = [
        term
        for term in required_run_log_terms
        if term not in run_log_text
    ]

    missing_ai_sections = [
        term
        for term in required_ai_sections
        if term not in ai_use_text
    ]

    missing_sources = [
        term
        for term in required_sources
        if term not in sources_text
    ]

    details = {
        "missing_metrics_terms": (
            missing_metrics_terms
        ),
        "missing_run_log_terms": (
            missing_run_log_terms
        ),
        "missing_ai_sections": (
            missing_ai_sections
        ),
        "missing_sources": missing_sources,
    }

    passed = not any(
        [
            missing_metrics_terms,
            missing_run_log_terms,
            missing_ai_sections,
            missing_sources,
        ]
    )

    return passed, details


def check_screenshots() -> tuple[bool, dict[str, Any]]:
    """Check the final evidence screenshots."""
    required_names = [
        "hw04_part1_logged_in_home.png",
        "hw04_part1_create_listing.png",
        "hw04_part1_update_listing.png",
        "hw04_part1_delete_confirmation.png",
        "hw04_part1_delete_result.png",
        "hw04_part1_logout.png",
        "hw04_part2_register.png",
        "hw04_part2_login_cookie.png",
        "hw04_part2_me.png",
        "hw04_part2_get_listings.png",
        "hw04_part2_create_listing.png",
        "hw04_part2_get_one_listing.png",
        "hw04_part2_update_listing.png",
        "hw04_part2_delete_listing.png",
        "hw04_part2_database_tables.png",
        "hw04_part2_database_schema.png",
        "hw04_part2_project_structure.png",
        "hw04_part3_seed_output.png",
        "hw04_part3_database_counts.png",
        "hw04_part3_naive_10.png",
        "hw04_part3_naive_50.png",
        "hw04_part3_naive_200.png",
        "hw04_part3_fixed_10.png",
        "hw04_part3_fixed_50.png",
        "hw04_part3_fixed_200.png",
        "hw04_part3_n_plus_one_summary.png",
        "hw04_part3_explain_before.png",
        "hw04_part3_explain_after.png",
        "hw04_part4_corpus.png",
        "hw04_part4_chunking.png",
        "hw04_part4_retrieval_printouts.png",
        "hw04_part4_rag_metrics_summary.png",
        "hw04_part4_refusal_results.png",
    ]

    missing_names = [
        name
        for name in required_names
        if not (SCREENSHOT_DIR / name).exists()
    ]

    empty_names = [
        name
        for name in required_names
        if (
            (SCREENSHOT_DIR / name).exists()
            and (SCREENSHOT_DIR / name).stat().st_size
            == 0
        )
    ]

    details = {
        "required_count": len(required_names),
        "found_count": (
            len(required_names)
            - len(missing_names)
        ),
        "missing_screenshots": missing_names,
        "empty_screenshots": empty_names,
    }

    return (
        not missing_names and not empty_names,
        details,
    )


def main() -> None:
    """Run the HW4 smoke test and save JSON output."""
    run_check(
        "project_files",
        check_project_files,
    )
    run_check(
        "application_smoke_test",
        check_application,
    )
    run_check(
        "evaluation_questions",
        check_questions,
    )
    run_check(
        "database_seed_and_index",
        check_database,
    )
    run_check(
        "n_plus_one_outputs",
        check_n_plus_one_outputs,
    )
    run_check(
        "rag_outputs",
        check_rag_outputs,
    )
    run_check(
        "documentation",
        check_documentation,
    )
    run_check(
        "screenshots",
        check_screenshots,
    )

    passed_count = sum(
        check["passed"]
        for check in checks
    )
    overall_passed = (
        passed_count == len(checks)
    )

    commit_hash = git_output(
        "rev-parse",
        "HEAD",
    )

    tags_at_commit = git_output(
        "tag",
        "--points-at",
        "HEAD",
    ).splitlines()

    verification = {
        "assignment": "HW4",
        "sid4": SID4,
        "domain_id": DOMAIN_ID,
        "assigned_domain": (
            "Rental housing listings"
        ),
        "port_base": PORT_BASE,
        "prefix": PREFIX,
        "commit_hash": commit_hash,
        "tags_at_commit": tags_at_commit,
        "model": "qwen3:8b",
        "embedding_model": (
            "sentence-transformers/"
            "all-MiniLM-L6-v2"
        ),
        "configurations": (
            EXPECTED_CONFIGURATIONS
        ),
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "generated_at_utc": (
            datetime.now(timezone.utc).isoformat()
        ),
        "overall_passed": overall_passed,
        "checks_passed": passed_count,
        "checks_total": len(checks),
        "checks": checks,
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            verification,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for check in checks:
        status = (
            "PASS"
            if check["passed"]
            else "FAIL"
        )

        print(
            f"[{status}] {check['name']}"
        )

        if not check["passed"]:
            print(
                json.dumps(
                    check["details"],
                    indent=2,
                    default=str,
                )
            )

    print()
    print(
        f"Checks passed: "
        f"{passed_count}/{len(checks)}"
    )
    print(
        f"Overall passed: "
        f"{overall_passed}"
    )
    print(
        f"Saved verification: "
        f"{OUTPUT_FILE}"
    )

    if not overall_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()