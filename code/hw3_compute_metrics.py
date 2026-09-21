import json
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "reports" / "hw03" / "raw"

RESULTS_FILE = (
    RAW_DIR
    / "retrieval_results.jsonl"
)

CHUNK_STATS_FILE = (
    RAW_DIR
    / "chunking_statistics.json"
)

SUMMARY_CSV = (
    RAW_DIR
    / "summary_metrics.csv"
)

SUMMARY_JSON = (
    RAW_DIR
    / "summary_metrics.json"
)

PER_QUERY_CSV = (
    RAW_DIR
    / "per_query_metrics.csv"
)


def load_jsonl(
    file_path: Path,
) -> list[dict[str, Any]]:
    payloads = []

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line in file:
            stripped_line = line.strip()

            if stripped_line:
                payloads.append(
                    json.loads(stripped_line)
                )

    return payloads


def main() -> None:
    query_payloads = load_jsonl(
        RESULTS_FILE
    )

    chunk_statistics = json.loads(
        CHUNK_STATS_FILE.read_text(
            encoding="utf-8"
        )
    )

    if len(query_payloads) != 15:
        raise ValueError(
            "Expected 15 query-technique results, "
            f"but found {len(query_payloads)}."
        )

    chunk_stats_by_technique = {
        item["technique"]: item
        for item in chunk_statistics
    }

    techniques = sorted(
        {
            payload["technique"]
            for payload in query_payloads
        }
    )

    summary_rows = []
    per_query_rows = []

    for technique_name in techniques:
        technique_payloads = [
            payload
            for payload in query_payloads
            if payload["technique"]
            == technique_name
        ]

        if len(technique_payloads) != 5:
            raise ValueError(
                f"Expected five questions for "
                f"{technique_name}, but found "
                f"{len(technique_payloads)}."
            )

        top1_cosines = []
        mean_at_k_cosines = []
        recall_at_k_values = []
        retrieval_latencies = []

        for payload in technique_payloads:
            results = payload["results"]

            cosine_values = [
                float(result["cosine_sim"])
                for result in results
            ]

            top1_cosine = cosine_values[0]

            mean_at_k_cosine = mean(
                cosine_values
            )

            recall_at_k = int(
                any(
                    result["source_match"]
                    for result in results
                )
            )

            retrieval_latency_ms = float(
                payload["retrieval_latency_ms"]
            )

            top1_cosines.append(
                top1_cosine
            )

            mean_at_k_cosines.append(
                mean_at_k_cosine
            )

            recall_at_k_values.append(
                recall_at_k
            )

            retrieval_latencies.append(
                retrieval_latency_ms
            )

            per_query_rows.append(
                {
                    "technique": technique_name,
                    "query_id": payload[
                        "query_id"
                    ],
                    "top1_cosine": (
                        top1_cosine
                    ),
                    "mean_at_k_cosine": (
                        mean_at_k_cosine
                    ),
                    "recall_at_k": (
                        recall_at_k
                    ),
                    "retrieval_latency_ms": (
                        retrieval_latency_ms
                    ),
                }
            )

        chunk_stats = (
            chunk_stats_by_technique[
                technique_name
            ]
        )

        summary_rows.append(
            {
                "technique": technique_name,
                "chunks": chunk_stats[
                    "chunks"
                ],
                "avg_chunk_length_chars": (
                    chunk_stats[
                        "avg_chunk_length_chars"
                    ]
                ),
                "top1_cosine": mean(
                    top1_cosines
                ),
                "mean_at_k_cosine": mean(
                    mean_at_k_cosines
                ),
                "recall_at_k": mean(
                    recall_at_k_values
                ),
                "mean_retrieval_latency_ms": (
                    mean(
                        retrieval_latencies
                    )
                ),
            }
        )

    summary_frame = pd.DataFrame(
        summary_rows
    )

    per_query_frame = pd.DataFrame(
        per_query_rows
    )

    summary_frame.to_csv(
        SUMMARY_CSV,
        index=False,
    )

    per_query_frame.to_csv(
        PER_QUERY_CSV,
        index=False,
    )

    SUMMARY_JSON.write_text(
        json.dumps(
            summary_rows,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("Summary metrics:")
    print(
        summary_frame.to_string(
            index=False,
            float_format=lambda value: (
                f"{value:.6f}"
            ),
        )
    )

    print("\nPer-query metrics:")
    print(
        per_query_frame.to_string(
            index=False,
            float_format=lambda value: (
                f"{value:.6f}"
            ),
        )
    )

    print(
        f"\nSaved summary CSV: "
        f"{SUMMARY_CSV}"
    )
    print(
        f"Saved summary JSON: "
        f"{SUMMARY_JSON}"
    )
    print(
        f"Saved per-query CSV: "
        f"{PER_QUERY_CSV}"
    )


if __name__ == "__main__":
    main()