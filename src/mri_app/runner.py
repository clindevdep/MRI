"""Launch and manage the orchestrator subprocess."""

import json
import subprocess
import signal
from datetime import datetime
from pathlib import Path

from .config import RUNS_DIR, UPLOADS_DIR, ORCHESTRATOR_PATH


def make_run_dir(molecule: str) -> Path:
    """Create a timestamped run directory."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / f"{molecule}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_upload(uploaded_file) -> Path:
    """Save a Streamlit UploadedFile to the uploads directory."""
    dest = UPLOADS_DIR / uploaded_file.name
    dest.write_bytes(uploaded_file.getvalue())
    return dest


def start_pipeline(
    run_dir: Path,
    molecule: str,
    mode: str,
    max_products: int = 10000,
    core_db: Path | None = None,
    basic_export: Path | None = None,
) -> int:
    """
    Launch the orchestrator as a background subprocess.
    Returns the PID.
    """
    cmd = [
        "python3",
        str(ORCHESTRATOR_PATH),
        "--run-dir", str(run_dir),
        "--molecule", molecule,
        "--mode", mode,
        "--max-products", str(max_products),
    ]

    if core_db:
        cmd += ["--core-db", str(core_db)]
    if basic_export:
        cmd += ["--basic-export", str(basic_export)]

    log_path = run_dir / "pipeline.log"
    log_file = open(log_path, "w")

    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    # Persist PID for status checking
    (run_dir / "pid").write_text(str(proc.pid))

    return proc.pid


def is_running(run_dir: Path) -> bool:
    """Check if the pipeline process is still alive."""
    pid_file = run_dir / "pid"
    if not pid_file.exists():
        return False

    pid = int(pid_file.read_text().strip())
    try:
        # Signal 0 checks existence without killing
        import os
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def stop_pipeline(run_dir: Path):
    """Send SIGTERM to the pipeline process."""
    pid_file = run_dir / "pid"
    if not pid_file.exists():
        return

    pid = int(pid_file.read_text().strip())
    try:
        import os
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def list_runs() -> list[dict]:
    """List all runs with their config and status.

    Scans both /data/runs/ (legacy) and /data/* project folders
    that contain a run_config.json.
    """
    runs = []
    seen = set()

    from .config import DATA_DIR, WORKSPACE_ROOT

    # Scan all candidate directories
    search_dirs = []
    if RUNS_DIR.exists():
        search_dirs.extend(d for d in RUNS_DIR.iterdir() if d.is_dir())
    if DATA_DIR.exists():
        search_dirs.extend(
            d for d in DATA_DIR.iterdir()
            if d.is_dir() and d.name not in ("runs", "uploads")
        )
    # Also scan workspace for project folders with run_config.json
    if WORKSPACE_ROOT.exists():
        for d in WORKSPACE_ROOT.rglob("run_config.json"):
            if d.parent not in search_dirs:
                search_dirs.append(d.parent)

    for run_dir in search_dirs:
        if run_dir in seen:
            continue
        seen.add(run_dir)

        # Only include folders that have been used as run dirs
        config_path = run_dir / "run_config.json"
        status_path = run_dir / "status.json"
        if not config_path.exists() and not status_path.exists():
            continue

        run = {"path": run_dir, "name": run_dir.name}

        if config_path.exists():
            run["config"] = json.loads(config_path.read_text())

        if status_path.exists():
            run["status"] = json.loads(status_path.read_text())

        run["running"] = is_running(run_dir)
        runs.append(run)

    runs.sort(key=lambda r: r.get("config", {}).get("started_at", ""), reverse=True)
    return runs
