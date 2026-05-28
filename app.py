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
# KORRIGERAD: Matchar nu din readme.md och GPU-optimering
MODEL_CONFIG = {
    "searcher": "qwen3.5:9b",          # Används även för att fatta beslut om sökning krävs
    "processor": "qwen3.5:9b",         # Snabb modell för att rensa HTML/data
    "expert": "qwen3.5:9b",     # Dedikerad kodmodell för att skriva lösningen
    "critic": "qwen3.5:9b"        # Tänkande modell för att hitta dolda buggar
}

# ==========================================
# 0. INITIERING AV DATABASER
# ==========================================

# KORRIGERAD: Ändrad till /app/db_data/ för att lagras i den persistenta Docker-volymen
DB_DIR = "/app/db_data"
DB_PATH = os.path.join(DB_DIR, "agent_archive.db")

def init_sqlite():
    # Säkerställ att mappen för volymen existerar i containern
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

chroma_client = chromadb.HttpClient(host="chromadb", port=8000)

# KORRIGERAD: En helt tom fejk-klass som lurar ChromaDB-klienten 
# att inte ladda ner någonting alls över internet.
class FakeEmbeddingFunction:
    def __call__(self, input):
        return []

collection = chroma_client.get_or_create_collection(
    name="search_knowledge",
    embedding_function=FakeEmbeddingFunction() # <-- Tvinga in denna här!
)

