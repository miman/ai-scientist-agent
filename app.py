import os
import sqlite3
import threading
import uuid
import requests
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup

app = FastAPI(title="Hermes AI Adaptive Multi-Agent Problem Solver API")

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
# 2. AGENT LOGIC & IN-MEMORY TOOLS
# ==========================================
def tool_web_search(query: str) -> str:
    query = query.strip('"').strip("'")
    web_pages_extracted = []
    
    try:
        print(f"📡 [Tool: Search] Initializing safe connection wrapper for query: '{query}'", flush=True)
        
        with DDGS() as ddgs:
            search_results = []
            try:
                # Execution Attempt 1: Standard organic text search
                search_results = list(ddgs.text(query, max_results=10))
            except Exception as e:
                print(f"⚠️ Primary text search blocked or timed out: {e}", flush=True)
            
            # CRITICAL FALLBACK 1: If organic text search is blocked, immediately pivot to the News index!
            if not search_results:
                print("🔄 [Tool: Search] Organic index empty. Pivoting immediately to DuckDuckGo News index...", flush=True)
                try:
                    # News index uses different rate-limiting thresholds and works better inside containers
                    news_results = list(ddgs.news(query, max_results=5))
                    # Map the news schema to match our expectations
                    search_results = [{"href": n.get("url"), "title": n.get("title"), "body": n.get("body")} for n in news_results]
                except Exception as news_err:
                    print(f"⚠️ News index pivot failed as well: {news_err}", flush=True)

            # CRITICAL FALLBACK 2: If still empty, trim keywords to a bare-minimum macro query
            if not search_results:
                print("🔄 [Tool: Search] News index empty. Retrying with ultra-trimmed macro keywords...", flush=True)
                try:
                    macro_query = " ".join(query.split()[:2]) # e.g., Just 'Volvo Group'
                    search_results = list(ddgs.text(macro_query, max_results=5))
                except Exception as macro_err:
                    print(f"⚠️ Macro keyword recovery failed: {macro_err}", flush=True)

            print(f"🔍 [Tool: Search] Total available target links after recovery phases: {len(search_results)}", flush=True)
            
            success_count = 0
            for i, r in enumerate(search_results):
                url = r.get('href')
                title = r.get('title', 'Untitled Destination')
                snippet_backup = r.get('body') or r.get('snippet') or ''
                
                if not url:
                    continue
                    
                print(f"🌐 [Scraper] Processing Index Position #{i+1} Target Link -> {url}", flush=True)
                
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    }
                    page_response = requests.get(url, headers=headers, timeout=6)
                    
                    if page_response.status_code == 200:
                        soup = BeautifulSoup(page_response.text, "html.parser")
                        
                        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                            element.extract()
                            
                        page_text = soup.get_text()
                        clean_text = " ".join(page_text.split())
                        trimmed_content = " ".join(clean_text.split()[:800])
                        
                        if len(trimmed_content.strip()) > 200:
                            print(f"✅ [Scraper] Successfully extracted {len(trimmed_content.split())} words of deep context from Link #{i+1}", flush=True)
                            web_pages_extracted.append(f"Source Link: {url}\nTitle: {title}\nFull-Content: {trimmed_content}\n")
                            success_count += 1
                            if success_count >= 3:
                                break
                            continue
                            
                    print(f"⚠️ Link #{i+1} returned bad status layout ({page_response.status_code}). Utilizing preview snippet context.", flush=True)
                    clean_snippet = " ".join(snippet_backup.split())
                    web_pages_extracted.append(f"Source Link: {url}\nTitle: {title}\nSnippet-Only: {clean_snippet}\n")
                    success_count += 1
                    
                except Exception as scrape_error:
                    print(f"⚠️ Connection failure on Link #{i+1} ({scrape_error}). Falling back to engine text summary.", flush=True)
                    clean_snippet = " ".join(snippet_backup.split())
                    web_pages_extracted.append(f"Source Link: {url}\nTitle: {title}\nSnippet-Only: {clean_snippet}\n")
                    success_count += 1
                    
                if success_count >= 3:
                    break

        if web_pages_extracted:
            return "\n\n---\n\n".join(web_pages_extracted)
            
        # HARD ABSOLUTE BACKUP STATEMENT: If internet connection is completely restricted inside container
        print("⚠️ All search parameters and fallbacks resulted in empty datasets.", flush=True)
        return "Factual context check: Searching for real-time market data returned no active text snippets. Target valuation analysis using standard fundamental metrics."
            
    except Exception as e:
        print(f"❌ Critical Exception caught inside tool_web_search module layer: {str(e)}", flush=True)
        return f"Web search tool execution failure: {str(e)}"

