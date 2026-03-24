"""New Run — start a download pipeline."""

import re

import streamlit as st
from mri_app.runner import make_run_dir, save_upload, start_pipeline

st.set_page_config(page_title="New Run — MRI", page_icon="🔍", layout="wide")
st.title("New Run")

# Mode selection
st.markdown("### **Source mode**")

mode = st.radio(
    "Select how to start the pipeline",
    options=["basic", "automatic", "full"],
    captions=[
        "Upload basic MRI export (.xlsx) — RECOMMENDED",
        "Search MRI portal by molecule name",
        "Upload pre-compiled full database (.xlsx)",
    ],
    index=0,
    horizontal=True,
)

st.divider()

# Mode-specific inputs
molecule = ""
uploaded_file = None
max_products = 10000

if mode == "basic":
    st.markdown(
        "**Step 1:** Export `.xlsx` from [mri.cts-mrp.eu](https://mri.cts-mrp.eu/)  \n"
        "**Step 2:** Upload it below. The pipeline will download extended info for each registration, "
        "then download PARs and extract bioequivalence data."
    )
    uploaded_file = st.file_uploader("Basic MRI export (.xlsx)", type=["xlsx"])
    molecule = st.text_input("Molecule label", placeholder="e.g. ketoprofen")
    max_products = st.number_input("Max products", min_value=1, value=10000, step=100)

    if uploaded_file and not molecule:
        name = uploaded_file.name.replace(".xlsx", "").lower()
        for suffix in ("_core_database", "_database", "_manual_mri"):
            name = name.replace(suffix, "")
        name = re.sub(r"[^a-z0-9]", "_", name).strip("_")
        molecule = name
        st.info(f"Auto-detected molecule label: **{molecule}**")

elif mode == "automatic":
    st.markdown(
        "Enter the molecule/active substance name. The pipeline will search the MRI portal, "
        "download product data, PARs, and extract bioequivalence data."
    )
    molecule = st.text_input("Molecule name (INN)", placeholder="e.g. ketoprofen")
    max_products = st.number_input("Max products", min_value=1, value=10000, step=100)

elif mode == "full":
    st.markdown(
        "Upload a previously-compiled full database. The pipeline will skip extended info download "
        "and go directly to PAR downloads."
    )
    uploaded_file = st.file_uploader("Full database (.xlsx)", type=["xlsx"])
    molecule = st.text_input("Molecule label", placeholder="e.g. ketoprofen")
    max_products = st.number_input("Max products", min_value=1, value=10000, step=100)

st.divider()

# Launch
can_start = bool(molecule)
if mode in ("basic", "full") and not uploaded_file:
    can_start = False

if st.button("Start Pipeline", type="primary", disabled=not can_start):
    with st.spinner("Launching pipeline..."):
        run_dir = make_run_dir(molecule)

        core_db = None
        basic_export = None

        if uploaded_file:
            saved = save_upload(uploaded_file)
            if mode == "basic":
                basic_export = saved
            elif mode == "full":
                core_db = saved

        pid = start_pipeline(
            run_dir=run_dir,
            molecule=molecule,
            mode=mode,
            max_products=max_products,
            core_db=core_db,
            basic_export=basic_export,
        )

    st.success(f"Pipeline started (PID {pid})")
    st.info(f"Run directory: `{run_dir}`")
    st.page_link("pages/2_Progress.py", label="Go to Progress", icon="📊")
