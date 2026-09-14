import json
import time
from typing import Any

from .state import AgentState
from pydantic import ValidationError

from .schemas import PlannerProposal


def _parse_json_object(content: str) -> dict[str, Any]: # Parse the json object.
    try:
        result = json.loads(content) # Load the json object.
    except json.JSONDecodeError as error:
        raise ValueError( # Raise an error if the json object is not valid.
            "The model did not return valid JSON."
        ) from error

    if not isinstance(result, dict): # Raise an error if the json object is not a dictionary.   
        raise ValueError(
            "The model response must be a JSON object."
        )

    return result


def _updated_trace( # Update the trace.
    state: AgentState,
    *,
    node: str,
    output: dict[str, Any],
    latency_ms: float,
) -> list[dict[str, Any]]: # Return the updated trace.
    return [
        *state.get("trace", []),
        {
            "node": node,
            "output": output,
            "latency_ms": latency_ms,
            "turn_count": state.get("turn_count", 0),
        },
    ]


def planner_node(state: AgentState) -> dict[str, Any]: # Planner node.
    print("--- NODE: Planner ---")

    reviewer_feedback = state.get( # Get the reviewer feedback.
        "reviewer_feedback",
        {}
    )

    correction_text = ""

    if reviewer_feedback.get("has_issues"): # Check if the reviewer feedback has issues.
        correction_text = ( # Correct the following problems from the previous attempt.
            "\nCorrect the following problems from the "
            "previous attempt:\n"
            + json.dumps(
                reviewer_feedback.get("issues", []), # Get the issues from the reviewer feedback.
                ensure_ascii=False,
            )
        ) # Return the corrected text.

    strict_text = "" # Set the strict text to an empty string.

    if state.get("strict", False): # Check if the strict flag is set.
        strict_text = ( # Set the strict text to the following text.
            "\nPrefer at least two multi-word tags."
        )

    messages = [ # Set the messages for the planner.
        {
            "role": "system",
            "content": (
                "You are the Planner for rental housing "
                "listings. Generate exactly three relevant "
                "tags and one concise summary. Return only "
                "valid JSON with this exact structure: "
                '{"tags": ["tag one", "tag two", "tag three"], '
                '"summary": "summary text"}. '
                "Each tag must contain 3 to 30 characters. "
                "The summary must contain no more than "
                "25 words."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Task: {state['task']}\n"
                f"Title: {state['title']}\n"
                f"Content: {state['content']}"
                f"{strict_text}"
                f"{correction_text}"
            ),
        },
    ]

    start_time = time.perf_counter()

    try:
        response = state["llm"].complete(messages) # Complete the messages.
        proposal = _parse_json_object(response.content) # Parse the json object.

        validated_proposal = PlannerProposal.model_validate(
            proposal # Set the proposal to the validated proposal.
        ) # Return the validated proposal.

        proposal = validated_proposal.model_dump() # Dump the validated proposal.

        latency_ms = round( # Round the latency to 2 decimal places.
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        print( # Print the proposal.  
            json.dumps(
                proposal,
                indent=2,
                ensure_ascii=False,
            )
        )

        return { # Return the planner proposal.
            "planner_proposal": proposal,
            "reviewer_feedback": {}, # Set the reviewer feedback to an empty dictionary.
            "last_error": "", # Set the last error to an empty string.
            "trace": _updated_trace( # Update the trace.
                state,
                node="planner",
                output=proposal,
                latency_ms=latency_ms,
            ),
        }

    except (
        ValidationError, # Catch the validation error.
        ValueError, # Catch the value error.
        KeyError, # Catch the key error.
    ) as error: # Catch the error.
        latency_ms = round( # Round the latency to 2 decimal places.
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        feedback = { # Set the feedback to the following dictionary.
            "has_issues": True,
            "issues": [str(error)], # Set the issues to the error.
            "source": "planner", # Set the source to the planner.
        }

        print(f"Planner error: {error}")

        return { # Return the planner proposal.
            "planner_proposal": {}, # Set the planner proposal to an empty dictionary.
            "reviewer_feedback": feedback, # Set the reviewer feedback to the feedback.
            "last_error": str(error), # Set the last error to the error.
            "trace": _updated_trace( # Update the trace.
                state,
                node="planner", # Set the node to the planner.
                output=feedback,
                latency_ms=latency_ms,
            ),
        }


def reviewer_node(state: AgentState) -> dict[str, Any]: # Reviewer node.
    print("--- NODE: Reviewer ---")

    start_time = time.perf_counter() # Start the timer.

    if state.get("force_reviewer_issue", False): # Check if the force reviewer issue flag is set.
        feedback = { # Set the feedback to the following dictionary.
            "has_issues": True,
            "issues": [
                "Forced issue for correction-loop testing." # Set the issues to the forced issue.
            ],
            "source": "forced_test", # Set the source to the forced test.
        }

        latency_ms = round( # Round the latency to 2 decimal places.
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        print( # Print the feedback.
            json.dumps(
                feedback,
                indent=2,
                ensure_ascii=False,
            )
        )

        return {
            "reviewer_feedback": feedback, # Set the reviewer feedback to the feedback.
            "last_error": "", # Set the last error to an empty string.
            "trace": _updated_trace( # Update the trace.
                state,
                node="reviewer",
                output=feedback,
                latency_ms=latency_ms,
            ),
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You are the Reviewer. Check whether the "
                "Planner produced exactly three relevant "
                "string tags, whether each tag contains "
                "3 to 30 characters, and whether the summary "
                "contains no more than 25 words. Return only "
                "valid JSON with this structure: "
                '{"has_issues": false, "issues": []}. '
                "Set has_issues to true and list specific "
                "problems when correction is required."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Title: {state['title']}\n"
                f"Content: {state['content']}\n"
                "Planner proposal:\n"
                + json.dumps(
                    state["planner_proposal"],
                    ensure_ascii=False,
                )
            ),
        },
    ]

    try:
        response = state["llm"].complete(messages) # Complete the messages.
        feedback = _parse_json_object(response.content) # Parse the json object.

        if not isinstance(
            feedback.get("has_issues"),
            bool, # Check if the has issues is a boolean.
        ):
            raise ValueError( # Raise an error if the has issues is not a boolean.
                "Reviewer output must contain a boolean "
                "has_issues field." # Set the error message to the following message.
            )

        if not isinstance(feedback.get("issues"), list):
            raise ValueError( # Raise an error if the issues is not a list.
                "Reviewer output must contain an issues list."
            )

        latency_ms = round( # Round the latency to 2 decimal places.
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        print(
            json.dumps(
                feedback,
                indent=2,
                ensure_ascii=False,
            )
        )

        return {
            "reviewer_feedback": feedback,
            "last_error": "",
            "trace": _updated_trace(
                state,
                node="reviewer",
                output=feedback,
                latency_ms=latency_ms,
            ),
        }

    except (ValueError, KeyError) as error: # Catch the error.
        latency_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        feedback = { # Set the feedback to the following dictionary.
            "has_issues": True,
            "issues": [str(error)],
            "source": "reviewer",
        }

        print(f"Reviewer error: {error}")

        return {
            "reviewer_feedback": feedback,
            "last_error": str(error),
            "trace": _updated_trace(
                state,
                node="reviewer",
                output=feedback,
                latency_ms=latency_ms,
            ),
        }