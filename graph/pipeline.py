"""
LangGraph pipeline definition.
Constructs the state graph with conditional edges for the critic feedback loop.
"""

from langgraph.graph import StateGraph, START, END

from graph.state import PipelineState
from graph.nodes import (
    router_node,
    searcher_node,
    processor_node,
    planner_node,
    expert_node,
    critic_node,
    sanitizer_node,
    archiver_node,
    increment_loop_node,
)


def _should_continue(state: PipelineState) -> str:
    """
    Conditional edge after the Critic node.
    Routes to 'accept' (sanitize → archive → end) or 'retry' (loop back).
    """
    if state["approved"]:
        return "accept"
    if state["loop_count"] >= state["max_loops"]:
        # Max retries exhausted — accept whatever we have
        return "accept"
    return "retry"


def build_graph() -> StateGraph:
    """
    Constructs and compiles the full LangGraph pipeline.

    Graph topology:
        START → router → searcher → processor → planner → expert → critic
                                                                      ↓
                                                              [conditional]
                                                             /             \\
                                                       accept             retry
                                                         ↓                  ↓
                                                    sanitizer        increment_loop
                                                         ↓                  ↓
                                                      archiver          searcher (loop back)
                                                         ↓
                                                        END
    """
    graph = StateGraph(PipelineState)

    # Register all nodes
    graph.add_node("router", router_node)
    graph.add_node("searcher", searcher_node)
    graph.add_node("processor", processor_node)
    graph.add_node("planner", planner_node)
    graph.add_node("expert", expert_node)
    graph.add_node("critic", critic_node)
    graph.add_node("sanitizer", sanitizer_node)
    graph.add_node("archiver", archiver_node)
    graph.add_node("increment_loop", increment_loop_node)

    # Linear edges
    graph.add_edge(START, "router")
    graph.add_edge("router", "searcher")
    graph.add_edge("searcher", "processor")
    graph.add_edge("processor", "planner")
    graph.add_edge("planner", "expert")
    graph.add_edge("expert", "critic")

    # Conditional branching after critic
    graph.add_conditional_edges(
        "critic",
        _should_continue,
        {
            "accept": "sanitizer",
            "retry": "increment_loop",
        },
    )

    # Retry loops back to searcher
    graph.add_edge("increment_loop", "searcher")

    # Accept path finishes
    graph.add_edge("sanitizer", "archiver")
    graph.add_edge("archiver", END)

    return graph.compile()
