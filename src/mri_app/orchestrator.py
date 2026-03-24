#!/usr/bin/env python3
"""
MRI Pipeline Orchestrator v20 — replaces RUN.sh for Docker container execution.

Three-step pipeline:
  1. Core DB acquisition (search portal, build from basic export, or use full DB)
  2. PAR document download (Playwright stealth browsers with Solo ID)
  3. Bioequivalence data extraction (PDF parsing)

Modes (inspired by RUN_v20.sh):
  automatic  — search MRI portal by molecule name, download extended info
  basic      — convert user-uploaded basic MRI export, download extended info
  full       — use pre-compiled full database directly

Features:
  - Auto-retry with stagnation detection for core + PAR stages
  - Tracker-based resume (core_download_tracker.json, download_tracker.json)
  - PAR collection folder for batch document analysis
  - Run report generation
  - status.json for Streamlit progress polling

Called as a background subprocess by the Streamlit app (runner.py).

Usage:
  python orchestrator.py --run-dir /data/runs/ketoprofen_20260324 \\
      --molecule ketoprofen --max-products 10000 \\
      --mode basic --basic-export /data/uploads/UDCA_03-03-2026.xlsx

  python orchestrator.py --run-dir /data/runs/ketoprofen_20260324 \\
      --molecule ketoprofen --mode full \\
      --core-db /data/uploads/ketoprofen_core_database.xlsx

  python orchestrator.py --run-dir /data/runs/ketoprofen_20260324 \\
      --molecule ketoprofen --mode automatic

  python orchestrator.py --run-dir /data/runs/ketoprofen_20260324 \\
      --molecule ketoprofen --mode resume
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path("/app/scripts")

# Retry configuration (matches RUN_v20.sh)
MAX_RETRY_ROUNDS = 10
MAX_STAGNANT_ROUNDS = 2
ALLOW_PARTIAL_CORE = True


# ── Status helpers ────────────────────────────────────────────────────────

def write_status(
    run_dir: Path,
    step: str,
    step_number: int,
    total_steps: int = 3,
    detail: str | None = None,
    error: str | None = None,
):
    """Write pipeline status for Streamlit to poll."""
    status = {
        "step": step,
        "step_number": step_number,
        "total_steps": total_steps,
        "detail": detail,
        "updated_at": datetime.now().isoformat(),
        "error": error,
    }
    (run_dir / "status.json").write_text(json.dumps(status, indent=2))


# ── Subprocess runner ─────────────────────────────────────────────────────

def run_step(cmd: list[str], cwd: Path, step_name: str) -> int:
    """Run a subprocess step, streaming output to stdout."""
    print(f"\n{'='*60}", flush=True)
    print(f"  Step: {step_name}", flush=True)
    print(f"  Command: {' '.join(str(c) for c in cmd)}", flush=True)
    print(f"  Working dir: {cwd}", flush=True)
    print(f"{'='*60}\n", flush=True)

    result = subprocess.run(cmd, cwd=str(cwd))
    return result.returncode


# ── Tracker helpers ───────────────────────────────────────────────────────

def get_tracker_failed_count(tracker_path: Path) -> int:
    """Count failed entries in a tracker JSON file."""
    if not tracker_path.exists():
        return 0
    data = json.loads(tracker_path.read_text())
    return sum(
        1 for entry in data.get("products", {}).values()
        if entry.get("status") == "failed"
    )


def reset_failed_for_retry(tracker_path: Path, search_json: Path | None = None):
    """Reset failed/in_progress entries to pending. Shuffle search_results for randomized retry."""
    import random

    if not tracker_path.exists():
        print(f"  No tracker yet at {tracker_path} (first run will create it)", flush=True)
        return

    data = json.loads(tracker_path.read_text())
    reset_count = 0
    for entry in data.get("products", {}).values():
        if entry.get("status") in ("failed", "in_progress"):
            entry["status"] = "pending"
            entry["last_error"] = None
            reset_count += 1

    if reset_count > 0:
        tracker_path.write_text(json.dumps(data, indent=2))
        print(f"  Reset {reset_count} failed/in-progress items to pending", flush=True)

    # Shuffle search_results.json for random retry order
    if search_json and search_json.exists():
        results = json.loads(search_json.read_text())
        random.shuffle(results)
        search_json.write_text(json.dumps(results, indent=2))
        print(f"  Shuffled {len(results)} items for random retry order", flush=True)


def archive_tracker(tracker_path: Path, label: str):
    """Archive existing tracker with timestamp for new-mode fresh start."""
    if tracker_path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = tracker_path.with_suffix(f".json.bak_{ts}")
        tracker_path.rename(backup)
        print(f"  Archived {label} tracker: {backup}", flush=True)


# ── convert_basic_to_json ─────────────────────────────────────────────────

def convert_basic_to_json(input_xlsx: Path, output_json: Path):
    """Convert basic MRI portal Excel export to search_results.json format."""
    df = pd.read_excel(input_xlsx)

    # Auto-detect header row (MRI exports sometimes have empty first rows)
    unnamed_count = sum(1 for col in df.columns if "unnamed" in str(col).lower())
    if unnamed_count > len(df.columns) * 0.5:
        df = pd.read_excel(input_xlsx, header=1)
        print(f"  Note: Using row 1 as header (detected unnamed columns in row 0)", flush=True)

    # Normalize column names
    df.columns = [re.sub(r"\s+", "_", col.strip().lower()) for col in df.columns]

    # Flexible column detection
    def find_col(candidates):
        for c in candidates:
            if c in df.columns:
                return c
            for col in df.columns:
                if c in col:
                    return col
        return None

    proc_col = find_col(["productnumber", "product_number", "procedure_code", "procedurecode", "procedure"])
    product_col = find_col(["productname", "product_name", "product", "name", "medicinal_product"])
    family_col = find_col(["family_code", "familycode", "family"])

    if not proc_col:
        raise ValueError(f"Could not find procedure code column. Available: {list(df.columns)}")

    results = []
    for _, row in df.iterrows():
        proc_code = str(row.get(proc_col, "")).strip()
        if not proc_code or proc_code == "nan":
            continue

        entry = {"procedure_code": proc_code}

        if family_col:
            fam = str(row.get(family_col, "")).strip()
            if fam and fam != "nan":
                entry["family_code"] = fam

        if product_col:
            prod = str(row.get(product_col, "")).strip()
            if prod and prod != "nan":
                entry["product_name"] = prod

        # Preserve extra columns
        for col in df.columns:
            if col not in [proc_col, family_col, product_col]:
                val = row.get(col)
                if pd.notna(val):
                    entry[col] = str(val).strip()

        results.append(entry)

    if not results:
        raise ValueError("No valid products found in Excel file")

    output_json.write_text(json.dumps(results, indent=2))
    print(f"  Converted {len(results)} products to JSON format", flush=True)
    return len(results)


# ── Core download with retry ─────────────────────────────────────────────

def run_core_downloader(run_dir: Path, core_db_path: Path, search_json: Path):
    """Run core downloader with automatic retry and stagnation detection."""
    core_tracker = run_dir / "core_download_tracker.json"
    previous_failed = -1
    stagnant_rounds = 0

    # Normalize stale states before first attempt
    reset_failed_for_retry(core_tracker, search_json)

    for round_num in range(1, MAX_RETRY_ROUNDS + 1):
        if round_num == 1:
            print(f"\n→ Core download round {round_num}/{MAX_RETRY_ROUNDS}", flush=True)
        else:
            print(f"\n→ Core retry round {round_num}/{MAX_RETRY_ROUNDS}", flush=True)
            reset_failed_for_retry(core_tracker, search_json)

        exit_code = run_step(
            [
                "node",
                str(SCRIPTS_DIR / "download_and_merge_products_v20.js"),
                str(search_json),
                str(core_db_path),
                "10000",
            ],
            cwd=run_dir,
            step_name=f"Core Database Download (round {round_num})",
        )

        if exit_code == 3:
            print("\n[WARN] Portal blocking detected (exit code 3). VPN rotation needed.", flush=True)
            return 3

        failed_count = get_tracker_failed_count(core_tracker)

        if failed_count == 0:
            print("✓ Full database ready (all downloads successful)", flush=True)
            return 0

        # Stagnation detection
        if previous_failed >= 0:
            if failed_count >= previous_failed:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
        previous_failed = failed_count

        print(f"  {failed_count} downloads failed.", flush=True)

        if ALLOW_PARTIAL_CORE and stagnant_rounds >= MAX_STAGNANT_ROUNDS:
            print(f"  Failed count stagnant for {stagnant_rounds} rounds.", flush=True)
            print("  Proceeding with partial database.", flush=True)
            return 0

    # Exhausted retries
    if ALLOW_PARTIAL_CORE:
        print(f"  Reached {MAX_RETRY_ROUNDS} retries with {failed_count} failures remaining.", flush=True)
        print("  Proceeding with partial database.", flush=True)
        return 0

    return 1


# ── PAR download with retry ──────────────────────────────────────────────

def run_par_downloads(run_dir: Path, molecule: str, core_db_path: Path):
    """Run PAR downloads with automatic retry."""
    par_tracker = run_dir / molecule / "download_tracker.json"

    for round_num in range(1, MAX_RETRY_ROUNDS + 1):
        if round_num == 1:
            print(f"\n→ PAR download round {round_num}/{MAX_RETRY_ROUNDS}", flush=True)
        else:
            print(f"\n→ PAR retry round {round_num}/{MAX_RETRY_ROUNDS}", flush=True)
            # Reset failed PAR downloads
            if par_tracker.exists():
                reset_failed_for_retry(par_tracker)

        exit_code = run_step(
            [
                "node",
                str(SCRIPTS_DIR / "process_molecule_v10.js"),
                "--core", str(core_db_path),
                "--molecule", molecule,
                "--max", "10000",
            ],
            cwd=run_dir,
            step_name=f"PAR Document Downloads (round {round_num})",
        )

        if exit_code == 3:
            print("\n[WARN] Portal blocking detected (exit code 3). VPN rotation needed.", flush=True)
            return 3

        failed_count = get_tracker_failed_count(par_tracker)

        if failed_count == 0:
            print("✓ PAR downloads completed (all successful)", flush=True)
            return 0

        print(f"  {failed_count} PAR downloads failed, will retry...", flush=True)

    print(f"  Reached {MAX_RETRY_ROUNDS} retries. Continuing with completed downloads.", flush=True)
    return 0


# ── PAR collection ────────────────────────────────────────────────────────

def create_par_collection(run_dir: Path, molecule: str):
    """Copy all PARs into a flat folder for batch import (NotebookLM etc.)."""
    source = run_dir / molecule
    collection = run_dir / f"{molecule}_PAR_collection"

    if not source.exists():
        return 0

    collection.mkdir(exist_ok=True)
    count = 0
    for pdf in source.rglob("*.pdf"):
        proc_dir = pdf.parent.name
        new_name = f"{proc_dir}_{pdf.name}"
        shutil.copy2(pdf, collection / new_name)
        count += 1

    if count > 0:
        print(f"  ✓ Copied {count} PARs to {collection}", flush=True)
    else:
        collection.rmdir()

    return count


# ── Run report ────────────────────────────────────────────────────────────

def generate_run_report(run_dir: Path, molecule: str, mode: str, max_products: int):
    """Generate run summary report."""
    report_path = run_dir / f"{molecule}_run_report.txt"
    report_path.write_text(f"""
