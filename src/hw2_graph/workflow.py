from langgraph.graph import END, START, StateGraph

from .nodes import planner_node, reviewer_node
from .router import router_logic, supervisor_node
from .state import AgentState


def build_graph(): # Build the graph.
    workflow = StateGraph(AgentState) # Create the workflow.

    workflow.add_node( # Add the supervisor node.   
        "supervisor",
        supervisor_node,
    )

    workflow.add_node( # Add the planner node.   
        "planner",
        planner_node,
    )

    workflow.add_node( # Add the reviewer node.   
        "reviewer",
        reviewer_node,
    )

    workflow.add_edge( # Add the edge from the start to the supervisor.   
        START,
        "supervisor",
    )

    workflow.add_conditional_edges( # Add the conditional edges from the supervisor to the router.   
        "supervisor",
        router_logic, # Set the router logic.
        { # Set the edges to the following nodes.
            "planner": "planner", # Set the edge to the planner.
            "reviewer": "reviewer", # Set the edge to the reviewer.
            "end": END, # Set the edge to the end.
        },
    ) # Return the workflow.

    workflow.add_edge( # Add the edge from the planner to the supervisor.   
        "planner",
        "supervisor",
    ) # Return the workflow.

    workflow.add_edge( # Add the edge from the reviewer to the supervisor.   
        "reviewer",
        "supervisor",
    ) # Return the workflow.

    return workflow.compile() # Return the compiled workflow.