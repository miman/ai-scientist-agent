"""
Graph node functions — each one receives PipelineState and returns a partial state update.
LangGraph merges the returned dict into the existing state automatically.
"""

import os
import sqlite3
from langchain_core.messages import SystemMessage, HumanMessage

from graph.state import PipelineState
from graph.llm import get_llm
from graph.tools import tool_web_search, tool_run_in_docker
from prompts.prompts import get_prompt


# ─── Database config ───
DB_DIR = os.getenv("DB_DIR", "/app/db_data")
DB_PATH = os.path.join(DB_DIR, "agent_archive.db")


def _invoke_llm(agent_name: str, system_prompt: str, user_content: str) -> str:
    """Helper to invoke the LLM for a given agent role and return the text response."""
    llm = get_llm(agent_name)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]
    response = llm.invoke(messages)
    return response.content


# ─────────────────────────────────────────────
# NODE: Router
# ─────────────────────────────────────────────
def router_node(state: PipelineState) -> dict:
    """Classifies the user prompt into a domain specialty."""
    print("🎯 [Router] Classifying domain...", flush=True)

    system_prompt = (
        "You are an expert dispatcher router.\n"
        "Analyze the user query and classify it into EXACTLY one of these specialties:\n"
        "- code (software development, scripting, debugging, databases, configs)\n"
        "- finance (stock analysis, accounting, valuation, market economics)\n"
        "- medical (health, medicine, biological sciences, drug interactions)\n"
        "- general (any other topics)\n\n"
        "Output ONLY the single classification word. No other text."
    )
    classification = _invoke_llm("planner", system_prompt, state["prompt"])
    specialty = classification.strip().lower()

    valid = ["code", "finance", "medical", "general"]
    for s in valid:
        if s in specialty:
            print(f"🎯 [Router] Routed to: '{s}'", flush=True)
            return {"specialty": s}

    print("🎯 [Router] Fallback: 'general'", flush=True)
    return {"specialty": "general"}


# ─────────────────────────────────────────────
# NODE: Searcher
# ─────────────────────────────────────────────
def searcher_node(state: PipelineState) -> dict:
    """Decides if web search is needed and fetches data if so."""
    print(f"🕵️ [Searcher] Loop {state['loop_count']} — assessing need for web data...", flush=True)

    system_prompt = get_prompt("searcher", specialty=state["specialty"])
    history_context = "\n\n".join(state["pipeline_history"])

    user_content = f"TARGET REQUEST:\n{state['prompt']}"
    if history_context:
        user_content += f"\n\nPAST EXECUTION HISTORY:\n{history_context}"

    raw_decision = _invoke_llm("searcher", system_prompt, user_content).strip()

    # Parse the decision
    if "DECISION: NO" in raw_decision or raw_decision.strip().upper() == "NO":
        print("💡 [Searcher] No web search required.", flush=True)
        return {"raw_search_data": None}

    if "SEARCH_QUERY:" in raw_decision:
        search_query = raw_decision.split("SEARCH_QUERY:")[-1].strip().strip('"').strip("'")
        if search_query:
            print(f"🌐 [Searcher] Query: '{search_query}'", flush=True)
            return {"raw_search_data": tool_web_search(search_query)}

    # Fallback parsing
    fallback_query = (
        raw_decision.replace("DECISION: YES", "")
        .replace("|", "")
        .replace("DECISION:", "")
        .strip()
        .strip('"')
        .strip("'")
    )
    if fallback_query and len(fallback_query) > 1:
        print(f"🌐 [Searcher] Fallback query: '{fallback_query}'", flush=True)
        return {"raw_search_data": tool_web_search(fallback_query)}

    print("⚠️ [Searcher] Unparseable response. Using prompt as query.", flush=True)
    return {"raw_search_data": tool_web_search(state["prompt"])}


