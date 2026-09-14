import argparse
import csv
import io
import json
import sys
import time
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from src.hw2_graph.state import create_initial_state
from src.hw2_graph.workflow import build_graph
from src.model_client import ModelClient


DEFAULT_RAW_DIR = (
    REPOSITORY_ROOT
    / "reports"
    / "hw02"
    / "raw"
)


def load_case(path: Path) -> dict[str, Any]:
    case = json.loads(
        path.read_text(encoding="utf-8")
    )

    required_fields = {
        "title",
        "content",
        "email",
        "strict",
    }

    missing_fields = required_fields - case.keys()

    if missing_fields:
        raise ValueError(
            "Input case is missing fields: "
            + ", ".join(sorted(missing_fields))
        )

    return case


def classify_outcome(
    final_state: dict[str, Any]
) -> str:
    if final_state.get("status") == "abandoned":
        return "hit_turn_ceiling"

    if final_state.get("status") != "completed":
        raise RuntimeError(
            "Graph ended without completed or "
            "abandoned status."
        )

    turn_count = int(
        final_state.get("turn_count", 0)
    )

    if turn_count == 1:
        return "valid_first_attempt"

    if turn_count == 2:
        return "valid_after_one_retry"

    return "valid_after_two_or_more_retries"


def calculate_summary(
    records: list[dict[str, Any]]
) -> dict[str, Any]:
    outcome_order = [
        "valid_first_attempt",
        "valid_after_one_retry",
        "valid_after_two_or_more_retries",
        "hit_turn_ceiling",
    ]

    counts = Counter(
        record["outcome"]
        for record in records
    )

    outcomes: dict[str, Any] = {}

    for outcome in outcome_order:
        latencies = [
            record["latency_ms"]
            for record in records
            if record["outcome"] == outcome
        ]

        mean_latency = (
            round(sum(latencies) / len(latencies), 2)
            if latencies
            else None
        )

        outcomes[outcome] = {
            "count": counts.get(outcome, 0),
            "mean_latency_ms": mean_latency,
        }

    completed_count = sum(
        1
        for record in records
        if record["status"] == "completed"
    )

    completion_rate = round(
        completed_count / len(records) * 100,
        2,
    )

    overall_mean_latency = round(
        sum(
            record["latency_ms"]
            for record in records
        )
        / len(records),
        2,
    )

    return {
        "total_runs": len(records),
        "completed_runs": completed_count,
        "completion_rate_percent": completion_rate,
        "overall_mean_latency_ms": (
            overall_mean_latency
        ),
        "outcomes": outcomes,
    }


def save_results(
    *,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    raw_dir: Path,
    output_stem: str,
    configuration: dict[str, Any],
) -> tuple[Path, Path]:
    raw_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = raw_dir / f"{output_stem}.json"
    csv_path = raw_dir / f"{output_stem}.csv"

    json_payload = {
        "configuration": configuration,
        "summary": summary,
        "runs": records,
    }

    json_path.write_text(
        json.dumps(
            json_payload,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    fieldnames = [
        "experiment",
        "run_number",
        "status",
        "outcome",
        "turn_count",
        "retry_count",
        "max_turns",
        "latency_ms",
        "tags",
        "summary",
        "last_error",
        "model",
        "temperature",
        "seed",
        "timestamp_utc",
    ]

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
            lineterminator="\n",
        )

        writer.writeheader()

        for record in records:
            csv_record = dict(record)
            csv_record["tags"] = json.dumps(
                record["tags"],
                ensure_ascii=False,
            )
            writer.writerow(csv_record)

    return json_path, csv_path


def run_experiment(
    *,
    case: dict[str, Any],
    experiment: str,
    runs: int,
    max_turns: int,
    model_name: str,
    temperature: float,
    seed: int,
) -> list[dict[str, Any]]:
    model_client = ModelClient(
        model_name=model_name,
        temperature=temperature,
        output_format="json",
        reasoning=False,
        seed=seed,
    )

    graph = build_graph()
    records: list[dict[str, Any]] = []

    for run_number in range(1, runs + 1):
        initial_state = create_initial_state(
            title=case["title"],
            content=case["content"],
            email=case["email"],
            strict=case["strict"],
            llm=model_client,
            max_turns=max_turns,
        )

        hidden_console_output = io.StringIO()
        start_time = time.perf_counter()

        with redirect_stdout(hidden_console_output):
            final_state = graph.invoke(
                initial_state,
                config={
                    "recursion_limit": (
                        max_turns * 5 + 10
                    )
                },
            )

        latency_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        outcome = classify_outcome(final_state)

        proposal = final_state.get(
            "planner_proposal",
            {},
        )

        turn_count = int(
            final_state.get("turn_count", 0)
        )

        record = {
            "experiment": experiment,
            "run_number": run_number,
            "status": final_state.get("status"),
            "outcome": outcome,
            "turn_count": turn_count,
            "retry_count": max(
                turn_count - 1,
                0,
            ),
            "max_turns": max_turns,
            "latency_ms": latency_ms,
            "tags": proposal.get("tags", []),
            "summary": proposal.get(
                "summary",
                "",
            ),
            "last_error": final_state.get(
                "last_error",
                "",
            ),
            "model": model_name,
            "temperature": temperature,
            "seed": seed,
            "timestamp_utc": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            ),
        }

        records.append(record)

        print(
            f"[{experiment}] "
            f"run {run_number:02d}/{runs} "
            f"outcome={outcome} "
            f"turns={turn_count} "
            f"latency_ms={latency_ms}"
        )

    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run repeatable DATA 260 HW2 "
            "LangGraph experiments."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--experiment",
        required=True,
    )

    parser.add_argument(
        "--runs",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--max-turns",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--output-stem",
        required=True,
    )

    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
    )

    parser.add_argument(
        "--model",
        default="qwen3:8b",
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=2974,
    )

    args = parser.parse_args()

    if args.runs < 1:
        parser.error("--runs must be at least 1")

    if args.max_turns < 1:
        parser.error(
            "--max-turns must be at least 1"
        )

    case = load_case(args.input)

    configuration = {
        "experiment": args.experiment,
        "input_file": str(args.input),
        "runs": args.runs,
        "max_turns": args.max_turns,
        "model": args.model,
        "temperature": args.temperature,
        "seed": args.seed,
    }

    print(
        "Experiment configuration:\n"
        + json.dumps(
            configuration,
            indent=2,
        )
    )

    records = run_experiment(
        case=case,
        experiment=args.experiment,
        runs=args.runs,
        max_turns=args.max_turns,
        model_name=args.model,
        temperature=args.temperature,
        seed=args.seed,
    )

    summary = calculate_summary(records)

    json_path, csv_path = save_results(
        records=records,
        summary=summary,
        raw_dir=args.raw_dir,
        output_stem=args.output_stem,
        configuration=configuration,
    )

    print("\nExperiment summary:")
    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    print(f"\nJSON saved to: {json_path}")
    print(f"CSV saved to: {csv_path}")


if __name__ == "__main__":
    main()