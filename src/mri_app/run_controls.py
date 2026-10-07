"""Shared widgets: run scope switch, PAR batch limit, and continue/resume controls."""

from pathlib import Path

import streamlit as st

from .runner import start_pipeline

SCOPE_LABELS = {
    "full": "Full run",
    "core": "Core base generation only",
}

def scope_switch(key: str, default: str = "full", disabled: bool = False) -> str:
    """On/off switch: off = full run (default), on = core database generation only."""
    core_only = st.toggle(
        SCOPE_LABELS["core"],
        value=default == "core",
        disabled=disabled,
        key=key,
        help="Off: full run (Core Database → PAR downloads → bioequivalence extraction). "
             "On: stop once the Core Database is built.",
    )
    return "core" if core_only else "full"


def par_limit_input(key: str, default: int = 0) -> int:
    """PAR batch limit for this session; 0 = unlimited."""
    limit = st.number_input(
        "PAR PDF limit for this session (0 = unlimited)",
        min_value=0,
        value=max(0, int(default or 0)),
        step=1,
        key=key,
        help="The session stops after this many new, distinct PAR PDFs (identical "
             "documents shared by several strengths count once). Resume the run later "
             "to download the next batch. 0 downloads everything.",
    )
    return int(limit)


def continue_controls(run_dir: Path, config: dict, step: str, key: str) -> bool:
    """Resume / continue controls for a finished-but-resumable run.

    Returns True when a new session was launched.
    """
    molecule = config.get("molecule", "")
    last_limit = int(config.get("par_limit") or 0)

    if step == "core_complete":
        st.markdown("**Core database is ready.** Continue the run to download its PARs.")
        scope = "full"
        button = "Download PARs"
    elif step == "batch_complete":
        st.markdown("**Batch finished.** Continue the run to download the next batch of PARs.")
        scope = "full"
        button = "Download next batch"
    else:
        scope = scope_switch(f"{key}:scope", default=config.get("scope", "full"))
        button = "Resume"

    par_limit = par_limit_input(f"{key}:limit", default=last_limit) if scope == "full" else 0

    if st.button(button, type="primary", key=f"{key}:go", disabled=not molecule):
        start_pipeline(
            run_dir=run_dir,
            molecule=molecule,
            mode="resume",
            scope=scope,
            par_limit=par_limit,
        )
        return True
    return False
