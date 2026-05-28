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
# KORRIGERAD: Returnerar nu en fejkad embedding-vektor i rätt format 
# så att ChromaDB:s längd-validering blir nöjd (utan att räkna på riktigt).
class FakeEmbeddingFunction:
    def __call__(self, input):
        # ChromaDB förväntar sig en lista av listor (en vektor per dokument)
        # Om vi skickar in ett dokument, ger vi den en lista med en fejkad 1-dimensionell vektor.
        if isinstance(input, str):
            return [[0.0]]
        return [[0.0] for _ in input]
    
    def name(self) -> str:
        return "FakeEmbeddingFunction"

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
    full_prompt = f"System: {system_prompt}\n\nUser: {user_content}\n\nAssistant:"
    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "options": {"temperature": 0.2},
        "keep_alive": "30m"  # Håll modellen laddad i 30 min i ditt VRAM
    }
    try:
        endpoint = f"{ollama_url.rstrip('/')}/api/generate"
        response = requests.post(endpoint, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        print(f"⚠️ Fel vid anrop till Ollama ({model_name}): {e}", flush=True)
        return f"Kunde inte generera svar: {str(e)}"

def agent_searcher(prompt: str) -> Optional[str]:
    print(f"🕵️‍♂️ [Agent 1: Sök] Analyserar om nätverkssökning krävs...", flush=True)
    decision_prompt = (
        "Du är en intelligent triage-agent. Analysera om vi behöver söka på internet efter aktuell dokumentation eller API-syntax.\n"
        "- Om ja: Svara ENBART med en kort söksträng.\n"
        "- Om nej (enkel logik/standardfunktion): Svara exakt med ordet 'NEJ'."
    )
    decision = call_hermes_llm(decision_prompt, prompt, model_name=MODEL_CONFIG["searcher"]).strip().strip('"').strip("'")
    if decision.upper().startswith("NEJ"):
        print("💡 [Agent 1: Sök] Ingen sökning krävs. Använder intern kunskap.", flush=True)
        return None
    print(f"🌐 [Agent 1: Sök] Agenten beslutade att söka: '{decision}'", flush=True)
    return tool_web_search(decision)

def agent_processor(raw_data: str, prompt_id: str):
    print(f"🧹 [Agent 2: Processor] Rensar data...", flush=True)
    cleaned_data = call_hermes_llm("Extrahera kodrelevanta fakta från texten.", raw_data, model_name=MODEL_CONFIG["processor"])
    
    # Lokal trådsäker ChromaDB-anslutning
    client = chromadb.HttpClient(host="chromadb", port=8000)
    coll = client.get_or_create_collection(name="search_knowledge", embedding_function=FakeEmbeddingFunction())
    try:
        coll.delete(ids=[f"doc_{prompt_id}"])
    except: pass
    coll.add(documents=[cleaned_data], ids=[f"doc_{prompt_id}"])
    return cleaned_data

def agent_expert(original_prompt: str, prompt_id: str):
    print(f"🧠 [Agent 3: Expert] Skapar kodlösning...", flush=True)
    
    # Lokal trådsäker ChromaDB-anslutning
    client = chromadb.HttpClient(host="chromadb", port=8000)
    coll = client.get_or_create_collection(name="search_knowledge", embedding_function=FakeEmbeddingFunction())
    try:
        chroma_result = coll.get(ids=[f"doc_{prompt_id}"])
        context = chroma_result['documents'][0] if (chroma_result and chroma_result['documents']) else ""
    except:
        context = ""
        
    return call_hermes_llm(
        "Du är en AI Code Scientist. Skriv en komplett, optimal och ren kodlösning.",
        f"Kontext:\n{context}\n\nProblem: {original_prompt}",
        model_name=MODEL_CONFIG["expert"]
    )

def agent_critic(original_prompt: str, solution: str, loop_count: int) -> tuple[bool, str]:
    print(f"⚖️ [Agent 4: Critic] Granskar koden (Försök {loop_count})...", flush=True)
    system_prompt = (
        "Du är en kodgranskare. Din uppgift är att kontrollera om koden uppfyller kravet.\n"
        "Om koden är korrekt och löser uppgiften, skriv ordet 'GODKÄND' någonstans i ditt svar.\n"
        "Om koden har fel eller kan förbättras, skriv 'UNDERKÄND' och förklara vad som ska ändras."
    )
    review_result = call_hermes_llm(system_prompt, f"KRAV:\n{original_prompt}\n\nKOD:\n{solution}", model_name=MODEL_CONFIG["critic"])
    
    # KORRIGERAD: Skriv ut hela kritiken direkt i loggen så du ser exakt vad den säger!
    print(f"\n💬 [Critic Feedback Försök {loop_count}]:\n{review_result}\n" + "-"*40, flush=True)
    
    # KORRIGERAD: Gör sökningen mer flexibel (strunta i exakt radbrytning eller skiftläge)
    if "GODKÄND" in review_result.upper() and "UNDERKÄND" not in review_result.upper():
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