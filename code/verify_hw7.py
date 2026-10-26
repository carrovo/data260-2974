import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = PROJECT_ROOT / "reports" / "hw07"
RAW_ROOT = REPORT_ROOT / "raw"
DEFAULT_OUTPUT = REPORT_ROOT / "verification.json"
FINAL_REPORT = REPORT_ROOT / "Li_HW7.pdf"
SID4 = 2974
SEED = 2974
VERIFY_SEED = 262974
MODEL = "qwen3:8b"
EXPECTED_SCREENSHOTS = {
    "P1_create.png",
    "P1_delete.png",
    "P1_login.png",
    "P1_me_invalid.png",
    "P1_me_missing.png",
    "P1_read.png",
    "P2_error_recovery.png",
    "P2_reliability_summary.png",
    "P2_task_A.png",
    "P2_task_B.png",
    "P2_task_C.png",
    "P3_comparison_runs.png",
    "P3_controlled_reflection.png",
    "P3_reflexion_A.png",
    "P3_reflexion_B.png",
    "P3_reflexion_C.png",
    "part4_membership_success.png",
    "part4_pay_per_use_success.png",
    "part4_preflight_ready_tools.png",
    "part5_security_matrix.png",
    "part6_file_tools_safety.png",
}
GOOGLE_KEY_PATTERN = re.compile(rb"AIza[0-9A-Za-z_-]{35}")
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
    ".zsh",
}


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _load_json(relative_path: str) -> dict[str, Any]:
    value = json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative_path} must contain one JSON object")
    return value


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _tracked(relative_path: str) -> bool:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative_path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _secret_pattern_count() -> int:
    count = 0
    for root in (PROJECT_ROOT / "code", REPORT_ROOT):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            count += len(GOOGLE_KEY_PATTERN.findall(path.read_bytes()))
    return count


def _part1_checks() -> list[dict[str, Any]]:
    required = [
        "code/auth_service.py",
        "code/jwt_service.py",
        "code/migrate_hw7_users.py",
        "code/test_hw7_auth_rbac.py",
        "code/test_hw7_user_migration.py",
    ]
    run_log = (REPORT_ROOT / "RUN_LOG.txt").read_text(encoding="utf-8")
    return [
        _check(
            "part1_required_sources",
            all((PROJECT_ROOT / path).is_file() for path in required),
            "JWT, RBAC, migration, and offline-test sources are present",
        ),
        _check(
            "part1_recorded_tests",
            "24/24 PASS" in run_log and "5/5 PASS" in run_log,
            "RUN_LOG records 24/24 RBAC and 5/5 migration checks",
        ),
    ]


def _part2_checks() -> list[dict[str, Any]]:
    summary = _load_json("reports/hw07/raw/part2_summary.json")
    rates = summary.get("call_level_well_formed_rate", {})
    completion = summary.get("run_level_completion_rate", {})
    failures = summary.get("failure_counts", {})
    passed = (
        summary.get("status") == "completed_real_model_run"
        and summary.get("sid4") == SID4
        and summary.get("actual_run_count") == 21
        and rates.get("all_attempts", {}).get("attempts") == 49
        and rates.get("all_attempts", {}).get("well_formed_calls") == 49
        and completion.get("completed_runs") == 21
        and completion.get("total_runs") == 21
        and failures
        and all(value == 0 for value in failures.values())
    )
    return [
        _check(
            "part2_real_reliability",
            passed,
            "21/21 runs and 49/49 calls completed with zero recorded failures",
        )
    ]


def _part3_checks() -> list[dict[str, Any]]:
    comparison = _load_json("reports/hw07/raw/part3_comparison.json")
    original = comparison.get("original_loop", {})
    reflexion = comparison.get("reflexion_loop", {})
    passed = comparison.get("status") == "completed_real_model_comparison"
    for result in (original, reflexion):
        passed = passed and (
            result.get("run_count") == 21
            and result.get("task_success_count") == 21
            and result.get("unsupported_claims") == 0
            and result.get("verifier_false_rejections") == 0
        )
    controlled = _load_json(
        "reports/hw07/raw/part3_controlled_offline_reflection_case.json"
    )
    controlled_result = controlled.get("result", {})
    controlled_passed = (
        controlled.get("case_type") == "controlled_offline_reflection_case"
        and controlled.get("real_model_result") is False
        and controlled_result.get("retry_count") == 1
        and controlled_result.get("stop_reason") == "success"
        and controlled_result.get("task_success") is True
    )
    return [
        _check(
            "part3_real_comparison",
            passed,
            "original and Reflexion loops each completed 21/21 verified runs",
        ),
        _check(
            "part3_controlled_reflection",
            controlled_passed,
            "controlled verifier failure recovered with one bounded retry",
        ),
    ]


