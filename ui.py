import streamlit as st
import requests
import time

st.set_page_config(page_title="AI Control Center", layout="wide")
st.title("🔬 AI Multi-Agent Control Center")

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
                current_agent = info.get("current_agent", "N/A")
                specialty = info.get("specialty", "N/A")
                loop_count = info.get("loop_count", 1)

                st.write(f"**Overall Status:** {info['status']} | **Active Node:** `{current_agent}`")
                
                col_a, col_b = st.columns(2)
                col_a.metric("Domain Specialty", specialty.upper())
                col_b.metric("Loop Attempt", f"#{loop_count}")

                tab_summary, tab_steps = st.tabs(["📊 State Artifacts", "🕵️‍♂️ Action History"])

                with tab_summary:
                    if info.get("blueprint"):
                        st.markdown("#### 📐 Blueprint Matrix")
                        st.info(info["blueprint"])

                    if info.get("solution"):
                        st.markdown("#### 🧠 Draft Solution")
                        st.markdown(info["solution"])

                    if info.get("critic_feedback"):
                        st.markdown("#### ⚖️ Critic Audit Feedback")
                        st.warning(info["critic_feedback"])

                with tab_steps:
                    agent_steps = info.get("agent_steps", [])
                    if not agent_steps:
                        st.caption("Initializing framework components...")
                    else:
                        for i, step in enumerate(agent_steps):
                            st.markdown(f"**Step {i+1}: Node `{step['agent']}`**")
                            st.caption(f"Input: {step['input']} | Action: {step['action']}")
                            if "```" in step["output"]:
                                st.markdown(step["output"])
                            else:
                                st.code(step["output"], language="json")
                            st.divider()
                                
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