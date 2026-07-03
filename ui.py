import streamlit as st
import requests
import time

st.set_page_config(page_title="Hermes AI Control Center", layout="wide")
st.title("🔬 Hermes AI Multi-Agent Control Center")

# Inside Docker compose, update this to "http://hermes_api:8500" instead of http://localhost:8500
API_URL = "http://hermes_api:8500" 

# ------------------------------------------------------------------
# SIDEBAR: TRIGGER NEW RUNS
# ------------------------------------------------------------------
st.sidebar.header("🚀 Trigger New Agent Run")
new_prompt = st.sidebar.text_area("Enter your engineering prompt:")
if st.sidebar.button("Launch Multi-Agent Squad"):
    if new_prompt.strip():
        try:
            res = requests.post(f"{API_URL}/api/ask", json={"prompt": new_prompt})
            if res.status_code == 200:
                st.sidebar.success("Pipeline successfully deployed to background!")
                time.sleep(1)
                st.rerun()
            else:
                st.sidebar.error("Failed to start pipeline.")
        except Exception as e:
            st.sidebar.error(f"Cannot connect to API: {e}")
    else:
        st.sidebar.warning("Prompt cannot be empty.")

# ------------------------------------------------------------------
# LAYOUT SPLIT: LEFT (LIVE ACTIONS), RIGHT (HISTORY)
# ------------------------------------------------------------------
left_col, right_col = st.columns([1, 1])

with left_col:
    st.subheader("📡 Live Pipeline Monitor")
    
    try:
        live_data = requests.get(f"{API_URL}/api/status").json()
    except:
        live_data = {}
        st.warning("Could not pull live tracking. Is the API running?")

    if not live_data:
        st.info("No active agents running right now.")
    else:
        for task_id, info in live_data.items():
            status_color = "🟢" if info["status"] == "Completed" else ("🔴" if info["status"] == "Failed" else "⏳")
            with st.expander(f"{status_color} Task {task_id}: {info['prompt'][:40]}...", expanded=(info["status"] == "In Progress")):
                st.metric(label="Active Agent Node", value=info["current_agent"], delta=f"Loop Cycle: {info['loop']}")
                st.text_area("Internal Agent Logs:", value="\n".join(info["logs"]), height=150)
                
    if any(task["status"] == "In Progress" for task in live_data.values()):
        time.sleep(2)
        st.rerun()

# --- All code below is now correctly nested inside the right column layout context ---
with right_col:
    st.subheader("🗄️ Historical Solutions Archive")
    
    try:
        history = requests.get(f"{API_URL}/api/solutions").json()
    except Exception as e:
        history = []

    if not history:
        st.info("No completed items found in archive database.")
    else:
        for item in history:
            db_id = item["id"]
            prompt = item["prompt"]
            timestamp = item["timestamp"]
            
            if st.button(f"📄 [{timestamp}] ID #{db_id}: {prompt[:50]}...", key=db_id):
                try:
                    solution_res = requests.get(f"{API_URL}/api/solutions/{db_id}").json()
                    st.markdown("---")
                    st.markdown(f"### Details for Run #{db_id}")
                    st.caption(f"**Original Prompt:** {solution_res['prompt']}")
                    st.markdown("#### Sanitized Production Artifact:")
                    st.markdown(solution_res['solution'])
                except Exception as e:
                    st.error(f"Failed to fetch solution details: {e}")