import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.model_client import ModelClient


AGENT_PATH = REPOSITORY_ROOT / "AGENT.md"


def history_length(
    history: list[dict[str, str]]
) -> int:
    """Return the serialized conversation-history length."""
    serialized = json.dumps(
        history,
        ensure_ascii=False
    )

    return len(serialized)


def follows_bullet_only(text: str) -> bool:
    """Check whether every non-empty line begins with '- '."""
    non_empty_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    return (
        bool(non_empty_lines)
        and all(
            line.startswith("- ")
            for line in non_empty_lines
        )
    )


def print_stats(
    turn_count: int,
    cumulative_input_tokens: int,
    cumulative_output_tokens: int,
    history: list[dict[str, str]]
) -> None:
    """Print statistics without changing conversation history."""
    print("\n--- Statistics ---")
    print(f"Turn count: {turn_count}")
    print(
        "Cumulative input tokens:",
        cumulative_input_tokens
    )
    print(
        "Cumulative output tokens:",
        cumulative_output_tokens
    )
    print(
        "Cumulative total tokens:",
        cumulative_input_tokens
        + cumulative_output_tokens
    )
    print(
        "Serialized history length:",
        history_length(history)
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HW1 interactive model client."
    )

    parser.add_argument(
        "--model",
        default="qwen3:8b"
    )

    args = parser.parse_args()

    agent_instructions = AGENT_PATH.read_text(
        encoding="utf-8"
    )

    client = ModelClient(
        model_name=args.model,
        temperature=0.0,
        reasoning=False
    )

    history: list[dict[str, str]] = []

    turn_count = 0
    cumulative_input_tokens = 0
    cumulative_output_tokens = 0

    print("HW1 Code Review Client")
    print("Commands: /stats, /exit")
    print(f"Model: {args.model}")

    while True:
        user_input = input("\nYou> ").strip()

        if not user_input:
            continue

        if user_input.lower() == "/exit":
            break

        if user_input.lower() == "/stats":
            print_stats(
                turn_count=turn_count,
                cumulative_input_tokens=(
                    cumulative_input_tokens
                ),
                cumulative_output_tokens=(
                    cumulative_output_tokens
                ),
                history=history
            )
            continue

        messages = [
            {
                "role": "system",
                "content": agent_instructions
            },
            *history,
            {
                "role": "user",
                "content": user_input
            }
        ]

        result = client.complete(messages)

        history.append(
            {
                "role": "user",
                "content": user_input
            }
        )
        history.append(
            {
                "role": "assistant",
                "content": result.content
            }
        )

        turn_count += 1
        cumulative_input_tokens += result.input_tokens
        cumulative_output_tokens += result.output_tokens

        print("\nModel>")
        print(result.content)

        print("\nToken usage:")
        print(
            f"Input tokens: {result.input_tokens}"
        )
        print(
            f"Output tokens: {result.output_tokens}"
        )
        print(
            f"Total tokens: {result.total_tokens}"
        )

        if follows_bullet_only(result.content):
            print("Bullet-only check: PASS")
        else:
            print("Bullet-only check: FAIL")

    print("\n--- Final Cumulative Statistics ---")
    print(f"Turn count: {turn_count}")
    print(
        "Cumulative input tokens:",
        cumulative_input_tokens
    )
    print(
        "Cumulative output tokens:",
        cumulative_output_tokens
    )
    print(
        "Cumulative total tokens:",
        cumulative_input_tokens
        + cumulative_output_tokens
    )


if __name__ == "__main__":
    main()