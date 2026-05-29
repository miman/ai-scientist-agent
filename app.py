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

app = FastAPI(title="AI Multi-Agent Problem Solver API")

# ==========================================
# CONFIGURATION: AGENT MODELS
# ==========================================
MODEL_CONFIG = {
    "searcher": "qwen3.5:9b",
    "processor": "qwen3.5:9b",
    "planner": "qwen3.5:9b",
    "expert": "qwen3.5:9b",
    "critic": "qwen3.5:9b",
    "sanitizer": "qwen3.5:9b"
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
# 2. AGENT LOGIC & DET_TOOLS
# ==========================================
def tool_web_search(query: str):
    query = query.strip('"').strip("'")
    try:
        with DDGS() as ddgs:
            # Fetch up to 3 results to save VRAM and keep context slim
            results = list(ddgs.text(query, max_results=3))
            raw_results = []
            for r in results:
                title = r.get('title', '')
                body = r.get('body', '')
                
                # PROGRAMMATIC TRIMMING: Instantly normalize rogue tabs, spacing, and clean text
                cleaned_body = " ".join(body.split())
                
                raw_results.append(f"Title: {title}\nFact-Snippet: {cleaned_body}\n")
            return "\n\n".join(raw_results)
    except Exception as e:
        return f"Web search failed: {str(e)}"

def call_hermes_llm(system_prompt: str, user_content: str, model_name: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://192.168.68.100:11434")
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "stream": False,
        "options": {"temperature": 0.0},  # Low temperature for deterministic, structured output
        "keep_alive": "30m"
    }
    
    try:
        endpoint = f"{ollama_url.rstrip('/')}/api/chat"
        response = requests.post(endpoint, json=payload, timeout=300)
        response.raise_for_status()
        return response.json()["message"]["content"]
    except Exception as e:
        print(f"⚠️ Error calling Ollama ({model_name}): {e}", flush=True)
        return f"Could not generate a response due to an internal timeout or connection error: {str(e)}"

def agent_searcher(prompt: str) -> Optional[str]:
    print(f"🕵️‍♂️ [Agent 1: Searcher] Analyzing if web search is needed...", flush=True)
    
    decision_prompt = (
        "You are a triage agent for an advanced execution pipeline.\n"
        "Analyze if we need to search the internet for updated documentation, financial data, real-time metrics, or specific API syntax to solve the user's request.\n\n"
        "You MUST respond in EXACTLY one of the following two formats (no other text or explanation):\n"
        "DECISION: NO\n"
        "DECISION: YES | SEARCH_QUERY: your optimized search keywords here"
    )
    
    raw_decision = call_hermes_llm(decision_prompt, prompt, model_name=MODEL_CONFIG["searcher"]).strip()
    
    if "DECISION: NO" in raw_decision:
        print("💡 [Agent 1: Searcher] No web search required. Relying on internal knowledge base.", flush=True)
        return None
        
    if "DECISION: YES" in raw_decision and "SEARCH_QUERY:" in raw_decision:
        search_query = raw_decision.split("SEARCH_QUERY:")[-1].strip().strip('"').strip("'")
        if search_query:
            print(f"🌐 [Agent 1: Searcher] Agent decided to search for: '{search_query}'", flush=True)
            return tool_web_search(search_query)
            
    fallback_query = raw_decision.replace("DECISION: YES", "").replace("|", "").strip().strip('"').strip("'")
    if fallback_query and len(fallback_query) > 1 and "DECISION" not in fallback_query:
        print(f"🌐 [Agent 1: Searcher] Fallback search execution for: '{fallback_query}'", flush=True)
        return tool_web_search(fallback_query)
        
    print("⚠️ [Agent 1: Searcher] Could not parse decision or search query string was empty. Skipping search.", flush=True)
    return None

def agent_processor(raw_data: str, prompt_id: str):
    print(f"🧹 [Agent 2: Processor] Synthesizing extracted facts...", flush=True)
    cleaned_data = call_hermes_llm(
        "You are an advanced data extraction assistant. Analyze the cleanly trimmed web results provided.\n"
        "Extract ONLY vital metrics, numbers, core statistics, and direct factual answers matching the request.\n"
        "Format the output as a concise bulleted list of facts under 500 words. Eliminate conversational fluff.", 
        raw_data, 
        model_name=MODEL_CONFIG["processor"]
    )
    
    client = chromadb.HttpClient(host="chromadb", port=8000)
    coll = client.get_or_create_collection(name="search_knowledge")
    try: coll.delete(ids=[f"doc_{prompt_id}"])
    except: pass
    coll.add(documents=[cleaned_data], embeddings=[[0.0]], ids=[f"doc_{prompt_id}"])
    return cleaned_data

def agent_planner(original_prompt: str, context: str) -> str:
    print(f"📋 [Agent 2.5: Planner] Generating structural solution blueprint...", flush=True)
    system_prompt = (
        "You are an expert Project Planner and Architect.\n"
        "Your task is to analyze the user's requirements and the gathered context, then draft a structured, step-by-step blueprint of what the final solution must include.\n"
        "Do not write the final solution code or report yourself. Instead, list the structural sections, constraints, logic requirements, or components needed.\n"
        "Output your blueprint as a clean, concise bulleted list for the implementation expert to follow."
    )
    user_content = f"CONTEXT DATA:\n{context}\n\nUSER ORIGINAL REQUIREMENTS:\n{original_prompt}"
    return call_hermes_llm(system_prompt, user_content, model_name=MODEL_CONFIG["planner"])

def agent_expert(original_prompt: str, blueprint: str, prompt_id: str):
    print(f"🧠 [Agent 3: Expert] Executing solution blueprint...", flush=True)
    
    client = chromadb.HttpClient(host="chromadb", port=8000)
    coll = client.get_or_create_collection(name="search_knowledge")
    try:
        chroma_result = coll.get(ids=[f"doc_{prompt_id}"])
        context = chroma_result['documents'][0] if (chroma_result and chroma_result['documents']) else ""
    except:
        context = ""
        
    system_prompt = (
        "You are an expert Subject Matter Assistant and Implementation Engineer.\n"
        "Your task is to craft a complete, optimal, accurate, and professional-grade solution following the provided blueprint.\n"
        "If code is requested, provide full production-ready code with error handling.\n"
        "If text/analysis is requested, provide a deep, well-structured, data-driven report."
    )
    user_content = f"RESEARCH CONTEXT:\n{context}\n\nSTRUCTURAL BLUEPRINT TO FOLLOW:\n{blueprint}\n\nUSER TARGET LOGIC:\n{original_prompt}"
    return call_hermes_llm(system_prompt, user_content, model_name=MODEL_CONFIG["expert"])

def agent_critic(original_prompt: str, solution: str, loop_count: int) -> tuple[bool, str]:
    print(f"⚖️ [Agent 4: Critic] Auditing solution (Attempt {loop_count})...", flush=True)
    
    system_prompt = (
        "You are a strict, cynical, and highly analytical Senior Quality Evaluator.\n"
        "Your task is to thoroughly audit the proposed solution against the original user requirements.\n\n"
        "CRITICAL INSTRUCTION:\n"
        "- If the user asked for CODE, ensure the code is bug-free, handles timeouts/errors, and matches all constraints.\n"
        "- If the user asked for an ANALYSIS, REPORT, or TEXT, ensure the facts are logical, numeric, complete, and contain no backend server logs.\n\n"
        "You MUST include exactly one of the following verdict tokens somewhere in your response:\n"
        "VERDICT: APPROVED (Only if the solution perfectly and completely satisfies all requirements)\n"
        "VERDICT: REJECTED (If there are missing facts, logical flaws, errors, or room for structural improvement)\n\n"
        "Provide clear, step-by-step technical feedback for the expert indicating exactly what needs adjustment."
    )
    
    review_result = call_hermes_llm(system_prompt, f"ORIGINAL REQUIREMENTS:\n{original_prompt}\n\nPROPOSED SOLUTION:\n{solution}", model_name=MODEL_CONFIG["critic"])
    
    print(f"\n================ CRITIC AUDIT REPORT (Loop {loop_count}) ================", flush=True)
    print(review_result, flush=True)
    print("====================================================================\n", flush=True)
    
    if "APPROVED" in review_result.upper() and "REJECTED" not in review_result.upper():
        return True, review_result
    return False, review_result

def agent_sanitizer(raw_solution: str) -> str:
    print("✨ [Agent 4.5: Sanitizer] Polishing solution and stripping chat filler...", flush=True)
    system_prompt = (
        "You are a professional Technical Editor and Content Sanitizer.\n"
        "Your task is to take an approved technical solution and strip away any conversational conversational metadata or developer filler text.\n"
        "Remove statements like: 'Sure, here is your updated solution', 'I have fixed the issues pointed out', or 'Hope this helps!'.\n"
        "Retain 100% of the actual core report text, financial analysis, markdown formatting, or source code intact.\n"
        "Output ONLY the clean, ready-to-use technical artifact."
    )
    return call_hermes_llm(system_prompt, raw_solution, model_name=MODEL_CONFIG["sanitizer"])

def agent_archiver(original_prompt: str, final_solution: str) -> int:
    print("🗄️ [Agent 5: Archive] Saving polished artifact to SQLite database...", flush=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO solutions (prompt, solution) VALUES (?, ?)", (original_prompt, final_solution))
    inserted_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return inserted_id

# ==========================================
# 3. ORCHESTRATION (Thread Worker Context)
# ==========================================
def run_agent_pipeline_background(user_problem: str, webhook_url: Optional[str] = None):
    print(f"🚀 Launching multi-agent pipeline for: '{user_problem[:40]}...'", flush=True)
    prompt_id = f"{hash(user_problem)}_{uuid.uuid4().hex[:8]}"
    loop_count = 1
    
    try:
        # Step 1 & 2: Dynamic Search & Processing
        raw_info = agent_searcher(user_problem)
        if raw_info:
            context_summary = agent_processor(raw_info, prompt_id)
        else:
            client = chromadb.HttpClient(host="chromadb", port=8000)
            coll = client.get_or_create_collection(name="search_knowledge")
            try: coll.delete(ids=[f"doc_{prompt_id}"])
            except: pass
            context_summary = "Rely exclusively on internal generalized pre-trained knowledge base parameters."
            coll.add(documents=[context_summary], embeddings=[[0.0]], ids=[f"doc_{prompt_id}"])
        
        # Step 2.5: Strategic Solution Blueprint Planning
        blueprint = agent_planner(user_problem, context_summary)
        
        # Step 3 & 4: Critic Refinement Loop
        while True:
            solution = agent_expert(user_problem, blueprint, prompt_id)
            approved, feedback = agent_critic(user_problem, solution, loop_count)
            
            if approved or loop_count >= 10:
                if loop_count >= 10 and not approved:
                    print("⚠️ Maximum iteration loops hit without absolute approval. Archiving current best variant.", flush=True)
                
                # Step 4.5: Clean out chatbot debris before saving
                polished_solution = agent_sanitizer(solution)
                
                # Step 5: Persistent Storage Integration
                db_id = agent_archiver(user_problem, polished_solution)
                print(f"🎉 Pipeline successfully concluded! Saved under SQLite Archive Row ID: {db_id}", flush=True)
                
                if webhook_url:
                    try: requests.post(webhook_url, json={"status": "completed", "id": db_id}, timeout=10)
                    except: pass
                break
            else:
                # Append critic feedback directly to the operational blueprint for the next loop run
                blueprint = f"{blueprint}\n\nCRITIC REJECTION AMENDMENT (ATTEMPT {loop_count}):\n{feedback}"
                loop_count += 1
                
    except Exception as e:
        print(f"❌ Critical pipeline failure within background process thread: {e}", flush=True)

# ==========================================
# 4. REST API ENDPOINTS
# ==========================================
@app.post("/api/ask")
def ask_question(request: QuestionRequest):
    # Offload processing loop onto an isolated native OS thread to shield FastAPI's async scheduler
    thread = threading.Thread(
        target=run_agent_pipeline_background, 
        args=(request.prompt, request.webhook_url)
    )
    thread.start()
    
    return {
        "status": "processing",
        "message": "The extended multi-agent pipeline workflow sequence has launched in a background thread."
    }

@app.get("/api/solutions/{solution_id}")
def get_solution(solution_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, prompt, solution, timestamp FROM solutions WHERE id = ?", (solution_id,))
    row = cursor.fetchone()
    conn.close()
    if not row: raise HTTPException(status_code=404, detail="Solution archive index record not found.")
    return {"id": row[0], "prompt": row[1], "solution": row[2], "timestamp": row[3]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)