# ─────────────────────────────────────────────
# NODE: Processor
# ─────────────────────────────────────────────
def processor_node(state: PipelineState) -> dict:
    """Extracts structured facts from raw web data and appends to the research log."""
    if not state.get("raw_search_data"):
        return {"processed_facts": None}

    print("🧹 [Processor] Extracting structured facts...", flush=True)
    system_prompt = get_prompt("processor", specialty=state["specialty"])
    processed = _invoke_llm("processor", system_prompt, state["raw_search_data"])

    print(f"\n[=== PROCESSOR OUTPUT ===]\n{processed}\n[========================]\n", flush=True)

    # Append to research log
    research_log = list(state.get("research_log", []))
    if processed.strip() and "error" not in processed.lower():
        research_log.append(processed)

    accumulated = "\n---\n".join(research_log) if research_log else "No external data collected yet."

    return {
        "processed_facts": processed,
        "research_log": research_log,
        "accumulated_context": accumulated,
    }


# ─────────────────────────────────────────────
# NODE: Planner
# ─────────────────────────────────────────────
def planner_node(state: PipelineState) -> dict:
    """Creates a structured blueprint for the Expert agent."""
    print("📋 [Planner] Building blueprint...", flush=True)

    system_prompt = get_prompt("planner", specialty=state["specialty"])
    accumulated = state.get("accumulated_context", "No external data collected yet.")
    user_content = f"ACCUMULATED KNOWLEDGE:\n{accumulated}\n\nORIGINAL REQUEST:\n{state['prompt']}"

    blueprint = _invoke_llm("planner", system_prompt, user_content)

    # Append rejection history if any
    history_context = "\n\n".join(state["pipeline_history"])
    if history_context:
        blueprint += f"\n\nCRITICAL ISSUES TO CORRECT FROM PREVIOUS ATTEMPTS:\n{history_context}"

    print(f"\n[=== BLUEPRINT ===]\n{blueprint}\n[=================]\n", flush=True)
    return {"blueprint": blueprint}


# ─────────────────────────────────────────────
# NODE: Expert
# ─────────────────────────────────────────────
def expert_node(state: PipelineState) -> dict:
    """Generates the production-ready solution."""
    print("🧠 [Expert] Generating solution...", flush=True)

    system_prompt = get_prompt("expert", specialty=state["specialty"])
    accumulated = state.get("accumulated_context", "No external data collected yet.")
    user_content = (
        f"ACCUMULATED KNOWLEDGE LOG:\n{accumulated}\n\n"
        f"BLUEPRINT MATRIX:\n{state['blueprint']}\n\n"
        f"TARGET USER PROMPT:\n{state['prompt']}"
    )

    solution = _invoke_llm("expert", system_prompt, user_content)

    print(f"\n[=== EXPERT SOLUTION ===]\n{solution}\n[=======================]\n", flush=True)
    return {"solution": solution}


# ─────────────────────────────────────────────
# NODE: Critic
# ─────────────────────────────────────────────
def critic_node(state: PipelineState) -> dict:
    """Audits the solution and decides APPROVED or REJECTED."""
    loop = state["loop_count"]
    print(f"⚖️ [Critic] Auditing solution (attempt {loop})...", flush=True)

    system_prompt = get_prompt("critic", specialty=state["specialty"])
    user_content = (
        f"ORIGINAL USER TARGET:\n{state['prompt']}\n\n"
        f"PROPOSED SOLUTION:\n{state['solution']}"
    )

    review = _invoke_llm("critic", system_prompt, user_content)

    print(f"\n[=== CRITIC AUDIT (Loop {loop}) ===]\n{review}\n[=================================]\n", flush=True)

    approved = "APPROVED" in review.upper() and "REJECTED" not in review.upper()
    return {"approved": approved, "critic_feedback": review}


# ─────────────────────────────────────────────
# DEV TEAM NODES
# ─────────────────────────────────────────────

def dev_architect_node(state: PipelineState) -> dict:
    """Architect node: Creates/refines system architecture."""
    loop = state["loop_count"]
    print(f"🏛️ [Architect] Designing system architecture (Loop {loop})...", flush=True)

    system_prompt = get_prompt("dev_architect", specialty=state["specialty"])
    
    user_content = f"USER REQUEST:\n{state['prompt']}"
    if state.get("accumulated_context") and state["accumulated_context"] != "No external data collected yet.":
        user_content += f"\n\nRESEARCH CONTEXT:\n{state['accumulated_context']}"
    
    if state.get("architecture"):
        user_content += f"\n\nPREVIOUS ARCHITECTURE:\n{state['architecture']}"

    history_context = "\n\n".join(state["pipeline_history"])
    if history_context:
        user_content += f"\n\nISSUES & FEEDBACK TO RESOLVE IN ARCHITECTURE:\n{history_context}"

    architecture = _invoke_llm("dev_architect", system_prompt, user_content)
    print(f"\n[=== ARCHITECTURE SPECIFICATION ===]\n{architecture}\n[==================================]\n", flush=True)
    return {"architecture": architecture}


