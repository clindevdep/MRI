#!/usr/bin/env python3
"""
MRI Pipeline Orchestrator v26 — replaces RUN.sh for Docker container execution.

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

Run scope (v26):
  --scope full   (default) core database → PARs → BE extraction
  --scope core   core database only; ends with status "core_complete". Resume
                 the run later with --scope full to download its PARs.

PAR batches (v26):
  --par-limit N  stop the PAR stage once N new distinct PAR PDFs were saved in
                 this session (0 = unlimited). Ends with status
                 "batch_complete" while products remain; resume the run (with
                 the same or another limit) to download the next batch.
"""

import argparse
import hashlib
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

# process_molecule_v10.js exit code: session PAR limit reached, products remain.
EXIT_PAR_LIMIT = 4


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


def get_tracker_incomplete_count(tracker_path: Path) -> int:
    """Count non-completed entries (pending, in_progress, failed) in a tracker."""
    if not tracker_path.exists():
        return -1  # tracker doesn't exist yet
    data = json.loads(tracker_path.read_text())
    return sum(
        1 for entry in data.get("products", {}).values()
        if entry.get("status") != "completed"
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
                str(SCRIPTS_DIR / "download_and_merge_products_v22.js"),
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

        # Check if script crashed before completing any work
        incomplete = get_tracker_incomplete_count(core_tracker)
        if exit_code != 0 and incomplete > 0:
            print(f"\n[ERROR] Core downloader crashed (exit code {exit_code}) with {incomplete} products incomplete.", flush=True)
            # Don't report success — continue to retry
            failed_count = incomplete
        else:
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

def unique_pdf_hashes(directory: Path) -> set[str]:
    """SHA-256 of every PDF under *directory* — the same notion of a distinct
    PAR document that process_molecule_v10.js counts against --par-limit."""
    hashes = set()
    if not directory.is_dir():
        return hashes
    for pdf in directory.rglob("*.pdf"):
        try:
            hashes.add(hashlib.sha256(pdf.read_bytes()).hexdigest())
        except OSError:
            continue
    return hashes


def run_par_downloads(run_dir: Path, molecule: str, core_db_path: Path, par_limit: int = 0):
    """Run PAR downloads with automatic retry.

    With *par_limit* > 0 the limit applies to the whole session, across retry
    rounds: each round is handed only what is left of it.

    Returns (exit_code, new_pars): exit_code is EXIT_PAR_LIMIT once the limit
    is used up while products remain; new_pars is the number of new distinct
    PAR PDFs saved in this session.
    """
    molecule_dir = run_dir / molecule
    par_tracker = molecule_dir / "download_tracker.json"
    session_start_hashes = unique_pdf_hashes(molecule_dir)
    code = _par_download_rounds(run_dir, molecule, core_db_path, par_limit, session_start_hashes)
    return code, len(unique_pdf_hashes(molecule_dir) - session_start_hashes)


def _par_download_rounds(
    run_dir: Path,
    molecule: str,
    core_db_path: Path,
    par_limit: int,
    session_start_hashes: set[str],
) -> int:
    molecule_dir = run_dir / molecule
    par_tracker = molecule_dir / "download_tracker.json"

    def new_this_session() -> int:
        return len(unique_pdf_hashes(molecule_dir) - session_start_hashes)

    for round_num in range(1, MAX_RETRY_ROUNDS + 1):
        if round_num == 1:
            print(f"\n→ PAR download round {round_num}/{MAX_RETRY_ROUNDS}", flush=True)
        else:
            print(f"\n→ PAR retry round {round_num}/{MAX_RETRY_ROUNDS}", flush=True)
            # Reset failed PAR downloads
            if par_tracker.exists():
                reset_failed_for_retry(par_tracker)

        cmd = [
            "node",
            str(SCRIPTS_DIR / "process_molecule_v10.js"),
            "--core", str(core_db_path),
            "--molecule", molecule,
            "--max", "10000",
        ]
        if par_limit > 0:
            downloaded = new_this_session()
            remaining = par_limit - downloaded
            if remaining <= 0:
                return EXIT_PAR_LIMIT
            cmd += ["--par-limit", str(remaining)]
            write_status(
                run_dir, "par_download", 2,
                detail=f"Batch: {downloaded}/{par_limit} new PAR PDFs this session",
            )

        exit_code = run_step(
            cmd,
            cwd=run_dir,
            step_name=f"PAR Document Downloads (round {round_num})",
        )

        if exit_code == EXIT_PAR_LIMIT:
            print(f"\n[OK] Session PAR limit of {par_limit} reached.", flush=True)
            return EXIT_PAR_LIMIT

        if exit_code == 3:
            print("\n[WARN] Portal blocking detected (exit code 3). VPN rotation needed.", flush=True)
            return 3

        # Check if script crashed (e.g. core DB not found)
        if exit_code != 0 and not par_tracker.exists():
            print(f"\n[ERROR] PAR downloader crashed (exit code {exit_code}). Core database may be missing.", flush=True)
            return 1

        incomplete = get_tracker_incomplete_count(par_tracker)
        if exit_code != 0 and incomplete > 0:
            print(f"\n[ERROR] PAR downloader crashed (exit code {exit_code}) with {incomplete} products incomplete.", flush=True)
            failed_count = incomplete
        else:
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

def generate_run_report(
    run_dir: Path,
    molecule: str,
    mode: str,
    max_products: int,
    scope: str = "full",
    par_limit: int = 0,
    outcome: str = "complete",
):
    """Generate run summary report."""
    per_proc_dir = run_dir / f"{molecule}_per_procedure"
    if not per_proc_dir.is_dir():
        per_proc_dir = run_dir / molecule
    report_path = run_dir / f"{molecule}_run_report.txt"
    report_path.write_text(f"""
╔═══════════════════════════════════════════════════════════════════╗
║            MRI Portal v26 (Docker) - Run Report                   ║
╚═══════════════════════════════════════════════════════════════════╝

RUN INFORMATION
───────────────────────────────────────────────────────────────────
  Molecule:          {molecule}
  Source Mode:       {mode}
  Run Scope:         {'Core base generation only' if scope == 'core' else 'Full run'}
  PAR Limit/Session: {par_limit if par_limit > 0 else 'unlimited'}
  Outcome:           {outcome}
  Max Products:      {max_products}
  Execution Time:    {datetime.now().isoformat()}
  Run Directory:     {run_dir}
  Version:           v26 Docker Edition

OUTPUT FILES
───────────────────────────────────────────────────────────────────
  • PAR per procedure:  {per_proc_dir}/
  • PAR collection:     {run_dir}/{molecule}_PAR_collection/
  • Core database:      {run_dir}/{molecule}_core_database.xlsx
  • Bioequivalence CSV: {run_dir}/{molecule}_bioequivalence.csv
  • This report:        {report_path}

FEATURES
───────────────────────────────────────────────────────────────────
  ✓ Run scope switch: full run / core base generation only (v26)
  ✓ PAR batches: per-session limit on new distinct PAR PDFs, resumable (v26)
  ✓ Auto-retry failed downloads (up to {MAX_RETRY_ROUNDS} rounds, random order)
  ✓ Stagnation detection (proceed after {MAX_STAGNANT_ROUNDS} stagnant rounds)
  ✓ Core download diagnostics + fallback retrieval
  ✓ Three source modes: automatic / basic / full
  ✓ NotebookLM batch collection (flat PAR folder)
  ✓ Resume via JSON trackers
  ✓ Unique browser identity per product download
  ✓ Docker container with VPN routing

Generated with MRI PAR Downloader v26 (Docker)
""")
    print(f"  ✓ {molecule}_run_report.txt", flush=True)


# ── Main pipeline ─────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def finish_core_only(run_dir: Path, molecule: str, core_db_path: Path, config: dict):
    """End a "Core base generation only" run once the core database exists."""
    if not core_db_path.exists():
        raise FileNotFoundError(f"Core database was not produced: {core_db_path.name}")
    try:
        n_products = len(pd.read_excel(core_db_path))
        size_txt = f" ({n_products} products)"
    except Exception:
        size_txt = ""
    write_status(run_dir, "finalizing", 1, detail="Writing run report")
    generate_run_report(
        run_dir, molecule, config["mode"], config["max_products"],
        scope="core", outcome=f"core database ready{size_txt}",
    )
    write_status(
        run_dir, "core_complete", 1,
        detail=f"Core database ready{size_txt} — continue the run to download PARs",
    )
    print(f"\n{'='*60}", flush=True)
    print(f"  Core database ready for {molecule}{size_txt}", flush=True)
    print(f"  {core_db_path}", flush=True)
    print(f"{'='*60}\n", flush=True)


def main():
    parser = argparse.ArgumentParser(description="MRI Pipeline Orchestrator v26")
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
    parser.add_argument(
        "--scope",
        choices=["full", "core"],
        default="full",
        help="full = core DB + PARs + BE extraction; core = core database generation only",
    )
    parser.add_argument(
        "--par-limit",
        type=int,
        default=0,
        help="Stop after this many new distinct PAR PDFs in this session (0 = unlimited)",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    molecule = args.molecule
    scope = args.scope
    par_limit = max(0, args.par_limit)

    core_db_path = run_dir / f"{molecule}_core_database.xlsx"
    search_json = run_dir / "search_results.json"
    core_tracker = run_dir / "core_download_tracker.json"
    molecule_dir = run_dir / molecule
    per_proc_dir = run_dir / f"{molecule}_per_procedure"
    par_tracker = molecule_dir / "download_tracker.json"

    is_resume = args.mode == "resume"
    previous_status = _read_json(run_dir / "status.json")
    # runner.start_pipeline replaces the last session's status with "starting"
    # and keeps the step it replaced as "resumed_from".
    previous_step = (
        previous_status.get("resumed_from")
        if previous_status.get("step") == "starting"
        else previous_status.get("step")
    )
    now = datetime.now().isoformat()

    # Save run config. A resumed run keeps its original config (source mode,
    # inputs, start time) and records each session, so History still shows how
    # the run was created rather than "resume".
    previous_config = _read_json(run_dir / "run_config.json") if is_resume else {}
    if previous_config:
        config = dict(previous_config)
        config["resumed_at"] = now
    else:
        config = {
            "molecule": molecule,
            "max_products": args.max_products,
            "mode": args.mode,
            "core_db": args.core_db,
            "basic_export": args.basic_export,
            "started_at": now,
        }
    config.setdefault("max_products", args.max_products)
    config["scope"] = scope
    config["par_limit"] = par_limit
    config.setdefault("sessions", []).append(
        {"started_at": now, "mode": args.mode, "scope": scope, "par_limit": par_limit}
    )
    (run_dir / "run_config.json").write_text(json.dumps(config, indent=2))

    print(
        f"[OK] Scope: {'core base generation only' if scope == 'core' else 'full run'}"
        f" · PAR limit this session: {par_limit if par_limit > 0 else 'unlimited'}",
        flush=True,
    )

    mode = args.mode

    if is_resume:
        # Runs finalized before v26 had {molecule}/ renamed to _per_procedure;
        # move it back so the PAR tracker resumes where it stopped.
        if (
            not molecule_dir.exists()
            and (per_proc_dir / "download_tracker.json").exists()
        ):
            per_proc_dir.rename(molecule_dir)
            print(f"[OK] Restored {molecule_dir.name}/ from {per_proc_dir.name}/ for resume", flush=True)

        # Auto-detect core DB path
        if not core_db_path.exists():
            alt = run_dir / f"{molecule}_database.xlsx"
            if alt.exists():
                core_db_path = alt
            elif args.core_db and Path(args.core_db).exists():
                core_db_path = Path(args.core_db)

        # Auto-detect what to resume
        if par_tracker.exists():
            print("[OK] Resuming PAR downloads", flush=True)
            mode = "_resume_par"
        elif previous_step == "core_complete" and core_db_path.exists():
            print("[OK] Core database ready — starting PAR downloads", flush=True)
            mode = "_resume_par"
        elif core_tracker.exists():
            print("[OK] Resuming core downloads", flush=True)
            mode = "_resume_core"
        elif core_db_path.exists():
            print("[OK] Core database found — starting PAR downloads", flush=True)
            mode = "_resume_par"
        else:
            print("[ERROR] No trackers found to resume from", flush=True)
            write_status(run_dir, "failed", 0, error="Nothing to resume: no trackers or core database found")
            sys.exit(1)

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

        # ── Core base generation only: stop here ───────────────────
        if scope == "core":
            finish_core_only(run_dir, molecule, core_db_path, config)
            return

        # ── Step 2: PAR Downloads ──────────────────────────────────
        write_status(
            run_dir, "par_download", 2,
            detail=f"Batch limit: {par_limit} new PAR PDFs this session" if par_limit > 0 else None,
        )

        exit_code, new_pars = run_par_downloads(run_dir, molecule, core_db_path, par_limit)

        if exit_code == 3:
            write_status(run_dir, "blocked", 2, error="Portal blocking detected. VPN rotation needed.")
            sys.exit(3)

        batch_paused = exit_code == EXIT_PAR_LIMIT

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

            # Aggregate the extracted PK/BE data into analysis-ready study rows + summary
            be_csv = run_dir / f"{molecule}_bioequivalence.csv"
            if be_csv.exists():
                print("[Step 3b] Aggregating PK study data...", flush=True)
                write_status(run_dir, "extraction", 3, detail="Aggregating PK study data")
                agg_code = run_step(
                    ["python3", str(SCRIPTS_DIR / "src" / "aggregate_pk_data.py"), str(be_csv)],
                    cwd=run_dir,
                    step_name="PK Data Aggregation",
                )
                if agg_code != 0:
                    print(f"[WARN] PK aggregation exited with code {agg_code}", flush=True)
        else:
            print(f"[SKIP] No PDFs found in {molecule_dir}, skipping BE extraction", flush=True)

        # ── Finalization ───────────────────────────────────────────
        write_status(run_dir, "finalizing", 3, detail="Creating collection and report")

        # PAR collection
        create_par_collection(run_dir, molecule)

        if batch_paused:
            # Keep {molecule}/ (and its tracker) in place: the next session
            # resumes from it. Results so far are already extracted above.
            left = get_tracker_incomplete_count(par_tracker)
            generate_run_report(
                run_dir, molecule, config["mode"], config["max_products"],
                scope=scope, par_limit=par_limit,
                outcome=f"batch finished — {new_pars} new PAR PDF(s) this session, "
                        f"{left} product(s) left for the next batch",
            )
            write_status(
                run_dir, "batch_complete", 3,
                detail=f"{new_pars} new PAR PDF(s) this session · {left} product(s) left — "
                       f"resume to download the next batch",
            )
            print(f"\n{'='*60}", flush=True)
            print(f"  Batch finished for {molecule}: {new_pars} new PAR PDF(s)", flush=True)
            print(f"  {left} product(s) left — resume the run for the next batch", flush=True)
            print(f"{'='*60}\n", flush=True)
            return

        # Rename molecule dir → _per_procedure for cleaner output
        if molecule_dir.is_dir() and not per_proc_dir.exists():
            molecule_dir.rename(per_proc_dir)

        # Run report
        generate_run_report(
            run_dir, molecule, config["mode"], config["max_products"],
            scope=scope, par_limit=par_limit,
            outcome=f"complete — {new_pars} new PAR PDF(s) this session",
        )

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
