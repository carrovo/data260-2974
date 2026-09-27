import csv
import getpass
import json
import math
import os
import time
from pathlib import Path

import httpx


BASE_URL = os.getenv("HW4_BASE_URL", "http://localhost:8274")
DEFAULT_EMAIL = "carol.hw4@example.com"

# HW4 requires 30 requests for each endpoint and page size.
MODES = ["naive", "fixed"]
PAGE_SIZES = [10, 50, 200]
REPETITIONS = 30

OUTPUT_DIR = Path("reports/hw04/raw")
CSV_PATH = OUTPUT_DIR / "n_plus_one_requests.csv"
JSON_PATH = OUTPUT_DIR / "n_plus_one_summary.json"


def percentile(values: list[float], percentage: float) -> float:
    """Calculate a percentile with linear interpolation."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100
    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return ordered[lower_index]

    weight = position - lower_index

    return (
        ordered[lower_index]
        + (ordered[upper_index] - ordered[lower_index]) * weight
    )


def summarize(rows: list[dict]) -> list[dict]:
    """Create p50, p95, and p99 latency summaries."""
    summary = []

    for mode in MODES:
        for page_size in PAGE_SIZES:
            matching_rows = [
                row
                for row in rows
                if row["mode"] == mode
                and row["page_size"] == page_size
            ]

            latencies = [
                float(row["duration_ms"])
                for row in matching_rows
                if row["status_code"] == 200
            ]

            summary.append(
                {
                    "mode": mode,
                    "page_size": page_size,
                    "requests": len(matching_rows),
                    "successful_requests": len(latencies),
                    "p50_ms": round(percentile(latencies, 50), 3),
                    "p95_ms": round(percentile(latencies, 95), 3),
                    "p99_ms": round(percentile(latencies, 99), 3),
                }
            )

    return summary


def main() -> None:
    email = os.getenv("HW4_TEST_EMAIL", DEFAULT_EMAIL)
    password = os.getenv("HW4_TEST_PASSWORD")

    # Prompt privately instead of storing the password in the script.
    if not password:
        password = getpass.getpass("HW4 test password: ")

    rows = []

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        base_url=BASE_URL,
        timeout=120.0,
    ) as client:
        # Create the authenticated HTTP session.
        login_response = client.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": password,
            },
        )
        login_response.raise_for_status()

        print("Login successful.")
        print(f"Base URL: {BASE_URL}")
        print(f"Requests per configuration: {REPETITIONS}")
        print()

        for mode in MODES:
            for page_size in PAGE_SIZES:
                endpoint = f"/api/listings/{mode}"
                print(
                    f"Running {mode} with page_size={page_size}..."
                )

                for request_number in range(1, REPETITIONS + 1):
                    start_time = time.perf_counter()

                    response = client.get(
                        endpoint,
                        params={"page_size": page_size},
                    )

                    duration_ms = (
                        time.perf_counter() - start_time
                    ) * 1000

                    response.raise_for_status()

                    payload = response.json()

                    # Confirm each request returned the expected page size.
                    if len(payload) != page_size:
                        raise RuntimeError(
                            f"Expected {page_size} records but received "
                            f"{len(payload)}."
                        )

                    rows.append(
                        {
                            "mode": mode,
                            "page_size": page_size,
                            "request_number": request_number,
                            "status_code": response.status_code,
                            "duration_ms": round(duration_ms, 3),
                        }
                    )

        summary = summarize(rows)

    # Save every raw request for reproducibility.
    with CSV_PATH.open("w", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[
                "mode",
                "page_size",
                "request_number",
                "status_code",
                "duration_ms",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    # Save the aggregate metrics and experiment configuration.
    result = {
        "base_url": BASE_URL,
        "repetitions": REPETITIONS,
        "page_sizes": PAGE_SIZES,
        "modes": MODES,
        "total_requests": len(rows),
        "summary": summary,
    }

    JSON_PATH.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Total requests: {len(rows)}")
    print(f"Raw CSV: {CSV_PATH}")
    print(f"Summary JSON: {JSON_PATH}")
    print()
    print("Summary:")

    for item in summary:
        print(
            f'{item["mode"]:>5} '
            f'page_size={item["page_size"]:>3} '
            f'p50={item["p50_ms"]:>8.3f} ms '
            f'p95={item["p95_ms"]:>8.3f} ms '
            f'p99={item["p99_ms"]:>8.3f} ms'
        )


if __name__ == "__main__":
    main()