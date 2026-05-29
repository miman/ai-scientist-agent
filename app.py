import os
import sqlite3
import threading
import uuid
import requests
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
from duckduckgo_search import DDGS
import chromadb

app = FastAPI(title="Hermes AI Code Scientist API")

# ==========================================
# CONFIGURATION: AGENT MODELS
# ==========================================
MODEL_CONFIG = {
    "searcher": "qwen3.5:9b",
    "processor": "qwen3.5:9b",
    "expert": "qwen3.5:9b",
    "critic": "qwen3.5:9b"
}

# ==========================================
# 0. DATABASE INITIALIZATION
# ==========================================
DB_DIR = "/app/db_data"
DB_PATH = os.path.join(DB_DIR, "agent_archive.db")

def init_sqlite():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS solutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT,
            solution TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_sqlite()

# ==========================================
# 1. PYDANTIC SCHEMAS
# ==========================================
class QuestionRequest(BaseModel):
    prompt: str
    webhook_url: Optional[str] = None

# ==========================================
# 2. AGENT LOGIC
# ==========================================
def tool_web_search(query: str):
    query = query.strip('"').strip("'")
    try:
        with DDGS() as ddgs:
            # Fetch up to 3 results to save VRAM and context windows
            results = list(ddgs.text(query, max_results=3))
            raw_results = []
            for r in results:
                raw_results.append(f"Title: {r.get('title','')}\nSnippet: {r.get('body','')}\n")
            return "\n\n".join(raw_results)
    except Exception as e:
        return f"Web search failed: {str(e)}"

def call_hermes_llm(system_prompt: str, user_content: str, model_name: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://192.168.68.100:11434")
    
    # Using /api/chat and structured messages for optimal Qwen model compatibility
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "stream": False,
        "options": {"temperature": 0.2},
        "keep_alive": "30m"
    }
    
    try:
        endpoint = f"{ollama_url.rstrip('/')}/api/chat"
        response = requests.post(endpoint, json=payload, timeout=300)
        response.raise_for_status()
        
        # Extract response content from the chat message structure
        return response.json()["message"]["content"]
        
    except Exception as e:
        print(f"⚠️ Error calling Ollama ({model_name}): {e}", flush=True)
        return f"Could not generate a response: {str(e)}"

def agent_searcher(prompt: str) -> Optional[str]:
    print(f"🕵️‍♂️ [Agent 1: Search] Analyzing if a network search is required...", flush=True)
    
    decision_prompt = (
        "You are a triage agent for a code generation pipeline.\n"
        "Analyze if we need to search the internet for updated documentation, external libraries, or specific API syntax to solve the user's request.\n\n"
        "You MUST respond in EXACTLY one of the following two formats (no other text or explanation):\n"
        "DECISION: NO\n"
        "DECISION: YES | SEARCH_QUERY: your optimized search keywords here"
    )
    
    raw_decision = call_hermes_llm(decision_prompt, prompt, model_name=MODEL_CONFIG["searcher"]).strip()
    
    if "DECISION: NO" in raw_decision:
        print("💡 [Agent 1: Search] No web search required. Using internal knowledge.", flush=True)
        return None
        
    if "DECISION: YES" in raw_decision and "SEARCH_QUERY:" in raw_decision:
        search_query = raw_decision.split("SEARCH_QUERY:")[-1].strip().strip('"').strip("'")
        if search_query:
            print(f"🌐 [Agent 1: Search] Agent decided to search for: '{search_query}'", flush=True)
            return tool_web_search(search_query)
            
    # Fallback if the model alters formatting but clearly intends to search
    fallback_query = raw_decision.replace("DECISION: YES", "").replace("|", "").strip().strip('"').strip("'")
    if fallback_query and len(fallback_query) > 1 and "DECISION" not in fallback_query:
        print(f"🌐 [Agent 1: Search] Fallback search execution for: '{fallback_query}'", flush=True)
        return tool_web_search(fallback_query)
        
    print("⚠️ [Agent 1: Search] Could not parse decision or search query string was empty. Skipping web search.", flush=True)
    return None

def agent_processor(raw_data: str, prompt_id: str):
    print(f"🧹 [Agent 2: Processor] Cleaning and compressing data...", flush=True)
    cleaned_data = call_hermes_llm(
        "You are an advanced data compression assistant. Analyze the provided search results and extract ONLY the vital statistics, numbers, and direct answers (such as stock prices or core facts). Summarize everything into less than 2000 words. Do not include fluff.", 
        raw_data, 
        model_name=MODEL_CONFIG["processor"]
    )
    
    client = chromadb.HttpClient(host="chromadb", port=8000)
    coll = client.get_or_create_collection(name="search_knowledge")
    try: coll.delete(ids=[f"doc_{prompt_id}"])
    except: pass
    coll.add(documents=[cleaned_data], embeddings=[[0.0]], ids=[f"doc_{prompt_id}"])
    return cleaned_data

