import csv
import json
import math
import random
import statistics
import time
from datetime import datetime
from pathlib import Path

from reliable_domain_tools import listing_details
from retry_policy import SeededFailureInjector


STUDENT_NAME = "Xuanhua Li"
SID4 = 2974
VERIFY_SEED = 262974

CALLS_PER_RATE = 50
FAILURE_RATES = [0.0, 0.2, 0.5]
MAX_ATTEMPTS = 3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = PROJECT_ROOT / "reports" / "hw05" / "raw"


def nearest_rank_p99(values: list[float]) -> float:
    ordered = sorted(values)
    index = math.ceil(0.99 * len(ordered)) - 1
    return ordered[index]


def expected_sequence(
    failure_rate: float,
) -> list[tuple[bool, int]]:
    generator = random.Random(VERIFY_SEED)
    sequence: list[tuple[bool, int]] = []

    for _ in range(CALLS_PER_RATE):
        success = False
        attempts = 0

        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempts = attempt

            if generator.random() >= failure_rate:
                success = True
                break

        sequence.append((success, attempts))

    return sequence


def run_rate(
    failure_rate: float,
) -> list[dict]:
    injector = SeededFailureInjector(
        failure_rate=failure_rate,
        seed=VERIFY_SEED,
    )

    records: list[dict] = []

    for call_number in range(1, CALLS_PER_RATE + 1):
        retry_trace: list[dict] = []
        started = time.perf_counter()

        result = listing_details(
            4,
            failure_injector=injector,
            retry_trace=retry_trace,
        )

        latency_ms = (
            time.perf_counter() - started
        ) * 1000.0

        records.append(
            {
                "failure_rate": failure_rate,
                "call_number": call_number,
                "success": result["ok"],
                "latency_ms": round(latency_ms, 3),
                "attempts": len(retry_trace),
                "injected_failures": sum(
                    item["status"] == "failure"
                    for item in retry_trace
                ),
                "error": result["error"],
            }
        )

    actual_sequence = [
        (record["success"], record["attempts"])
        for record in records
    ]

    assert actual_sequence == expected_sequence(
        failure_rate
    )

    return records


def calculate_metrics(
    records: list[dict],
    failure_rate: float,
) -> dict:
    selected = [
        record
        for record in records
        if record["failure_rate"] == failure_rate
    ]

    latencies = [
        record["latency_ms"]
        for record in selected
    ]

    successful_calls = sum(
        record["success"]
        for record in selected
    )

    return {
        "failure_rate": failure_rate,
        "calls": len(selected),
        "successful_calls": successful_calls,
        "success_rate_percent": round(
            100.0 * successful_calls / len(selected),
            2,
        ),
        "mean_latency_ms": round(
            statistics.fmean(latencies),
            3,
        ),
        "p99_latency_ms": round(
            nearest_rank_p99(latencies),
            3,
        ),
    }


def write_outputs(
    records: list[dict],
    metrics: list[dict],
) -> None:
    RAW_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        RAW_DIRECTORY
        / "failure_injection_calls.json"
    )
    csv_path = (
        RAW_DIRECTORY
        / "failure_injection_calls.csv"
    )
    metrics_path = (
        RAW_DIRECTORY
        / "failure_injection_metrics.json"
    )

    payload = {
        "student": STUDENT_NAME,
        "sid4": SID4,
        "verify_seed": VERIFY_SEED,
        "run_at": datetime.now().astimezone().isoformat(),
        "retry_policy": {
            "max_attempts": 3,
            "timeout_seconds": 1.0,
            "base_delay_seconds": 0.01,
            "max_delay_seconds": 0.04,
        },
        "records": records,
    }

    json_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    fieldnames = [
        "failure_rate",
        "call_number",
        "success",
        "latency_ms",
        "attempts",
        "injected_failures",
        "error",
    ]

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(records)

    metrics_path.write_text(
        json.dumps(
            {
                "verify_seed": VERIFY_SEED,
                "metrics": metrics,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    print(f"Student: {STUDENT_NAME} | SID4: {SID4}")
    print(f"VERIFY_SEED: {VERIFY_SEED}")
    print(
        "Retry policy: 3 attempts, 1.0s timeout, "
        "10ms/20ms bounded backoff"
    )

    all_records: list[dict] = []

    for failure_rate in FAILURE_RATES:
        all_records.extend(
            run_rate(failure_rate)
        )

    metrics = [
        calculate_metrics(all_records, failure_rate)
        for failure_rate in FAILURE_RATES
    ]

    write_outputs(all_records, metrics)

    print(
        "\nRATE   CALLS   SUCCESS RATE   "
        "MEAN LATENCY   P99 LATENCY"
    )
    print("-" * 64)

    for row in metrics:
        print(
            f"{row['failure_rate'] * 100:>3.0f}%"
            f"{row['calls']:>8}"
            f"{row['success_rate_percent']:>14.2f}%"
            f"{row['mean_latency_ms']:>15.3f} ms"
            f"{row['p99_latency_ms']:>14.3f} ms"
        )

    print(f"\nRAW CALL RECORDS: {len(all_records)}")
    print("DETERMINISM CHECK: PASS")
    print("FAILURE-INJECTION EXPERIMENT: PASS")


if __name__ == "__main__":
    main()