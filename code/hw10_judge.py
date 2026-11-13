"""Run bounded local DeepEval/GEval validation for DATA 260 HW10."""

import argparse
import csv
import hashlib
import json
import os
import signal
import subprocess
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterator

from deepeval.metrics import GEval
from deepeval.metrics.g_eval import Rubric
from deepeval.models import OllamaModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

from hw10_judge_core import (
    EXPECTED_RUN_COUNT,
    build_case_rows,
    load_eval_cases,
    load_human_labels,
    normalized_to_five_point,
    summarize_judge_runs,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = PROJECT_ROOT / "reports" / "hw10" / "raw"
DEFAULT_CASES = PROJECT_ROOT / "eval_cases.json"
DEFAULT_LABELS = PROJECT_ROOT / "human_labels.csv"
DEFAULT_RAW_RUNS = REPORT_ROOT / "judge_runs.json"
DEFAULT_SUMMARY = REPORT_ROOT / "judge_validation_summary.json"
DEFAULT_CASE_CSV = REPORT_ROOT / "judge_validation_cases.csv"

JUDGE_MODEL = os.getenv("HW10_JUDGE_MODEL", "qwen3:8b")
JUDGE_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://127.0.0.1:11434",
)
JUDGE_TEMPERATURE = 0.0
JUDGE_SEED = 2974
JUDGE_TIMEOUT_SECONDS = int(os.getenv("HW10_JUDGE_TIMEOUT_SECONDS", "180"))
RUBRIC_VERSION = "writer-helpfulness-v1"

WRITER_RUBRIC = [
    Rubric(
        score_range=(1, 1),
        expected_outcome=(
            "Very poor: irrelevant, misleading, seriously incorrect, or unusable."
        ),
    ),
    Rubric(
        score_range=(2, 2),
        expected_outcome=(
            "Poor: limited usefulness with major omissions, confusion, or "
            "unsupported claims."
        ),
    ),
    Rubric(
        score_range=(3, 3),
        expected_outcome=(
            "Acceptable: relevant and partly useful, but generic, incomplete, "
            "or insufficiently actionable."
        ),
    ),
    Rubric(
        score_range=(4, 4),
        expected_outcome=(
            "Good: accurate, clear, and useful with only minor omissions or "
            "wording issues."
        ),
    ),
    Rubric(
        score_range=(5, 5),
        expected_outcome=(
            "Excellent: directly relevant, accurate, complete, actionable, "
            "clear, concise, and free of unsupported claims."
        ),
    ),
]

WRITER_STEPS = [
    "Check whether the draft directly answers the rental-housing question.",
    "Check factual plausibility and penalize invented laws, prices, guarantees, "
    "or unsupported specifics.",
    "Assess whether the answer covers the important points and gives practical, "
    "actionable guidance.",
    "Assess clarity, organization, and conciseness.",
    "Apply the supplied 1-5 rubric and give a brief reason for that score.",
]


class JudgeTimeoutError(TimeoutError):
    """Raised when a single bounded local judge call exceeds its deadline."""


def utc_now() -> str:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC).isoformat()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of one frozen input file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    """Return the full current Git commit hash."""

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@contextmanager
def hard_timeout(seconds: int) -> Iterator[None]:
    """Bound one synchronous judge call with the Unix interval timer."""

    if seconds < 1:
        raise ValueError("judge timeout must be at least one second")
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def handle_timeout(_signum: int, _frame: object) -> None:
        raise JudgeTimeoutError(f"local judge exceeded the {seconds}-second deadline")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def build_model() -> OllamaModel:
    """Build the documented local DeepEval Ollama model adapter."""

    return OllamaModel(
        model=JUDGE_MODEL,
        base_url=JUDGE_BASE_URL,
        temperature=JUDGE_TEMPERATURE,
        generation_kwargs={
            "seed": JUDGE_SEED,
            "num_predict": 512,
        },
        timeout=JUDGE_TIMEOUT_SECONDS,
    )