def call_hermes_llm(system_prompt: str, user_content: str, model_name: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://192.168.68.100:11434")
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "stream": False,
        "options": {"temperature": 0.0}, 
        "keep_alive": "30m"
    }
    try:
        endpoint = f"{ollama_url.rstrip('/')}/api/chat"
        response = requests.post(endpoint, json=payload, timeout=300)
        response.raise_for_status()
        return response.json()["message"]["content"]
    except Exception as e:
        print(f"⚠️ Error calling Ollama ({model_name}): {e}", flush=True)
        return f"Internal generation pipeline error/timeout: {str(e)}"

def agent_searcher(prompt: str, history_context: str = "") -> Optional[str]:
    print(f"🕵️‍♂️ [Agent 1: Searcher] Assessing if web search or supplementary data is needed...", flush=True)
    
    system_prompt = (
        "You are an information retrieval triage specialist.\n"
        "Determine if we must query the live web to fetch real-time facts, specific data points, documentation, or answers to fulfill the request.\n"
        "If previous loop execution history is attached, analyze the missing gaps or rejections and generate a search query specifically targeted at finding the data needed to resolve those rejections.\n\n"
        "You MUST respond in EXACTLY one of these formats:\n"
        "DECISION: NO\n"
        "DECISION: YES | SEARCH_QUERY: keywords focusing only on what is missing"
    )
    
    user_content = f"TARGET REQUEST:\n{prompt}"
    if history_context:
        user_content += f"\n\nPAST EXECUTION HISTORY:\n{history_context}"
        
    raw_decision = call_hermes_llm(system_prompt, user_content, model_name=MODEL_CONFIG["searcher"]).strip()
    
    if "DECISION: NO" in raw_decision or raw_decision.strip().upper() == "NO":
        print("💡 [Agent 1: Searcher] Decision: No new web search required.", flush=True)
        return None
        
    if "SEARCH_QUERY:" in raw_decision:
        search_query = raw_decision.split("SEARCH_QUERY:")[-1].strip().strip('"').strip("'")
        if search_query:
            print(f"🌐 [Agent 1: Searcher] Target query generated: '{search_query}'", flush=True)
            return tool_web_search(search_query)
            
    fallback_query = raw_decision.replace("DECISION: YES", "").replace("|", "").replace("DECISION:", "").strip().strip('"').strip("'")
    if fallback_query and len(fallback_query) > 1:
        print(f"🌐 [Agent 1: Searcher] Executing fallback string parameters: '{fallback_query}'", flush=True)
        return tool_web_search(fallback_query)
        
    print("⚠️ [Agent 1: Searcher] Search parsing format variant caught. Running query fallback directly.", flush=True)
    return tool_web_search(prompt)

def agent_processor(raw_data: str) -> str:
    print(f"🧹 [Agent 2: Processor] Condensing newly discovered web items...", flush=True)
    return call_hermes_llm(
        "You are an advanced data extraction assistant. Read the provided raw text data segments.\n"
        "Isolate and pull out ALL vital metrics, values, core statistics, dates, constraints, and direct factual answers matching the request requirements.\n"
        "Format the result as a concise bulleted itemized list of facts under 250 words. Completely avoid narrative filler or conversational explanations.", 
        raw_data, 
        model_name=MODEL_CONFIG["processor"]
    )

