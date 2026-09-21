from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
CORPUS_DIR = ROOT / "corpus" / "hw03"
REPORT_DIR = ROOT / "reports" / "hw03"
RAW_DIR = REPORT_DIR / "raw"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"
OUTPUT_FILE = REPORT_DIR / "verification.json"

DOMAIN_ID = 6
VERIFY_SEED = 262974
MINIMUM_CORPUS_BYTES = 200_000

checks: list[dict[str, Any]] = []


def record(name: str, passed: bool, details: Any) -> None:
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "details": details,
        }
    )


def run_check(name: str, function) -> None:
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def git_output(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def first_commit_for(path: str) -> str:
    output = git_output(
        "log",
        "--reverse",
        "--format=%H",
        "--",
        path,
    )
    commits = [line for line in output.splitlines() if line.strip()]
    return commits[0] if commits else ""


def check_application() -> tuple[bool, dict[str, Any]]:
    import asyncio

    import httpx

    os.environ["HW3_HTTPS_ONLY"] = "false"
    os.environ["HW3_IDLE_TIMEOUT_SECONDS"] = "1"

    if str(CODE_DIR) not in sys.path:
        sys.path.insert(0, str(CODE_DIR))

    from main import app

    async def exercise_application() -> dict[str, Any]:
        results: dict[str, Any] = {}

        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            home_response = await client.get("/")
            results["home_status"] = home_response.status_code
            results["home_passed"] = home_response.status_code == 200

            protected_response = await client.get("/dashboard")
            results["protected_status"] = protected_response.status_code
            results["protected_location"] = (
                protected_response.headers.get("location")
            )
            results["protected_passed"] = (
    protected_response.status_code in {302, 303, 307}
    and protected_response.headers.get(
        "location",
        "",
    ).startswith("/login")
)

            invalid_response = await client.post(
                "/login",
                data={
                    "username": "admin",
                    "password": "wrong-password",
                },
            )
            results["invalid_login_status"] = (
                invalid_response.status_code
            )
            results["invalid_login_passed"] = (
                invalid_response.status_code in {400, 401, 403}
            )

            login_response = await client.post(
                "/login",
                data={
                    "username": "admin",
                    "password": "password",
                },
            )

            cookie_header = login_response.headers.get(
                "set-cookie",
                "",
            )
            cookie_lower = cookie_header.lower()

            results["valid_login_status"] = login_response.status_code
            results["valid_login_location"] = (
                login_response.headers.get("location")
            )
            results["valid_login_passed"] = (
                login_response.status_code in {302, 303, 307}
                and login_response.headers.get("location") == "/dashboard"
            )

            results["cookie_httponly"] = (
                "httponly" in cookie_lower
            )
            results["cookie_samesite_lax"] = (
                "samesite=lax" in cookie_lower
            )
            results["cookie_max_age"] = (
                "max-age=3600" in cookie_lower
            )

            dashboard_response = await client.get("/dashboard")
            results["dashboard_status"] = (
                dashboard_response.status_code
            )
            results["dashboard_passed"] = (
                dashboard_response.status_code == 200
            )

            logout_response = await client.get("/logout")
            results["logout_status"] = logout_response.status_code
            results["logout_passed"] = (
                logout_response.status_code in {302, 303, 307}
            )

            after_logout_response = await client.get("/dashboard")
            results["after_logout_status"] = (
                after_logout_response.status_code
            )
            results["after_logout_passed"] = (
    after_logout_response.status_code in {302, 303, 307}
    and after_logout_response.headers.get(
        "location",
        "",
    ).startswith("/login")
)

        timeout_transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=timeout_transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as timeout_client:
            timeout_login = await timeout_client.post(
                "/login",
                data={
                    "username": "admin",
                    "password": "password",
                },
            )

            await asyncio.sleep(1.2)

            timeout_response = await timeout_client.get("/dashboard")

            results["timeout_login_status"] = (
                timeout_login.status_code
            )
            results["timeout_status"] = timeout_response.status_code
            results["timeout_location"] = (
                timeout_response.headers.get("location")
            )
            results["timeout_passed"] = (
    timeout_response.status_code in {302, 303, 307}
    and timeout_response.headers.get(
        "location",
        "",
    ).startswith("/login")
)

        return results

    results = asyncio.run(exercise_application())

    main_source = (CODE_DIR / "main.py").read_text(
        encoding="utf-8"
    )
    compact_source = main_source.replace(" ", "")

    results["secure_cookie_configured"] = (
        "SESSION_HTTPS_ONLY" in main_source
        and "https_only=SESSION_HTTPS_ONLY" in compact_source
    )

    required_results = [
        results["home_passed"],
        results["protected_passed"],
        results["invalid_login_passed"],
        results["valid_login_passed"],
        results["cookie_httponly"],
        results["cookie_samesite_lax"],
        results["cookie_max_age"],
        results["dashboard_passed"],
        results["logout_passed"],
        results["after_logout_passed"],
        results["timeout_passed"],
        results["secure_cookie_configured"],
    ]

    return all(required_results), results


def check_corpus() -> tuple[bool, dict[str, Any]]:
    pdf_files = sorted(CORPUS_DIR.glob("*.pdf"))
    total_bytes = sum(path.stat().st_size for path in pdf_files)

    details = {
        "file_count": len(pdf_files),
        "total_bytes": total_bytes,
        "minimum_required_bytes": MINIMUM_CORPUS_BYTES,
        "files": [
            {
                "filename": str(path.relative_to(ROOT)),
                "byte_size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in pdf_files
        ],
    }

    passed = (
        len(pdf_files) == 3
        and total_bytes >= MINIMUM_CORPUS_BYTES
    )

    return passed, details


def check_manifest() -> tuple[bool, dict[str, Any]]:
    manifest_path = ROOT / "CORPUS_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    pdf_files = sorted(CORPUS_DIR.glob("*.pdf"))
    actual_total = sum(path.stat().st_size for path in pdf_files)

    details = {
        "domain_id": manifest.get("domain_id"),
        "file_count": manifest.get("file_count"),
        "recorded_total_bytes": manifest.get("total_bytes"),
        "actual_total_bytes": actual_total,
        "meets_minimum_size": manifest.get("meets_minimum_size"),
    }

    passed = (
        manifest.get("domain_id") == DOMAIN_ID
        and manifest.get("file_count") == 3
        and manifest.get("total_bytes") == actual_total
        and manifest.get("meets_minimum_size") is True
    )

    return passed, details


def check_questions() -> tuple[bool, dict[str, Any]]:
    questions_path = ROOT / "questions.yaml"
    data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))

    if isinstance(data, dict):
        questions = data.get("questions", [])
    elif isinstance(data, list):
        questions = data
    else:
        questions = []

    question_ids = [
        question.get("id")
        for question in questions
        if isinstance(question, dict)
    ]

    details = {
        "question_count": len(questions),
        "question_ids": question_ids,
    }

    passed = (
        len(questions) == 5
        and question_ids == ["q1", "q2", "q3", "q4", "q5"]
    )

    return passed, details


