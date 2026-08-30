import streamlit as st
import requests
import time
import json

st.set_page_config(page_title="AI Control Center", layout="wide")
st.title("🔬 AI Multi-Agent Control Center")

API_URL = "http://hermes_api:8500" 

# ------------------------------------------------------------------
# SIDEBAR: TRIGGER RUNS
# ------------------------------------------------------------------
st.sidebar.header("🚀 Trigger New Agent Run")

pipeline_choice = st.sidebar.selectbox(
    "Select Agent Pipeline:",
    options=["Developer Team Pipeline", "Standard Research Pipeline"],
    index=0
)
pipeline_type = "dev_team" if pipeline_choice == "Developer Team Pipeline" else "research"

new_prompt = st.sidebar.text_area("Enter your engineering prompt:")

if st.sidebar.button("Launch Multi-Agent Squad"):
    if new_prompt.strip():
        try:
            res = requests.post(
                f"{API_URL}/api/ask",
                json={"prompt": new_prompt, "pipeline_type": pipeline_type}
            )
            if res.status_code == 200:
                st.sidebar.success(f"Pipeline ({pipeline_choice}) successfully deployed!")
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
            pipe_label = "🧑‍💻 Dev Team" if info.get("pipeline_type") == "dev_team" else "🔬 Standard"
            
            with st.container(border=True):
                current_agent = info.get("current_agent", "N/A")
                specialty = info.get("specialty", "N/A")
                loop_count = info.get("loop_count", 1)

                st.markdown(f"### {status_color} [{pipe_label}] Task `{task_id}`")
                st.caption(f"**Prompt:** {info['prompt']}")
                st.write(f"**Overall Status:** {info['status']} | **Active Node:** `{current_agent}`")
                
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Pipeline Mode", pipe_label)
                col_b.metric("Domain Specialty", specialty.upper())
                col_c.metric("Loop Attempt", f"#{loop_count}")

                tab_steps, tab_summary = st.tabs(["🕵️‍♂️ Step-by-Step Flow (Collapsible)", "📊 Current State Snapshot"])

                with tab_steps:
                    agent_steps = info.get("agent_steps", [])
                    if not agent_steps:
                        st.caption("Initializing framework components...")
                    else:
                        total_steps = len(agent_steps)
                        for i, step in enumerate(agent_steps):
                            is_latest = (i == total_steps - 1) and (info["status"] == "In Progress")
                            step_num = i + 1
                            agent_name = step["agent"]
                            
                            step_title = f"Step {step_num}: Node `{agent_name}` {'🟢 (Active)' if is_latest else '✅ (Done)'}"
                            
                            with st.expander(step_title, expanded=is_latest):
                                st.caption(f"Input Context: {step['input']} | Action: {step['action']}")
                                output_text = step["output"]
                                
                                # Render step output as formatted markdown
                                st.markdown(output_text)

                with tab_summary:
                    if info.get("pipeline_type") == "dev_team":
                        if info.get("architecture"):
                            st.markdown("#### 🏛️ Architecture Specification")
                            st.info(info["architecture"])
                        if info.get("backend_logic"):
                            st.markdown("#### ⚙️ Backend Logic")
                            st.code(info["backend_logic"], language="python")
                        if info.get("frontend_code"):
                            st.markdown("#### 🎨 Frontend UI Code")
                            st.code(info["frontend_code"], language="javascript")
                        if info.get("docker_logs"):
                            st.markdown("#### 🐳 Docker Execution Console Logs")
                            st.code(info["docker_logs"], language="text")
                        if info.get("qa_feedback"):
                            st.markdown("#### 🔍 QA Engineer Feedback")
                            st.warning(info["qa_feedback"])
                        if info.get("tester_feedback"):
                            st.markdown("#### 🧪 Tester Feedback")
                            st.warning(info["tester_feedback"])
                    else:
                        if info.get("blueprint"):
                            st.markdown("#### 📐 Blueprint Matrix")
                            st.info(info["blueprint"])

                        if info.get("solution"):
                            st.markdown("#### 🧠 Draft Solution")
                            st.markdown(info["solution"])

                        if info.get("critic_feedback"):
                            st.markdown("#### ⚖️ Critic Audit Feedback")
                            st.warning(info["critic_feedback"])

                # If finished, optionally view final output right here
                if info["status"] == "Completed" and info.get("final_solution"):
                    st.success("✨ Final Solution Generated!")
                    if st.button("Display Production Artifact Below", key=f"show_live_{task_id}"):
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