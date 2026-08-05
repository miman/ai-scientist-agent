# 🔬 AI Code Scientist

An autonomous, multi-agent local engineering pipeline designed to research, implement, and self-correct software development solutions. Powered entirely by local infrastructure using **FastAPI**, **Streamlit**, **Podman-Compose**, **ChromaDB**, and **Ollama**, this framework transforms raw engineering prompts into verified, production-ready source code.

---

## 🎯 Purpose & Philosophy

Traditional AI code generation utilities operate in a complete vacuum—they lack live research data, fail to verify their own outputs, and easily succumb to logical hallucinations. 

**AI Code Scientist** bridges this gap by creating an autonomous, iterative engineering loop run entirely on local compute. By leveraging distinct agents specialized in information retrieval, state preservation, source implementation, and critical reasoning, the architecture mimics a full-cycle software development squad. 

With the integrated **Streamlit Control Center**, users can trigger runs, observe agent interactions in real time, and audit the exact input, action, and output of each agent node during recursive repair loops.

---

## 🧠 Architectural Workflow & Streamlit Monitor Interface

When a new prompt is received via the UI or the REST API, the system kicks off an asynchronous background state machine consisting of 5 specific agents. The **Streamlit UI** tracks every progression via an expanded structured telemetry schema:

1. **🕵️‍♂️ Agent 1: The Searcher (Information Retrieval)**
   Translates an unrefined user prompt into optimized engineering strings, executing them against search indexes via a self-hosted SearXNG instance to scrape contemporary documentation and patterns. 
   * *UI Tracking:* Displays the query generated and the scraped web data or snippet backups.
2. **🧹 Agent 2: The Processor (Context Sanitization & Vectoring)**
   Parses raw, unstructured web data, strips out markup noise/HTML layouts, and compresses facts into itemized bulleted context blocks.
   * *UI Tracking:* Displays the exact parsed technical context before it is passed down the wire.
3. **📋 Agent 2.5: The Planner (Strategic Blueprinting)**
   Formulates a distinct task sequence and implementation blueprint combining prompt rules with discovered web content.
   * *UI Tracking:* Inspect the markdown task roadmap before execution begins.
4. **🧠 Agent 3: The Expert (Source Generation)**
   Queries references, matches them against specifications, and synthesizes clean, fully documented, production-ready source code.
   * *UI Tracking:* Displays raw candidate code assets and structural implementations.
5. **⚖️ Agent 4: The Critic (Logistical Validation & Review)**
   A high-cognitive reasoning model acting as a strict Senior Code Reviewer. It checks for bugs, security risks, or missing handlers, explicitly issuing a `VERDICT: APPROVED` or `VERDICT: REJECTED` with adjustment requirements.
   * *UI Tracking:* Reveals the full multi-loop repair progression, including exact validation logs and rejection reasonings.
6. **✨ Agent 4.5: The Sanitizer & Agent 5: The Archiver**
   Erases conversational remnants and commits the pristine output to persistent storage (SQLite and UI final view).

---

## 📊 Streamlit Control Center Interface

The unified control panel is accessible by default at **`http://localhost:8501`**.

* **🚀 Run Trigger Panel:** Input raw programming prompts and click "Launch Multi-Agent Squad" to instantly dispatch tasks to asynchronous host background threads.
* **📡 Telemetry Live Monitor:** Displays active tasks utilizing recursive step expanders. Each block opens to show:
  * **📥 Agent Input:** The precise context block fed to the LLM node.
  * **⚙️ What it did:** The specific strategy or routine executed by the agent.
  * **📤 Agent Output:** The resulting code block or feedback text generated.
* **🗄️ Solutions History Explorer:** Pulls lightweight indexes directly from the backend API. Clicking any historical record loads the finalized, sanitized production artifact with full native markdown styling.