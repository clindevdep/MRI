"""Helpers for packaging run artifacts for download."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import ARCHIVES_DIR


def _safe_archive_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "archive"


def _latest_mtime(target: Path) -> float:
    latest = target.stat().st_mtime
    if not target.is_dir():
        return latest

    for child in target.rglob("*"):
        try:
            latest = max(latest, child.stat().st_mtime)
        except OSError:
            continue
    return latest


def ensure_directory_zip(target: Path, archive_name: str) -> Path:
    """Create or refresh a cached zip archive for a directory."""
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(f"Directory not found: {target}")

    safe_name = _safe_archive_name(archive_name)
    zip_path = ARCHIVES_DIR / f"{safe_name}.zip"

    if zip_path.exists() and zip_path.stat().st_mtime >= _latest_mtime(target):
        return zip_path

    base_path = ARCHIVES_DIR / f".{safe_name}"
    tmp_zip = base_path.with_suffix(".zip")

    if tmp_zip.exists():
        tmp_zip.unlink()

    shutil.make_archive(str(base_path), "zip", root_dir=target.parent, base_dir=target.name)
    tmp_zip.replace(zip_path)
    return zip_path
