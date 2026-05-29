# 🔬 AI Scientist

This is a sequential/reviewing multi-agent pipeline.

An autonomous, multi-agent local engineering pipeline designed to research, implement, and self-correct software development solutions. Powered entirely by local infrastructure using **FastAPI**, **Podman-Compose**, **ChromaDB**, and **Ollama**, this framework transforms raw engineering prompts into verified, production-ready source code.

---

## 🎯 Purpose & Philosophy

Traditional AI code generation utilities operate in a complete vacuum—they lack live research data, fail to verify their own outputs, and easily succumb to logical hallucinations. 

**Hermes AI Code Scientist** bridges this gap by creating an autonomous, iterative engineering loop run entirely on local compute. By leveraging distinct agents specialized in information retrieval, state preservation, source implementation, and critical reasoning, the architecture mimics a full-cycle software development squad. It handles transient network context, cross-examines solutions against strict functional benchmarks, and executes auto-remediation cycles without requiring human oversight or incurring premium token costs.

---

## 🧠 Architectural Workflow & Agent Roles

When a new prompt is received, the system kicks off an asynchronous background state machine consisting of 5 specific agents:

1. **🕵️‍♂️ Agent 1: The Searcher (Information Retrieval)**
   Translates an unrefined user prompt into optimized engineering strings, executing them against search indexes via the DuckDuckGo API to scrape contemporary documentation, API syntaxes, and structural patterns.
2. **🧹 Agent 2: The Processor (Context Sanitization & Vectoring)**
   Parses raw, unstructured web data, strips out markup noise/HTML layouts, and persists the extracted engineering facts into a localized **ChromaDB Vector Store** as embeddings.
3. **🧠 Agent 3: The Expert (Source Generation)**
   Queries ChromaDB for contextual references, matches them against the core requirements, and synthesizes clean, fully documented, production-ready source code.
4. **⚖️ Agent 4: The Critic (Logistical Validation & Review)**
   A high-cognitive reasoning model acting as a strict Senior Code Reviewer. It screens outputs for functional edge cases, compilation landmines, and syntax correctness. It explicitly issues either a `STATUS: GODKÄND` (Pass) or `STATUS: UNDERKÄND` (Fail) directive accompanied by prescriptive engineering adjustments.
5. **🗄️ Agent 5: The Archiver (State Preservation)**
   Upon validation or loop exhaustion, flushes the final artifacts down to persistent storage, appending rows to a relational SQLite database and exporting standalone, clean markdown files to active storage blocks.

---

## ⚙️ Core Stack & Component Mappings

* **Framework Engine:** FastAPI (Python 3.11-slim) executing non-blocking `BackgroundTasks`.
* **Vector State Layer:** ChromaDB HTTP server running locally for retrieval-augmented context injection.
* **Relational Storage:** SQLite 3 utilizing isolated transaction boundaries.
* **Local Compute Backend:** Ollama orchestrating specialized deep learning networks directly inside Host VRAM (optimally balanced for GPUs such as the **RTX 5070 Ti**):
  * **Processing & Extraction Workhorse:** `qwen3.5:9b` (Low latency, crisp functional instruction-following).
  * **Dedicated Generator:** `qwen2.5-coder:14b` (Highly specialized in writing complex software architecture).
  * **Deep Validation Engine:** `deepseek-r1:14b` (High-cognitive reasoning via internal chain-of-thought verification paths).

---

## 📊 API Interface Overview

### 1. Dispatch Request Pipeline
* **Endpoint:** `POST /api/ask`
* **Payload:**
```json
{
  "prompt": "Skriv en Python-funktion som validerar om en sträng är en korrekt e-postadress. Använd regex.",
  "webhook_url": "[https://your-ci-cd-pipeline.local/webhooks/catch](https://your-ci-cd-pipeline.local/webhooks/catch)"
}
"timestamp": "2026-05-28 23:15:00"
}
```