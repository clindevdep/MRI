"""MRI Portal PAR Downloader — live dashboard (landing page).

This entry page IS the session dashboard and opens on the Progress tab so the
user lands directly on live progress. New Run and History are sidebar pages.
"""

import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from mri_app.downloads import ensure_directory_zip
from mri_app.runner import list_runs, is_running, stop_pipeline
from mri_app.sample_size import run_cvw_screening, study_from_row, SampleSizeError
from mri_app.tracker import read_status, tracker_stats, find_trackers, read_log_tail

st.set_page_config(
    page_title="MRI PAR Downloader",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sidebar styling + distinguishable tabs
st.markdown("""
<style>
    [data-testid="stSidebarNav"] li a span {
        font-size: 1.15rem;
        font-weight: 700;
    }
    [data-testid="stSidebarNav"] li a {
        padding: 0.5rem 1rem;
    }
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

st.title("MRI Portal PAR Downloader")

runs = list_runs()
active_runs = [r for r in runs if r.get("running")]
recent_runs = [r for r in runs if not r.get("running")][:5]

if not runs:
    st.info("No runs yet. Start a new download session from the **New Run** page.")
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

# Tabs — Progress first so the app opens on live progress
tab_progress, tab_results, tab_samplesize = st.tabs(["Progress", "Results", "Sample Size"])

# ── Progress Tab ──────────────────────────────────────────────────────────

with tab_progress:
    trackers = find_trackers(run_dir, molecule)
    core = tracker_stats(trackers["core"])
    par = tracker_stats(trackers["par"])

    # Composite progress bar — blends within-stage tracker completion so the
    # bar reflects real work rather than jumping in coarse 1/3 steps.
    step_name = status.get("step", "") if status else ""
    detail = status.get("detail", "") if status else ""

    core_frac = core["completed"] / core["total"] if core["total"] > 0 else 0.0
    par_frac = par["processed"] / par["total"] if par["total"] > 0 else 0.0
    if step_name == "complete":
        extraction_frac = 1.0
    elif step_name in ("extraction", "finalizing"):
        extraction_frac = 0.5
    else:
        extraction_frac = 0.0

    if step_name == "complete":
        overall = 1.0
    else:
        overall = 0.45 * core_frac + 0.45 * par_frac + 0.10 * extraction_frac

    bar_text = (step_name or "starting").replace("_", " ").title()
    if detail:
        bar_text += f" — {detail}"
    st.progress(min(max(overall, 0.0), 1.0), text=f"{bar_text} · {int(overall * 100)}%")

    # Tracker stats
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Core Downloads")
        if core["total"] > 0:
            c1, c2, c3 = st.columns(3)
            c1.metric("Completed", core["completed"])
            c2.metric("Pending", core["pending"])
            c3.metric("Failed", core["failed"])
            st.progress(core["completed"] / core["total"])
            st.caption(f"{core['completed']}/{core['total']} products")
        else:
            st.caption("No core tracker yet")

    with col2:
        st.subheader("PAR Downloads")
        if par["total"] > 0:
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("With PARs", par["with_pars"])
            p2.metric("Empty", par["empty"], help="Processed but no PAR found on the source")
            p3.metric("Failed", par["failed"])
            p4.metric("PARs", par["pars"])
            st.progress(par["processed"] / par["total"])
            caption = f"{par['processed']}/{par['total']} processed · {par['pending']} pending"
            if par["sources"]:
                src_txt = ", ".join(f"{k}: {v}" for k, v in sorted(par["sources"].items()))
                caption += f" · sources → {src_txt}"
            st.caption(caption)
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

        # ── Aggregated PK study data — selectable, feeds Sample Size tab ──
        pk_studies_csv = run_dir / f"{molecule}_pk_studies.csv"
        if pk_studies_csv.exists():
            st.subheader("Aggregated PK Study Data")
            st.caption(
                "Tick **Pool** for the studies whose CVw should be pooled, then open the "
                "**Sample Size** tab. CVw is calculated from each study's CI + N."
            )
            pk_df = pd.read_csv(pk_studies_csv)
            pk_df.insert(0, "Pool", True)
            edited = st.data_editor(
                pk_df,
                use_container_width=True,
                hide_index=True,
                disabled=[c for c in pk_df.columns if c != "Pool"],
                key=f"pk_editor:{run_dir.name}",
            )
            # Store all rows + their pool flag for the Sample Size tab.
            st.session_state[f"cvw_pk_rows:{run_dir.name}"] = edited.to_dict("records")
            n_pool = int(edited["Pool"].sum())
            st.caption(f"{len(edited)} studies · {n_pool} flagged for pooling")

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

# ── Sample Size Tab ───────────────────────────────────────────────────────

with tab_samplesize:
    st.subheader("CVw Screening & Pooled Sample Size")
    st.caption(
        "Calculates intra-subject CVw from each study's confidence interval (CVfromCI), "
        "pools the flagged studies by PK (CVpooled), and derives the required sample size "
        "(sampleN.TOST). Flag studies to pool in the **Results** tab."
    )

    pk_rows = st.session_state.get(f"cvw_pk_rows:{run_dir.name}", [])
    if not pk_rows:
        st.info("No aggregated PK studies for this run yet. They appear once the pipeline "
                "extracts bioequivalence data (see the Results tab).")
    else:
        c1, c2, c3 = st.columns(3)
        theta0 = c1.number_input("Expected GMR (theta0)", min_value=0.80, max_value=1.20,
                                 value=0.95, step=0.01)
        design = c2.selectbox("Design", ["2x2", "2x2x3", "2x2x4", "parallel"], index=0)
        be_limit = c3.number_input("Lower BE limit", min_value=0.50, max_value=0.95,
                                   value=0.80, step=0.05,
                                   help="Upper limit = 1 / lower (e.g. 0.80 ↔ 1.25).")
        powers = st.multiselect("Target power", options=[0.80, 0.85, 0.90, 0.95],
                                default=[0.80, 0.90])

        if st.button("Run CVw Screening", type="primary"):
            if not powers:
                st.error("Select at least one target power.")
            else:
                studies = [
                    study_from_row(row, incl=bool(row.get("Pool", True)),
                                   design=design, low_be_limit=be_limit)
                    for row in pk_rows
                ]
                try:
                    with st.spinner("Running CVw screening (PowerTOST)..."):
                        result = run_cvw_screening(studies, targetpowers=sorted(powers),
                                                   theta0=theta0)
                except SampleSizeError as exc:
                    st.error(f"CVw screening failed: {exc}")
                else:
                    # Pooled results per PK
                    st.markdown("#### Pooled result (by PK)")
                    pooled = result.get("pooled", {})
                    if pooled:
                        prows = []
                        for pk, s in pooled.items():
                            r = {"PK": pk, "Pooled CVw (%)": s.get("cvw_pooled"),
                                 "Studies": s.get("n_studies")}
                            for k, v in s.items():
                                if k.startswith("N-Pwr"):
                                    r[k] = v
                            prows.append(r)
                        st.dataframe(pd.DataFrame(prows), use_container_width=True, hide_index=True)
                    else:
                        st.caption("No studies flagged for pooling.")

                    # Per-study cross-check (reported vs calculated CVw)
                    st.markdown("#### Per-study CVw (reported vs calculated)")
                    per = pd.DataFrame(result.get("per_study", []))
                    if not per.empty:
                        if {"CVw_reported", "CVw_calc"}.issubset(per.columns):
                            per["Δ (calc−rep)"] = per["CVw_calc"] - per["CVw_reported"]
                        st.dataframe(per, use_container_width=True, hide_index=True)
                        st.caption("Large Δ between reported and calculated CVw flags a possible "
                                   "extraction or reporting inconsistency worth reviewing.")

                    try:
                        (run_dir / f"{molecule}_sample_size.json").write_text(json.dumps(result, indent=2))
                    except OSError:
                        pass


# Auto-refresh while running
if running:
    time.sleep(3)
    st.rerun()
