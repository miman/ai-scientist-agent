"""
Typed state schema for the LangGraph pipeline.
This is the single shared state object that flows through every node in the graph.
"""

from typing import Optional
from typing_extensions import TypedDict


class PipelineState(TypedDict):
    """State that travels through the entire agent graph."""

    # --- Inputs ---
    prompt: str
    webhook_url: Optional[str]
    pipeline_type: str  # "research" (default standard) or "dev_team"

    # --- Router output ---
    specialty: str

    # --- Loop tracking ---
    loop_count: int
    max_loops: int
    pipeline_history: list[str]
    research_log: list[str]

    # --- Intermediate artifacts (Standard Pipeline) ---
    raw_search_data: Optional[str]
    processed_facts: Optional[str]
    accumulated_context: str
    blueprint: str
    solution: str

    # --- Intermediate artifacts (Dev Team Pipeline) ---
    architecture: str
    backend_logic: str
    frontend_code: str
    qa_feedback: str
    tester_feedback: str
    docker_logs: str

    # --- Critic / QA / Tester output ---
    approved: bool
    critic_feedback: str

    # --- Final output ---
    final_solution: Optional[str]
    db_id: Optional[int]
