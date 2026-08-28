"""
Tools module providing web search capabilities and Docker execution/logging tools.
"""

import os
import re
import shutil
import subprocess
import tempfile
import time
import requests
from bs4 import BeautifulSoup


SEARXNG_URL = os.getenv("SEARXNG_URL", "").strip()


def _parse_multi_files(content: str) -> dict:
    """
    Parses code payload containing file paths formatted like:
    // File: filename or # File: filename or ```json / ```typescript with file headers.
    Returns a dict mapping filename -> file_content.
    """
    files = {}
    current_file = None
    current_lines = []

    file_header_pattern = re.compile(
        r"^(?://|#|/\*|\*)\s*(?:File|Path|filename):\s*([a-zA-Z0-9_\-./]+)", re.IGNORECASE
    )

    for line in content.splitlines():
        match = file_header_pattern.match(line.strip())
        if match:
            if current_file and current_lines:
                files[current_file] = "\n".join(current_lines)
                current_lines = []
            current_file = match.group(1).strip()
            continue
        if current_file:
            current_lines.append(line)

    if current_file and current_lines:
        files[current_file] = "\n".join(current_lines)

    return files


def tool_run_in_docker(code_or_files: str, language: str = "python") -> str:
    """
    Builds, runs, and captures logs from code execution inside an isolated Docker container.
    Supports parsing multi-file structures, package.json, TypeScript, Python, and custom Dockerfiles.
    Uses lightweight memory limits and build constraints to prevent host OOM kills.
    """
    print(f"🐳 [Tool: Docker Runner] Preparing execution container for language/type: {language}...", flush=True)

    temp_dir = tempfile.mkdtemp(prefix="agent_dev_run_")

    try:
        # Extract contents from markdown code blocks
        blocks = re.findall(r"```(?:[a-zA-Z0-9_-]+)?\s*[\r\n]+(.*?)```", code_or_files, re.DOTALL)
        raw_payload = "\n\n".join(blocks) if blocks else code_or_files

        # Try parsing multi-file structure
        parsed_files = _parse_multi_files(raw_payload)

        # Write parsed files into temporary workspace directory
        if parsed_files:
            print(f"📂 [Tool: Docker Runner] Extracted {len(parsed_files)} multi-file assets: {list(parsed_files.keys())}", flush=True)
            for file_path, file_content in parsed_files.items():
                abs_path = os.path.join(temp_dir, file_path)
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(file_content)

        lang_lower = language.lower()

        # If LLM wrote a multi-stage Dockerfile that builds heavy node_modules, replace it with a memory-safe execution template
        if "package.json" in parsed_files or "package.json" in raw_payload or "typescript" in lang_lower or "ts" in lang_lower:
            if "package.json" not in parsed_files:
                pkg_match = re.search(r'\{\s*"name":.*?\n\}', raw_payload, re.DOTALL)
                if pkg_match:
                    with open(os.path.join(temp_dir, "package.json"), "w", encoding="utf-8") as f:
                        f.write(pkg_match.group(0))

            dockerfile_content = (
                "FROM docker.io/library/node:18-slim\n"
                "WORKDIR /app\n"
                "RUN npm install -g ts-node typescript\n"
                "COPY . .\n"
                "RUN npm install --production --prefer-offline --no-audit || true\n"
                "CMD [\"npm\", \"start\"]\n"
            )
        elif "Dockerfile" in parsed_files and "npm ci" not in parsed_files["Dockerfile"]:
            dockerfile_content = parsed_files["Dockerfile"]
        elif "python" in lang_lower:
            if not parsed_files:
                with open(os.path.join(temp_dir, "main.py"), "w", encoding="utf-8") as f:
                    f.write(raw_payload)
            dockerfile_content = (
                "FROM docker.io/library/python:3.11-slim\n"
                "WORKDIR /app\n"
                "COPY . .\n"
                "RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi\n"
                "CMD [\"python\", \"main.py\"]\n"
            )
        elif "go" in lang_lower or "golang" in lang_lower:
            if not parsed_files:
                with open(os.path.join(temp_dir, "main.go"), "w", encoding="utf-8") as f:
                    f.write(raw_payload)
            dockerfile_content = (
                "FROM docker.io/library/golang:1.21-alpine\n"
                "WORKDIR /app\n"
                "COPY . .\n"
                "CMD [\"go\", \"run\", \"main.go\"]\n"
            )
        else:
            if not parsed_files:
                with open(os.path.join(temp_dir, "index.js"), "w", encoding="utf-8") as f:
                    f.write(raw_payload)
            dockerfile_content = (
                "FROM docker.io/library/node:18-slim\n"
                "WORKDIR /app\n"
                "COPY . .\n"
                "CMD [\"node\", \"index.js\"]\n"
            )

        with open(os.path.join(temp_dir, "Dockerfile"), "w", encoding="utf-8") as f:
            f.write(dockerfile_content)

        image_tag = f"dev_agent_test_{int(time.time())}"

        # 1. Build image with memory limit constraint
        print(f"📦 [Tool: Docker Runner] Building image '{image_tag}'...", flush=True)
        build_cmd = ["docker", "build", "-t", image_tag, temp_dir]
        build_res = subprocess.run(build_cmd, capture_output=True, text=True, timeout=120)

        if build_res.returncode != 0:
            return f"❌ Docker Build Failed:\nSTDOUT:\n{build_res.stdout}\nSTDERR:\n{build_res.stderr}"

        # 2. Run container with RAM limit to protect main agent container
        print(f"🚀 [Tool: Docker Runner] Running container '{image_tag}'...", flush=True)
        run_cmd = ["docker", "run", "--rm", "--memory=512m", "--name", image_tag, image_tag]
        run_res = subprocess.run(run_cmd, capture_output=True, text=True, timeout=60)

        # Clean up image
        subprocess.run(["docker", "rmi", "-f", image_tag], capture_output=True)

        status_msg = "SUCCESS" if run_res.returncode == 0 else f"FAILED (Exit Code {run_res.returncode})"
        result_log = (
            f"=== DOCKER EXECUTION & CONTAINER LOGS ({status_msg}) ===\n"
            f"--- STDOUT ---\n{run_res.stdout.strip() or '(no output)'}\n"
            f"--- STDERR ---\n{run_res.stderr.strip() or '(no errors)'}\n"
            f"========================================================"
        )
        return result_log

    except subprocess.TimeoutExpired:
        return "❌ Docker Execution Timed Out after 120 seconds."
    except Exception as e:
        return f"❌ Error running code in Docker: {str(e)}"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _search_searxng(query: str) -> str:
    """Search using a self-hosted SearXNG instance and scrape results."""
    query = query.strip('"').strip("'")
    web_pages_extracted = []

    try:
        print(f"📡 [Tool: Search] Querying SearXNG at: {SEARXNG_URL} with query: '{query}'", flush=True)

        endpoint = f"{SEARXNG_URL.rstrip('/')}/search"
        params = {"q": query, "format": "json"}

        response = requests.get(endpoint, params=params, timeout=15)
        response.raise_for_status()
        search_results = response.json().get("results", [])

        print(f"🔍 [Tool: Search] Total results from SearXNG: {len(search_results)}", flush=True)

        success_count = 0
        for i, r in enumerate(search_results):
            url = r.get("url")
            title = r.get("title", "Untitled")
            snippet_backup = r.get("content") or ""

            if not url:
                continue

            print(f"🌐 [Scraper] Processing #{i+1} -> {url}", flush=True)

            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
                        print(f"✅ [Scraper] Extracted {len(trimmed_content.split())} words from #{i+1}", flush=True)
                        web_pages_extracted.append(
                            f"Source Link: {url}\nTitle: {title}\nFull-Content: {trimmed_content}\n"
                        )
                        success_count += 1
                        if success_count >= 3:
                            print("🎯 Quota of 3 pages reached.", flush=True)
                            break
                        continue

                print(f"⚠️ #{i+1} bad status ({page_response.status_code}). Using snippet.", flush=True)
                clean_snippet = " ".join(snippet_backup.split())
                web_pages_extracted.append(
                    f"Source Link: {url}\nTitle: {title}\nSnippet-Only: {clean_snippet}\n"
                )

            except Exception as scrape_error:
                print(f"⚠️ #{i+1} failed ({scrape_error}). Using snippet.", flush=True)
                clean_snippet = " ".join(snippet_backup.split())
                web_pages_extracted.append(
                    f"Source Link: {url}\nTitle: {title}\nSnippet-Only: {clean_snippet}\n"
                )

            if success_count >= 3:
                break

        if web_pages_extracted:
            return "\n\n---\n\n".join(web_pages_extracted)

        print("⚠️ All search parameters resulted in empty datasets.", flush=True)
        return "Web search returned no usable text content."

    except Exception as e:
        print(f"❌ Critical exception in SearXNG search: {str(e)}", flush=True)
        return f"Web search tool execution failure: {str(e)}"


def _search_duckduckgo(query: str) -> str:
    """Search using DuckDuckGo via LangChain (no API key needed)."""
    from langchain_community.tools import DuckDuckGoSearchResults

    query = query.strip('"').strip("'")

    try:
        print(f"🦆 [Tool: Search] Querying DuckDuckGo with: '{query}'", flush=True)
        search = DuckDuckGoSearchResults(num_results=5)
        results = search.run(query)
        print(f"✅ [Tool: Search] DuckDuckGo returned results.", flush=True)
        return results
    except Exception as e:
        print(f"❌ Critical exception in DuckDuckGo search: {str(e)}", flush=True)
        return f"Web search tool execution failure: {str(e)}"


def tool_web_search(query: str) -> str:
    """
    Executes a web search query.
    Uses SearXNG if SEARXNG_URL is configured, otherwise falls back to DuckDuckGo.
    """
    if SEARXNG_URL:
        return _search_searxng(query)
    else:
        return _search_duckduckgo(query)