╔═══════════════════════════════════════════════════════════════════╗
║            MRI Portal v20 (Docker) - Run Report                   ║
╚═══════════════════════════════════════════════════════════════════╝

RUN INFORMATION
───────────────────────────────────────────────────────────────────
  Molecule:          {molecule}
  Source Mode:       {mode}
  Max Products:      {max_products}
  Execution Time:    {datetime.now().isoformat()}
  Run Directory:     {run_dir}
  Version:           v20 Docker Edition

OUTPUT FILES
───────────────────────────────────────────────────────────────────
  • PAR documents:      {run_dir}/{molecule}/
  • PAR collection:     {run_dir}/{molecule}_PAR_collection/
  • Database:           {run_dir}/{molecule}_database.xlsx
  • Bioequivalence CSV: {run_dir}/{molecule}_bioequivalence.csv
  • This report:        {report_path}

v20 FEATURES
───────────────────────────────────────────────────────────────────
  ✓ Auto-retry failed downloads (up to {MAX_RETRY_ROUNDS} rounds, random order)
  ✓ Stagnation detection (proceed after {MAX_STAGNANT_ROUNDS} stagnant rounds)
  ✓ Core download diagnostics + fallback retrieval
  ✓ Three source modes: automatic / basic / full
  ✓ NotebookLM batch collection (flat PAR folder)
  ✓ Resume via JSON trackers
  ✓ Unique browser identity per product download
  ✓ Docker container with VPN routing

