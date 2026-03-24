"""New Run — start a download pipeline."""

import re
from pathlib import Path

import streamlit as st
from mri_app.config import WORKSPACE_ROOT
from mri_app.runner import start_pipeline

st.set_page_config(page_title="New Run — MRI", page_icon="🔍", layout="wide")
st.title("New Run")


# ── Folder browser helpers ────────────────────────────────────────────────

def list_subfolders(parent: Path) -> list[Path]:
    """List visible subdirectories of a path."""
    if not parent.is_dir():
        return []
    try:
        return sorted(
            [d for d in parent.iterdir() if d.is_dir() and not d.name.startswith(".")],
            key=lambda d: d.name.lower(),
        )
    except PermissionError:
        return []


def detect_project_type(folder: Path) -> tuple[str, Path | None, str]:
    """Auto-detect source mode from folder contents."""
    xlsx_files = sorted(folder.glob("*.xlsx"))

    if not xlsx_files:
        return "automatic", None, "No .xlsx files found — will search MRI portal"

    for f in xlsx_files:
        if "export" in f.stem.lower():
            return "basic", f, f"Found basic MRI export: **{f.name}**"

    for f in xlsx_files:
        if "_core_database" in f.stem.lower() or "_database" in f.stem.lower():
            return "full", f, f"Found full database: **{f.name}**"

    return "basic", xlsx_files[0], f"Found .xlsx file: **{xlsx_files[0].name}** (assuming basic export)"


def derive_molecule(folder: Path) -> str:
    """Derive molecule label from folder name."""
    name = folder.name.lower()
    name = re.sub(r"_\d{8}_?\d{0,6}$", "", name)
    for suffix in ("_core_database", "_database", "_export", "_manual_mri"):
        name = name.replace(suffix, "")
    name = re.sub(r"[^a-z0-9]", "_", name).strip("_")
    return name or "molecule"


# ── Step 1: Select project folder ─────────────────────────────────────────

st.markdown("### **Select project folder**")
st.caption(f"Browsing host filesystem (mounted at `{WORKSPACE_ROOT}`)")

# Initialize session state for current browse path
if "browse_path" not in st.session_state:
    st.session_state.browse_path = str(WORKSPACE_ROOT)

# Path input — user can type or paste any path
browse_path = st.text_input(
    "Folder path",
    value=st.session_state.browse_path,
    help="Type a path or use the browser below to navigate",
)
current = Path(browse_path)

if not current.exists():
    st.error(f"Path does not exist: `{current}`")
    st.stop()

if not current.is_dir():
    st.error(f"Not a directory: `{current}`")
    st.stop()

# Folder browser — show subfolders as clickable buttons
subfolders = list_subfolders(current)

if subfolders or current != WORKSPACE_ROOT:
    with st.container(border=True):
        # Parent navigation
        if current != Path("/"):
            if st.button(f".. (up to {current.parent.name or '/'})", key="nav_parent"):
                st.session_state.browse_path = str(current.parent)
                st.rerun()

        # Subfolder navigation
        cols_per_row = 4
        for i in range(0, len(subfolders), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(subfolders):
                    folder = subfolders[idx]
                    if col.button(f"📁 {folder.name}", key=f"nav_{folder}", use_container_width=True):
                        st.session_state.browse_path = str(folder)
                        st.rerun()

# Select current folder as project
st.markdown(f"**Selected:** `{current}`")

# Show folder contents summary
xlsx_files = sorted(current.glob("*.xlsx"))
pdf_count = len(list(current.rglob("*.pdf")))
json_files = sorted(current.glob("*.json"))

content_parts = []
if xlsx_files:
    content_parts.append(f"{len(xlsx_files)} .xlsx")
if pdf_count:
    content_parts.append(f"{pdf_count} .pdf")
if json_files:
    content_parts.append(f"{len(json_files)} .json")
if content_parts:
    st.caption(f"Contents: {', '.join(content_parts)}")
else:
    st.caption("Folder is empty")

project_dir = current

st.divider()

# ── Step 2: Auto-detect mode from folder contents ─────────────────────────

detected_mode, detected_file, detection_reason = detect_project_type(project_dir)
auto_molecule = derive_molecule(project_dir)

if xlsx_files:
    with st.expander(f"Excel files in folder ({len(xlsx_files)})", expanded=False):
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
        st.warning("No .xlsx file in project folder. Switch to Automatic mode.")

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
        st.warning("No .xlsx file in project folder. Switch to Automatic mode.")

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
