"""Run the HW9 Part 3 threshold sweep against the frozen 40-case dataset."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

import yaml

from hw9_config import STUDENT_NAME
from hw9_semantic_cache import SemanticResponseCache

FROZEN_CASES_SHA256 = (
    "d890964a9274795d0afb18828776e13ed863c3e391024aebb6063750b6aea179"
)
THRESHOLDS = (0.75, 0.80, 0.85, 0.90, 0.95)
EXPECTED_CATEGORY_COUNTS = {
    "exact_duplicate": 10,
    "paraphrase_should_hit": 10,
    "similar_different_answer_should_miss": 10,
    "unrelated_should_miss": 10,
}


def load_frozen_cases(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Load the cases only when their committed pre-sweep hash is unchanged."""

    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if digest != FROZEN_CASES_SHA256:
        raise RuntimeError(
            "cache_cases.yaml changed after labeling; expected SHA-256 "
            f"{FROZEN_CASES_SHA256}, received {digest}"
        )

    document = yaml.safe_load(raw_bytes)
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != 40:
        raise ValueError("cache_cases.yaml must contain exactly 40 cases")

    counts = Counter(case.get("category") for case in cases)
    if counts != EXPECTED_CATEGORY_COUNTS:
        raise ValueError(f"Unexpected category counts: {dict(counts)}")
    if len({case.get("case_id") for case in cases}) != 40:
        raise ValueError("Every cache case must have a unique case_id")
    return cases, digest


def calculate_metrics(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    """Calculate hit, false-hit, false-miss, and latency measurements."""

    if not rows:
        raise ValueError("At least one result row is required")

    hit_count = sum(bool(row["predicted_hit"]) for row in rows)
    expected_miss_count = sum(not bool(row["expected_hit"]) for row in rows)
    false_hit_count = sum(
        bool(row["predicted_hit"]) and not bool(row["expected_hit"])
        for row in rows
    )
    false_miss_count = sum(
        not bool(row["predicted_hit"]) and bool(row["expected_hit"])
        for row in rows
    )
    correct_count = sum(
        bool(row["predicted_hit"]) == bool(row["expected_hit"])
        for row in rows
    )

    return {
        "case_count": len(rows),
        "hit_count": hit_count,
        "hit_rate_pct": 100 * hit_count / len(rows),
        "false_hit_count": false_hit_count,
        "false_hit_rate_pct": (
            100 * false_hit_count / expected_miss_count
            if expected_miss_count
            else 0.0
        ),
        "false_miss_count": false_miss_count,
        "correct_count": correct_count,
        "accuracy_pct": 100 * correct_count / len(rows),
        "mean_latency_ms": mean(float(row["latency_ms"]) for row in rows),
    }


def run_threshold(
    cache: SemanticResponseCache,
    cases: list[dict[str, Any]],
    threshold: float,
) -> tuple[dict[str, float | int], list[dict[str, Any]]]:
    """Evaluate all cases in isolation at one semantic threshold."""

    cache.threshold = threshold
    rows: list[dict[str, Any]] = []

    for case in cases:
        cache.clear_entries()
        cached_answer = (
            f"Controlled cached answer for {case['case_id']}: "
            f"{case['cached_query']}"
        )
        cache.store(str(case["cached_query"]), cached_answer)

        started = perf_counter()
        lookup = cache.find(str(case["incoming_query"]))
        latency_ms = (perf_counter() - started) * 1000
        predicted_hit = lookup.is_hit
        expected_hit = bool(case["expected_hit"])

        rows.append(
            {
                "threshold": threshold,
                "case_id": case["case_id"],
                "category": case["category"],
                "cached_query": case["cached_query"],
                "incoming_query": case["incoming_query"],
                "expected_hit": expected_hit,
                "predicted_hit": predicted_hit,
                "is_false_hit": predicted_hit and not expected_hit,
                "is_false_miss": not predicted_hit and expected_hit,
                "similarity": round(lookup.similarity, 6),
                "latency_ms": round(latency_ms, 3),
            }
        )

    return calculate_metrics(rows), rows


def write_results(
    summaries: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    dataset_sha256: str,
) -> None:
    """Write machine-readable detailed results and the required table."""

    output_directory = Path("reports/hw09/raw")
    output_directory.mkdir(parents=True, exist_ok=True)

    json_path = output_directory / "part3_threshold_sweep.json"
    json_path.write_text(
        json.dumps(
            {
                "student_name": STUDENT_NAME,
                "dataset_sha256": dataset_sha256,
                "thresholds": list(THRESHOLDS),
                "false_hit_rate_definition": (
                    "false hits divided by the 20 labeled should-miss cases"
                ),
                "summaries": summaries,
                "case_results": all_rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    csv_path = output_directory / "part3_threshold_table.csv"
    with csv_path.open("w", newline="") as csv_file:
        fieldnames = [
            "threshold",
            "hit_rate_pct",
            "false_hit_rate_pct",
            "mean_latency_ms",
            "false_hit_count",
            "false_miss_count",
            "accuracy_pct",
            "total_cost",
        ]
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for summary in summaries:
            writer.writerow(
                {
                    **{name: summary[name] for name in fieldnames[:-1]},
                    "total_cost": "PENDING_PART_3_4",
                }
            )


def main() -> None:
    """Run all five thresholds and print the required measurement table."""

    cases, digest = load_frozen_cases(Path("cache_cases.yaml"))
    cache = SemanticResponseCache()
    cache.clear_entries(reset_data_version=True)

    # Warm up both the local encoder and Redis vector search outside timing.
    cache.store("Warm-up rental listing query", "Warm-up answer")
    cache.find("Warm-up rental listing query")
    cache.clear_entries(reset_data_version=True)

    summaries: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    try:
        for threshold in THRESHOLDS:
            metrics, rows = run_threshold(cache, cases, threshold)
            summary = {
                "threshold": threshold,
                **{
                    key: round(value, 3) if isinstance(value, float) else value
                    for key, value in metrics.items()
                },
            }
            summaries.append(summary)
            all_rows.extend(rows)
            print(
                f"Completed threshold {threshold:.2f}: "
                f"hits={summary['hit_count']}/40, "
                f"false_hits={summary['false_hit_count']}, "
                f"false_misses={summary['false_miss_count']}",
                flush=True,
            )
    finally:
        cache.clear_entries(reset_data_version=True)

    write_results(summaries, all_rows, digest)

    print(f"\nStudent: {STUDENT_NAME}")
    print(f"Frozen dataset SHA-256: {digest}")
    print("=== HW9 Part 3.2 Threshold Sweep ===")
    print(
        "Threshold | Hit rate | False-hit rate | Mean latency (ms) | "
        "Total cost"
    )
    for summary in summaries:
        print(
            f"{summary['threshold']:.2f}      | "
            f"{summary['hit_rate_pct']:.1f}%    | "
            f"{summary['false_hit_rate_pct']:.1f}%          | "
            f"{summary['mean_latency_ms']:.3f}             | "
            "PENDING 3.4"
        )
    print("PART3_SWEEP_STATUS: PASS")


if __name__ == "__main__":
    main()