def agent_planner(original_prompt: str, accumulated_context: str) -> str:
    print(f"📋 [Agent 2.5: Planner] Engineering strategic blueprint layout...", flush=True)
    system_prompt = (
        "You are a sharp Project Planner and System Architect.\n"
        "Review the user query and the accumulated data points context log.\n"
        "Draft a direct, clear, and straightforward structural blueprint for the final response.\n"
        "Specify exactly what structural layout sections, data parameters, logic structures, or evaluation conclusions the expert must provide.\n"
        "Match the scale and depth of the blueprint to the complexity of the question. Do not bloat simple requests.\n"
        "Do not write the final answer text or code yourself. Output ONLY the list of step-by-step blueprint guidelines."
    )
    user_content = f"COMPLETE ACCUMULATED KNOWLEDGE:\n{accumulated_context}\n\nORIGINAL REQUEST TARGETS:\n{original_prompt}"
    blueprint_output = call_hermes_llm(system_prompt, user_content, model_name=MODEL_CONFIG["planner"])
    
    print(f"\n[=== PLANNER SOLUTION BLUEPRINT ===]", flush=True)
    print(blueprint_output, flush=True)
    print(f"[===================================]\n", flush=True)
    
    return blueprint_output

def agent_expert(original_prompt: str, blueprint: str, accumulated_context: str) -> str:
    print(f"🧠 [Agent 3: Expert] Assembling comprehensive solution matrix...", flush=True)
    
    print(f"\n[=== RESEARCH SEARCH EXTRACT SENT TO EXPERT ===]", flush=True)
    print(accumulated_context, flush=True)
    print(f"[==============================================]\n", flush=True)
    
    system_prompt = (
        "You are an expert Subject Matter Engineer and Technical Writer.\n"
        "Your task is to craft a flawless, production-ready solution following the provided blueprint instructions.\n"
        "CRITICAL: You must explicitly ground your answer using the data, numbers, logic parameters, and variables provided inside the ACCUMULATED CONTEXT.\n"
        "If code is required, output complete scripts with error handling. If reports are requested, output a deep data-driven analysis."
    )
    user_content = f"ACCUMULATED KNOWLEDGE LOG:\n{accumulated_context}\n\nBLUEPRINT MATRIX:\n{blueprint}\n\nTARGET USER PROMPT:\n{original_prompt}"
    return call_hermes_llm(system_prompt, user_content, model_name=MODEL_CONFIG["expert"])

def agent_critic(original_prompt: str, solution: str, loop_count: int) -> tuple[bool, str]:
    print(f"⚖️ [Agent 4: Critic] Auditing structural composition (Attempt {loop_count})...", flush=True)
    system_prompt = (
        "You are a strict, cynical, and highly analytical Senior Quality Auditor.\n"
        "Your single task is to perform an intense audit on the proposed solution against the original user requirements.\n\n"
        "CRITICAL GUIDELINES:\n"
        "- If a report or text analysis is requested, check if real-world metrics, numbers, or specific required data points are missing, vague, or filled with placeholder descriptions.\n"
        "- If code is requested, check for logical bugs, syntax breaks, optimization failures, or missing handling mechanisms.\n\n"
        "You MUST explicitly write exactly one of these verdict tokens in your audit summary:\n"
        "VERDICT: APPROVED (Only if the text completely satisfies the user perfectly without flaws)\n"
        "VERDICT: REJECTED (If facts are missing, numbers are absent, or improvements are critically needed)\n\n"
        "Provide a concrete explanation detailing exactly what data, variables, or features are missing so the pipeline can fix it."
    )
    user_content = f"ORIGINAL USER TARGET:\n{original_prompt}\n\nPROPOSED SOLUTION STRATEGEMS:\n{solution}"
    review_result = call_hermes_llm(system_prompt, user_content, model_name=MODEL_CONFIG["critic"])
    
    print(f"\n================ CRITIC AUDIT RECONNAISSANCE (Loop {loop_count}) ================", flush=True)
    print(review_result, flush=True)
    print("====================================================================\n", flush=True)
    
    if "APPROVED" in review_result.upper() and "REJECTED" not in review_result.upper():
        return True, review_result
    return False, review_result

