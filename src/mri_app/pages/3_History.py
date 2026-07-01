"""History — list all past runs."""

import streamlit as st
from mri_app.runner import list_runs

st.set_page_config(page_title="History — MRI", page_icon="📜", layout="wide")

# Sidebar styling
st.markdown("""
<style>
    [data-testid="stSidebarNav"] li a span {
        font-size: 1.15rem;
        font-weight: 700;
    }
    [data-testid="stSidebarNav"] li a {
        padding: 0.5rem 1rem;
    }
</style>
""", unsafe_allow_html=True)
st.title("Run History")

runs = list_runs()

if not runs:
    st.info("No runs found.")
    st.page_link("pages/1_New_Run.py", label="Start New Run", icon="🔍")
    st.stop()

for run in runs:
    config = run.get("config", {})
    status = run.get("status", {})
    running = run.get("running", False)

    molecule = config.get("molecule", "?")
    mode = config.get("mode", "?")
    started = config.get("started_at", "?")
    step = status.get("step", "unknown")
    error = status.get("error")

    # Status indicator
    if running:
        icon = "🟢"
        label = "Running"
    elif step == "complete":
        icon = "✅"
        label = "Complete"
    elif step == "failed":
        icon = "❌"
        label = "Failed"
    elif step == "blocked":
        icon = "🟠"
        label = "Blocked"
    else:
        icon = "⚪"
        label = step

    with st.expander(f"{icon} **{run['name']}** — {molecule} ({mode}) — {label}", expanded=running):
        col1, col2, col3 = st.columns(3)
        col1.markdown(f"**Molecule:** {molecule}")
        col2.markdown(f"**Mode:** {mode}")
        col3.markdown(f"**Started:** {started}")

        if error:
            st.error(error)

        bcol1, bcol2, bcol3 = st.columns(3)

        if step == "complete":
            if bcol1.button("View Results", key=f"view_{run['name']}"):
                st.session_state["selected_run"] = run["name"]
                st.switch_page("Home.py")

        if running:
            if bcol2.button("View Progress", key=f"progress_{run['name']}"):
                st.session_state["selected_run"] = run["name"]
                st.switch_page("Home.py")

        if not running and step != "complete":
            if bcol3.button("Resume", key=f"resume_{run['name']}"):
                from mri_app.runner import start_pipeline

                pid = start_pipeline(
                    run_dir=run["path"],
                    molecule=molecule,
                    mode="resume",
                )
                st.success(f"Resumed (PID {pid})")
                st.rerun()
