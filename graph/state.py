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

    # --- Router output ---
    specialty: str

    # --- Loop tracking ---
    loop_count: int
    max_loops: int
    pipeline_history: list[str]
    research_log: list[str]

    # --- Intermediate artifacts ---
    raw_search_data: Optional[str]
    processed_facts: Optional[str]
    accumulated_context: str
    blueprint: str
    solution: str

    # --- Critic output ---
    approved: bool
    critic_feedback: str

    # --- Final output ---
    final_solution: Optional[str]
    db_id: Optional[int]
