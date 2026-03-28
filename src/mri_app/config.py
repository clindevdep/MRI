"""App-wide configuration and path constants."""

import os
from pathlib import Path

# Base data directory (Docker volume mount)
DATA_DIR = Path(os.getenv("MRI_DATA_DIR", "/data"))
RUNS_DIR = DATA_DIR / "runs"
UPLOADS_DIR = DATA_DIR / "uploads"
ARCHIVES_DIR = DATA_DIR / "archives"

# Orchestrator
ORCHESTRATOR_PATH = Path("/app/src/mri_app/orchestrator.py")

# Ensure directories exist when the configured data directory is writable.
for path in (RUNS_DIR, UPLOADS_DIR, ARCHIVES_DIR):
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
