from typing import Any, Literal, TypedDict


GraphStatus = Literal[
    "running",
    "completed",
    "abandoned"
]# GraphStatus is the status of the graph.


class AgentState(TypedDict, total=False): # AgentState is the state of the agent.
    title: str 
    content: str
    email: str
    strict: bool
    task: str
    llm: Any

    planner_proposal: dict[str, Any] # Planner proposal is the proposal from the planner.
    reviewer_feedback: dict[str, Any] # Reviewer feedback is the feedback from the reviewer.

    turn_count: int
    max_turns: int
    status: GraphStatus

    last_error: str
    force_reviewer_issue: bool
    trace: list[dict[str, Any]]


def create_initial_state( # Create the initial state of the agent.
    *,
    title: str,
    content: str,
    email: str,
    strict: bool,
    llm: Any,
    max_turns: int,
    force_reviewer_issue: bool = False,
) -> AgentState:
    return AgentState( # Return the initial state of the agent.
        title=title,
        content=content,
        email=email,
        strict=strict,
        task=(
            "Generate exactly three relevant tags and a "
            "summary containing no more than 25 words."
        ),
        llm=llm, # Set the llm.
        planner_proposal={},
        reviewer_feedback={},
        turn_count=0,
        max_turns=max_turns,
        status="running",
        last_error="",
        force_reviewer_issue=force_reviewer_issue,
        trace=[],
    ) # Return the initial state of the agent.