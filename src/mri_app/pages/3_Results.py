"""Results — browse completed runs, PARs, and bioequivalence data."""

from pathlib import Path

import pandas as pd
import streamlit as st

from mri_app.downloads import ensure_directory_zip
from mri_app.runner import list_runs

st.set_page_config(page_title="Results — MRI", page_icon="📋", layout="wide")
st.title("Results")

runs = list_runs()
completed = [r for r in runs if r.get("status", {}).get("step") == "complete"]

if not completed:
    st.info("No completed runs yet.")
    st.page_link("pages/1_New_Run.py", label="Start New Run", icon="🔍")
    st.stop()

selected_name = st.selectbox(
    "Select completed run",
    options=[r["name"] for r in completed],
)
selected = next(r for r in completed if r["name"] == selected_name)
run_dir: Path = selected["path"]
config = selected.get("config", {})
molecule = config.get("molecule", "unknown")
molecule_dir = run_dir / molecule
collection = run_dir / f"{molecule}_PAR_collection"

st.divider()

with st.expander("Run Configuration", expanded=False):
    st.json(config)

st.subheader("Run Downloads")
archive_specs = []
if molecule_dir.exists():
    archive_specs.append(("Output Folder (.zip)", molecule_dir, f"{run_dir.name}_{molecule}_output"))
if collection.exists():
    archive_specs.append(("PAR Collection (.zip)", collection, f"{run_dir.name}_{molecule}_par_collection"))
archive_specs.append(("Full Run Bundle (.zip)", run_dir, f"{run_dir.name}_bundle"))

archive_columns = st.columns(len(archive_specs))
for col, (label, target, archive_name) in zip(archive_columns, archive_specs):
    with col:
        try:
            with st.spinner(f"Preparing {label.lower()}..."):
                archive_path = ensure_directory_zip(target, archive_name)
            col.download_button(
                label,
                data=archive_path.read_bytes(),
                file_name=archive_path.name,
                mime="application/zip",
                key=f"archive:{archive_name}",
                use_container_width=True,
            )
        except Exception as exc:
            col.caption(f"{label} unavailable: {exc}")

st.divider()

be_csv = run_dir / f"{molecule}_bioequivalence.csv"
if be_csv.exists():
    st.subheader("Bioequivalence Data")
    df = pd.read_csv(be_csv)
    st.dataframe(df, use_container_width=True)

    st.download_button(
        "Download CSV",
        data=be_csv.read_bytes(),
        file_name=be_csv.name,
        mime="text/csv",
    )
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
            col1, col2 = st.columns([3, 1])
            col1.markdown(f"`{rel}`")
            col2.download_button(
                "Download",
                data=pdf.read_bytes(),
                file_name=pdf.name,
                mime="application/pdf",
                key=str(pdf),
            )
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
db_path = run_dir / f"{molecule}_database.xlsx"
if db_path.exists():
    st.download_button(
        "Download Database (.xlsx)",
        data=db_path.read_bytes(),
        file_name=db_path.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
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
