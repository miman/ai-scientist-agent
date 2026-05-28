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
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

app = FastAPI(title="Hermes AI Code Scientist API")

# ==========================================
# CONFIGURATION: MODELLER FÖR AGENTERNA
# ==========================================
MODEL_CONFIG = {
    "searcher": "qwen3.5:9b",
    "processor": "qwen3.5:9b",
    "expert": "qwen3.5:9b",
    "critic": "qwen3.5:9b"
}

# ==========================================
# 0. INITIERING AV DATABASER
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

# En tom fejk-klass så att klienten ALDRIG laddar ner ONNX lokalt över internet
class FakeEmbeddingFunction(EmbeddingFunction):
    def __init__(self):
        pass

    def __call__(self, input: Documents) -> Embeddings:
        if isinstance(input, str):
            return [[0.0]]
        return [[0.0] for _ in input]
    
    def name(self) -> str:
        return "FakeEmbeddingFunction"
        
    def get_config(self) -> dict:
        return {"model": "fake"}

    @classmethod
    def build_from_config(cls, config: dict):
        return cls()

# ==========================================
# 1. PYDANTIC SCHEMAN
# ==========================================
class QuestionRequest(BaseModel):
    prompt: str
    webhook_url: Optional[str] = None

# ==========================================
# 2. AGENTERNAS LOGIK
# ==========================================
def tool_web_search(query: str):
    query = query.strip('"').strip("'")
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
            return "\n\n".join([f"Titel: {r['title']}\nLänk: {r['href']}\nInnehåll: {r['body']}" for r in results])
    except Exception as e:
        return f"Sökning misslyckades: {str(e)}"