def _part4_checks() -> list[dict[str, Any]]:
    acceptance = _load_json("reports/hw07/raw/part4_agent_acceptance.json")
    expected = {
        "membership_wins": "Buy Monthly Membership",
        "pay_per_use_wins": "Pay Per Ride/Minute",
    }
    runs = acceptance.get("runs", [])
    passed = acceptance.get("status") == "completed_real_part4_agent_run"
    passed = passed and {run.get("scenario") for run in runs} == set(expected)
    for run in runs:
        analysis = run.get("analysis", {})
        timeline = analysis.get("timeline", [])
        tools = [event.get("tool") for event in timeline]
        metrics = analysis.get("metrics", {})
        passed = passed and (
            analysis.get("stop_reason") == "success"
            and analysis.get("errors") == []
            and analysis.get("verification", {}).get("passed") is True
            and analysis.get("result", {}).get("recommendation")
            == expected.get(run.get("scenario"))
            and tools[:3] == ["csv_sql", "csv_sql", "csv_sql"]
            and set(tools) == {"csv_sql", "policy_retriever", "calculator"}
            and metrics.get("tool_calls", 13) <= 12
            and metrics.get("ollama_request_timeout_seconds") == 90.0
            and metrics.get("wall_budget_seconds") == 300.0
        )
    return [
        _check(
            "part4_real_acceptance",
            passed,
            "both opposite-winner scenarios passed independent verification",
        )
    ]


def _part5_checks() -> list[dict[str, Any]]:
    evidence = _load_json("reports/hw07/raw/part5_attack_results.json")
    attacks = evidence.get("attacks", [])
    controls = evidence.get("controls", {})
    passed = (
        evidence.get("status") == "completed_deterministic_security_evaluation"
        and evidence.get("all_after_combined_defenses_pass") is True
        and len(attacks) == 3
        and all(
            item.get("after_prompt_and_tool_defense", "").startswith("PASS")
            for item in attacks
        )
        and controls
        and all(controls.values())
    )
    return [
        _check(
            "part5_security_matrix",
            passed,
            "three hostile probes passed after combined prompt and tool defenses",
        )
    ]


def _part6_checks() -> list[dict[str, Any]]:
    evidence = _load_json("reports/hw07/raw/part6_safety_results.json")
    safety = evidence.get("safety_test", {})
    integration = evidence.get("integration", {})
    passed = (
        evidence.get("status") == "completed_part6_file_tool_evaluation"
        and evidence.get("all_passed") is True
        and integration.get("required_sequence")
        == ["glob_files", "search_in_files", "read_file"]
        and integration.get("passed") is True
        and safety.get("passed_count") == 10
        and safety.get("total_count") == 10
        and len(safety.get("allowed", [])) == 5
        and len(safety.get("blocked", [])) == 5
    )
    return [
        _check(
            "part6_file_tools_and_safety",
            passed,
            "glob-search-read integration and 10/10 command cases passed",
        )
    ]


