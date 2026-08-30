"""
FastAPI application that exposes the LangGraph multi-agent pipeline via REST endpoints.
"""

import os
import sqlite3
import threading
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from graph import build_graph


app = FastAPI(title="AI Adaptive Multi-Agent Problem Solver API (LangGraph)")

# ─── Database ───
DB_DIR = os.getenv("DB_DIR", "/app/db_data")
DB_PATH = os.path.join(DB_DIR, "agent_archive.db")

# Fetch MAX_LOOPS from environment variable with a default of 3
MAX_LOOPS = int(os.getenv("MAX_LOOPS", 3))

# In-memory tracking for active/completed runs
LIVE_TRACKING: dict = {}


def init_sqlite():
    """Ensures the SQLite database and solutions table exist."""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS solutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT,
            solution TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


init_sqlite()

# Compile the graph once at startup
pipeline = build_graph()


# ─── Pydantic schemas ───
class QuestionRequest(BaseModel):
    prompt: str
    webhook_url: Optional[str] = None
    pipeline_type: Optional[str] = "research"  # "research" or "dev_team"


# ─── Background pipeline runner ───
def run_pipeline_background(user_prompt: str, webhook_url: Optional[str] = None, pipeline_type: str = "research"):
    """Runs the LangGraph pipeline in a background thread."""
    task_id = str(uuid.uuid4())[:8]

    # Clean up previous runs when a new job starts
    LIVE_TRACKING.clear()

    LIVE_TRACKING[task_id] = {
        "prompt": user_prompt,
        "pipeline_type": pipeline_type,
        "status": "In Progress",
        "current_agent": "Initializing",
        "specialty": "code" if pipeline_type == "dev_team" else "general",
        "loop_count": 1,
        "blueprint": "",
        "architecture": "",
        "backend_logic": "",
        "frontend_code": "",
        "qa_feedback": "",
        "tester_feedback": "",
        "docker_logs": "",
        "solution": "",
        "critic_feedback": "",
        "agent_steps": [],
        "final_solution": None,
    }

    try:
        # Initial state fed into the graph
        initial_state = {
            "prompt": user_prompt,
            "webhook_url": webhook_url,
            "pipeline_type": pipeline_type,
            "specialty": "code" if pipeline_type == "dev_team" else "general",
            "loop_count": 1,
            "max_loops": MAX_LOOPS,
            "pipeline_history": [],
            "research_log": [],
            "raw_search_data": None,
            "processed_facts": None,
            "accumulated_context": "No external data collected yet.",
            "blueprint": "",
            "architecture": "",
            "backend_logic": "",
            "frontend_code": "",
            "qa_feedback": "",
            "tester_feedback": "",
            "docker_logs": "",
            "solution": "",
            "approved": False,
            "critic_feedback": "",
            "final_solution": None,
            "db_id": None,
        }

        # Stream through graph execution node by node
        final_state = dict(initial_state)
        for chunk in pipeline.stream(initial_state, stream_mode="updates"):
            for node_name, state_update in chunk.items():
                LIVE_TRACKING[task_id]["current_agent"] = node_name
                
                # Extract main artifact string from state update dict
                artifact_content = ""
                if isinstance(state_update, dict):
                    for key in ["architecture", "backend_logic", "frontend_code", "qa_feedback", "tester_feedback", "docker_logs", "solution", "blueprint", "processed_facts", "final_solution"]:
                        if key in state_update and state_update[key]:
                            artifact_content = str(state_update[key])
                            break

                # Store agent step details
                step_record = {
                    "agent": node_name,
                    "input": f"Loop {final_state.get('loop_count', 1)} | Pipeline: {pipeline_type}",
                    "action": f"Executed LangGraph node '{node_name}'",
                    "output": artifact_content or str(state_update),
                }
                LIVE_TRACKING[task_id]["agent_steps"].append(step_record)

                # Merge updates into final_state and LIVE_TRACKING telemetry
                if isinstance(state_update, dict):
                    final_state.update(state_update)
                    for key in ["specialty", "loop_count", "blueprint", "architecture", "backend_logic", "frontend_code", "qa_feedback", "tester_feedback", "docker_logs", "solution", "critic_feedback", "final_solution", "db_id"]:
                        if key in state_update:
                            LIVE_TRACKING[task_id][key] = state_update[key]

        LIVE_TRACKING[task_id]["status"] = "Completed"
        LIVE_TRACKING[task_id]["current_agent"] = "END"
        LIVE_TRACKING[task_id]["final_solution"] = final_state.get("final_solution")
        LIVE_TRACKING[task_id]["db_id"] = final_state.get("db_id")

    except Exception as e:
        print(f"❌ Pipeline crashed: {e}", flush=True)
        LIVE_TRACKING[task_id]["status"] = "Failed"
        LIVE_TRACKING[task_id]["error"] = str(e)


# ─── API Endpoints ───
@app.post("/api/ask")
def ask_question(request: QuestionRequest):
    """Launches the multi-agent pipeline in a background thread."""
    pipe_type = request.pipeline_type if request.pipeline_type in ["research", "dev_team"] else "research"
    thread = threading.Thread(
        target=run_pipeline_background,
        args=(request.prompt, request.webhook_url, pipe_type),
    )
    thread.start()
    return {
        "status": "processing",
        "pipeline_type": pipe_type,
        "message": f"LangGraph ({pipe_type}) pipeline launched in background.",
    }


@app.get("/api/status")
def get_live_status():
    """Returns all active or recently completed runs."""
    return LIVE_TRACKING


@app.get("/api/solutions")
def get_all_solutions():
    """Returns a list of all historical solutions from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, prompt, timestamp FROM solutions ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@app.get("/api/solutions/{solution_id}")
def get_solution_by_id(solution_id: int):
    """Returns a single solution record by ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM solutions WHERE id = ?", (solution_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Solution not found.")
    return dict(row)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8500, reload=False)
