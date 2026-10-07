"""History — list all past runs."""

import streamlit as st
from mri_app.run_controls import SCOPE_LABELS, continue_controls
from mri_app.runner import RESULT_STATES, list_runs

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
    elif step == "core_complete":
        icon = "🗂️"
        label = "Core database ready"
    elif step == "batch_complete":
        icon = "⏸️"
        label = "Batch complete — more to download"
    else:
        icon = "⚪"
        label = step

    with st.expander(f"{icon} **{run['name']}** — {molecule} ({mode}) — {label}", expanded=running):
        col1, col2, col3 = st.columns(3)
        col1.markdown(f"**Molecule:** {molecule}")
        col2.markdown(f"**Mode:** {mode}")
        col3.markdown(f"**Started:** {started}")

        scope = SCOPE_LABELS.get(config.get("scope", "full"), "Full run")
        par_limit = int(config.get("par_limit") or 0)
        sessions = len(config.get("sessions", [])) or 1
        st.caption(
            f"Scope: {scope} · PAR limit (last session): "
            f"{par_limit if par_limit > 0 else 'unlimited'} · sessions: {sessions}"
        )
        if status.get("detail") and step in RESULT_STATES:
            st.caption(status["detail"])

        if error:
            st.error(error)

        bcol1, bcol2, bcol3 = st.columns(3)

        if step in RESULT_STATES:
            if bcol1.button("View Results", key=f"view_{run['name']}"):
                st.session_state["selected_run"] = run["name"]
                st.switch_page("Home.py")

        if running:
            if bcol2.button("View Progress", key=f"progress_{run['name']}"):
                st.session_state["selected_run"] = run["name"]
                st.switch_page("Home.py")

        if not running and step != "complete":
            st.divider()
            if continue_controls(run["path"], config, step, key=f"resume_{run['name']}"):
                st.session_state["selected_run"] = run["name"]
                st.switch_page("Home.py")
