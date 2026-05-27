"""Session — monitor progress and browse results."""

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from mri_app.downloads import ensure_directory_zip
from mri_app.runner import list_runs, is_running, stop_pipeline
from mri_app.tracker import read_status, tracker_stats, find_trackers, read_log_tail

st.set_page_config(page_title="Session — MRI", page_icon="📊", layout="wide")

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
    /* Distinguishable tabs */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 0.5rem;
        border-bottom: 2px solid rgba(0,0,0,0.1);
    }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        font-size: 1.25rem;
        font-weight: 700;
        padding: 0.7rem 2.5rem;
        border: 2px solid rgba(0,0,0,0.12);
        border-bottom: none;
        border-radius: 10px 10px 0 0;
        background: rgba(0,0,0,0.04);
    }
    [data-testid="stTabs"] [aria-selected="true"] {
        background: white;
        border-color: rgba(0,0,0,0.2);
        border-bottom: 2px solid white;
        margin-bottom: -2px;
    }
</style>
""", unsafe_allow_html=True)
st.title("Session")

runs = list_runs()
active_runs = [r for r in runs if r.get("running")]
recent_runs = [r for r in runs if not r.get("running")][:5]

if not runs:
    st.info("No runs found. Start a new run from the New Run page.")
    st.page_link("pages/1_New_Run.py", label="Start New Run", icon="🔍")
    st.stop()

# Build options list — active first, then recent
all_options = [(r["name"], r) for r in active_runs] + [(r["name"], r) for r in recent_runs]
if not all_options:
    st.info("No runs to display.")
    st.stop()

# Honor selected_run from History page
default_idx = 0
if "selected_run" in st.session_state:
    target = st.session_state.pop("selected_run")
    names = [name for name, _ in all_options]
    if target in names:
        default_idx = names.index(target)

selected_name = st.selectbox(
    "Select run",
    options=[name for name, _ in all_options],
    index=default_idx,
)
selected_run = next(r for name, r in all_options if name == selected_name)
run_dir: Path = selected_run["path"]
config = selected_run.get("config", {})
molecule = config.get("molecule", "unknown")

st.divider()

# Status badge
status = read_status(run_dir)
running = is_running(run_dir)
step = status.get("step", "unknown") if status else "unknown"

if running:
    st.markdown("**Status:** :green[Running]")
elif step == "complete":
    st.markdown("**Status:** :green[Complete]")
elif step == "failed":
    st.markdown(f"**Status:** :red[Failed] — {status.get('error', '')}")
elif step == "blocked":
    st.markdown(f"**Status:** :orange[Blocked] — {status.get('error', '')}")
else:
    st.markdown(f"**Status:** :gray[{step}]")

# Tabs
tab_results, tab_progress = st.tabs(["Results", "Progress"])

# ── Progress Tab ──────────────────────────────────────────────────────────

with tab_progress:
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

# ── Results Tab ───────────────────────────────────────────────────────────

with tab_results:
    per_proc = run_dir / f"{molecule}_per_procedure"
    molecule_dir = per_proc if per_proc.is_dir() else run_dir / molecule
    collection = run_dir / f"{molecule}_PAR_collection"

    if step != "complete":
        st.info("Results will appear here once the pipeline completes.")
    else:
        with st.expander("Run Configuration", expanded=False):
            st.json(config)

        st.subheader("Download")
        st.caption("Use a single zip archive to download the full result bundle for this run.")
        try:
            with st.spinner("Preparing full run bundle..."):
                archive_path = ensure_directory_zip(run_dir, run_dir.name, molecule=molecule)
            st.download_button(
                "Download All Results (.zip)",
                data=archive_path.read_bytes(),
                file_name=archive_path.name,
                mime="application/zip",
                key=f"archive:{run_dir.name}",
                use_container_width=True,
                type="primary",
            )
        except Exception as exc:
            st.error(f"Bundle unavailable: {exc}")

        st.divider()

        be_csv = run_dir / f"{molecule}_bioequivalence.csv"
        if be_csv.exists():
            st.subheader("Bioequivalence Data")
            df = pd.read_csv(be_csv)
            st.dataframe(df, use_container_width=True)
        else:
            st.caption("No bioequivalence CSV found for this run.")

        st.divider()

        st.subheader("PAR Documents")
        if molecule_dir.exists():
            pdfs = sorted(molecule_dir.rglob("*.pdf"))
            if pdfs:
                st.markdown(f"**{len(pdfs)} PDF(s)** found")
                for pdf in pdfs:
                    rel = pdf.relative_to(molecule_dir)
                    st.markdown(f"`{rel}`")
            else:
                st.caption("No PDFs found.")
        else:
            st.caption("Molecule directory not found.")

        if collection.exists():
            flat_pdfs = sorted(collection.glob("*.pdf"))
            if flat_pdfs:
                st.divider()
                st.subheader("PAR Collection (flat)")
                st.caption(f"{len(flat_pdfs)} PDFs in flat folder for batch import")

        st.divider()
        st.subheader("Database")
        db_path = run_dir / f"{molecule}_core_database.xlsx"
        if not db_path.exists():
            db_path = run_dir / f"{molecule}_database.xlsx"
        if db_path.exists():
            try:
                db_df = pd.read_excel(db_path)
                st.dataframe(db_df.head(20), use_container_width=True)
                st.caption(f"Showing first 20 of {len(db_df)} rows")
            except Exception:
                st.caption("Could not preview database.")
        else:
            st.caption("No database file found.")

        report = run_dir / f"{molecule}_run_report.txt"
        if report.exists():
            with st.expander("Run Report"):
                st.code(report.read_text(), language="text")

# Auto-refresh while running
if running:
    time.sleep(3)
    st.rerun()