def agent_expert(original_prompt: str, prompt_id: str):
    print(f"🧠 [Agent 3: Expert] Generating solution...", flush=True)
    
    client = chromadb.HttpClient(host="chromadb", port=8000)
    coll = client.get_or_create_collection(name="search_knowledge")
    try:
        chroma_result = coll.get(ids=[f"doc_{prompt_id}"])
        context = chroma_result['documents'][0] if (chroma_result and chroma_result['documents']) else ""
    except:
        context = ""
        
    return call_hermes_llm(
        "You are an expert Subject Matter Assistant and Problem Solver. Provide a complete, optimal, accurate, and comprehensive solution or analysis that fully addresses the user requirements. If code is requested, provide professional-grade code; if analysis or text is requested, provide a deep and structured response.",
        f"Fetched Context/Documentation:\n{context}\n\nUser Requirements:\n{original_prompt}",
        model_name=MODEL_CONFIG["expert"]
    )

def agent_critic(original_prompt: str, solution: str, loop_count: int) -> tuple[bool, str]:
    print(f"⚖️ [Agent 4: Critic] Auditing solution (Attempt {loop_count})...", flush=True)
    
    system_prompt = (
        "You are a strict, cynical, and highly analytical Senior Quality Evaluator.\n"
        "Your task is to thoroughly audit the proposed solution against the original user requirements.\n\n"
        "CRITICAL INSTRUCTION:\n"
        "- If the user asked for CODE, ensure the code is bug-free and optimal.\n"
        "- If the user asked for an ANALYSIS, REPORT, or TEXT, ensure the facts are logical, comprehensive, and fully answer the question.\n\n"
        "You MUST include exactly one of the following verdict tokens somewhere in your response:\n"
        "VERDICT: APPROVED (Only if the solution perfectly and completely satisfies all requirements)\n"
        "VERDICT: REJECTED (If there are missing facts, logical flaws, errors, or room for structural improvement)\n\n"
        "Provide a clear, step-by-step technical feedback explanation for why the solution is approved or rejected."
    )
    
    review_result = call_hermes_llm(system_prompt, f"ORIGINAL REQUIREMENTS:\n{original_prompt}\n\nPROPOSED SOLUTION:\n{solution}", model_name=MODEL_CONFIG["critic"])
    
    print(f"\n================ CRITIC FEEDBACK (Loop {loop_count}) ================", flush=True)
    print(review_result, flush=True)
    print("===============================================================\n", flush=True)
    
    if "APPROVED" in review_result.upper() and "REJECTED" not in review_result.upper():
        return True, review_result
    return False, review_result

def agent_archiver(original_prompt: str, final_solution: str) -> int:
    print("🗄️ [Agent 5: Archive] Saving final results to SQLite database...", flush=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO solutions (prompt, solution) VALUES (?, ?)", (original_prompt, final_solution))
    inserted_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return inserted_id

# ==========================================
# 3. ORCHESTRATION (Runs in a dedicated thread)
# ==========================================
def run_agent_pipeline_background(user_problem: str, webhook_url: Optional[str] = None):
    print(f"🚀 Launching agent pipeline for: '{user_problem[:40]}...'", flush=True)
    prompt_id = f"{hash(user_problem)}_{uuid.uuid4().hex[:8]}"
    loop_count = 1
    
    try:
        # Integrated optimized result extraction logic directly inside the workflow
        raw_info = agent_searcher(user_problem)
        if raw_info:
            agent_processor(raw_info, prompt_id)
        else:
            client = chromadb.HttpClient(host="chromadb", port=8000)
            coll = client.get_or_create_collection(name="search_knowledge")
            try:
                coll.delete(ids=[f"doc_{prompt_id}"])
            except: pass
            coll.add(documents=["Use internal knowledge base."], embeddings=[[0.0]], ids=[f"doc_{prompt_id}"])
        
        while True:
            solution = agent_expert(user_problem, prompt_id)
            approved, feedback = agent_critic(user_problem, solution, loop_count)
            
            if approved or loop_count >= 10:
                if loop_count >= 10 and not approved:
                    print("⚠️ Maximum processing loops reached. Archiving best attempt.", flush=True)
                db_id = agent_archiver(user_problem, solution)
                print(f"🎉 Success! Saved in SQLite archive with database ID: {db_id}", flush=True)
                
                if webhook_url:
                    try: requests.post(webhook_url, json={"status": "completed", "id": db_id}, timeout=10)
                    except: pass
                break
            else:
                loop_count += 1
    except Exception as e:
        print(f"❌ Critical pipeline failure within background process thread: {e}", flush=True)

# ==========================================
# 4. REST API ENDPOINTS
# ==========================================
@app.post("/api/ask")
def ask_question(request: QuestionRequest):
    # Starts an isolated, dedicated OS thread to bypass the async event loop and prevent locks
    thread = threading.Thread(
        target=run_agent_pipeline_background, 
        args=(request.prompt, request.webhook_url)
    )
    thread.start()
    
    return {
        "status": "processing",
        "message": "The multi-agent execution loop has successfully started in a dedicated background process thread."
    }

@app.get("/api/solutions/{solution_id}")
def get_solution(solution_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, prompt, solution, timestamp FROM solutions WHERE id = ?", (solution_id,))
    row = cursor.fetchone()
    conn.close()
    if not row: raise HTTPException(status_code=404, detail="Solution record not found.")
    return {"id": row[0], "prompt": row[1], "solution": row[2], "timestamp": row[3]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)