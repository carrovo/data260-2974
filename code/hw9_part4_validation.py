"""Validate a reusable lesson before keeping it for HW9 Part 4.3."""

import json
from pathlib import Path
from typing import Any

from hw9_part4_agents import (
    LessonStore,
    ReferenceStore,
    TwoAgentSystem,
    load_inputs,
)


def decide_validation(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the three required regression checks and the keep decision."""

    before_by_id = {row["question_id"]: row for row in before}
    after_by_id = {row["question_id"]: row for row in after}
    if set(before_by_id) != set(after_by_id):
        raise ValueError("Before and after validation IDs must match")

    before_correct = {
        question_id
        for question_id, row in before_by_id.items()
        if row["final_evaluation"] == "PASS"
    }
    after_correct = {
        question_id
        for question_id, row in after_by_id.items()
        if row["final_evaluation"] == "PASS"
    }
    before_failed = set(before_by_id) - before_correct
    failure_cases_not_worse = all(
        after_by_id[question_id]["final_evaluation"]
        in {"PASS", before_by_id[question_id]["final_evaluation"]}
        for question_id in before_failed
    )
    previously_correct_preserved = before_correct <= after_correct
    unrelated_safe = all(
        "S2974-" not in row["final_answer"]
        for row in after
        if row["question_id"] == "validation_03"
    )
    listing_case_improved = (
        before_by_id["validation_01"]["final_evaluation"] == "REVISE"
        and after_by_id["validation_01"]["final_evaluation"] == "PASS"
    )
    keep_lesson = all(
        (
            failure_cases_not_worse,
            previously_correct_preserved,
            unrelated_safe,
            listing_case_improved,
        )
    )
    return {
        "before_correct_count": len(before_correct),
        "after_correct_count": len(after_correct),
        "failure_cases_not_worse": failure_cases_not_worse,
        "previously_correct_preserved": previously_correct_preserved,
        "unrelated_questions_safe": unrelated_safe,
        "listing_case_improved": listing_case_improved,
        "keep_lesson": keep_lesson,
    }


def run_validation(
    system: TwoAgentSystem,
    items: list[dict[str, str]],
    *,
    use_lessons: bool,
) -> list[dict[str, Any]]:
    """Run a fixed validation split without revision or lesson creation."""

    return [
        system.run(
            item,
            allow_revision=False,
            use_lessons=use_lessons,
            count_lesson_use=False,
        )
        for item in items
    ]


def main() -> None:
    """Compare validation before and after the lesson and keep only if safe."""

    from hw9_config import STUDENT_NAME

    lesson_store = LessonStore()
    original_lessons = lesson_store.load()
    if not original_lessons:
        raise RuntimeError("Part 4.2 must create lesson_001 first")

    items = load_inputs(Path("validation_data.json"))
    system = TwoAgentSystem(
        reference_store=ReferenceStore(),
        lesson_store=lesson_store,
    )
    before = run_validation(system, items, use_lessons=False)
    after = run_validation(system, items, use_lessons=True)
    decision = decide_validation(before, after)

    if decision["keep_lesson"]:
        lesson_store.save(original_lessons)
        action = "KEPT"
    else:
        lesson_store.save([])
        action = "REMOVED"

    evidence = {
        "student_name": STUDENT_NAME,
        "validation_dataset": "validation_data.json",
        "before": before,
        "after": after,
        "decision": decision,
        "lesson_action": action,
        "test_data_used": False,
    }
    output_path = Path("reports/hw09/raw/part4_validation.json")
    output_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )

    print(f"Student: {STUDENT_NAME}")
    print("=== HW9 Part 4.3: Validate Before Keeping Lesson ===")
    print("Case | Before | After | Loaded lesson after")
    for before_row, after_row in zip(before, after, strict=True):
        print(
            f"{before_row['question_id']} | "
            f"{before_row['final_evaluation']} | "
            f"{after_row['final_evaluation']} | "
            f"{after_row['loaded_lesson_ids']}"
        )
    print(
        "Failure cases improved or unchanged: "
        f"{decision['failure_cases_not_worse']}"
    )
    print(
        "Previously correct answers preserved: "
        f"{decision['previously_correct_preserved']}"
    )
    print(
        "Unrelated questions remain safe: "
        f"{decision['unrelated_questions_safe']}"
    )
    print(f"Listing-specific case improved: {decision['listing_case_improved']}")
    print(f"Test data used during validation: {evidence['test_data_used']}")
    print(f"Lesson decision: {action}")
    print("PART4_3_STATUS: PASS" if action == "KEPT" else "PART4_3_STATUS: FAIL")


if __name__ == "__main__":
    main()