def call_hermes_llm(system_prompt: str, user_content: str, model_name: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://192.168.68.100:11434")
    
    # KORRIGERAD: Vi använder /api/chat och strukturerade roller för maximal Qwen-kompatibilitet
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
        # KORRIGERAD: Ändrat endpoint till /api/chat
        endpoint = f"{ollama_url.rstrip('/')}/api/chat"
        response = requests.post(endpoint, json=payload, timeout=120)
        response.raise_for_status()
        
        # KORRIGERAD: Hämtar svaret från det strukturerade chat-objektet
        return response.json()["message"]["content"]
        
    except Exception as e:
        print(f"⚠️ Fel vid anrop till Ollama ({model_name}): {e}", flush=True)
        return f"Kunde inte generera svar: {str(e)}"

def agent_searcher(prompt: str) -> Optional[str]:
    print(f"🕵️‍♂️ [Agent 1: Sök] Analyserar om nätverkssökning krävs...", flush=True)
    
    # Engelskt systemprompt för maximal träffsäkerhet i triagen
    decision_prompt = (
        "You are a triage agent for a code generation pipeline.\n"
        "Analyze if we need to search the internet for updated documentation, external libraries, or specific API syntax to solve the user's request.\n\n"
        "You MUST respond in EXACTLY one of the following two formats (no other text or explanation):\n"
        "DECISION: NO\n"
        "DECISION: YES | SEARCH_QUERY: your optimized search keywords here"
    )
    
    raw_decision = call_hermes_llm(decision_prompt, prompt, model_name=MODEL_CONFIG["searcher"]).strip()
    
    if "DECISION: NO" in raw_decision:
        print("💡 [Agent 1: Sök] Ingen sökning krävs. Använder intern kunskap.", flush=True)
        return None
        
    if "DECISION: YES" in raw_decision and "SEARCH_QUERY:" in raw_decision:
        search_query = raw_decision.split("SEARCH_QUERY:")[-1].strip().strip('"').strip("'")
        if search_query:
            print(f"🌐 [Agent 1: Sök] Agenten beslutade att söka efter: '{search_query}'", flush=True)
            return tool_web_search(search_query)
            
    # Fallback om modellen blandar formaten men ändå vill söka
    fallback_query = raw_decision.replace("DECISION: YES", "").replace("|", "").strip().strip('"').strip("'")
    if fallback_query and len(fallback_query) > 1 and "DECISION" not in fallback_query:
        print(f"🌐 [Agent 1: Sök] Fallback-sökning efter: '{fallback_query}'", flush=True)
        return tool_web_search(fallback_query)
        
    print("⚠️ [Agent 1: Sök] Kunde inte tolka beslut eller söksträngen blev tom. Skippar sökning.", flush=True)
    return None

def agent_processor(raw_data: str, prompt_id: str):
    print(f"🧹 [Agent 2: Processor] Rensar data...", flush=True)
    # Rensar data på engelska för bättre struktur
    cleaned_data = call_hermes_llm(
        "You are a data processing assistant. Extract all code-relevant facts, API specifications, and documentation details from the text.", 
        raw_data, 
        model_name=MODEL_CONFIG["processor"]
    )
    
    client = chromadb.HttpClient(host="chromadb", port=8000)
    coll = client.get_or_create_collection(name="search_knowledge", embedding_function=FakeEmbeddingFunction())
    try:
        coll.delete(ids=[f"doc_{prompt_id}"])
    except: pass
    coll.add(documents=[cleaned_data], ids=[f"doc_{prompt_id}"])
    return cleaned_data

def agent_expert(original_prompt: str, prompt_id: str):
    print(f"🧠 [Agent 3: Expert] Skapar kodlösning...", flush=True)
    
    client = chromadb.HttpClient(host="chromadb", port=8000)
    coll = client.get_or_create_collection(name="search_knowledge", embedding_function=FakeEmbeddingFunction())
    try:
        chroma_result = coll.get(ids=[f"doc_{prompt_id}"])
        context = chroma_result['documents'][0] if (chroma_result and chroma_result['documents']) else ""
    except:
        context = ""
        
    return call_hermes_llm(
        "You are an expert AI Code Scientist. Write a complete, optimal, secure, and production-ready code solution that fulfills all user requirements. Always write clean code with proper error handling.",
        f"Fetched Documentation/Context:\n{context}\n\nUser Requirements (Might be in Swedish):\n{original_prompt}",
        model_name=MODEL_CONFIG["expert"]
    )

def agent_critic(original_prompt: str, solution: str, loop_count: int) -> tuple[bool, str]:
    print(f"⚖️ [Agent 4: Critic] Granskar koden (Försök {loop_count})...", flush=True)
    
    system_prompt = (
        "You are a strict and cynical Senior Code Reviewer.\n"
        "Your task is to thoroughly audit the proposed code solution against the original requirements.\n\n"
        "You MUST include exactly one of the following verdict tokens somewhere in your response:\n"
        "VERDICT: APPROVED (Only if the code is 100% flawless and matches all requirements)\n"
        "VERDICT: REJECTED (If there is even a minor bug, missing requirement, or room for structural improvement)\n\n"
        "Provide a clear, technical, step-by-step feedback explanation for the developer."
    )
    
    review_result = call_hermes_llm(system_prompt, f"ORIGINAL REQUIREMENTS:\n{original_prompt}\n\nPROPOSED CODE:\n{solution}", model_name=MODEL_CONFIG["critic"])
    
    # TVINGA UT UTSKRIFTEN: Gör en rå print direkt så vi garanterat ser texten i Podman
    print(f"\n================ CRITIC FEEDBACK (Loop {loop_count}) ================", flush=True)
    print(review_result, flush=True)
    print("===============================================================\n", flush=True)
    
    # MATCHNING: Kolla efter de ENGELSKA orden APPROVED / REJECTED
    if "APPROVED" in review_result.upper() and "REJECTED" not in review_result.upper():
        return True, review_result
    return False, review_result

def agent_archiver(original_prompt: str, final_solution: str) -> int:
    print("🗄️ [Agent 5: Arkiv] Sparar slutresultat i SQLite...", flush=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO solutions (prompt, solution) VALUES (?, ?)", (original_prompt, final_solution))
    inserted_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return inserted_id

# ==========================================
# 3. ORKESTRERING (Körs i en ren tråd)
# ==========================================
def run_agent_pipeline_background(user_problem: str, webhook_url: Optional[str] = None):
    print(f"🚀 Startar agent-pipeline för: '{user_problem[:40]}...'", flush=True)
    prompt_id = f"{hash(user_problem)}_{uuid.uuid4().hex[:8]}"
    loop_count = 1
    
    try:
        raw_info = agent_searcher(user_problem)
        if raw_info:
            agent_processor(raw_info, prompt_id)
        else:
            client = chromadb.HttpClient(host="chromadb", port=8000)
            coll = client.get_or_create_collection(name="search_knowledge", embedding_function=FakeEmbeddingFunction())
            try:
                coll.delete(ids=[f"doc_{prompt_id}"])
            except: pass
            coll.add(documents=["Använd intern kunskap."], ids=[f"doc_{prompt_id}"])
        
        while True:
            solution = agent_expert(user_problem, prompt_id)
            approved, feedback = agent_critic(user_problem, solution, loop_count)
            
            if approved or loop_count >= 10:
                if loop_count >= 10 and not approved:
                    print("⚠️ Max antal loopar nådda. Arkiverar bästa försök.", flush=True)
                db_id = agent_archiver(user_problem, solution)
                print(f"🎉 Klart! Sparat i SQLite med ID: {db_id}", flush=True)
                
                if webhook_url:
                    try: requests.post(webhook_url, json={"status": "completed", "id": db_id}, timeout=10)
                    except: pass
                break
            else:
                loop_count += 1
    except Exception as e:
        print(f"❌ Kritiskt fel i pipeline-tråden: {e}", flush=True)

# ==========================================
# 4. REST API ENDPOINTS
# ==========================================
@app.post("/api/ask")
def ask_question(request: QuestionRequest):
    # KORRIGERAD: Starta en helt fristående OS-tråd istället för BackgroundTasks
    thread = threading.Thread(
        target=run_agent_pipeline_background, 
        args=(request.prompt, request.webhook_url)
    )
    thread.start()
    
    return {
        "status": "processing",
        "message": "Agent-loopen har startats i en dedikerad bakgrundstråd."
    }

@app.get("/api/solutions/{solution_id}")
def get_solution(solution_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, prompt, solution, timestamp FROM solutions WHERE id = ?", (solution_id,))
    row = cursor.fetchone()
    conn.close()
    if not row: raise HTTPException(status_code=404, detail="Hittades inte.")
    return {"id": row[0], "prompt": row[1], "solution": row[2], "timestamp": row[3]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)