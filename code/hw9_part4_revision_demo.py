"""Demonstrate one complete HW9 Part 4.1 evaluator-repair sequence."""

import json
from pathlib import Path

from hw9_config import STUDENT_NAME
from hw9_part4_agents import (
    LessonStore,
    ReferenceStore,
    TwoAgentSystem,
    load_inputs,
)


def main() -> None:
    """Run the controlled incomplete answer through one grounded revision."""

    training_items = load_inputs(Path("training_data.json"))
    controlled_item = training_items[0]
    system = TwoAgentSystem(
        reference_store=ReferenceStore(),
        lesson_store=LessonStore(),
    )
    result = system.run(
        controlled_item,
        allow_revision=True,
        use_lessons=False,
        controlled_incomplete=True,
    )
    attempts = result["attempts"]
    if len(attempts) != 2:
        raise RuntimeError("Controlled repair must use exactly two attempts")
    if attempts[0]["evaluation"] != "REVISE":
        raise RuntimeError("The controlled initial answer should require revision")
    if result["final_evaluation"] != "PASS":
        raise RuntimeError("The revised answer did not pass the evaluator")

    raw_directory = Path("reports/hw09/raw")
    raw_directory.mkdir(parents=True, exist_ok=True)
    (raw_directory / "part4_revision_sequence.json").write_text(
        json.dumps(
            {"student_name": STUDENT_NAME, **result},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    print(f"Student: {STUDENT_NAME}")
    print("=== HW9 Part 4.1: Evaluator Feedback and Repair ===")
    print(f"Question: {result['question']}")
    print(f"Initial answer: {attempts[0]['answer']}")
    print(f"Initial evaluation: {attempts[0]['evaluation']}")
    print(f"Evaluator explanation: {attempts[0]['explanation']}")
    print(f"Evaluator feedback: {attempts[0]['feedback']}")
    print(f"Revised answer: {attempts[1]['answer']}")
    print(f"Final evaluation: {result['final_evaluation']}")
    print(f"Number of attempts: {result['attempt_count']}")
    print(f"Final response: {result['final_answer']}")
    print(f"Latency: {result['latency_ms']:.2f} ms")
    print("PART4_1_STATUS: PASS")


if __name__ == "__main__":
    main()