def agent_sanitizer(raw_solution: str) -> str:
    print("✨ [Agent 4.5: Sanitizer] Extracting pristine technical content...", flush=True)
    system_prompt = (
        "You are a professional Technical Editor.\n"
        "Take the approved solution and strip out all conversational filler, chat pleasantries, or pipeline internal remarks.\n"
        "Remove text like 'Sure here is the edit', 'I have added the stock numbers as requested', or 'Let me know if you need anything else'.\n"
        "Retain 100% of the core report data, markdown structural layouts, or code objects intact. Output ONLY the clean result."
    )
    return call_hermes_llm(system_prompt, raw_solution, model_name=MODEL_CONFIG["sanitizer"])

def agent_archiver(original_prompt: str, final_solution: str) -> int:
    print("🗄️ [Agent 5: Archive] Committing polished artifact to persistent storage...", flush=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO solutions (prompt, solution) VALUES (?, ?)", (original_prompt, final_solution))
    inserted_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return inserted_id

# ==========================================
# 3. CORE ORCHESTRATION PIPELINE
# ==========================================
def run_agent_pipeline_background(user_problem: str, webhook_url: Optional[str] = None):
    print(f"🚀 Launching adaptive multi-agent research loop for: '{user_problem[:40]}...'", flush=True)
    loop_count = 1
    
    research_log: List[str] = []
    pipeline_history: List[str] = []
    
    try:
        while True:
            history_context = "\n\n".join(pipeline_history)
            
            raw_info = agent_searcher(user_problem, history_context=history_context)
            if raw_info:
                fresh_facts = agent_processor(raw_info)
                if fresh_facts.strip() and "error" not in fresh_facts.lower():
                    research_log.append(fresh_facts)
            
            accumulated_context = "\n---\n".join(research_log) if research_log else "No external web data logged yet."
            
            blueprint = agent_planner(user_problem, accumulated_context)
                
            if history_context:
                blueprint += f"\n\nCRITICAL ISSUES TO CORRECT FROM PREVIOUS ATTEMPTS:\n{history_context}"
            
            solution = agent_expert(user_problem, blueprint, accumulated_context)
            approved, feedback = agent_critic(user_problem, solution, loop_count)
            
            if approved or loop_count >= 5:
                if loop_count >= 5 and not approved:
                    print("⚠️ Maximum correction cycles hit. Archiving best available variant draft.", flush=True)
                
                polished_solution = agent_sanitizer(solution)
                db_id = agent_archiver(user_problem, polished_solution)
                print(f"🎉 Pipeline successfully concluded! Saved under SQLite row key entry: {db_id}", flush=True)
                
                if webhook_url:
                    try: requests.post(webhook_url, json={"status": "completed", "id": db_id}, timeout=10)
                    except: pass
                break
            else:
                pipeline_history.append(f"Attempt {loop_count} Rejected.\nCritic Reasonings:\n{feedback}")
                loop_count += 1
                
    except Exception as e:
        print(f"❌ Critical pipeline failure within background process thread: {e}", flush=True)

# ==========================================
# 4. REST API ENDPOINTS
# ==========================================
@app.post("/api/ask")
def ask_question(request: QuestionRequest):
    thread = threading.Thread(
        target=run_agent_pipeline_background, 
        args=(request.prompt, request.webhook_url)
    )
    thread.start()
    return {
        "status": "processing",
        "message": "The adaptive loop pipeline has successfully launched in a background thread context."
    }

@app.get("/api/solutions/{solution_id}")
def get_solution(solution_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, prompt, solution, timestamp FROM solutions WHERE id = ?", (solution_id,))
    row = cursor.fetchone()
    conn.close()
    if not row: raise HTTPException(status_code=404, detail="Archive index entry target not found.")
    return {"id": row[0], "prompt": row[1], "solution": row[2], "timestamp": row[3]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)