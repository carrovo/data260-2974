"""Pure validation and statistics for DATA 260 HW10 judge evaluation."""

import csv
import json
import math
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any

EXPECTED_CASE_COUNT = 20
EXPECTED_RUN_COUNT = 3


def normalized_to_five_point(score: float) -> int:
    """Recover the integer 1-5 rubric score from G-Eval normalization."""

    if not 0 <= score <= 1:
        raise ValueError("normalized judge score must be between 0 and 1")
    return min(5, max(1, int(round(1 + 4 * score))))


def load_eval_cases(path: Path) -> list[dict[str, Any]]:
    """Load exactly 20 unique frozen Writer-draft cases."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != EXPECTED_CASE_COUNT:
        raise ValueError(f"{path} must contain exactly {EXPECTED_CASE_COUNT} cases")
    seen: set[str] = set()
    cases: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"case {index} must be a JSON object")
        case_id = item.get("case_id")
        question = item.get("question")
        draft = item.get("draft")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"case {index} has an invalid case_id")
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{case_id} has an invalid question")
        if not isinstance(draft, str) or not draft.strip():
            raise ValueError(f"{case_id} has an invalid draft")
        seen.add(case_id)
        cases.append(item)
    return cases


def load_human_labels(
    path: Path,
    expected_case_ids: list[str],
) -> dict[str, int]:
    """Load frozen human labels and require the exact case order."""

    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    case_ids = [str(row.get("case_id", "")) for row in rows]
    if case_ids != expected_case_ids:
        raise ValueError("human-label case IDs or order do not match eval cases")

    labels: dict[str, int] = {}
    for row in rows:
        case_id = str(row["case_id"])
        try:
            score = int(str(row.get("human_score", "")))
        except ValueError as exc:
            raise ValueError(f"{case_id} has an invalid human score") from exc
        if not 1 <= score <= 5:
            raise ValueError(f"{case_id} human score must be between 1 and 5")
        labels[case_id] = score
    return labels


def rank_with_ties(values: list[float]) -> list[float]:
    """Return one-based average ranks, including tied values."""

    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        average_rank = ((cursor + 1) + end) / 2
        for position in range(cursor, end):
            ranks[indexed[position][0]] = average_rank
        cursor = end
    return ranks


def pearson_correlation(
    left: list[float],
    right: list[float],
) -> float | None:
    """Return Pearson correlation, or None when either side is constant."""

    if len(left) != len(right) or not left:
        raise ValueError("correlation inputs must be non-empty and equal length")
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_sum = sum((value - left_mean) ** 2 for value in left)
    right_sum = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_sum * right_sum)
    if denominator == 0:
        return None
    return numerator / denominator


def spearman_correlation(
    left: list[float],
    right: list[float],
) -> float | None:
    """Return Spearman correlation using average ranks for ties."""

    return pearson_correlation(rank_with_ties(left), rank_with_ties(right))


def mean_absolute_difference(
    left: list[float],
    right: list[float],
) -> float:
    """Return the mean absolute difference between two score vectors."""

    if len(left) != len(right) or not left:
        raise ValueError("difference inputs must be non-empty and equal length")
    return mean(
        abs(left_value - right_value)
        for left_value, right_value in zip(left, right, strict=True)
    )


def summarize_judge_runs(
    case_ids: list[str],
    human_labels: dict[str, int],
    score_by_run: list[dict[str, int]],
) -> dict[str, Any]:
    """Compute agreement and repeatability from three complete judge runs."""

    if len(score_by_run) != EXPECTED_RUN_COUNT:
        raise ValueError(f"exactly {EXPECTED_RUN_COUNT} judge runs are required")
    expected = set(case_ids)
    for index, run in enumerate(score_by_run, start=1):
        if set(run) != expected:
            raise ValueError(f"judge run {index} is incomplete")
        if not all(1 <= score <= 5 for score in run.values()):
            raise ValueError(f"judge run {index} contains an invalid score")

    human = [float(human_labels[case_id]) for case_id in case_ids]
    per_run = []
    for index, run in enumerate(score_by_run, start=1):
        judge = [float(run[case_id]) for case_id in case_ids]
        per_run.append(
            {
                "run": index,
                "spearman_correlation": spearman_correlation(human, judge),
                "mean_absolute_difference": mean_absolute_difference(
                    human,
                    judge,
                ),
            }
        )

    mean_judge = [mean(run[case_id] for run in score_by_run) for case_id in case_ids]
    changed_case_ids = [
        case_id
        for case_id in case_ids
        if len({run[case_id] for run in score_by_run}) > 1
    ]
    pairwise_differences = [
        abs(left[case_id] - right[case_id])
        for left, right in combinations(score_by_run, 2)
        for case_id in case_ids
    ]
    changed_comparisons = sum(value != 0 for value in pairwise_differences)

    aggregate_spearman = spearman_correlation(human, mean_judge)
    aggregate_mad = mean_absolute_difference(human, mean_judge)
    changed_rate = len(changed_case_ids) / len(case_ids)
    trustworthy = (
        aggregate_spearman is not None
        and aggregate_spearman >= 0.70
        and aggregate_mad <= 0.50
        and changed_rate <= 0.10
    )

    return {
        "case_count": len(case_ids),
        "run_count": len(score_by_run),
        "agreement_using_mean_judge_score": {
            "spearman_correlation": aggregate_spearman,
            "mean_absolute_difference": aggregate_mad,
        },
        "agreement_by_run": per_run,
        "repeatability": {
            "changed_case_count": len(changed_case_ids),
            "changed_case_rate": changed_rate,
            "changed_case_ids": changed_case_ids,
            "pairwise_comparison_count": len(pairwise_differences),
            "changed_pairwise_comparison_count": changed_comparisons,
            "changed_pairwise_comparison_rate": (
                changed_comparisons / len(pairwise_differences)
            ),
            "mean_absolute_score_change": mean(pairwise_differences),
            "maximum_absolute_score_change": max(pairwise_differences),
        },
        "deployment_gate_recommendation": {
            "trust_to_gate_deployment": trustworthy,
            "decision_rule": (
                "Trust only if Spearman is at least 0.70, mean absolute "
                "difference is at most 0.50, and changed-case rate is at "
                "most 0.10."
            ),
            "additional_evidence_required": [
                "A broader human-label distribution with more weak and "
                "adversarial drafts.",
                "Labels from a second independent human reviewer.",
                "Validation on new questions not used in these 20 cases.",
            ],
        },
    }


def build_case_rows(
    case_ids: list[str],
    human_labels: dict[str, int],
    score_by_run: list[dict[str, int]],
) -> list[dict[str, Any]]:
    """Build raw per-case rows from which all statistics can be recomputed."""

    rows = []
    for case_id in case_ids:
        scores = [run[case_id] for run in score_by_run]
        mean_score = mean(scores)
        rows.append(
            {
                "case_id": case_id,
                "human_score": human_labels[case_id],
                "judge_run_1": scores[0],
                "judge_run_2": scores[1],
                "judge_run_3": scores[2],
                "judge_mean": mean_score,
                "absolute_difference_from_human": abs(
                    human_labels[case_id] - mean_score
                ),
                "score_changed": len(set(scores)) > 1,
            }
        )
    return rows