def writer_metric(model: OllamaModel) -> GEval:
    """Create one state-isolated Writer Helpfulness G-Eval metric."""

    return GEval(
        name="Writer Helpfulness",
        criteria=(
            "Evaluate whether the Writer draft is accurate, directly relevant "
            "to the rental-housing question, practically useful, complete enough, "
            "clear, concise, and free of unsupported claims."
        ),
        evaluation_steps=WRITER_STEPS,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        rubric=WRITER_RUBRIC,
        model=model,
        threshold=0,
        async_mode=False,
        strict_mode=False,
    )


def score_writer_case(
    model: OllamaModel,
    question: str,
    draft: str,
) -> dict[str, Any]:
    """Score one Writer draft on 1-5 and retain DeepEval's reason."""

    metric = writer_metric(model)
    test_case = LLMTestCase(input=question, actual_output=draft)
    started = time.perf_counter()
    with hard_timeout(JUDGE_TIMEOUT_SECONDS):
        normalized_score = float(metric.measure(test_case, _show_indicator=False))
    latency_ms = (time.perf_counter() - started) * 1000
    raw_score = normalized_to_five_point(normalized_score)
    return {
        "judge_score": raw_score,
        "deepeval_normalized_score": normalized_score,
        "reason": metric.reason,
        "latency_ms": round(latency_ms, 2),
    }


