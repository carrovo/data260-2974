"""Self-improving two-agent system for DATA 260 Homework 9 Part 4."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

ModelRunner = Callable[[str, str], str]


def local_model_runner(system_prompt: str, user_prompt: str) -> str:
    """Reuse the deterministic local-Ollama adapter from Homework 8."""

    from hw8_agent_common import call_ollama

    return call_ollama(system_prompt, user_prompt)


def load_inputs(path: Path) -> list[dict[str, str]]:
    """Load one question-only split and validate its small public schema."""

    document = json.loads(path.read_text())
    inputs = document.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError(f"{path} must contain a non-empty inputs list")
    results: list[dict[str, str]] = []
    for item in inputs:
        if set(item) != {"question_id", "question"}:
            raise ValueError(
                f"{path} inputs may contain only question_id and question"
            )
        question_id = str(item["question_id"]).strip()
        question = str(item["question"]).strip()
        if not question_id or not question:
            raise ValueError(f"{path} contains an empty question")
        results.append({"question_id": question_id, "question": question})
    return results


class ReferenceStore:
    """Ground-truth facts used only for answer context and evaluation."""

    def __init__(self, path: Path = Path("reference_data.json")) -> None:
        document = json.loads(path.read_text())
        records = document.get("records")
        if not isinstance(records, dict) or not records:
            raise ValueError("reference_data.json must contain records")
        self.records: dict[str, dict[str, Any]] = records

    def get(self, question_id: str) -> dict[str, Any]:
        """Return the ground-truth record for one known question."""

        try:
            return self.records[question_id]
        except KeyError as exc:
            raise KeyError(f"No reference record for {question_id}") from exc

    def check(self, question_id: str, answer: str) -> dict[str, Any]:
        """Return a deterministic fact check against the reference record."""

        record = self.get(question_id)
        normalized = answer.casefold()
        missing: list[list[str]] = []
        for alternatives in record["required_concepts"]:
            if not any(str(value).casefold() in normalized for value in alternatives):
                missing.append([str(value) for value in alternatives])
        forbidden = [
            str(value)
            for value in record.get("forbidden_concepts", [])
            if str(value).casefold() in normalized
        ]
        passed = not missing and not forbidden
        feedback_parts: list[str] = []
        if missing:
            feedback_parts.append(
                "Include these ground-truth facts: "
                + " ".join(str(value) for value in record["facts"])
            )
        if forbidden:
            feedback_parts.append(
                "Remove unsupported or conflicting details: "
                + ", ".join(forbidden)
            )
        return {
            "result": "PASS" if passed else "REVISE",
            "missing_concepts": missing,
            "forbidden_concepts_found": forbidden,
            "feedback": " ".join(feedback_parts),
        }


class LessonStore:
    """Persist, retrieve, and count reusable failure-pattern lessons."""

    def __init__(self, path: Path = Path("lessons.json")) -> None:
        self.path = path

    def load(self) -> list[dict[str, Any]]:
        """Return all saved lessons."""

        document = json.loads(self.path.read_text())
        lessons = document.get("lessons")
        if not isinstance(lessons, list):
            raise ValueError("lessons.json must contain a lessons list")
        return lessons

    def save(self, lessons: list[dict[str, Any]]) -> None:
        """Persist lessons with stable readable formatting."""

        self.path.write_text(
            json.dumps({"lessons": lessons}, indent=2, sort_keys=True) + "\n"
        )

    def relevant(
        self,
        question: str,
        *,
        increment_use: bool = False,
    ) -> list[dict[str, Any]]:
        """Return lessons whose keyword list matches the current question."""

        lessons = self.load()
        normalized = question.casefold()
        matched = [
            lesson
            for lesson in lessons
            if any(
                str(keyword).casefold() in normalized
                for keyword in lesson.get("keywords", [])
            )
        ]
        if increment_use and matched:
            matched_ids = {lesson["lesson_id"] for lesson in matched}
            for lesson in lessons:
                if lesson["lesson_id"] in matched_ids:
                    lesson["use_count"] = int(lesson.get("use_count", 0)) + 1
            self.save(lessons)
        return matched


@dataclass(frozen=True)
class Evaluation:
    """Evaluator Agent result for one answer attempt."""

    result: str
    explanation: str
    feedback: str
    missing_concepts: list[list[str]]
    forbidden_concepts_found: list[str]


class AnsweringAgent:
    """Generate an answer using feedback and relevant reusable lessons."""

    def __init__(self, model_runner: ModelRunner = local_model_runner) -> None:
        self.model_runner = model_runner

    def answer(
        self,
        *,
        question: str,
        reference: dict[str, Any],
        lessons: list[dict[str, Any]],
        feedback: str = "",
        controlled_incomplete: bool = False,
    ) -> str:
        """Generate one answer attempt with optional lesson and feedback context."""

        lesson_text = "\n".join(
            f"- {lesson['correction']}" for lesson in lessons
        )
        include_reference = any(
            bool(lesson.get("use_reference_facts")) for lesson in lessons
        )
        reference_text = (
            "\n".join(f"- {fact}" for fact in reference["facts"])
            if include_reference
            else "Not supplied on the initial attempt."
        )
        system_prompt = (
            "You are the Answering Agent for a rental-listing system. Answer "
            "concisely and do not invent facts. Apply supplied lessons and "
            "revision feedback."
        )
        user_prompt = (
            f"QUESTION:\n{question}\n\n"
            f"RELEVANT LESSONS:\n{lesson_text or 'None'}\n\n"
            f"REFERENCE FACTS AVAILABLE TO ANSWERER:\n{reference_text}\n\n"
            f"EVALUATOR FEEDBACK:\n{feedback or 'None'}"
        )
        answer = self.model_runner(system_prompt, user_prompt).strip()
        if controlled_incomplete:
            # A reproducible fault injection required for the Part 4.1 demo.
            answer = (
                "The listing has a recorded monthly rent and listing code, "
                "but those exact values should be verified before replying."
            )
        return answer


class EvaluatorAgent:
    """Evaluate an answer against the separate ground-truth reference data."""

    def __init__(
        self,
        reference_store: ReferenceStore,
        model_runner: ModelRunner = local_model_runner,
    ) -> None:
        self.reference_store = reference_store
        self.model_runner = model_runner

    def evaluate(
        self,
        *,
        question_id: str,
        question: str,
        answer: str,
    ) -> Evaluation:
        """Return PASS or REVISE plus concise grounded feedback."""

        reference = self.reference_store.get(question_id)
        deterministic = self.reference_store.check(question_id, answer)
        system_prompt = (
            "You are the Evaluator Agent. Compare the answer only with the "
            "provided ground-truth facts. Return a concise explanation."
        )
        user_prompt = (
            f"QUESTION:\n{question}\n\nANSWER:\n{answer}\n\n"
            "GROUND TRUTH:\n"
            + "\n".join(f"- {fact}" for fact in reference["facts"])
            + f"\n\nFACT CHECK RESULT: {deterministic['result']}"
        )
        model_explanation = self.model_runner(system_prompt, user_prompt).strip()
        explanation = (
            "The answer covers every required reference concept without a "
            "conflicting fact."
            if deterministic["result"] == "PASS"
            else model_explanation
        )
        return Evaluation(
            result=str(deterministic["result"]),
            explanation=explanation,
            feedback=str(deterministic["feedback"]),
            missing_concepts=deterministic["missing_concepts"],
            forbidden_concepts_found=deterministic[
                "forbidden_concepts_found"
            ],
        )


class TwoAgentSystem:
    """Coordinate answer, evaluation, and at most one revision."""

    def __init__(
        self,
        *,
        reference_store: ReferenceStore,
        lesson_store: LessonStore,
        model_runner: ModelRunner = local_model_runner,
    ) -> None:
        self.reference_store = reference_store
        self.lesson_store = lesson_store
        self.answering_agent = AnsweringAgent(model_runner)
        self.evaluator_agent = EvaluatorAgent(reference_store, model_runner)

    def run(
        self,
        item: dict[str, str],
        *,
        allow_revision: bool,
        use_lessons: bool,
        controlled_incomplete: bool = False,
        count_lesson_use: bool = False,
    ) -> dict[str, Any]:
        """Run one question with a strict maximum of two answer attempts."""

        started = perf_counter()
        question_id = item["question_id"]
        question = item["question"]
        reference = self.reference_store.get(question_id)
        lessons = (
            self.lesson_store.relevant(
                question,
                increment_use=count_lesson_use,
            )
            if use_lessons
            else []
        )
        feedback = ""
        attempts: list[dict[str, Any]] = []

        for attempt_number in (1, 2):
            answer = self.answering_agent.answer(
                question=question,
                reference=reference,
                lessons=lessons,
                feedback=feedback,
                controlled_incomplete=(
                    controlled_incomplete and attempt_number == 1
                ),
            )
            evaluation = self.evaluator_agent.evaluate(
                question_id=question_id,
                question=question,
                answer=answer,
            )
            attempts.append(
                {
                    "attempt": attempt_number,
                    "answer": answer,
                    "evaluation": evaluation.result,
                    "explanation": evaluation.explanation,
                    "feedback": evaluation.feedback,
                }
            )
            if evaluation.result == "PASS":
                break
            if not allow_revision or attempt_number == 2:
                break
            feedback = evaluation.feedback

        final = attempts[-1]
        return {
            "question_id": question_id,
            "question": question,
            "loaded_lesson_ids": [lesson["lesson_id"] for lesson in lessons],
            "attempts": attempts,
            "attempt_count": len(attempts),
            "final_answer": final["answer"],
            "final_evaluation": final["evaluation"],
            "latency_ms": round((perf_counter() - started) * 1000, 2),
        }