def dev_backend_node(state: PipelineState) -> dict:
    """Backend Developer node: Implements backend logic using architecture."""
    loop = state["loop_count"]
    print(f"⚙️ [Backend Dev] Writing backend logic (Loop {loop})...", flush=True)

    system_prompt = get_prompt("dev_backend", specialty=state["specialty"])

    user_content = (
        f"USER REQUEST:\n{state['prompt']}\n\n"
        f"ARCHITECTURE SPECIFICATION:\n{state['architecture']}"
    )

    if state.get("qa_feedback"):
        user_content += f"\n\nQA FEEDBACK TO FIX:\n{state['qa_feedback']}"

    if state.get("tester_feedback"):
        user_content += f"\n\nTESTER FEEDBACK TO FIX:\n{state['tester_feedback']}"

    history_context = "\n\n".join(state["pipeline_history"])
    if history_context:
        user_content += f"\n\nREPAIR HISTORY:\n{history_context}"

    backend_logic = _invoke_llm("dev_backend", system_prompt, user_content)
    print(f"\n[=== BACKEND LOGIC ===]\n{backend_logic}\n[=====================]\n", flush=True)

    combined_solution = f"### Architecture\n{state['architecture']}\n\n### Backend Logic\n{backend_logic}"
    return {"backend_logic": backend_logic, "solution": combined_solution}


def dev_frontend_node(state: PipelineState) -> dict:
    """Frontend Developer node: Implements UI using backend logic and architecture."""
    loop = state["loop_count"]
    print(f"🎨 [Frontend Dev] Writing frontend UI (Loop {loop})...", flush=True)

    system_prompt = get_prompt("dev_frontend", specialty=state["specialty"])

    user_content = (
        f"USER REQUEST:\n{state['prompt']}\n\n"
        f"ARCHITECTURE SPECIFICATION:\n{state['architecture']}\n\n"
        f"BACKEND LOGIC & APIs:\n{state['backend_logic']}"
    )

    history_context = "\n\n".join(state["pipeline_history"])
    if history_context:
        user_content += f"\n\nREPAIR HISTORY:\n{history_context}"

    frontend_code = _invoke_llm("dev_frontend", system_prompt, user_content)
    print(f"\n[=== FRONTEND CODE ===]\n{frontend_code}\n[=====================]\n", flush=True)

    combined_solution = (
        f"### Architecture\n{state['architecture']}\n\n"
        f"### Backend Logic\n{state['backend_logic']}\n\n"
        f"### Frontend UI\n{frontend_code}"
    )
    return {"frontend_code": frontend_code, "solution": combined_solution}


def dev_qa_node(state: PipelineState) -> dict:
    """QA Engineer node: Validates full solution against requirements."""
    loop = state["loop_count"]
    print(f"🔍 [QA Engineer] Validating code & functional requirements (Loop {loop})...", flush=True)

    system_prompt = get_prompt("dev_qa", specialty=state["specialty"])

    user_content = (
        f"ORIGINAL USER REQUEST:\n{state['prompt']}\n\n"
        f"ARCHITECTURE:\n{state['architecture']}\n\n"
        f"BACKEND LOGIC:\n{state['backend_logic']}\n\n"
        f"FRONTEND CODE:\n{state['frontend_code']}"
    )

    qa_review = _invoke_llm("dev_qa", system_prompt, user_content)
    print(f"\n[=== QA REVIEW (Loop {loop}) ===]\n{qa_review}\n[==============================]\n", flush=True)

    approved = "APPROVED" in qa_review.upper() and "REJECTED" not in qa_review.upper()
    return {"approved": approved, "qa_feedback": qa_review, "critic_feedback": qa_review}


