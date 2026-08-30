import argparse
import contextlib
import io
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any

from agents_demo import run_pipeline


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    REPOSITORY_ROOT
    / "reports"
    / "hw01"
    / "cases"
    / "nondeterminism_input.json"
)

OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "reports"
    / "hw01"
    / "raw"
    / "nondeterminism_runs.json"
)


def percentile(
    values: list[float],
    percent: float
) -> float:
    """Calculate a percentile using linear interpolation."""
    if not values:
        raise ValueError("Cannot calculate a percentile without values.")

    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100

    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return round(ordered[lower_index], 2)

    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    fraction = position - lower_index

    result = lower_value + (
        upper_value - lower_value
    ) * fraction

    return round(result, 2)


def summarize_runs(
    records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Calculate tag and latency metrics for one temperature."""
    distinct_tag_sets = {
        tuple(
            sorted(
                tag.strip().lower()
                for tag in record["tags"]
            )
        )
        for record in records
    }

    tag_counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}

    for record in records:
        tags_in_this_run = {
            tag.strip().lower()
            for tag in record["tags"]
        }

        for normalized_tag in tags_in_this_run:
            tag_counts[normalized_tag] += 1

        for tag in record["tags"]:
            display_names.setdefault(
                tag.strip().lower(),
                tag.strip()
            )

    total_runs = len(records)

    tags_in_all_runs = sorted(
        display_names[tag]
        for tag, count in tag_counts.items()
        if count == total_runs
    )

    tags_in_exactly_one_run = sorted(
        display_names[tag]
        for tag, count in tag_counts.items()
        if count == 1
    )

    latencies = [
        float(record["latencyMs"])
        for record in records
    ]

    return {
        "runCount": total_runs,
        "distinctTagSets": len(distinct_tag_sets),
        "tagsInAllRuns": tags_in_all_runs,
        "tagsInExactlyOneRun": tags_in_exactly_one_run,
        "latencyMs": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99)
        }
    }


def run_one_experiment(
    title: str,
    content: str,
    email: str,
    model_name: str,
    temperature: float
) -> tuple[dict[str, Any], int]:
    """
    Run one successful pipeline.

    A failed JSON response is retried up to three times and does not
    count as one of the required 20 successful runs.
    """
    maximum_attempts = 3

    for attempt in range(1, maximum_attempts + 1):
        try:
            hidden_console_output = io.StringIO()

            with contextlib.redirect_stdout(
                hidden_console_output
            ):
                result = run_pipeline(
                    title=title,
                    content=content,
                    email=email,
                    model_name=model_name,
                    temperature=temperature,
                    strict=True
                )

            return result, attempt

        except Exception as error:
            print(
                f"Attempt {attempt} failed: {error}"
            )

            if attempt == maximum_attempts:
                raise

            print("Retrying the same run...")

    raise RuntimeError("Experiment failed unexpectedly.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the HW1 non-determinism experiment."
    )

    parser.add_argument(
        "--email",
        required=True,
        help="Student email for the publish package."
    )
    parser.add_argument(
        "--model",
        default="qwen3:8b",
        help="Local Ollama model."
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=20,
        help="Successful runs per temperature."
    )

    args = parser.parse_args()

    with INPUT_PATH.open(
        "r",
        encoding="utf-8"
    ) as input_file:
        fixed_input = json.load(input_file)

    title = fixed_input["title"]
    content = fixed_input["content"]

    all_records: list[dict[str, Any]] = []

    for temperature in (0.0, 0.7):
        print(
            f"\nStarting temperature {temperature}"
        )

        for run_number in range(1, args.runs + 1):
            result, attempts = run_one_experiment(
                title=title,
                content=content,
                email=args.email,
                model_name=args.model,
                temperature=temperature
            )

            final_data = result["agents"]["final"]

            record = {
                "temperature": temperature,
                "runNumber": run_number,
                "attempts": attempts,
                "tags": final_data["tags"],
                "summary": final_data["summary"],
                "latencyMs": result["latencyMs"],
                "timestamp": result["submissionDate"]
            }

            all_records.append(record)

            print(
                f"Temperature {temperature} | "
                f"Run {run_number:02d}/{args.runs} | "
                f"Latency {record['latencyMs']} ms | "
                f"Tags: {record['tags']}"
            )

    metrics: dict[str, Any] = {}

    for temperature in (0.0, 0.7):
        temperature_records = [
            record
            for record in all_records
            if record["temperature"] == temperature
        ]

        metrics[str(temperature)] = summarize_runs(
            temperature_records
        )

    output = {
        "generatedAt": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime()
        ),
        "model": args.model,
        "runsPerTemperature": args.runs,
        "fixedInput": fixed_input,
        "runs": all_records,
        "metrics": metrics
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("\n--- Experiment Metrics ---")
    print(
        json.dumps(
            metrics,
            indent=2,
            ensure_ascii=False
        )
    )

    print(
        f"\nSaved raw results to:\n{OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()