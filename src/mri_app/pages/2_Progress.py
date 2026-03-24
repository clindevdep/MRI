"""Progress — monitor active pipeline runs."""

import time
import streamlit as st
from mri_app.runner import list_runs, is_running, stop_pipeline
from mri_app.tracker import read_status, tracker_stats, find_trackers, read_log_tail

st.set_page_config(page_title="Progress — MRI", page_icon="📊", layout="wide")
st.title("Progress")

runs = list_runs()
active_runs = [r for r in runs if r.get("running")]
recent_runs = [r for r in runs if not r.get("running")][:5]

if not runs:
    st.info("No runs found. Start a new run from the New Run page.")
    st.page_link("pages/1_New_Run.py", label="Start New Run", icon="🔍")
    st.stop()

# Select run to monitor
all_options = [(r["name"], r) for r in active_runs] + [(r["name"], r) for r in recent_runs]
if not all_options:
    st.info("No runs to display.")
    st.stop()

selected_name = st.selectbox(
    "Select run",
    options=[name for name, _ in all_options],
    index=0,
)
selected_run = next(r for name, r in all_options if name == selected_name)
run_dir = selected_run["path"]
config = selected_run.get("config", {})
molecule = config.get("molecule", "unknown")

st.divider()

# Status
status = read_status(run_dir)
running = is_running(run_dir)

if running:
    st.markdown(f"**Status:** :green[Running]")
else:
    step = status.get("step", "unknown") if status else "unknown"
    if step == "complete":
        st.markdown("**Status:** :green[Complete]")
    elif step == "failed":
        st.markdown(f"**Status:** :red[Failed] — {status.get('error', '')}")
    elif step == "blocked":
        st.markdown(f"**Status:** :orange[Blocked] — {status.get('error', '')}")
    else:
        st.markdown(f"**Status:** :gray[{step}]")

# Progress bar
if status:
    step_num = status.get("step_number", 0)
    total = status.get("total_steps", 3)
    step_name = status.get("step", "")
    detail = status.get("detail", "")

    progress = step_num / total if total > 0 else 0
    st.progress(progress, text=f"Step {step_num}/{total}: {step_name}" + (f" — {detail}" if detail else ""))

# Tracker stats
col1, col2 = st.columns(2)

trackers = find_trackers(run_dir, molecule)

with col1:
    st.subheader("Core Downloads")
    core = tracker_stats(trackers["core"])
    if core["total"] > 0:
        c1, c2, c3 = st.columns(3)
        c1.metric("Completed", core["completed"])
        c2.metric("Pending", core["pending"])
        c3.metric("Failed", core["failed"])
        if core["total"] > 0:
            st.progress(core["completed"] / core["total"])
    else:
        st.caption("No core tracker yet")

with col2:
    st.subheader("PAR Downloads")
    par = tracker_stats(trackers["par"])
    if par["total"] > 0:
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Completed", par["completed"])
        p2.metric("Pending", par["pending"])
        p3.metric("Failed", par["failed"])
        p4.metric("PARs", par["pars"])
        if par["total"] > 0:
            st.progress(par["completed"] / par["total"])
    else:
        st.caption("No PAR tracker yet")

# Controls
st.divider()
col_a, col_b = st.columns(2)

with col_a:
    if running and st.button("Stop Pipeline", type="secondary"):
        stop_pipeline(run_dir)
        st.warning("Stop signal sent.")
        time.sleep(1)
        st.rerun()

with col_b:
    if running:
        if st.button("Refresh"):
            st.rerun()

# Log output
st.divider()
st.subheader("Pipeline Log")
log_text = read_log_tail(run_dir, lines=80)
if log_text:
    st.code(log_text, language="text")
else:
    st.caption("No log output yet")

# Auto-refresh while running
if running:
    time.sleep(3)
    st.rerun()
