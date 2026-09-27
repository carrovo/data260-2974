import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT
    / "reports"
    / "hw04"
    / "raw"
    / "rag_outputs.jsonl"
)

OUTPUT_DIR = (
    ROOT
    / "reports"
    / "hw04"
    / "raw"
)

PER_RUN_FILE = OUTPUT_DIR / "rag_per_run_metrics.jsonl"
SUMMARY_FILE = OUTPUT_DIR / "rag_metrics_summary.json"


# Each question uses simple answer checks for reproducible evaluation.
QUESTION_CHECKS = {
    "q1": [
        ["one month", "1 month"],
        ["two month", "2 month"],
    ],
    "q2": [
        ["21 days"],
    ],
    "q3": [
        ["assistance animal"],
        ["pet deposit", "extra rent"],
        ["no", "not", "without"],
    ],
    "q4": [
        ["translated", "translation"],
        ["language"],
    ],
}


def normalize(text: str) -> str:
    """Normalize text before keyword checks."""
    return (
        text.lower()
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
    )


def answer_contains_required_terms(
    query_id: str,
    answer: str,
) -> bool:
    """Check whether the answer contains required concepts."""
    checks = QUESTION_CHECKS.get(query_id)

    if not checks:
        return False

    normalized_answer = normalize(answer)

    return all(
        any(
            phrase in normalized_answer
            for phrase in phrase_group
        )
        for phrase_group in checks
    )


def source_was_retrieved(row: dict[str, Any]) -> bool:
    """Check whether the expected source appears in retrieved context."""
    expected_source = row["expected_source_file"]

    if not expected_source:
        return False

    contexts = row["contexts"]

    return any(
        context["source_file"] == expected_source
        for context in contexts
    )


def load_rows() -> list[dict[str, Any]]:
    """Load raw RAG output rows."""
    rows = []

    with INPUT_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))

    return rows


def main() -> None:
    rows = load_rows()

    if len(rows) != 54:
        raise ValueError(
            f"Expected 54 RAG rows, found {len(rows)}."
        )

    evaluated_rows = []

    for row in rows:
        in_domain = bool(row["in_domain"])

        if in_domain:
            answer_pass = answer_contains_required_terms(
                row["query_id"],
                row["answer"],
            )
            source_pass = source_was_retrieved(row)
            refusal_pass = None
            overall_pass = answer_pass and source_pass
        else:
            answer_pass = None
            source_pass = None
            refusal_pass = bool(row["refusal_detected"])
            overall_pass = refusal_pass

        evaluated_rows.append(
            {
                "configuration": row["configuration"],
                "technique": row["technique"],
                "k": row["k"],
                "query_id": row["query_id"],
                "in_domain": in_domain,
                "answer_term_pass": answer_pass,
                "source_recall_pass": source_pass,
                "refusal_pass": refusal_pass,
                "overall_pass": overall_pass,
                "retrieval_latency_ms": row[
                    "retrieval_latency_ms"
                ],
                "llm_latency_ms": row[
                    "llm_latency_ms"
                ],
            }
        )

    grouped_rows = defaultdict(list)

    for row in evaluated_rows:
        key = (
            row["configuration"],
            row["technique"],
            row["k"],
        )
        grouped_rows[key].append(row)

    summary_rows = []

    for (
        configuration,
        technique,
        k,
    ), group in grouped_rows.items():
        in_domain_rows = [
            row
            for row in group
            if row["in_domain"]
        ]

        refusal_rows = [
            row
            for row in group
            if not row["in_domain"]
        ]

        summary_rows.append(
            {
                "configuration": configuration,
                "technique": technique,
                "k": k,
                "runs": len(group),
                "answer_term_accuracy": round(
                    mean(
                        row["answer_term_pass"]
                        for row in in_domain_rows
                    ),
                    4,
                ),
                "source_recall_at_k": round(
                    mean(
                        row["source_recall_pass"]
                        for row in in_domain_rows
                    ),
                    4,
                ),
                "refusal_rate": round(
                    mean(
                        row["refusal_pass"]
                        for row in refusal_rows
                    ),
                    4,
                ),
                "overall_pass_rate": round(
                    mean(
                        row["overall_pass"]
                        for row in group
                    ),
                    4,
                ),
                "mean_retrieval_latency_ms": round(
                    mean(
                        row["retrieval_latency_ms"]
                        for row in group
                    ),
                    3,
                ),
                "mean_llm_latency_ms": round(
                    mean(
                        row["llm_latency_ms"]
                        for row in group
                    ),
                    3,
                ),
            }
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with PER_RUN_FILE.open("w", encoding="utf-8") as file:
        for row in evaluated_rows:
            file.write(
                json.dumps(row)
                + "\n"
            )

    summary = {
        "total_rows": len(evaluated_rows),
        "in_domain_rows": sum(
            row["in_domain"]
            for row in evaluated_rows
        ),
        "out_of_domain_rows": sum(
            not row["in_domain"]
            for row in evaluated_rows
        ),
        "summary": summary_rows,
    }

    SUMMARY_FILE.write_text(
        json.dumps(summary, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print("RAG evaluation summary:")

    for row in summary_rows:
        print(
            f"{row['configuration']:>18} "
            f"k={row['k']} "
            f"answer={row['answer_term_accuracy']:.2f} "
            f"source={row['source_recall_at_k']:.2f} "
            f"refusal={row['refusal_rate']:.2f} "
            f"overall={row['overall_pass_rate']:.2f}"
        )

    print()
    print(f"Saved per-run metrics: {PER_RUN_FILE}")
    print(f"Saved summary metrics: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()