def dev_tester_node(state: PipelineState) -> dict:
    """
    Tester node: Builds, deploys, runs the generated code in a Docker container,
    captures logs/output, and performs audit verification based on container output.
    """
    loop = state["loop_count"]
    print(f"🧪 [Tester] Deploying, running & testing code inside Docker container (Loop {loop})...", flush=True)

    # Combine backend & frontend code to run/test
    code_payload = f"{state.get('backend_logic', '')}\n\n{state.get('frontend_code', '')}"

    # Determine execution language
    language = "python"
    if "node" in code_payload.lower() or "typescript" in state["prompt"].lower() or "javascript" in state["prompt"].lower():
        language = "javascript"

    # Execute container & capture logs
    docker_logs = tool_run_in_docker(code_payload, language=language)
    print(f"\n[=== DOCKER CONTAINER EXECUTION LOGS ===]\n{docker_logs}\n[=======================================]\n", flush=True)

    system_prompt = get_prompt("dev_tester", specialty=state["specialty"])

    user_content = (
        f"ORIGINAL USER REQUEST:\n{state['prompt']}\n\n"
        f"ARCHITECTURE:\n{state['architecture']}\n\n"
        f"BACKEND LOGIC:\n{state['backend_logic']}\n\n"
        f"FRONTEND CODE:\n{state['frontend_code']}\n\n"
        f"ACTUAL CONTAINER EXECUTION LOGS & OUTPUT:\n{docker_logs}"
    )

    tester_review = _invoke_llm("dev_tester", system_prompt, user_content)
    print(f"\n[=== TESTER REVIEW (Loop {loop}) ===]\n{tester_review}\n[=================================]\n", flush=True)

    approved = "APPROVED" in tester_review.upper() and "REJECTED" not in tester_review.upper()
    
    combined_solution = (
        f"### Architecture\n{state['architecture']}\n\n"
        f"### Backend Logic\n{state['backend_logic']}\n\n"
        f"### Frontend UI\n{state['frontend_code']}\n\n"
        f"### Container Test Logs & Output\n```text\n{docker_logs}\n```\n\n"
        f"### Tester Audit Verification\n{tester_review}"
    )

    # Automatically increment loop counter and append repair history when rejected
    history = list(state.get("pipeline_history", []))
    new_loop_count = state["loop_count"]
    if not approved:
        new_loop_count += 1
        history.append(f"Tester Loop {state['loop_count']} Rejected:\nDocker Logs:\n{docker_logs}\nFeedback:\n{tester_review}")

    return {
        "approved": approved,
        "loop_count": new_loop_count,
        "pipeline_history": history,
        "docker_logs": docker_logs,
        "tester_feedback": f"Docker Execution Logs:\n{docker_logs}\n\nTester Audit:\n{tester_review}",
        "critic_feedback": f"Docker Execution Logs:\n{docker_logs}\n\nTester Audit:\n{tester_review}",
        "solution": combined_solution,
    }


# ─────────────────────────────────────────────
# NODE: Sanitizer
# ─────────────────────────────────────────────
def sanitizer_node(state: PipelineState) -> dict:
    """Cleans the approved solution of conversational filler."""
    print("✨ [Sanitizer] Cleaning output...", flush=True)

    system_prompt = get_prompt("sanitizer", specialty=state["specialty"])
    polished = _invoke_llm("sanitizer", system_prompt, state["solution"])
    return {"final_solution": polished}


# ─────────────────────────────────────────────
# NODE: Archiver
# ─────────────────────────────────────────────
def archiver_node(state: PipelineState) -> dict:
    """Persists the final solution to SQLite."""
    print("🗄️ [Archiver] Saving to database...", flush=True)

    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO solutions (prompt, solution) VALUES (?, ?)",
        (state["prompt"], state["final_solution"]),
    )
    db_id = cursor.lastrowid
    conn.commit()
    conn.close()

    print(f"🗄️ [Archiver] Saved as ID: {db_id}", flush=True)
    return {"db_id": db_id}


# ─────────────────────────────────────────────
# NODE: Increment Loop (transition helper)
# ─────────────────────────────────────────────
def increment_loop_node(state: PipelineState) -> dict:
    """Appends critic feedback to history and bumps the loop counter."""
    history = list(state["pipeline_history"])
    history.append(
        f"Attempt {state['loop_count']} Rejected.\nFeedback:\n{state['critic_feedback']}"
    )
    return {
        "loop_count": state["loop_count"] + 1,
        "pipeline_history": history,
    }
