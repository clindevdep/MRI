"""Helpers for packaging run artifacts for download."""

from __future__ import annotations

import re
import shutil
import zipfile
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


def ensure_directory_zip(target: Path, archive_name: str, molecule: str = "") -> Path:
    """Create or refresh a cached zip archive for a run directory.

    When *molecule* is provided the zip is restructured:
      - No wrapper folder (files directly at zip root)
      - {molecule}_per_procedure/ (renamed from {molecule}/)
      - {molecule}_PAR_collection/
      - {molecule}_bioequivalence.csv
      - {molecule}_core_database.xlsx
      - Run/  (everything else)
    """
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(f"Directory not found: {target}")

    safe_name = _safe_archive_name(archive_name)
    zip_path = ARCHIVES_DIR / f"{safe_name}.zip"

    if zip_path.exists() and zip_path.stat().st_mtime >= _latest_mtime(target):
        return zip_path

    tmp_zip = ARCHIVES_DIR / f".{safe_name}.zip"
    if tmp_zip.exists():
        tmp_zip.unlink()

    if molecule:
        _build_structured_zip(target, tmp_zip, molecule)
    else:
        shutil.make_archive(str(tmp_zip.with_suffix("")), "zip",
                            root_dir=target.parent, base_dir=target.name)

    tmp_zip.replace(zip_path)
    return zip_path


def _build_structured_zip(run_dir: Path, zip_path: Path, molecule: str):
    """Build a zip with clean structure: primary outputs at root, rest in Run/."""
    # Top-level names that stay at the zip root
    primary_tops = {
        f"{molecule}_PAR_collection",
        f"{molecule}_bioequivalence.csv",
        f"{molecule}_core_database.xlsx",
    }
    # Directory to rename
    rename_source = molecule
    per_proc = f"{molecule}_per_procedure"

    # Also accept already-renamed dir (idempotent)
    if (run_dir / per_proc).is_dir() and not (run_dir / rename_source).is_dir():
        rename_source = per_proc

    # Skip these files entirely
    skip_tops = {f"{molecule}_database.xlsx"}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(run_dir.rglob("*")):
            if not item.is_file():
                continue

            rel = item.relative_to(run_dir)
            top = rel.parts[0]

            if top in skip_tops:
                continue

            # Rename {molecule}/ → {molecule}_per_procedure/
            if top == rename_source:
                if rel.name == "download_tracker.json":
                    zf.write(item, f"Run/{rel}")
                else:
                    arc_path = str(Path(per_proc) / Path(*rel.parts[1:]))
                    zf.write(item, arc_path)
                continue

            # Primary outputs stay at root
            if top in primary_tops:
                zf.write(item, str(rel))
                continue

            # Everything else → Run/
            zf.write(item, f"Run/{rel}")
