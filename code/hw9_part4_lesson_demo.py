"""Create and reuse one persistent lesson for HW9 Part 4.2."""

import json
from pathlib import Path

from hw9_config import STUDENT_NAME
from hw9_part4_agents import (
    LessonStore,
    ReferenceStore,
    TwoAgentSystem,
    load_inputs,
)

LESSON = {
    "lesson_id": "lesson_001",
    "failure_pattern": (
        "Answers to listing-specific questions omit the exact current value "
        "or listing code."
    ),
    "correction": (
        "For listing-specific questions, load the matching reference record "
        "and include its exact listing code and numeric value."
    ),
    "created_at": "2026-11-07",
    "use_count": 0,
    "keywords": ["listing", "rent", "monthly"],
    "use_reference_facts": True,
}


def main() -> None:
    """Save a lesson from the controlled failure and reuse it once."""

    raw_directory = Path("reports/hw09/raw")
    revision_path = raw_directory / "part4_revision_sequence.json"
    revision = json.loads(revision_path.read_text())
    first_attempt = revision["attempts"][0]
    if first_attempt["evaluation"] != "REVISE":
        raise RuntimeError("The source failure was not found")

    lesson_store = LessonStore()
    lesson_store.save([dict(LESSON)])
    later_item = load_inputs(Path("training_data.json"))[1]
    system = TwoAgentSystem(
        reference_store=ReferenceStore(),
        lesson_store=lesson_store,
    )
    result = system.run(
        later_item,
        allow_revision=True,
        use_lessons=True,
        count_lesson_use=True,
    )
    saved_lesson = lesson_store.load()[0]

    if result["loaded_lesson_ids"] != ["lesson_001"]:
        raise RuntimeError("lesson_001 was not loaded for the later question")
    if saved_lesson["use_count"] != 1:
        raise RuntimeError("lesson_001 use_count was not incremented")
    if result["attempt_count"] != 1:
        raise RuntimeError("The reused lesson should produce a first-attempt pass")
    if result["final_evaluation"] != "PASS":
        raise RuntimeError("The lesson-assisted answer did not pass")

    evidence = {
        "student_name": STUDENT_NAME,
        "source_question": revision["question"],
        "source_failure": first_attempt,
        "lesson": saved_lesson,
        "later_result": result,
    }
    output_path = raw_directory / "part4_lesson_reuse.json"
    output_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )

    print(f"Student: {STUDENT_NAME}")
    print("=== HW9 Part 4.2: Save and Reuse a Lesson ===")
    print(f"Source question: {revision['question']}")
    print(f"Source evaluation: {first_attempt['evaluation']}")
    print(f"Failure pattern: {saved_lesson['failure_pattern']}")
    print(f"Saved lesson ID: {saved_lesson['lesson_id']}")
    print(f"Correction: {saved_lesson['correction']}")
    print(f"Later question: {result['question']}")
    print(f"Loaded lessons: {result['loaded_lesson_ids']}")
    print(f"Lesson-assisted answer: {result['final_answer']}")
    print(f"Final evaluation: {result['final_evaluation']}")
    print(f"Number of attempts: {result['attempt_count']}")
    print(f"Updated use_count: {saved_lesson['use_count']}")
    print("PART4_2_STATUS: PASS")


if __name__ == "__main__":
    main()