def _artifact_checks() -> list[dict[str, Any]]:
    screenshots = REPORT_ROOT / "screenshots"
    actual = {path.name for path in screenshots.glob("*.png")}
    required_docs = [
        "reports/hw07/AI_USE.md",
        "reports/hw07/METRICS.md",
        "reports/hw07/RUN_LOG.txt",
        "reports/hw07/PART2_RUN.md",
        "reports/hw07/PART3_RUN.md",
        "reports/hw07/PART4_RUN.md",
        "reports/hw07/PART5_RUN.md",
        "reports/hw07/PART6_RUN.md",
    ]
    raw_files = [
        "reports/hw07/raw/part2_reliability.json",
        "reports/hw07/raw/part3_comparison.json",
        "reports/hw07/raw/part4_agent_acceptance.json",
        "reports/hw07/raw/part5_attack_results.json",
        "reports/hw07/raw/part6_safety_results.json",
    ]
    ai_use = (REPORT_ROOT / "AI_USE.md").read_text(encoding="utf-8")
    return [
        _check(
            "required_screenshots",
            EXPECTED_SCREENSHOTS <= actual,
            f"{len(EXPECTED_SCREENSHOTS)} required screenshots are present",
        ),
        _check(
            "required_documentation",
            all((PROJECT_ROOT / path).is_file() for path in required_docs),
            "AI use, metrics, run log, and Part 2-6 run notes are present",
        ),
        _check(
            "required_evidence_tracked",
            all(_tracked(path) for path in [*required_docs, *raw_files])
            and all(
                _tracked(f"reports/hw07/screenshots/{name}")
                for name in EXPECTED_SCREENSHOTS
            ),
            "required documentation, raw evidence, and screenshots are tracked",
        ),
        _check(
            "ai_use_four_questions",
            all(f"## {number}." in ai_use for number in range(1, 5)),
            "AI_USE.md answers all four required questions",
        ),
        _check(
            "secret_pattern_scan",
            _secret_pattern_count() == 0,
            "count-only Google API key pattern scan found zero matches",
        ),
    ]


def build_verification() -> dict[str, Any]:
    """Build the bounded HW7 verification result from committed evidence."""

    part2 = _load_json("reports/hw07/raw/part2_summary.json")
    part4 = _load_json("reports/hw07/raw/part4_agent_acceptance.json")
    checks = [
        *_part1_checks(),
        *_part2_checks(),
        *_part3_checks(),
        *_part4_checks(),
        *_part5_checks(),
        *_part6_checks(),
        *_artifact_checks(),
    ]
    return {
        "homework": 7,
        "student": "Xuanhua Li",
        "sid4": SID4,
        "commit_hash": _git("rev-parse", "HEAD"),
        "branch": _git("branch", "--show-current"),
        "model": MODEL,
        "model_config": {
            "parts_2_and_3": part2.get("model_config"),
            "part_4": part4.get("model_config"),
        },
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": (
            "committed Parts 1-6 source, evidence, metrics, documentation, "
            "and screenshots; final PDF and tag are checked separately"
        ),
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }


def _final_checks() -> list[dict[str, Any]]:
    existing = _load_json("reports/hw07/verification.json")
    head = _git("rev-parse", "HEAD")
    try:
        tagged = _git("rev-parse", "hw7^{}")
    except subprocess.CalledProcessError:
        tagged = ""
    verified_commit = str(existing.get("commit_hash", ""))
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", verified_commit, head],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
    ).returncode == 0
    return [
        _check(
            "verification_json_passed",
            existing.get("passed") is True,
            "committed verification.json reports PASS",
        ),
        _check(
            "verified_commit_is_ancestor",
            bool(verified_commit) and ancestor,
            "verified source commit is included in the final submission history",
        ),
        _check(
            "final_report_pdf",
            FINAL_REPORT.is_file() and FINAL_REPORT.stat().st_size > 0,
            "reports/hw07/Li_HW7.pdf is present and nonempty",
        ),
        _check(
            "hw7_tag_points_to_head",
            bool(tagged) and tagged == head,
            "annotated hw7 tag resolves to the final HEAD",
        ),
        _check(
            "final_worktree_clean",
            _git("status", "--porcelain") == "",
            "final tagged worktree is clean",
        ),
    ]


def _print_result(result: dict[str, Any]) -> None:
    print("HW7 FINAL VERIFICATION")
    print(f"COMMIT: {result['commit_hash']}")
    for check in result["checks"]:
        label = "PASS" if check["passed"] else "FAIL"
        print(f"{label} | {check['name']} | {check['detail']}")
    print(f"FINAL_STATUS: {'PASS' if result['passed'] else 'FAIL'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify HW7 submission evidence")
    parser.add_argument("--write", action="store_true", help="write verification.json")
    parser.add_argument(
        "--final-check",
        action="store_true",
        help="also require the final PDF, hw7 tag, and clean worktree",
    )
    args = parser.parse_args()
    if args.write and args.final_check:
        parser.error("--write and --final-check must be run as separate steps")

    result = build_verification()
    if args.final_check:
        result["checks"].extend(_final_checks())
        result["passed"] = all(check["passed"] for check in result["checks"])
    if args.write:
        DEFAULT_OUTPUT.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    _print_result(result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
