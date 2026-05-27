"""New Run — start a download pipeline."""

import re

import streamlit as st
from mri_app.runner import make_run_dir, save_upload, start_pipeline

st.set_page_config(page_title="New Run — MRI", page_icon="🔍", layout="wide")

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
    /* Prominent mode selection panel */
    .mode-panel {
        background: linear-gradient(135deg, rgba(49,108,244,0.07) 0%, rgba(49,108,244,0.02) 100%);
        border: 2px solid rgba(49,108,244,0.22);
        border-radius: 14px;
        padding: 1.2rem 1.6rem 0.8rem;
        margin-bottom: 1rem;
    }
    .mode-panel [data-testid="stRadio"] > label > div[data-testid="stMarkdownContainer"] p {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
    }
    .mode-panel [data-baseweb="radio"] > div:last-child > div {
        font-size: 1.05rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)
st.title("New Run")

# Mode selection — prominent panel
_MODE_LABELS = {
    "basic": "Basic Export",
    "automatic": "Automatic Search",
    "full": "From Core Database",
}

with st.container(border=False):
    st.markdown('<div class="mode-panel">', unsafe_allow_html=True)
    st.markdown("### **Source mode**")
    mode = st.radio(
        "Select how to start the pipeline",
        options=["basic", "automatic", "full"],
        captions=[
            "Upload basic MRI export (.xlsx)",
            "Search MRI portal by molecule name",
            "Upload an existing Core Database (.xlsx)",
        ],
        format_func=lambda x: _MODE_LABELS[x],
        index=0,
        horizontal=True,
    )
    if mode == "basic":
        st.markdown(
            '<span style="background:#16a34a; color:white; font-weight:700; '
            'padding:0.2rem 0.7rem; border-radius:6px; font-size:0.95rem;">'
            'RECOMMENDED</span>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# Mode-specific inputs
molecule = ""
uploaded_file = None
max_products = 10000

if mode == "basic":
    st.markdown(
        "**Step 1:** Export `.xlsx` from [MRI Production](https://mri-production.cts-mrp.eu/advanced-search)  \n"
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
        "Upload an existing Core Database. The pipeline will skip the portal search and "
        "extended info download, and go directly to PAR downloads and bioequivalence extraction."
    )
    uploaded_file = st.file_uploader("Core Database (.xlsx)", type=["xlsx"])
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

    st.session_state["selected_run"] = run_dir.name
    st.switch_page("pages/2_Session.py")
