"""App-wide configuration and path constants."""

from pathlib import Path

# Base data directory (Docker volume mount)
DATA_DIR = Path("/data")
RUNS_DIR = DATA_DIR / "runs"
UPLOADS_DIR = DATA_DIR / "uploads"

# Orchestrator
ORCHESTRATOR_PATH = Path("/app/src/mri_app/orchestrator.py")

# Ensure directories exist
RUNS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
