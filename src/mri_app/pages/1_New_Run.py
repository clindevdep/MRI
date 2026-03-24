"""New Run — start a download pipeline."""

import re
from pathlib import Path

import streamlit as st
from mri_app.config import DATA_DIR
from mri_app.runner import start_pipeline

st.set_page_config(page_title="New Run — MRI", page_icon="🔍", layout="wide")
st.title("New Run")


# ── Project folder detection helpers ──────────────────────────────────────

def list_project_folders() -> list[Path]:
    """List subdirectories under /data that can serve as project folders."""
    if not DATA_DIR.exists():
        return []
    folders = sorted(
        [d for d in DATA_DIR.iterdir() if d.is_dir() and d.name not in ("runs", "uploads")],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return folders


def detect_project_type(folder: Path) -> tuple[str, Path | None, str]:
    """
    Auto-detect source mode from folder contents.
    Returns (mode, xlsx_path, reason).
    """
    xlsx_files = sorted(folder.glob("*.xlsx"))

    if not xlsx_files:
        return "automatic", None, "No .xlsx files found — will search MRI portal"

    # Check for basic export (filename contains 'export')
    for f in xlsx_files:
        if "export" in f.stem.lower():
            return "basic", f, f"Found basic MRI export: {f.name}"

    # Check for script-generated full database
    for f in xlsx_files:
        if "_core_database" in f.stem.lower() or "_database" in f.stem.lower():
            return "full", f, f"Found full database: {f.name}"

    # Has xlsx but doesn't match patterns — default to basic
    return "basic", xlsx_files[0], f"Found .xlsx file: {xlsx_files[0].name} (assuming basic export)"


def derive_molecule(folder: Path) -> str:
    """Derive molecule label from folder name."""
    name = folder.name.lower()
    # Strip common suffixes and timestamps
    name = re.sub(r"_\d{8}_?\d{0,6}$", "", name)
    for suffix in ("_core_database", "_database", "_export", "_manual_mri"):
        name = name.replace(suffix, "")
    name = re.sub(r"[^a-z0-9]", "_", name).strip("_")
    return name or "molecule"


# ── Step 1: Select project folder ─────────────────────────────────────────

st.markdown("### **Select project folder**")

existing_folders = list_project_folders()

if not existing_folders:
    st.warning(f"No project folders found under `{DATA_DIR}`. Create a folder with your .xlsx files and restart.")
    st.stop()

selected_name = st.selectbox(
    "Project folder",
    options=[f.name for f in existing_folders],
    index=0,
    help=f"Folders under {DATA_DIR}",
)
project_dir = DATA_DIR / selected_name

st.divider()

# ── Step 2: Auto-detect mode from folder contents ─────────────────────────

detected_mode, detected_file, detection_reason = detect_project_type(project_dir)
auto_molecule = derive_molecule(project_dir)

# Show detected xlsx files
xlsx_files = sorted(project_dir.glob("*.xlsx"))
if xlsx_files:
    with st.expander(f"Files in `{project_dir.name}/`  ({len(xlsx_files)} .xlsx)", expanded=False):
        for f in xlsx_files:
            st.text(f"  {f.name}  ({f.stat().st_size / 1024:.0f} KB)")

st.info(f"**Auto-detected:** {detection_reason}")

# Mode selection with override
st.markdown("### **Source mode**")

mode_labels = {
    "basic": "Basic MRI export — download extended info, then PARs",
    "automatic": "Automatic search — search MRI portal by molecule name",
    "full": "Full database — skip extended info, download PARs directly",
}

mode = st.radio(
    "Override if needed",
    options=["basic", "automatic", "full"],
    captions=[mode_labels[m] for m in ["basic", "automatic", "full"]],
    index=["basic", "automatic", "full"].index(detected_mode),
    horizontal=True,
)

st.divider()

# ── Step 3: Mode-specific inputs ──────────────────────────────────────────

molecule = ""
source_file = None

if mode == "basic":
    if detected_file and detected_mode == "basic":
        source_file = detected_file
        st.markdown(f"**Using:** `{detected_file.name}`")
    elif xlsx_files:
        chosen = st.selectbox("Select basic export file", options=[f.name for f in xlsx_files])
        source_file = project_dir / chosen
    else:
        st.warning("No .xlsx file in project folder. Upload one or switch to Automatic mode.")

    molecule = st.text_input("Molecule label", value=auto_molecule, placeholder="e.g. ketoprofen")
    max_products = st.number_input("Max products", min_value=1, value=10000, step=100)

elif mode == "automatic":
    molecule = st.text_input("Molecule name (INN)", value=auto_molecule, placeholder="e.g. ketoprofen")
    max_products = st.number_input("Max products", min_value=1, value=10000, step=100)

elif mode == "full":
    if detected_file and detected_mode == "full":
        source_file = detected_file
        st.markdown(f"**Using:** `{detected_file.name}`")
    elif xlsx_files:
        chosen = st.selectbox("Select full database file", options=[f.name for f in xlsx_files])
        source_file = project_dir / chosen
    else:
        st.warning("No .xlsx file in project folder. Upload one or switch to Automatic mode.")

    molecule = st.text_input("Molecule label", value=auto_molecule, placeholder="e.g. ketoprofen")
    max_products = st.number_input("Max products", min_value=1, value=10000, step=100)

st.divider()

# ── Launch ─────────────────────────────────────────────────────────────────

can_start = bool(molecule)
if mode in ("basic", "full") and not source_file:
    can_start = False

if st.button("Start Pipeline", type="primary", disabled=not can_start):
    with st.spinner("Launching pipeline..."):
        core_db = None
        basic_export = None

        if source_file:
            if mode == "basic":
                basic_export = source_file
            elif mode == "full":
                core_db = source_file

        pid = start_pipeline(
            run_dir=project_dir,
            molecule=molecule,
            mode=mode,
            max_products=max_products,
            core_db=core_db,
            basic_export=basic_export,
        )

    st.success(f"Pipeline started (PID {pid})")
    st.info(f"Run directory: `{project_dir}`")
    st.page_link("pages/2_Progress.py", label="Go to Progress", icon="📊")
