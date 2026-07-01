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
    """Get summary stats from a tracker file.

    Keeps the legacy keys (total/completed/pending/failed/pars) for backward
    compatibility and adds richer, source-aware fields:
      - with_pars: completed entries that yielded >=1 PAR
      - empty:     completed entries that yielded 0 PARs (processed, nothing found)
      - processed: completed + failed (i.e. attempts that reached a terminal state)
      - sources:   {source_label: count} across completed entries (e.g. mri_portal, swe_agency)
    """
    empty_stats = {
        "total": 0, "completed": 0, "pending": 0, "failed": 0, "pars": 0,
        "with_pars": 0, "empty": 0, "processed": 0, "sources": {},
    }
    data = read_tracker(tracker_path)
    if not data:
        return empty_stats

    products = data.get("products", {})
    stats = dict(empty_stats)
    stats["total"] = len(products)
    sources: dict[str, int] = {}

    for entry in products.values():
        status = entry.get("status", "unknown")
        try:
            par_count = int(entry.get("par_count") or 0)
        except (TypeError, ValueError):
            par_count = 0

        if status == "completed":
            stats["completed"] += 1
            if par_count > 0:
                stats["with_pars"] += 1
            else:
                stats["empty"] += 1
            src = entry.get("source") or "mri_portal"
            sources[src] = sources.get(src, 0) + 1
        elif status in ("pending", "in_progress"):
            stats["pending"] += 1
        elif status == "failed":
            stats["failed"] += 1

        stats["pars"] += par_count

    stats["processed"] = stats["completed"] + stats["failed"]
    stats["sources"] = sources
    return stats


def find_trackers(run_dir: Path, molecule: str) -> dict:
    """Find core and PAR tracker paths for a run."""
    par_path = run_dir / molecule / "download_tracker.json"
    if not par_path.exists():
        # Fallback to renamed folder (post-finalization)
        alt_path = run_dir / f"{molecule}_per_procedure" / "download_tracker.json"
        if alt_path.exists():
            par_path = alt_path
    return {
        "core": run_dir / "core_download_tracker.json",
        "par": par_path,
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