def check_precommit_order() -> tuple[bool, dict[str, Any]]:
    questions_commit = first_commit_for("questions.yaml")
    experiment_commit = first_commit_for(
        "code/hw3_retrieval_experiment.py"
    )

    ancestor_result = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            questions_commit,
            experiment_commit,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    passed = (
        bool(questions_commit)
        and bool(experiment_commit)
        and questions_commit != experiment_commit
        and ancestor_result.returncode == 0
    )

    details = {
        "questions_first_commit": questions_commit,
        "experiment_first_commit": experiment_commit,
        "questions_committed_before_experiment": passed,
    }

    return passed, details


def check_retrieval_outputs() -> tuple[bool, dict[str, Any]]:
    techniques = ["token", "semantic", "sentence_window"]
    expected_files = [
        RAW_DIR / f"{technique}_q{number}.json"
        for technique in techniques
        for number in range(1, 6)
    ]

    missing_files = [
        str(path.relative_to(ROOT))
        for path in expected_files
        if not path.exists()
    ]

    invalid_top_k: list[str] = []

    for path in expected_files:
        if not path.exists():
            continue

        payload = json.loads(path.read_text(encoding="utf-8"))
        results = payload.get("results", [])

        if len(results) != 5:
            invalid_top_k.append(
                f"{path.name}: {len(results)} results"
            )

    jsonl_path = RAW_DIR / "retrieval_results.jsonl"
    jsonl_lines = [
        line
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    csv_path = RAW_DIR / "retrieval_results.csv"
    csv_lines = [
        line
        for line in csv_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    details = {
        "expected_query_technique_runs": 15,
        "individual_json_files_found": (
            len(expected_files) - len(missing_files)
        ),
        "jsonl_records": len(jsonl_lines),
        "csv_lines_including_header": len(csv_lines),
        "missing_files": missing_files,
        "invalid_top_k": invalid_top_k,
    }

    passed = (
        not missing_files
        and not invalid_top_k
        and len(jsonl_lines) == 15
        and len(csv_lines) == 76
    )

    return passed, details


def check_metrics() -> tuple[bool, dict[str, Any]]:
    required_files = [
        RAW_DIR / "summary_metrics.csv",
        RAW_DIR / "summary_metrics.json",
        RAW_DIR / "per_query_metrics.csv",
        RAW_DIR / "chunking_statistics.json",
        REPORT_DIR / "METRICS.md",
        REPORT_DIR / "RUN_LOG.txt",
    ]

    missing_files = [
        str(path.relative_to(ROOT))
        for path in required_files
        if not path.exists()
    ]

    summary_path = RAW_DIR / "summary_metrics.json"
    summary_data = json.loads(
        summary_path.read_text(encoding="utf-8")
    )

    if isinstance(summary_data, dict):
        summary_records = summary_data.get("records", [])
        if not summary_records:
            summary_records = summary_data.get("metrics", [])
    elif isinstance(summary_data, list):
        summary_records = summary_data
    else:
        summary_records = []

    metrics_text = (REPORT_DIR / "METRICS.md").read_text(
        encoding="utf-8"
    )

    details = {
        "missing_files": missing_files,
        "summary_record_count": len(summary_records),
        "contains_false_positive_analysis": (
            "High-Scoring Result" in metrics_text
        ),
        "contains_ai_verification": (
            "Generative AI Use and Verification" in metrics_text
        ),
    }

    passed = (
        not missing_files
        and len(summary_records) == 3
        and details["contains_false_positive_analysis"]
        and details["contains_ai_verification"]
    )

    return passed, details


def check_screenshots() -> tuple[bool, dict[str, Any]]:
    required_names = [
        "part1-cookie-header.png",
        "part1-dashboard.png",
        "part1-home.png",
        "part1-invalid-login.png",
        "part1-login-required.png",
        "part1-logout.png",
        "part1-templates-directory.png",
        "part1-timeout-before.png",
        "part1-timeout-expired.png",
        "part2-chunker-warmup.png",
        "part2-corpus-check.png",
        "part2-embedding-check.png",
        "part2-false-positive.png",
        "part2-formal-experiment.png",
        "part2-summary-metrics.png",
    ]

    missing_names = [
        name
        for name in required_names
        if not (SCREENSHOT_DIR / name).exists()
    ]

    details = {
        "required_count": len(required_names),
        "found_count": len(required_names) - len(missing_names),
        "missing_screenshots": missing_names,
    }

    return not missing_names, details


def main() -> None:
    run_check("part1_application", check_application)
    run_check("part2_corpus", check_corpus)
    run_check("corpus_manifest", check_manifest)
    run_check("evaluation_questions", check_questions)
    run_check("questions_precommitted", check_precommit_order)
    run_check("retrieval_outputs", check_retrieval_outputs)
    run_check("metrics_and_analysis", check_metrics)
    run_check("screenshots", check_screenshots)

    passed_count = sum(check["passed"] for check in checks)
    overall_passed = passed_count == len(checks)

    verification = {
        "assignment": "HW3",
        "domain_id": DOMAIN_ID,
        "assigned_domain": "Rental housing listings",
        "verify_seed": VERIFY_SEED,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_passed": overall_passed,
        "checks_passed": passed_count,
        "checks_total": len(checks),
        "checks": checks,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(verification, indent=2),
        encoding="utf-8",
    )

    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"[{status}] {check['name']}")

        if not check["passed"]:
            print(
                json.dumps(
                    check["details"],
                    indent=2,
                    default=str,
                )
            )

    print()
    print(f"Checks passed: {passed_count}/{len(checks)}")
    print(f"Overall passed: {overall_passed}")
    print(f"Saved verification: {OUTPUT_FILE}")

    if not overall_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()