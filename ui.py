import streamlit as st
import requests
import time

st.set_page_config(page_title="Hermes AI Control Center", layout="wide")
st.title("🔬 Hermes AI Multi-Agent Control Center")

API_URL = "http://hermes_api:8500" 

# ------------------------------------------------------------------
# SIDEBAR: TRIGGER RUNS
# ------------------------------------------------------------------
st.sidebar.header("🚀 Trigger New Agent Run")
new_prompt = st.sidebar.text_area("Enter your engineering prompt:")
if st.sidebar.button("Launch Multi-Agent Squad"):
    if new_prompt.strip():
        try:
            res = requests.post(f"{API_URL}/api/ask", json={"prompt": new_prompt})
            if res.status_code == 200:
                st.sidebar.success("Pipeline successfully deployed!")
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.sidebar.error(f"Cannot connect to API: {e}")

# ------------------------------------------------------------------
# MONITOR & INSPECTOR LAYOUT
# ------------------------------------------------------------------
left_col, right_col = st.columns([1, 1])

with left_col:
    st.subheader("📡 Live Pipeline & Agent Step Telemetry")
    try:
        live_data = requests.get(f"{API_URL}/api/status").json()
    except:
        live_data = {}

    if not live_data:
        st.info("No active agents running right now.")
    else:
        for task_id, info in live_data.items():
            status_color = "🟢" if info["status"] == "Completed" else ("🔴" if info["status"] == "Failed" else "⏳")
            
            with st.expander(f"{status_color} Task {task_id}: {info['prompt'][:40]}...", expanded=(info["status"] == "In Progress")):
                st.write(f"**Overall Status:** {info['status']} | **Active Node:** {info['current_agent']}")
                
                # --- NEW FEATURE: STEP BY STEP BREAKDOWN ---
                st.write("---")
                st.markdown("#### 🕵️‍♂️ Individual Agent Actions Work History:")
                
                if not info["agent_steps"]:
                    st.caption("Initializing framework components...")
                else:
                    for i, step in enumerate(info["agent_steps"]):
                        with st.expander(f"Step {i+1}: {step['agent']}"):
                            st.markdown("**📥 Agent Input:**")
                            st.code(step["input"], language="text")
                            st.markdown(f"**⚙️ What it did:**\n*{step['action']}*")
                            st.markdown("**📤 Agent Output:**")
                            if "```" in step["output"]:
                                st.markdown(step["output"])
                            else:
                                st.code(step["output"], language="markdown")
                                
                # If finished, optionally view final output right here
                if info["status"] == "Completed" and info.get("final_solution"):
                    st.success("✨ Final Answer Generated!")
                    if st.button("Display Clean Code Below", key=f"show_live_{task_id}"):
                        st.markdown(info["final_solution"])

    if any(task["status"] == "In Progress" for task in live_data.values()):
        time.sleep(2)
        st.rerun()

with right_col:
    st.subheader("🗄️ Historical Solutions Archive")
    try:
        history = requests.get(f"{API_URL}/api/solutions").json()
    except:
        history = []

    if not history:
        st.info("No completed items found in archive database.")
    else:
        for item in history:
            db_id = item["id"]
            prompt = item["prompt"]
            timestamp = item["timestamp"]
            
            if st.button(f"📄 [{timestamp}] ID #{db_id}: {prompt[:50]}...", key=f"hist_{db_id}"):
                try:
                    solution_res = requests.get(f"{API_URL}/api/solutions/{db_id}").json()
                    
                    # Store selected view in streamlit state to show under the history feed
                    st.session_state["selected_solution"] = solution_res
                except Exception as e:
                    st.error(f"Error: {e}")
        
        # Display the selected historical solution
        if "selected_solution" in st.session_state:
            sol = st.session_state["selected_solution"]
            st.markdown("---")
            st.markdown(f"### 🎉 Final Answer for Run #{sol['id']}")
            st.caption(f"**Prompt:** {sol['prompt']}")
            st.markdown("#### Sanitized Production Output:")
            st.markdown(sol['solution'])