# ==========================================
# 1. PYDANTIC SCHEMAN (För API-input)
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
    """
    Anropar Ollama med den modell som skickas med från respektive agent.
    """
    ollama_url = os.getenv("OLLAMA_URL", "http://192.168.68.100:11434")
    full_prompt = f"System: {system_prompt}\n\nUser: {user_content}\n\nAssistant:"
    
    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }
    
    try:
        endpoint = f"{ollama_url.rstrip('/')}/api/generate"
        response = requests.post(endpoint, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        print(f"⚠️ Fel vid anrop till Ollama ({model_name}) på {ollama_url}: {e}")
        return f"Kunde inte generera svar på grund av fel: {str(e)}"

# --- AGENT 1: Sökagenten ---
def agent_searcher(prompt: str) -> Optional[str]:
    print(f"🕵️‍♂️ [Agent 1: Sök] Analyserar om nätverkssökning krävs med {MODEL_CONFIG['searcher']}...")
    
    decision_prompt = (
        "Du är en intelligent triage-agent för en kod-pipeline.\n"
        "Din uppgift är att analyserar om vi faktiskt behöver söka på internet efter aktuell dokumentation, "
        "externa bibliotek, API-syntaxer eller specifik information för att kunna lösa problemet.\n\n"
        "Instruktioner:\n"
        "- Om problemet kräver sökning (t.ex. externa bibliotek, nya ramverk, APIer): Svara ENBART med en optimerad, kort söksträng för DuckDuckGo.\n"
        "- Om problemet är enkelt (standardalgoritmer, ren logik eller grundläggande funktioner som du redan behärskar till 100%): Svara exakt med ordet 'NEJ'.\n"
        "Svara aldrig med citattecken eller extra förklaringar."
    )
    
    decision = call_hermes_llm(decision_prompt, prompt, model_name=MODEL_CONFIG["searcher"]).strip().strip('"').strip("'")
    
    if decision.upper() == "NEJ" or decision.upper().startswith("NEJ"):
        print("💡 [Agent 1: Sök] Agenten bedömde att ingen sökning krävs. Använder intern kunskap direkt.")
        return None
        
    print(f"🌐 [Agent 1: Sök] Agenten beslutade att söka! Söksträng: '{decision}'")
    return tool_web_search(decision)

# --- AGENT 2: Processagenten ---
def agent_processor(raw_data: str, prompt_id: str):
    print(f"🧹 [Agent 2: Processor] Rensar data med {MODEL_CONFIG['processor']}...")
    cleaned_data = call_hermes_llm(
        "Du är en databearbetare. Extrahera kodrelevanta fakta och API-detaljer från texten.", 
        raw_data,
        model_name=MODEL_CONFIG["processor"]
    )
    
    try:
        collection.delete(ids=[f"doc_{prompt_id}"])
    except:
        pass
        
    collection.add(documents=[cleaned_data], ids=[f"doc_{prompt_id}"])
    return cleaned_data

# --- AGENT 3: Expertagenten ---
def agent_expert(original_prompt: str, prompt_id: str):
    print(f"🧠 [Agent 3: Expert] Skapar kodlösning med {MODEL_CONFIG['expert']}...")
    chroma_result = collection.get(ids=[f"doc_{prompt_id}"])
    context = chroma_result['documents'][0] if (chroma_result and chroma_result['documents']) else ""
    return call_hermes_llm(
        "Du är en AI Code Scientist. Skriv en komplett, optimal och ren kodlösning.", 
        f"Hämtad Dokumentation (Valfri kontext):\n{context}\n\nProblem: {original_prompt}",
        model_name=MODEL_CONFIG["expert"]
    )

# --- AGENT 4: Critic-agent ---
def agent_critic(original_prompt: str, solution: str, loop_count: int) -> tuple[bool, str]:
    print(f"⚖️ [Agent 4: Critic] Granskar koden med {MODEL_CONFIG['critic']} (Försök {loop_count})...")
    
    system_prompt = (
        "Du är en extremt noggrann och cynisk kodgranskare (Senior Code Reviewer).\n"
        "Din uppgift är att avgöra om den föreslagna koden uppfyller ALLA ursprungliga krav.\n\n"
        "Du MÅSTE inleda ditt svar på första raden med exakt ett av följande två format:\n"
        "STATUS: GODKÄND - Om koden är perfekt och uppfyller alla krav.\n"
        "STATUS: UNDERKÄND - Om det finns minsta lilla bugg eller missat krav.\n\n"
        "Efter denna statusrad ger du din tekniska feedback och motivering till utvecklaren."
    )
    
    user_content = f"URSPRUNGLIGA KRAV:\n{original_prompt}\n\nFÖRESLAGEN KODLÖSNING:\n{solution}"
    review_result = call_hermes_llm(system_prompt, user_content, model_name=MODEL_CONFIG["critic"])
    
    print(f"💬 [Critic Feedback]:\n{review_result}\n" + "-"*40)
    
    if "STATUS: GODKÄND" in review_result:
        return True, review_result
    return False, review_result

# --- AGENT 5: Arkiveringsagenten ---
def agent_archiver(original_prompt: str, final_solution: str) -> int:
    print("🗄️ [Agent 5: Arkiv] Sparar slutresultat i databasen...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO solutions (prompt, solution) VALUES (?, ?)", (original_prompt, final_solution))
    inserted_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return inserted_id

# ==========================================
# 3. ASYNKRON ORKESTRERING
# ==========================================

def run_agent_pipeline_background(user_problem: str, webhook_url: Optional[str] = None):
    print(f"🚀 Startar agent-pipeline för: '{user_problem[:30]}...'")
    prompt_id = f"{hash(user_problem)}_{uuid.uuid4().hex[:8]}"
    loop_count = 1
    current_prompt = user_problem
    
    try:
        raw_info = agent_searcher(current_prompt)
        
        if raw_info:
            agent_processor(raw_info, prompt_id)
        else:
            try:
                collection.delete(ids=[f"doc_{prompt_id}"])
            except:
                pass
            collection.add(
                documents=["Ingen extern nätverksdokumentation behövdes för denna uppgift. Lös uppgiften baserat på din inbyggda kunskap."], 
                ids=[f"doc_{prompt_id}"]
            )
        
        while True:
            solution = agent_expert(user_problem, prompt_id)
            approved, feedback = agent_critic(user_problem, solution, loop_count)
            
            if approved or loop_count >= 10:
                if loop_count >= 10 and not approved:
                    print("⚠️ Max antal loopar (10) nådda utan godkännande. Arkiverar bästa försök.")
                    
                db_id = agent_archiver(user_problem, solution)
                print(f"🎉 Klart! Sparat med ID: {db_id}")
                
                if webhook_url:
                    payload = {"status": "completed", "id": db_id, "prompt": user_problem, "solution": solution}
                    try:
                        requests.post(webhook_url, json=payload, timeout=10)
                    except:
                        pass
                break
            else:
                current_prompt = f"{user_problem} (Feedback från granskare: {feedback})"
                raw_info = agent_searcher(current_prompt)
                if raw_info:
                    agent_processor(raw_info, prompt_id)
                loop_count += 1
    except Exception as e:
        print(f"❌ Ett kritiskt fel avbröt loopen: {e}")

# ==========================================
# 4. REST API ENDPOINTS
# ==========================================

@app.post("/api/ask")
async def ask_question(request: QuestionRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_agent_pipeline_background, request.prompt, request.webhook_url)
    return {
        "status": "processing",
        "message": "Agent-loopen körs asynkront i bakgrunden."
    }

@app.get("/api/solutions/{solution_id}")
async def get_solution(solution_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, prompt, solution, timestamp FROM solutions WHERE id = ?", (solution_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Lösningen hittades inte i databasen.")
        
    return {"id": row[0], "prompt": row[1], "solution": row[2], "timestamp": row[3]}

@app.get("/api/solutions")
async def get_all_solutions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, prompt, timestamp FROM solutions ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "prompt": r[1], "timestamp": r[2]} for r in rows]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)