Generated with MRI PAR Downloader v20 (Docker)
""")
    print(f"  ✓ {molecule}_run_report.txt", flush=True)


# ── Main pipeline ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MRI Pipeline Orchestrator v20")
    parser.add_argument("--run-dir", required=True, help="Directory for this run's output")
    parser.add_argument("--molecule", required=True, help="Active substance name")
    parser.add_argument("--max-products", type=int, default=10000, help="Max products to process")
    parser.add_argument(
        "--mode",
        choices=["automatic", "basic", "full", "resume"],
        required=True,
    )
    parser.add_argument("--core-db", default=None, help="Path to full core database Excel (mode=full)")
    parser.add_argument("--basic-export", default=None, help="Path to basic MRI export Excel (mode=basic)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    molecule = args.molecule

    core_db_path = run_dir / f"{molecule}_core_database.xlsx"
    search_json = run_dir / "search_results.json"
    core_tracker = run_dir / "core_download_tracker.json"
    par_tracker = run_dir / molecule / "download_tracker.json"

    # Save run config
    config = {
        "molecule": molecule,
        "max_products": args.max_products,
        "mode": args.mode,
        "core_db": args.core_db,
        "basic_export": args.basic_export,
        "started_at": datetime.now().isoformat(),
    }
    (run_dir / "run_config.json").write_text(json.dumps(config, indent=2))

    # Determine if resuming
    is_resume = args.mode == "resume"
    mode = args.mode

    if is_resume:
        # Auto-detect what to resume
        if par_tracker.exists():
            print("[OK] Resuming PAR downloads", flush=True)
            mode = "_resume_par"
        elif core_tracker.exists():
            print("[OK] Resuming core downloads", flush=True)
            mode = "_resume_core"
        else:
            print("[ERROR] No trackers found to resume from", flush=True)
            sys.exit(1)

        # Auto-detect core DB path
        if not core_db_path.exists():
            alt = run_dir / f"{molecule}_database.xlsx"
            if alt.exists():
                core_db_path = alt
            elif args.core_db and Path(args.core_db).exists():
                core_db_path = Path(args.core_db)

    try:
        # ── Step 1: Core Database ──────────────────────────────────
        write_status(run_dir, "core_database", 1)

        if mode == "full":
            # User provided full database — copy it
            src = Path(args.core_db)
            if not src.exists():
                raise FileNotFoundError(f"Full database not found: {src}")
            shutil.copy2(src, core_db_path)
            print(f"[OK] Full database copied: {src.name}", flush=True)

        elif mode == "basic":
            # Convert basic export to search_results.json, then download extended info
            src = Path(args.basic_export)
            if not src.exists():
                raise FileNotFoundError(f"Basic export not found: {src}")

            # Archive old trackers for fresh start
            archive_tracker(core_tracker, "core download")
            archive_tracker(par_tracker, "PAR download")

            print("[Step 1] Converting basic export → search_results.json", flush=True)
            write_status(run_dir, "converting_export", 1, detail="Converting basic MRI export")
            convert_basic_to_json(src, search_json)

            print("[Step 1] Downloading extended info for each registration...", flush=True)
            write_status(run_dir, "core_database", 1, detail="Downloading extended product info")
            exit_code = run_core_downloader(run_dir, core_db_path, search_json)
            if exit_code == 3:
                write_status(run_dir, "blocked", 1, error="Portal blocking detected. VPN rotation needed.")
                sys.exit(3)

        elif mode == "automatic":
            # Search portal + download extended info
            archive_tracker(core_tracker, "core download")
            archive_tracker(par_tracker, "PAR download")

            print("[Step 1a] Searching MRI portal...", flush=True)
            write_status(run_dir, "portal_search", 1, detail="Searching MRI portal")
            exit_code = run_step(
                [
                    "node",
                    str(SCRIPTS_DIR / "src" / "search_molecule_stealth_v14.js"),
                    molecule,
                    str(args.max_products),
                ],
                cwd=run_dir,
                step_name="Portal Search",
            )
            if exit_code != 0:
                raise RuntimeError(f"Portal search failed with exit code {exit_code}")

            print("[Step 1b] Downloading extended info...", flush=True)
            write_status(run_dir, "core_database", 1, detail="Downloading extended product info")
            exit_code = run_core_downloader(run_dir, core_db_path, search_json)
            if exit_code == 3:
                write_status(run_dir, "blocked", 1, error="Portal blocking detected. VPN rotation needed.")
                sys.exit(3)

        elif mode == "_resume_core":
            # Resume core downloads
            write_status(run_dir, "core_database", 1, detail="Resuming extended info downloads")
            if not search_json.exists():
                raise FileNotFoundError(f"search_results.json not found in {run_dir}")
            exit_code = run_core_downloader(run_dir, core_db_path, search_json)
            if exit_code == 3:
                write_status(run_dir, "blocked", 1, error="Portal blocking detected. VPN rotation needed.")
                sys.exit(3)

        elif mode == "_resume_par":
            # Core DB should already exist — skip step 1
            if not core_db_path.exists():
                alt = run_dir / f"{molecule}_database.xlsx"
                if alt.exists():
                    core_db_path = alt
                else:
                    raise FileNotFoundError(f"No core database found for resume in {run_dir}")
            print(f"[OK] Resuming with existing core database: {core_db_path.name}", flush=True)

        # ── Step 2: PAR Downloads ──────────────────────────────────
        write_status(run_dir, "par_download", 2)

        molecule_dir = run_dir / molecule
        exit_code = run_par_downloads(run_dir, molecule, core_db_path)

        if exit_code == 3:
            write_status(run_dir, "blocked", 2, error="Portal blocking detected. VPN rotation needed.")
            sys.exit(3)

        # ── Step 3: Bioequivalence Extraction ──────────────────────
        write_status(run_dir, "extraction", 3)

        if molecule_dir.exists() and any(molecule_dir.rglob("*.pdf")):
            exit_code = run_step(
                [
                    "python3",
                    str(SCRIPTS_DIR / "src" / "extract_bioequivalence.py"),
                    str(molecule_dir),
                ],
                cwd=run_dir,
                step_name="Bioequivalence Extraction",
            )
            if exit_code != 0:
                print(f"[WARN] BE extraction completed with warnings (exit {exit_code})", flush=True)
        else:
            print(f"[SKIP] No PDFs found in {molecule_dir}, skipping BE extraction", flush=True)

        # ── Finalization ───────────────────────────────────────────
        write_status(run_dir, "finalizing", 3, detail="Creating collection and report")

        # Copy database
        if core_db_path.exists():
            db_copy = run_dir / f"{molecule}_database.xlsx"
            if db_copy != core_db_path:
                shutil.copy2(core_db_path, db_copy)

        # PAR collection
        create_par_collection(run_dir, molecule)

        # Run report
        generate_run_report(run_dir, molecule, args.mode, args.max_products)

        # ── Done ───────────────────────────────────────────────────
        write_status(run_dir, "complete", 3)
        print(f"\n{'='*60}", flush=True)
        print(f"  Pipeline complete for {molecule}", flush=True)
        print(f"  Results in: {run_dir}", flush=True)
        print(f"{'='*60}\n", flush=True)

    except Exception as e:
        write_status(run_dir, "failed", 0, error=str(e))
        print(f"\n[ERROR] Pipeline failed: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
