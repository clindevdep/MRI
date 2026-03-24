"""Poll status.json and tracker files for progress display."""

import json
from pathlib import Path


def read_status(run_dir: Path) -> dict | None:
    """Read the pipeline status.json."""
    path = run_dir / "status.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def read_tracker(tracker_path: Path) -> dict | None:
    """Read a download tracker JSON file."""
    if not tracker_path.exists():
        return None
    try:
        return json.loads(tracker_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def tracker_stats(tracker_path: Path) -> dict:
    """Get summary stats from a tracker file."""
    data = read_tracker(tracker_path)
    if not data:
        return {"total": 0, "completed": 0, "pending": 0, "failed": 0, "pars": 0}

    products = data.get("products", {})
    stats = {"total": len(products), "completed": 0, "pending": 0, "failed": 0, "pars": 0}

    for entry in products.values():
        status = entry.get("status", "unknown")
        if status == "completed":
            stats["completed"] += 1
        elif status in ("pending", "in_progress"):
            stats["pending"] += 1
        elif status == "failed":
            stats["failed"] += 1

        try:
            stats["pars"] += int(entry.get("par_count") or 0)
        except (TypeError, ValueError):
            pass

    return stats


def find_trackers(run_dir: Path, molecule: str) -> dict:
    """Find core and PAR tracker paths for a run."""
    return {
        "core": run_dir / "core_download_tracker.json",
        "par": run_dir / molecule / "download_tracker.json",
    }


def read_log_tail(run_dir: Path, lines: int = 50) -> str:
    """Read the last N lines of the pipeline log."""
    log_path = run_dir / "pipeline.log"
    if not log_path.exists():
        return ""
    try:
        text = log_path.read_text()
        all_lines = text.splitlines()
        return "\n".join(all_lines[-lines:])
    except OSError:
        return ""
