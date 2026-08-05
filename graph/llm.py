"""
LLM client configuration using LangChain's Ollama integration.
"""

import os
from langchain_ollama import ChatOllama


# Default model for all agents (override per-agent via env vars if needed)
BASE_MODEL = os.getenv("BASE_MODEL", "nemotron-3-nano:4b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")


MODEL_CONFIG = {
    "searcher": os.getenv("MODEL_SEARCHER", BASE_MODEL),
    "processor": os.getenv("MODEL_PROCESSOR", BASE_MODEL),
    "planner": os.getenv("MODEL_PLANNER", BASE_MODEL),
    "expert": os.getenv("MODEL_EXPERT", BASE_MODEL),
    "critic": os.getenv("MODEL_CRITIC", BASE_MODEL),
    "sanitizer": os.getenv("MODEL_SANITIZER", BASE_MODEL),
}


def get_llm(agent_name: str) -> ChatOllama:
    """
    Returns a ChatOllama instance configured for the given agent role.
    Uses zero temperature for deterministic outputs.
    """
    return ChatOllama(
        model=MODEL_CONFIG.get(agent_name, BASE_MODEL),
        base_url=OLLAMA_URL,
        temperature=0.0,
        keep_alive="30m",
    )
