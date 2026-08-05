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


# ─── Background pipeline runner ───
def run_pipeline_background(user_prompt: str, webhook_url: Optional[str] = None):
    """Runs the LangGraph pipeline in a background thread."""
    task_id = str(uuid.uuid4())[:8]

    LIVE_TRACKING[task_id] = {
        "prompt": user_prompt,
        "status": "In Progress",
        "final_solution": None,
    }

    try:
        # Initial state fed into the graph
        initial_state = {
            "prompt": user_prompt,
            "webhook_url": webhook_url,
            "specialty": "general",
            "loop_count": 1,
            "max_loops": 5,
            "pipeline_history": [],
            "research_log": [],
            "raw_search_data": None,
            "processed_facts": None,
            "accumulated_context": "No external data collected yet.",
            "blueprint": "",
            "solution": "",
            "approved": False,
            "critic_feedback": "",
            "final_solution": None,
            "db_id": None,
        }

        # Execute the full graph — blocks until END is reached
        final_state = pipeline.invoke(initial_state)

        LIVE_TRACKING[task_id]["status"] = "Completed"
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
    thread = threading.Thread(
        target=run_pipeline_background,
        args=(request.prompt, request.webhook_url),
    )
    thread.start()
    return {
        "status": "processing",
        "message": "LangGraph pipeline launched in background.",
    }


@app.get("/api/status")
def get_live_status():
    """Returns all active or recently completed runs."""
    return LIVE_TRACKING


@app.get("/api/solutions")
def get_all_solutions():
    """Lists all archived solutions (lightweight — no full payloads)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, prompt, timestamp FROM solutions ORDER BY id DESC")
        rows = cursor.fetchall()
        solutions = [{"id": r[0], "prompt": r[1], "timestamp": r[2]} for r in rows]
    except Exception as e:
        solutions = []
        print(f"⚠️ Error fetching history: {e}", flush=True)
    finally:
        conn.close()
    return solutions


@app.get("/api/solutions/{solution_id}")
def get_solution(solution_id: int):
    """Fetches a single archived solution by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, prompt, solution, timestamp FROM solutions WHERE id = ?",
        (solution_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Solution not found.")
    return {"id": row[0], "prompt": row[1], "solution": row[2], "timestamp": row[3]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)
