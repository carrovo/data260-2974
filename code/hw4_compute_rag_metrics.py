import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = (
    ROOT
    / "reports"
    / "hw04"
    / "raw"
)

INPUT_FILE = RAW_DIR / "rag_outputs.jsonl"
PER_RUN_FILE = RAW_DIR / "rag_per_run_metrics.jsonl"
SUMMARY_FILE = RAW_DIR / "rag_metrics_summary.json"
QUESTIONS_FILE = ROOT / "questions_hw4.yaml"


def normalize(text: str) -> str:
    """Normalize text before keyword checks."""
    return (
        text.lower()
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
    )


def load_questions() -> dict[str, dict[str, Any]]:
    """Load question evaluation rules."""
    data = yaml.safe_load(
        QUESTIONS_FILE.read_text(
            encoding="utf-8"
        )
    )

    return {
        question["id"]: question
        for question in data["questions"]
    }


def load_rows() -> list[dict[str, Any]]:
    """Load raw RAG experiment rows."""
    rows: list[dict[str, Any]] = []

    with INPUT_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))

    return rows


def answer_contains_required_terms(
    question_data: dict[str, Any],
    answer: str,
) -> bool:
    """Check required answer concepts."""
    normalized_answer = normalize(answer)

    required_terms = question_data.get(
        "required_terms",
        [],
    )

    return all(
        any(
            normalize(term) in normalized_answer
            for term in term_group
        )
        for term_group in required_terms
    )


def source_retrieval_pass(
    row: dict[str, Any],
) -> bool | None:
    """Check whether all expected sources were retrieved."""
    if row["answerability"] != "answerable":
        return None

    expected_sources = set(
        row["expected_source_files"]
    )

    retrieved_sources = {
        context["source_file"]
        for context in row["contexts"]
    }

    return expected_sources.issubset(
        retrieved_sources
    )


def refusal_pass(
    row: dict[str, Any],
) -> bool | None:
    """Check refusal behavior for unsupported questions."""
    if row["answerability"] == "answerable":
        return None

    return bool(row["refusal_detected"])


def format_pass(
    row: dict[str, Any],
) -> bool:
    """Check source citation format for context RAG."""
    if row["configuration"] != (
        "C_context_engineered_rag"
    ):
        return True

    answer = normalize(row["answer"])

    if row["answerability"] != "answerable":
        return bool(row["refusal_detected"])

    source_markers = [
        "source 1",
        "source 2",
        "source 3",
        "[source",
    ]

    return any(
        marker in answer
        for marker in source_markers
    )


def evaluate_row(
    row: dict[str, Any],
    question_data: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one question/configuration run."""
    answerable = (
        row["answerability"] == "answerable"
    )

    if answerable:
        correct_answer = (
            answer_contains_required_terms(
                question_data=question_data,
                answer=row["answer"],
            )
        )

        correct_retrieval = (
            source_retrieval_pass(row)
        )

        format_compliance = format_pass(row)

        # Grounding requires evidence and answer support.
        grounded = bool(
            correct_retrieval
            and correct_answer
            and format_compliance
        )

        refused_when_needed = None

        overall_pass = bool(
            correct_retrieval
            and correct_answer
            and grounded
            and format_compliance
        )
    else:
        correct_answer = None
        correct_retrieval = None
        grounded = None
        format_compliance = format_pass(row)
        refused_when_needed = refusal_pass(row)
        overall_pass = bool(
            refused_when_needed
        )

    return {
        "configuration": row["configuration"],
        "retrieval_mode": row["retrieval_mode"],
        "k": row["k"],
        "query_id": row["query_id"],
        "question_type": row["question_type"],
        "answerability": row["answerability"],
        "correct_retrieval": correct_retrieval,
        "correct_answer": correct_answer,
        "grounded": grounded,
        "refused_when_needed": refused_when_needed,
        "format_compliance": format_compliance,
        "overall_pass": overall_pass,
        "retrieval_latency_ms": row[
            "retrieval_latency_ms"
        ],
        "llm_latency_ms": row[
            "llm_latency_ms"
        ],
    }


def mean_boolean(
    rows: list[dict[str, Any]],
    field: str,
) -> float | None:
    """Average a boolean field while ignoring None."""
    values = [
        row[field]
        for row in rows
        if row[field] is not None
    ]

    if not values:
        return None

    return round(
        mean(values),
        4,
    )


def main() -> None:
    """Compute the HW4 RAG evaluation tables."""
    question_rules = load_questions()
    rows = load_rows()

    if len(rows) != 54:
        raise ValueError(
            f"Expected 54 rows, found {len(rows)}."
        )

    evaluated_rows = []

    for row in rows:
        question_data = question_rules[
            row["query_id"]
        ]

        evaluated_rows.append(
            evaluate_row(
                row=row,
                question_data=question_data,
            )
        )

    grouped_rows: dict[
        tuple[str, int],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in evaluated_rows:
        grouped_rows[
            (
                row["configuration"],
                row["k"],
            )
        ].append(row)

    summary_rows = []

    for (
        configuration,
        k,
    ), group in grouped_rows.items():
        answerable_rows = [
            row
            for row in group
            if row["answerability"]
            == "answerable"
        ]

        refusal_rows = [
            row
            for row in group
            if row["answerability"]
            != "answerable"
        ]

        summary_rows.append(
            {
                "configuration": configuration,
                "k": k,
                "runs": len(group),
                "answer_accuracy": mean_boolean(
                    answerable_rows,
                    "correct_answer",
                ),
                "retrieval_accuracy": mean_boolean(
                    answerable_rows,
                    "correct_retrieval",
                ),
                "grounded_rate": mean_boolean(
                    answerable_rows,
                    "grounded",
                ),
                "format_compliance_rate": mean_boolean(
                    group,
                    "format_compliance",
                ),
                "refusal_rate": mean_boolean(
                    refusal_rows,
                    "refused_when_needed",
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
                        row[
                            "retrieval_latency_ms"
                        ]
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

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with PER_RUN_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        for row in evaluated_rows:
            file.write(
                json.dumps(row)
                + "\n"
            )

    summary = {
        "total_rows": len(evaluated_rows),
        "answerable_rows": sum(
            row["answerability"]
            == "answerable"
            for row in evaluated_rows
        ),
        "unsupported_rows": sum(
            row["answerability"]
            == "unsupported"
            for row in evaluated_rows
        ),
        "out_of_domain_rows": sum(
            row["answerability"]
            == "out_of_domain"
            for row in evaluated_rows
        ),
        "summary": summary_rows,
    }

    SUMMARY_FILE.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("RAG evaluation summary:")

    for row in summary_rows:
        print(
            f"{row['configuration']:>28} "
            f"k={row['k']} "
            f"answer={row['answer_accuracy']} "
            f"retrieval={row['retrieval_accuracy']} "
            f"grounded={row['grounded_rate']} "
            f"refusal={row['refusal_rate']} "
            f"overall={row['overall_pass_rate']}"
        )

    print()
    print(
        f"Saved per-run metrics: "
        f"{PER_RUN_FILE}"
    )
    print(
        f"Saved summary metrics: "
        f"{SUMMARY_FILE}"
    )


if __name__ == "__main__":
    main()