def write_json_atomic(path: Path, payload: object) -> None:
    """Write one checkpoint atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def stable_metadata(cases_path: Path, labels_path: Path) -> dict[str, Any]:
    """Build settings that must remain identical across all three runs."""

    return {
        "schema_version": 1,
        "rubric_version": RUBRIC_VERSION,
        "judge_framework": "DeepEval GEval",
        "deepeval_version": version("deepeval"),
        "judge_provider": "local Ollama",
        "judge_model": JUDGE_MODEL,
        "judge_base_url": JUDGE_BASE_URL,
        "temperature": JUDGE_TEMPERATURE,
        "seed": JUDGE_SEED,
        "timeout_seconds_per_case": JUDGE_TIMEOUT_SECONDS,
        "score_scale": {"minimum": 1, "maximum": 5},
        "eval_cases_sha256": file_sha256(cases_path),
        "human_labels_sha256": file_sha256(labels_path),
        "frozen_inputs_commit": subprocess.run(
            [
                "git",
                "log",
                "-1",
                "--format=%H",
                "--",
                str(cases_path.resolve()),
                str(labels_path.resolve()),
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "evaluation_code_commit": git_head(),
    }


def load_or_create_checkpoint(
    path: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Load a compatible checkpoint or initialize a new validation run."""

    if not path.exists():
        return {
            "metadata": metadata,
            "started_at": utc_now(),
            "completed_at": None,
            "runs": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("metadata") != metadata:
        raise ValueError(
            "existing judge checkpoint uses different frozen inputs or settings"
        )
    return payload


def run_entry(checkpoint: dict[str, Any], run_number: int) -> dict[str, Any]:
    """Return or create one numbered repeatability run."""

    runs = checkpoint.setdefault("runs", [])
    for item in runs:
        if item.get("run") == run_number:
            return item
    item = {
        "run": run_number,
        "started_at": utc_now(),
        "completed_at": None,
        "cases": [],
    }
    runs.append(item)
    return item


def completed_result(
    run: dict[str, Any],
    case_id: str,
) -> dict[str, Any] | None:
    """Return a successful case result; discard an old failed attempt."""

    cases = run.setdefault("cases", [])
    for item in list(cases):
        if item.get("case_id") != case_id:
            continue
        if item.get("error") is None and isinstance(item.get("judge_score"), int):
            return item
        cases.remove(item)
    return None


def complete_validation(
    checkpoint: dict[str, Any],
    cases: list[dict[str, Any]],
    labels: dict[str, int],
    raw_path: Path,
    summary_path: Path,
    case_csv_path: Path,
) -> dict[str, Any]:
    """Calculate final statistics and write recomputable JSON and CSV outputs."""

    case_ids = [str(item["case_id"]) for item in cases]
    score_by_run = []
    for run_number in range(1, EXPECTED_RUN_COUNT + 1):
        run = next(item for item in checkpoint["runs"] if item["run"] == run_number)
        indexed = {
            str(item["case_id"]): int(item["judge_score"])
            for item in run["cases"]
            if item.get("error") is None
        }
        score_by_run.append(indexed)

    summary = summarize_judge_runs(case_ids, labels, score_by_run)
    summary["metadata"] = checkpoint["metadata"]
    summary["completed_at"] = utc_now()
    rows = build_case_rows(case_ids, labels, score_by_run)

    checkpoint["completed_at"] = summary["completed_at"]
    write_json_atomic(raw_path, checkpoint)
    write_json_atomic(summary_path, summary)
    case_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with case_csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return summary


def run_full_validation(
    cases_path: Path,
    labels_path: Path,
    raw_path: Path,
    summary_path: Path,
    case_csv_path: Path,
) -> dict[str, Any]:
    """Run three bounded judge passes with per-case resumable checkpoints."""

    cases = load_eval_cases(cases_path)
    case_ids = [str(item["case_id"]) for item in cases]
    labels = load_human_labels(labels_path, case_ids)
    metadata = stable_metadata(cases_path, labels_path)
    checkpoint = load_or_create_checkpoint(raw_path, metadata)
    model = build_model()

    for run_number in range(1, EXPECTED_RUN_COUNT + 1):
        run = run_entry(checkpoint, run_number)
        for index, case in enumerate(cases, start=1):
            case_id = str(case["case_id"])
            if completed_result(run, case_id) is not None:
                print(
                    f"[HW10 JUDGE] run={run_number}/3 case={index}/20 "
                    f"{case_id} already complete",
                    flush=True,
                )
                continue
            print(
                f"[HW10 JUDGE] run={run_number}/3 case={index}/20 scoring {case_id}",
                flush=True,
            )
            try:
                result = score_writer_case(
                    model,
                    str(case["question"]),
                    str(case["draft"]),
                )
                entry = {
                    "case_id": case_id,
                    "human_score": labels[case_id],
                    **result,
                    "error": None,
                    "evaluated_at": utc_now(),
                }
                run["cases"].append(entry)
                print(
                    f"[HW10 JUDGE] {case_id} score={entry['judge_score']} "
                    f"latency_ms={entry['latency_ms']}",
                    flush=True,
                )
            except Exception as exc:
                run["cases"].append(
                    {
                        "case_id": case_id,
                        "human_score": labels[case_id],
                        "judge_score": None,
                        "reason": None,
                        "error": f"{type(exc).__name__}: {exc}",
                        "evaluated_at": utc_now(),
                    }
                )
                write_json_atomic(raw_path, checkpoint)
                raise
            write_json_atomic(raw_path, checkpoint)
        run["completed_at"] = utc_now()
        write_json_atomic(raw_path, checkpoint)

    return complete_validation(
        checkpoint,
        cases,
        labels,
        raw_path,
        summary_path,
        case_csv_path,
    )


def parse_args() -> argparse.Namespace:
    """Parse paths and the optional non-persistent smoke case."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--raw-runs", type=Path, default=DEFAULT_RAW_RUNS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--case-csv", type=Path, default=DEFAULT_CASE_CSV)
    parser.add_argument(
        "--smoke-case",
        help="Score one case ID without writing validation outputs.",
    )
    return parser.parse_args()


def main() -> None:
    """Run a smoke case or the complete three-run validation."""

    args = parse_args()
    cases = load_eval_cases(args.cases)
    if args.smoke_case:
        case = next(
            (item for item in cases if item["case_id"] == args.smoke_case),
            None,
        )
        if case is None:
            raise ValueError(f"unknown smoke case: {args.smoke_case}")
        result = score_writer_case(
            build_model(),
            str(case["question"]),
            str(case["draft"]),
        )
        print(json.dumps({"case_id": args.smoke_case, **result}, indent=2))
        return

    summary = run_full_validation(
        args.cases,
        args.labels,
        args.raw_runs,
        args.summary,
        args.case_csv,
    )
    print("[HW10 JUDGE] validation complete", flush=True)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
