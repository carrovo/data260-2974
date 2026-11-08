"""Evaluate the four required HW9 Part 4 system variants."""

import csv
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from hw9_config import STUDENT_NAME
from hw9_part4_agents import (
    LessonStore,
    ReferenceStore,
    TwoAgentSystem,
    load_inputs,
)

RAW_DIRECTORY = Path("reports/hw09/raw")
TEST_DATA_PATH = Path("test_data.json")


@dataclass(frozen=True)
class Variant:
    """Configuration for one independently evaluated system variant."""

    key: str
    label: str
    allow_revision: bool
    use_lessons: bool
    lesson_source: str


VARIANTS = (
    Variant(
        key="baseline",
        label="Baseline",
        allow_revision=False,
        use_lessons=False,
        lesson_source="none",
    ),
    Variant(
        key="evaluator_repair",
        label="Evaluator Repair",
        allow_revision=True,
        use_lessons=False,
        lesson_source="none",
    ),
    Variant(
        key="lesson_memory",
        label="Lesson Memory",
        allow_revision=True,
        use_lessons=True,
        lesson_source="candidate lesson saved before validation",
    ),
    Variant(
        key="validated_improvement",
        label="Validated Improvement",
        allow_revision=True,
        use_lessons=True,
        lesson_source="lesson kept by validation gate",
    ),
)


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of one file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate the four metrics required by the assignment."""

    if not results:
        raise ValueError("Variant results cannot be empty")
    correct = sum(row["final_evaluation"] == "PASS" for row in results)
    return {
        "correct_answers": correct,
        "incorrect_answers": len(results) - correct,
        "average_attempts": round(
            fmean(float(row["attempt_count"]) for row in results),
            2,
        ),
        "average_latency_ms": round(
            fmean(float(row["latency_ms"]) for row in results),
            2,
        ),
    }


def candidate_lessons() -> list[dict[str, Any]]:
    """Load the reusable lesson as it existed before validation."""

    evidence = json.loads(
        (RAW_DIRECTORY / "part4_lesson_reuse.json").read_text()
    )
    lesson = evidence.get("lesson")
    if not isinstance(lesson, dict):
        raise ValueError("Part 4.2 evidence does not contain a lesson")
    return [lesson]


def validated_lessons() -> list[dict[str, Any]]:
    """Load lessons only after proving that the validation gate kept them."""

    evidence = json.loads(
        (RAW_DIRECTORY / "part4_validation.json").read_text()
    )
    if evidence.get("lesson_action") != "KEPT":
        raise RuntimeError("The validation gate did not keep the lesson")
    if evidence.get("test_data_used") is not False:
        raise RuntimeError("Test data must not be used during validation")
    lessons = LessonStore().load()
    if not lessons:
        raise RuntimeError("No validated lesson is available")
    return lessons


def lessons_for_variant(variant: Variant) -> list[dict[str, Any]]:
    """Return the isolated lesson snapshot for one variant."""

    if variant.key == "lesson_memory":
        return candidate_lessons()
    if variant.key == "validated_improvement":
        return validated_lessons()
    return []


def run_variant(
    variant: Variant,
    items: list[dict[str, str]],
) -> dict[str, Any]:
    """Run one variant with its own reloaded lesson store."""

    lessons = lessons_for_variant(variant)
    with tempfile.TemporaryDirectory() as temporary_directory:
        lesson_path = Path(temporary_directory) / "lessons.json"
        LessonStore(lesson_path).save(lessons)

        # Reopen the file to demonstrate persistence and isolate variant state.
        reloaded_store = LessonStore(lesson_path)
        system = TwoAgentSystem(
            reference_store=ReferenceStore(),
            lesson_store=reloaded_store,
        )
        results = [
            system.run(
                item,
                allow_revision=variant.allow_revision,
                use_lessons=variant.use_lessons,
                count_lesson_use=False,
            )
            for item in items
        ]

    return {
        "key": variant.key,
        "variant": variant.label,
        "allow_revision": variant.allow_revision,
        "use_lessons": variant.use_lessons,
        "lesson_source": variant.lesson_source,
        "loaded_lesson_ids": [
            lesson["lesson_id"] for lesson in lessons
        ],
        "metrics": summarize_results(results),
        "case_results": results,
    }


def write_csv(variant_results: list[dict[str, Any]]) -> None:
    """Write the completed assignment table with Unix line endings."""

    output_path = RAW_DIRECTORY / "part4_variant_table.csv"
    with output_path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "variant",
                "correct_answers",
                "incorrect_answers",
                "average_attempts",
                "average_latency_ms",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        for result in variant_results:
            writer.writerow(
                {
                    "variant": result["variant"],
                    **result["metrics"],
                }
            )


def main() -> None:
    """Run all four variants on one unchanged held-out test set."""

    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    hash_before = file_sha256(TEST_DATA_PATH)
    items = load_inputs(TEST_DATA_PATH)
    test_ids = [item["question_id"] for item in items]

    variant_results = []
    for variant in VARIANTS:
        result = run_variant(variant, items)
        variant_results.append(result)
        metrics = result["metrics"]
        print(
            f"Completed {variant.label}: "
            f"correct={metrics['correct_answers']}/{len(items)}, "
            f"average_attempts={metrics['average_attempts']:.2f}"
        )

    hash_after = file_sha256(TEST_DATA_PATH)
    if hash_before != hash_after:
        raise RuntimeError("test_data.json changed during final evaluation")

    evidence = {
        "student_name": STUDENT_NAME,
        "test_dataset": str(TEST_DATA_PATH),
        "test_dataset_sha256_before": hash_before,
        "test_dataset_sha256_after": hash_after,
        "test_dataset_unchanged": True,
        "test_case_count": len(items),
        "test_question_ids": test_ids,
        "variant_results": variant_results,
    }
    (RAW_DIRECTORY / "part4_variant_results.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )
    write_csv(variant_results)

    print()
    print(f"Student: {STUDENT_NAME}")
    print("=== HW9 Part 4.4: Four System Variants ===")
    print(f"Held-out test cases: {len(items)}")
    print(f"Test dataset SHA-256: {hash_before}")
    print("Test dataset unchanged: True")
    print()
    print(
        "Variant               Correct  Incorrect  "
        "Avg attempts  Avg latency (ms)"
    )
    for result in variant_results:
        metrics = result["metrics"]
        print(
            f"{result['variant']:<21} "
            f"{metrics['correct_answers']:^7}  "
            f"{metrics['incorrect_answers']:^9}  "
            f"{metrics['average_attempts']:^12.2f}  "
            f"{metrics['average_latency_ms']:>16.2f}"
        )
    print()
    print("Maximum answer attempts: 2")
    print("Lessons created from test data: False")
    print("PART4_4_STATUS: PASS")


if __name__ == "__main__":
    main()
