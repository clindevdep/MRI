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
    scope: str = "full",
    par_limit: int = 0,
) -> int:
    """
    Launch the orchestrator as a background subprocess.
    Returns the PID.

    scope:     "full" (core DB → PARs → BE extraction) or "core" (core
               database generation only).
    par_limit: stop the PAR stage after this many new distinct PAR PDFs in
               this session; 0 = unlimited. Resume the run for the next batch.
    """
    cmd = [
        "python3",
        str(ORCHESTRATOR_PATH),
        "--run-dir", str(run_dir),
        "--molecule", molecule,
        "--mode", mode,
        "--max-products", str(max_products),
        "--scope", scope,
        "--par-limit", str(max(0, int(par_limit or 0))),
    ]

    if core_db:
        cmd += ["--core-db", str(core_db)]
    if basic_export:
        cmd += ["--basic-export", str(basic_export)]

    # Make the run discoverable before the orchestrator has started up.
    # list_runs() ignores a directory until it holds a run_config.json, and the
    # orchestrator only writes one once it is running — so without this the
    # just-launched run is still invisible on the dashboard the New Run page
    # redirects to, and the dashboard silently falls back to another run. The
    # orchestrator rewrites this file with the authoritative values moments later.
    # A resumed run already has its config, which the orchestrator extends —
    # overwriting it here would lose the run's original source mode and inputs.
    config_path = run_dir / "run_config.json"
    if mode != "resume" or not config_path.exists():
        config = {
            "molecule": molecule,
            "max_products": max_products,
            "mode": mode,
            "core_db": str(core_db) if core_db else None,
            "basic_export": str(basic_export) if basic_export else None,
            "scope": scope,
            "par_limit": par_limit,
            "started_at": datetime.now().isoformat(),
        }
        config_path.write_text(json.dumps(config, indent=2))

    # Clear a terminal status left by the previous session of a resumed run,
    # otherwise is_running() reports the run as finished until the
    # orchestrator writes its first status. The step being replaced is kept as
    # "resumed_from": the orchestrator needs it (core_complete → go to PARs).
    status_path = run_dir / "status.json"
    resumed_from = None
    if mode == "resume" and status_path.exists():
        try:
            previous = json.loads(status_path.read_text())
            resumed_from = previous.get("resumed_from") if previous.get("step") == "starting" \
                else previous.get("step")
        except (json.JSONDecodeError, OSError):
            pass
    status_path.write_text(json.dumps({
        "step": "starting",
        "step_number": 0,
        "total_steps": 3,
        "detail": None,
        "updated_at": datetime.now().isoformat(),
        "error": None,
        "resumed_from": resumed_from,
    }, indent=2))

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


# Statuses the orchestrator writes as its final action for a run. Once one of
# these is present, the run is finished regardless of PID/zombie state — this
# is authoritative and prevents the UI "running" spinner from sticking forever.
#
# core_complete:  a "Core base generation only" run finished; resumable to fetch PARs.
# batch_complete: a session reached its PAR limit; resumable for the next batch.
TERMINAL_STATES = {"complete", "failed", "blocked", "core_complete", "batch_complete"}

# Terminal states whose outputs are worth showing on the Results tab.
RESULT_STATES = {"complete", "core_complete", "batch_complete"}


def is_running(run_dir: Path) -> bool:
    """Check if the pipeline process is still alive and belongs to the orchestrator."""
    # Authoritative short-circuit: a terminal status.json means the run ended.
    status_file = run_dir / "status.json"
    if status_file.exists():
        try:
            step = json.loads(status_file.read_text()).get("step")
            if step in TERMINAL_STATES:
                return False
        except (json.JSONDecodeError, OSError):
            pass

    pid_file = run_dir / "pid"
    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, TypeError):
        return False

    try:
        # Signal 0 checks existence without killing
        import os
        os.kill(pid, 0)

        # Check if the process is a zombie
        proc_status_path = Path(f"/proc/{pid}/status")
        if proc_status_path.exists():
            try:
                for line in proc_status_path.read_text().splitlines():
                    if line.startswith("State:"):
                        state = line.split(":", 1)[1].strip()
                        if "zombie" in state.lower() or state.startswith("Z"):
                            return False
            except OSError:
                pass

        # Check if the PID belongs to orchestrator.py (recycled PID check)
        proc_cmdline_path = Path(f"/proc/{pid}/cmdline")
        if proc_cmdline_path.exists():
            try:
                cmdline = proc_cmdline_path.read_text()
                if "orchestrator.py" not in cmdline:
                    return False
            except OSError:
                pass

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

    from .config import DATA_DIR

    # Scan all candidate directories
    search_dirs = []
    if RUNS_DIR.exists():
        search_dirs.extend(d for d in RUNS_DIR.iterdir() if d.is_dir())
    if DATA_DIR.exists():
        search_dirs.extend(
            d for d in DATA_DIR.iterdir()
            if d.is_dir() and d.name not in ("runs", "uploads")
        )

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
