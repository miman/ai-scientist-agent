"""
LangGraph pipeline definition.
Constructs the state graph with conditional edges for standard research and developer team pipelines.
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
    dev_architect_node,
    dev_backend_node,
    dev_frontend_node,
    dev_qa_node,
    dev_tester_node,
    sanitizer_node,
    archiver_node,
    increment_loop_node,
)


def _route_initial(state: PipelineState) -> str:
    """Routes from START to standard research pipeline or developer team pipeline based on pipeline_type."""
    if state.get("pipeline_type") == "dev_team":
        return "dev_architect"
    return "router"


def _should_continue_critic(state: PipelineState) -> str:
    """Conditional edge after Critic in standard research pipeline."""
    if state["approved"] or state["loop_count"] >= state["max_loops"]:
        return "accept"
    return "retry"


def _evaluate_dev_backend(state: PipelineState) -> str:
    """
    Conditional edge after Backend Developer node.
    If dev finds an architectural issue, send it back to the architect with what needs to be changed.
    Otherwise proceed to Frontend Developer.
    """
    backend_output = state.get("backend_logic", "")
    if "ARCHITECTURAL_ISSUE:" in backend_output:
        return "architectural_issue"
    return "proceed_frontend"


def _evaluate_dev_qa(state: PipelineState) -> str:
    """
    Conditional edge after QA Engineer node.
    If QA approves, proceed to Tester.
    If QA finds an issue, check loop count: if max loops exhausted, accept; else send back to developer.
    """
    if state["approved"]:
        return "proceed_tester"
    if state["loop_count"] >= state["max_loops"]:
        return "accept"
    return "reject_to_dev"


def _evaluate_dev_tester(state: PipelineState) -> str:
    """
    Conditional edge after Tester node.
    If Tester approves, accept.
    If Tester finds an issue, check loop count: if max loops exhausted, accept; else send back to developer.
    """
    if state["approved"]:
        return "accept"
    if state["loop_count"] >= state["max_loops"]:
        return "accept"
    return "reject_to_dev"


def build_graph() -> StateGraph:
    """
    Constructs and compiles the full LangGraph pipeline supporting both research and dev_team pipelines.
    """
    graph = StateGraph(PipelineState)

    # Register all nodes
    graph.add_node("router", router_node)
    graph.add_node("searcher", searcher_node)
    graph.add_node("processor", processor_node)
    graph.add_node("planner", planner_node)
    graph.add_node("expert", expert_node)
    graph.add_node("critic", critic_node)

    graph.add_node("dev_architect", dev_architect_node)
    graph.add_node("dev_backend", dev_backend_node)
    graph.add_node("dev_frontend", dev_frontend_node)
    graph.add_node("dev_qa", dev_qa_node)
    graph.add_node("dev_tester", dev_tester_node)

    graph.add_node("sanitizer", sanitizer_node)
    graph.add_node("archiver", archiver_node)
    graph.add_node("increment_loop", increment_loop_node)

    # Conditional start node routing
    graph.add_conditional_edges(
        START,
        _route_initial,
        {
            "router": "router",
            "dev_architect": "dev_architect",
        },
    )

    # --- Standard Research Pipeline Edges ---
    graph.add_edge("router", "searcher")
    graph.add_edge("searcher", "processor")
    graph.add_edge("processor", "planner")
    graph.add_edge("planner", "expert")
    graph.add_edge("expert", "critic")

    graph.add_conditional_edges(
        "critic",
        _should_continue_critic,
        {
            "accept": "sanitizer",
            "retry": "increment_loop",
        },
    )

    # Standard loop back to searcher
    graph.add_edge("increment_loop", "searcher")

    # --- Dev Team Pipeline Edges ---
    graph.add_edge("dev_architect", "dev_backend")

    graph.add_conditional_edges(
        "dev_backend",
        _evaluate_dev_backend,
        {
            "architectural_issue": "dev_architect",
            "proceed_frontend": "dev_frontend",
        },
    )

    graph.add_edge("dev_frontend", "dev_qa")

    graph.add_conditional_edges(
        "dev_qa",
        _evaluate_dev_qa,
        {
            "proceed_tester": "dev_tester",
            "reject_to_dev": "dev_backend",
            "accept": "sanitizer",
        },
    )

    graph.add_conditional_edges(
        "dev_tester",
        _evaluate_dev_tester,
        {
            "accept": "sanitizer",
            "reject_to_dev": "dev_backend",
        },
    )

    # --- Final common output path ---
    graph.add_edge("sanitizer", "archiver")
    graph.add_edge("archiver", END)

    return graph.compile()
