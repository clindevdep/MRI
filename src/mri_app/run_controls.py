"""Shared widgets: run scope switch, PAR batch limit, and continue/resume controls."""

from pathlib import Path

import streamlit as st

from .runner import start_pipeline

SCOPE_LABELS = {
    "full": "Full run",
    "core": "Core base generation only",
}

DEFAULT_BATCH_SIZE = 10


def scope_switch(
    key: str,
    default: str = "full",
    disabled: bool = False,
    label_visibility: str = "visible",
) -> str:
    """Two-way switch between a full run and core database generation only."""
    choice = st.segmented_control(
        "Run scope",
        options=list(SCOPE_LABELS),
        format_func=SCOPE_LABELS.get,
        default=default,
        required=True,
        disabled=disabled,
        label_visibility=label_visibility,
        key=key,
    )
    return choice or default


def par_limit_input(key: str, default: int = 0) -> int:
    """PAR batch limit: 0 (unlimited) unless the user switches the limit on."""
    limited = st.toggle(
        "Limit PAR downloads per session",
        value=default > 0,
        key=f"{key}:on",
        help="Unlimited by default. When on, the session stops after this many new, "
             "distinct PAR PDFs (identical documents shared by several strengths count "
             "once) and the run can be resumed later for the next batch.",
    )
    if not limited:
        st.caption("PAR downloads: **unlimited** — all products are processed in this session.")
        return 0
    limit = st.number_input(
        "PAR PDFs to download in this session",
        min_value=1,
        value=default if default > 0 else DEFAULT_BATCH_SIZE,
        step=1,
        key=f"{key}:n",
    )
    st.caption(
        f"The session ends after **{int(limit)}** new PAR PDF(s). Resume the run from "
        "the dashboard or History to download the next batch."
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
