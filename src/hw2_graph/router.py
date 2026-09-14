from typing import Any, Literal

from .state import AgentState


RouteName = Literal[
    "planner",
    "reviewer",
    "end"
]


def _supervisor_trace( # Update the trace.
    state: AgentState,
    *,
    action: str,
    turn_count: int,
) -> list[dict[str, Any]]: # Return the updated trace.
    return [
        *state.get("trace", []),
        {
            "node": "supervisor",
            "action": action,
            "turn_count": turn_count,
        },
    ]


def supervisor_node( # Supervisor node.
    state: AgentState
) -> dict[str, Any]:
    print("--- NODE: Supervisor ---")

    current_turn = state.get("turn_count", 0) # Get the current turn.
    max_turns = state.get("max_turns", 2) # Get the max turns.      

    proposal = state.get("planner_proposal", {}) # Get the planner proposal.
    feedback = state.get("reviewer_feedback", {}) # Get the reviewer feedback.

    if state.get("status") in { # Check if the status is completed or abandoned.
        "completed",
        "abandoned",
    }:
        return {} # Return an empty dictionary.

    if proposal and feedback:
        if not feedback.get("has_issues", False): # Check if the feedback has issues.
            print("Supervisor decision: task completed")

            return { # Return the completed status.
                "status": "completed",
                "trace": _supervisor_trace(
                    state,
                    action="complete", # Set the action to complete.
                    turn_count=current_turn,
                ),
            } # Return the completed status.

    needs_planner = ( # Check if the needs planner is true.
        not proposal
        or feedback.get("has_issues", False)
    ) # Return the needs planner.

    if needs_planner: # Check if the needs planner is true.
        if current_turn >= max_turns:
            print( # Print the turn ceiling reached.
                "Supervisor decision: turn ceiling reached"
            )

            return { # Return the abandoned status.
                "status": "abandoned", # Set the status to abandoned.   
                "last_error": ( # Set the last error to the following message.
                    "The graph reached the turn ceiling "
                    "before producing an approved proposal."
                ), # Return the last error.
                "trace": _supervisor_trace( # Update the trace.
                    state,
                    action="turn_ceiling", # Set the action to turn ceiling.
                    turn_count=current_turn,
                ),
            } # Return the abandoned status.

        next_turn = current_turn + 1 # Set the next turn to the current turn plus 1.

        print( # Print the supervisor decision. of planner attempt.
            f"Supervisor decision: planner attempt "
            f"{next_turn} of {max_turns}"
        ) # Return the supervisor decision of planner attempt.

        return { # Return the supervisor decision of planner attempt.   
            "turn_count": next_turn, # Set the turn count to the next turn. 
            "status": "running", # Set the status to running.
            "trace": _supervisor_trace( # Update the trace.
                state,
                action="route_to_planner", # Set the action to route to planner.
                turn_count=next_turn,
            ), # Return the supervisor decision of planner attempt. 
        }

    print("Supervisor decision: route to reviewer")

    return { # Return the supervisor decision of reviewer attempt.   
        "trace": _supervisor_trace(
            state,
            action="route_to_reviewer", # Set the action to route to reviewer.
            turn_count=current_turn,
        ),
    }


def router_logic(state: AgentState) -> RouteName: # Router logic.
    status = state.get("status", "running")

    if status in {"completed", "abandoned"}:
        return "end"

    proposal = state.get("planner_proposal", {})
    feedback = state.get("reviewer_feedback", {})

    if not proposal:
        return "planner"

    if not feedback:
        return "reviewer"

    if feedback.get("has_issues", False):
        return "planner"

    return "end"