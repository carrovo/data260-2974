"""Pure message and prompt logic for the HW8 three-agent pipeline."""

from typing import Any


def processing_delay_seconds(message: dict[str, Any]) -> float:
    """Return a bounded test delay requested by a failure-test message."""

    value = message.get("processing_delay_seconds", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("processing_delay_seconds must be numeric")
    if value < 0 or value > 120:
        raise ValueError("processing_delay_seconds must be between 0 and 120")
    return float(value)


def required_text(message: dict[str, Any], field: str) -> str:
    """Return a required non-empty string field or raise a clean error."""

    value = message.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def planner_prompt(message: dict[str, Any]) -> str:
    """Build the Planner prompt from an inbox question."""

    question = required_text(message, "question")
    return (
        "Create a short, practical plan for answering this rental-housing "
        f"question:\n\n{question}\n\nReturn 3 to 5 concise planning steps."
    )


def planner_message(
    source: dict[str, Any],
    model_output: str,
) -> dict[str, Any]:
    """Build the message sent from Planner to the tasks topic."""

    return {
        "correlation_id": required_text(source, "correlation_id"),
        "stage": "planned",
        "question": required_text(source, "question"),
        "plan": model_output.strip(),
    }


def writer_prompt(message: dict[str, Any]) -> str:
    """Build the Writer prompt from a Planner task."""

    question = required_text(message, "question")
    plan = required_text(message, "plan")
    return (
        "Write a clear, concise answer to the rental-housing question using "
        "the supplied plan. Do not invent laws, prices, or listing facts.\n\n"
        f"Question:\n{question}\n\nPlan:\n{plan}"
    )


def writer_message(
    source: dict[str, Any],
    model_output: str,
) -> dict[str, Any]:
    """Build the message sent from Writer to the drafts topic."""

    return {
        "correlation_id": required_text(source, "correlation_id"),
        "stage": "drafted",
        "question": required_text(source, "question"),
        "plan": required_text(source, "plan"),
        "draft": model_output.strip(),
    }


def reviewer_prompt(message: dict[str, Any]) -> str:
    """Build the Reviewer prompt from a Writer draft."""

    question = required_text(message, "question")
    draft = required_text(message, "draft")
    return (
        "Review the draft for relevance, clarity, and unsupported claims. "
        "Return only the corrected final answer, without review notes.\n\n"
        f"Question:\n{question}\n\nDraft:\n{draft}"
    )


def reviewer_message(
    source: dict[str, Any],
    model_output: str,
) -> dict[str, Any]:
    """Build the final approved JSON message."""

    return {
        "correlation_id": required_text(source, "correlation_id"),
        "status": "approved",
        "answer": model_output.strip(),
    }
