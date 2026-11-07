"""Apply the HW9 Part 3.4 cost model to threshold-sweep results."""

import csv
import json
from pathlib import Path
from typing import Any

from hw9_config import STUDENT_NAME

MISS_COST_DOLLARS = 0.02
FALSE_HIT_COST_DOLLARS = 2.00


def calculate_total_cost(
    *,
    case_count: int,
    hit_count: int,
    false_hit_count: int,
) -> tuple[int, float]:
    """Return miss count and total modeled cost for one threshold."""

    if not 0 <= hit_count <= case_count:
        raise ValueError("hit_count must be between zero and case_count")
    if not 0 <= false_hit_count <= hit_count:
        raise ValueError("false_hit_count must be between zero and hit_count")

    miss_count = case_count - hit_count
    total_cost = (
        miss_count * MISS_COST_DOLLARS
        + false_hit_count * FALSE_HIT_COST_DOLLARS
    )
    return miss_count, round(total_cost, 2)


def analyze_summaries(
    summaries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Calculate threshold costs and select the minimum-cost threshold."""

    if not summaries:
        raise ValueError("Threshold summaries are required")

    analyzed: list[dict[str, Any]] = []
    for summary in summaries:
        miss_count, total_cost = calculate_total_cost(
            case_count=int(summary["case_count"]),
            hit_count=int(summary["hit_count"]),
            false_hit_count=int(summary["false_hit_count"]),
        )
        analyzed.append(
            {
                **summary,
                "miss_count": miss_count,
                "miss_cost_dollars": round(
                    miss_count * MISS_COST_DOLLARS,
                    2,
                ),
                "false_hit_support_cost_dollars": round(
                    int(summary["false_hit_count"])
                    * FALSE_HIT_COST_DOLLARS,
                    2,
                ),
                "total_cost_dollars": total_cost,
            }
        )

    selected = min(
        analyzed,
        key=lambda row: (
            float(row["total_cost_dollars"]),
            int(row["false_hit_count"]),
            -float(row["threshold"]),
        ),
    )
    return analyzed, selected


def update_csv_table(
    path: Path,
    analyzed: list[dict[str, Any]],
) -> None:
    """Fill the required total-cost column in the existing sweep table."""

    rows = list(csv.DictReader(path.open(newline="")))
    cost_by_threshold = {
        round(float(row["threshold"]), 2): row["total_cost_dollars"]
        for row in analyzed
    }
    for row in rows:
        threshold = round(float(row["threshold"]), 2)
        row["total_cost"] = f"{cost_by_threshold[threshold]:.2f}"

    with path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Calculate costs, choose a threshold, and write report evidence."""

    raw_directory = Path("reports/hw09/raw")
    sweep_path = raw_directory / "part3_threshold_sweep.json"
    sweep = json.loads(sweep_path.read_text())

    analyzed, selected = analyze_summaries(sweep["summaries"])
    selected_threshold = float(selected["threshold"])
    selection_reason = (
        f"Threshold {selected_threshold:.2f} has the lowest modeled total "
        f"cost (${selected['total_cost_dollars']:.2f}). It reduces false "
        "hits to one while avoiding the additional miss introduced at 0.95."
    )

    result = {
        "student_name": STUDENT_NAME,
        "cost_model": {
            "cache_miss_cost_dollars": MISS_COST_DOLLARS,
            "cache_miss_justification": (
                "Estimated local compute and user-wait cost for the observed "
                "approximately 21-second non-cached agent path; this is not "
                "an external API charge."
            ),
            "false_hit_support_cost_dollars": FALSE_HIT_COST_DOLLARS,
            "false_hit_justification": (
                "Conservative human review/support cost for detecting and "
                "correcting a plausible but wrong domain answer."
            ),
            "formula": (
                "total_cost = miss_count * 0.02 + false_hit_count * 2.00"
            ),
        },
        "threshold_results": analyzed,
        "selected_threshold": selected_threshold,
        "selection_reason": selection_reason,
    }
    output_path = raw_directory / "part3_cost_analysis.json"
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    update_csv_table(
        raw_directory / "part3_threshold_table.csv",
        analyzed,
    )

    print(f"Student: {STUDENT_NAME}")
    print("=== HW9 Part 3.4: Cost Model and Threshold Choice ===")
    print(f"Cache-miss cost: ${MISS_COST_DOLLARS:.2f}")
    print(f"False-hit/support cost: ${FALSE_HIT_COST_DOLLARS:.2f}")
    print(
        "Threshold | Misses | False hits | Total cost | "
        "Accuracy"
    )
    for row in analyzed:
        print(
            f"{row['threshold']:.2f}      | "
            f"{row['miss_count']:>6} | "
            f"{row['false_hit_count']:>10} | "
            f"${row['total_cost_dollars']:>9.2f} | "
            f"{row['accuracy_pct']:.1f}%"
        )
    print(f"Selected threshold to ship: {selected_threshold:.2f}")
    print(f"Reason: {selection_reason}")
    print("COST_MODEL_STATUS: PASS")


if __name__ == "__main__":
    main()
