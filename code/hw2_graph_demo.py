import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1] # Get the repository root.

if str(REPOSITORY_ROOT) not in sys.path: # Check if the repository root is not in the system path.
    sys.path.insert(0, str(REPOSITORY_ROOT)) # Insert the repository root into the system path.


from src.hw2_graph.state import create_initial_state
from src.hw2_graph.workflow import build_graph
from src.model_client import ModelClient


DEFAULT_TITLE = "Studio Near SJSU"

DEFAULT_CONTENT = (
    "This furnished studio is located within walking "
    "distance of the SJSU campus."
)

DEFAULT_EMAIL = "xuanhua.li@sjsu.edu"


def print_stream_update( # Print the stream update.
    event: dict[str, Any]
) -> None:
    visible_event: dict[str, Any] = {} # Create a dictionary to store the visible event.

    for node_name, update in event.items(): # Iterate over the event.
        if not isinstance(update, dict): # Check if the update is a dictionary.
            visible_event[node_name] = update # Set the visible event to the update.    
            continue # Continue the loop.

        visible_event[node_name] = { # Set the visible event to the update.
            key: value # Set the key to the value.
            for key, value in update.items() # Iterate over the update.
            if key not in {"trace", "llm"} # Check if the key is not trace or llm.
        } # Return the visible event.

    print("\n--- STREAM UPDATE ---")
    print(
        json.dumps(
            visible_event,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )


def run_graph( # Run the graph.
    *,
    title: str,
    content: str,
    email: str,
    model_name: str,
    temperature: float,
    strict: bool,
    max_turns: int,
    force_reviewer_issue: bool,
) -> dict[str, Any]:
    model_client = ModelClient( # Create the model client.
        model_name=model_name,
        temperature=temperature,
        output_format="json",
        reasoning=False,
    )

    initial_state = create_initial_state( # Create the initial state.
        title=title,
        content=content,
        email=email,
        strict=strict,
        llm=model_client,
        max_turns=max_turns,
        force_reviewer_issue=force_reviewer_issue,
    )

    graph = build_graph()
    final_state = dict(initial_state) # Create a dictionary to store the final state.

    start_time = time.perf_counter() # Start the timer.

    for event in graph.stream( # Stream the graph.
        initial_state,
        stream_mode="updates",
    ): # Iterate over the event.
        print_stream_update(event)

        for update in event.values():
            if isinstance(update, dict):
                final_state.update(update)

    total_latency_ms = round( # Round the total latency to 2 decimal places.
        (time.perf_counter() - start_time) * 1000,
        2,
    )

    final_output = {
        "status": final_state.get("status"),
        "turn_count": final_state.get("turn_count"),
        "max_turns": final_state.get("max_turns"),
        "planner_proposal": final_state.get(
            "planner_proposal",
            {},
        ),
        "reviewer_feedback": final_state.get(
            "reviewer_feedback",
            {},
        ),
        "last_error": final_state.get(
            "last_error",
            "",
        ),
        "total_latency_ms": total_latency_ms,
    }

    print("\n=== FINAL GRAPH RESULT ===")
    print(
        json.dumps(
            final_output,
            indent=2,
            ensure_ascii=False,
        )
    )

    return final_output


def main() -> None: # Main function.
    parser = argparse.ArgumentParser( # Create the argument parser.
        description=( # Set the description to the following message.
            "Run the DATA 260 Homework 2 "
            "stateful LangGraph workflow."
        )
    )

    parser.add_argument( # Add the title argument.
        "--title",
        default=DEFAULT_TITLE,
    )

    parser.add_argument( # Add the content argument.
        "--content",
        default=DEFAULT_CONTENT,
    )

    parser.add_argument( # Add the email argument.
        "--email",
        default=DEFAULT_EMAIL,
    )

    parser.add_argument( # Add the model argument.
        "--model",
        default="qwen3:8b",
    )

    parser.add_argument( # Add the temperature argument.
        "--temperature",
        type=float,
        default=0.0,
    )

    parser.add_argument( # Add the max turns argument.
        "--max-turns",
        type=int,
        default=4,
    )

    parser.add_argument( # Add the strict argument.
        "--strict",
        action="store_true",
    )

    parser.add_argument( # Add the force reviewer issue argument.
        "--force-reviewer-issue",
        action="store_true",
    )

    args = parser.parse_args() # Parse the arguments.

    if args.max_turns < 1: # Check if the max turns is less than 1.
        parser.error("--max-turns must be at least 1")

    run_graph( # Run the graph.
        title=args.title,
        content=args.content,
        email=args.email,
        model_name=args.model,
        temperature=args.temperature,
        strict=args.strict,
        max_turns=args.max_turns,
        force_reviewer_issue=args.force_reviewer_issue,
    )


if __name__ == "__main__":
    main()