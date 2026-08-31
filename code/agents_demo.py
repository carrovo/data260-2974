import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.model_client import ModelClient


OUTPUT_SCHEMA = """
Return only one valid JSON object using exactly this structure:

{
  "thought": "brief explanation",
  "message": "brief non-empty message",
  "data": {
    "tags": ["tag one", "tag two", "tag three"],
    "summary": "one sentence with no more than 25 words.",
    "issues": []
  }
}

Rules:
- Return exactly three distinct topical tags.
- Derive the tags and summary only from the supplied title and content.
- The summary must contain no more than 25 words.
- Do not return Markdown or code fences.
- Do not write anything outside the JSON object.
"""


def parse_json_response(content: str) -> dict[str, Any]:
    """Convert the model's JSON text into a Python dictionary."""
    try:
        result = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Model did not return valid JSON:\n{content}"
        ) from error

    if not isinstance(result, dict):
        raise ValueError("Model response must be a JSON object.")

    return result


def count_words(text: str) -> int:
    """Count words in the summary."""
    return len(re.findall(r"\b[\w'-]+\b", text))


def validate_final_output(result: dict[str, Any]) -> None:
    """Check the required final JSON fields."""
    data = result.get("data")

    if not isinstance(data, dict):
        raise ValueError("Final output is missing data.")

    tags = data.get("tags")
    summary = data.get("summary")

    if not isinstance(tags, list) or len(tags) != 3:
        raise ValueError(
            "Final output must contain exactly three tags."
        )

    if not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise ValueError("Every tag must be a non-empty string.")

    normalized_tags = {
        tag.strip().lower()
        for tag in tags
    }

    if len(normalized_tags) != 3:
        raise ValueError("The three tags must be distinct.")

    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("The summary must be a non-empty string.")

    if count_words(summary) > 25:
        raise ValueError(
            "The summary must contain no more than 25 words."
        )


def call_agent(
    model: ModelClient,
    role_instructions: str,
    task: str
) -> dict[str, Any]:
    """Send one role-specific request through the model adapter."""
    response = model.complete(
        [
            {
                "role": "system",
                "content": role_instructions
            },
            {
                "role": "user",
                "content": task
            }
        ]
    )

    return parse_json_response(response.content)


def run_pipeline(
    title: str,
    content: str,
    email: str,
    model_name: str,
    temperature: float,
    strict: bool
) -> dict[str, Any]:
    """Run Planner, Reviewer, and Finalizer in sequence."""
    model = ModelClient(
        model_name=model_name,
        temperature=temperature,
        output_format="json",
        reasoning=False
)

    strict_instruction = ""

    if strict:
        strict_instruction = (
            "\nPrefer at least two multi-word tags."
        )

    domain_input = f"""
Title:
{title}

Content:
{content}
"""

    start_time = time.perf_counter()

    planner = call_agent(
        model=model,
        role_instructions=(
            "You are the Planner. Propose exactly three distinct "
            "topical tags and a one-sentence summary based only on "
            "the supplied title and content."
        ),
        task=(
            domain_input
            + strict_instruction
            + OUTPUT_SCHEMA
        )
    )

    reviewer = call_agent(
        model=model,
        role_instructions=(
            "You are the Reviewer. Check the Planner output. "
            "Correct generic or irrelevant tags, duplicate tags, "
            "and summaries longer than 25 words. List corrections "
            "in data.issues; otherwise use an empty list."
        ),
        task=(
            domain_input
            + "\nPlanner output:\n"
            + json.dumps(
                planner,
                ensure_ascii=False
            )
            + strict_instruction
            + OUTPUT_SCHEMA
        )
    )

    finalizer = call_agent(
        model=model,
        role_instructions=(
            "You are the Finalizer. Use the Planner and Reviewer "
            "outputs to produce the final answer. Return exactly "
            "three tags and one summary of at most 25 words. "
            "Set data.issues to an empty list."
        ),
        task=(
            domain_input
            + "\nPlanner output:\n"
            + json.dumps(
                planner,
                ensure_ascii=False
            )
            + "\nReviewer output:\n"
            + json.dumps(
                reviewer,
                ensure_ascii=False
            )
            + strict_instruction
            + OUTPUT_SCHEMA
        )
    )

    finalizer.setdefault("data", {})["issues"] = []

    validate_final_output(finalizer)

    latency_ms = round(
        (time.perf_counter() - start_time) * 1000,
        2
    )

    publish_output = {
        "title": title,
        "email": email,
        "content": content,
        "agents": {
            "transcript": [
                {
                    "role": "Planner",
                    "content": planner
                },
                {
                    "role": "Reviewer",
                    "content": reviewer
                }
            ],
            "final": finalizer["data"]
        },
        "model": model_name,
        "temperature": temperature,
        "latencyMs": latency_ms,
        "submissionDate": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime()
        )
    }

    print("\n--- Planner Output ---")
    print(
        json.dumps(
            planner,
            indent=2,
            ensure_ascii=False
        )
    )

    print("\n--- Reviewer Output ---")
    print(
        json.dumps(
            reviewer,
            indent=2,
            ensure_ascii=False
        )
    )

    print("\n--- Finalized Output ---")
    print(
        json.dumps(
            finalizer,
            indent=2,
            ensure_ascii=False
        )
    )

    print("\n--- Publish Output ---")
    print(
        json.dumps(
            publish_output,
            indent=2,
            ensure_ascii=False
        )
    )

    return publish_output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the HW1 local agent pipeline."
    )

    parser.add_argument(
        "--title",
        required=True
    )
    parser.add_argument(
        "--content",
        required=True
    )
    parser.add_argument(
        "--email",
        required=True
    )
    parser.add_argument(
        "--model",
        default="qwen3:8b"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0
    )
    parser.add_argument(
        "--strict",
        action="store_true"
    )

    args = parser.parse_args()

    run_pipeline(
        title=args.title,
        content=args.content,
        email=args.email,
        model_name=args.model,
        temperature=args.temperature,
        strict=args.strict
    )


if __name__ == "__main__":
    main()