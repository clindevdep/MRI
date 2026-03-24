#!/usr/bin/env python3
"""
MRI Pipeline Orchestrator — replaces RUN.sh for Docker container execution.

Three-step pipeline:
  1. Core DB acquisition (search portal or use uploaded Excel)
  2. PAR document download (Playwright stealth browsers)
  3. Bioequivalence data extraction (PDF parsing)

Called as a background subprocess by the Streamlit app (runner.py).
Writes status.json to run_dir for progress polling.

Usage:
  python orchestrator.py --run-dir /data/runs/ketoprofen_20260324 \
      --molecule ketoprofen --max-products 10000 --mode new_upload \
      --core-db /data/uploads/ketoprofen_database.xlsx
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path("/app/scripts")


def write_status(run_dir: Path, step: str, step_number: int, error: str | None = None):
    """Write pipeline status for Streamlit to poll."""
    status = {
        "step": step,
        "step_number": step_number,
        "total_steps": 3,
        "updated_at": datetime.now().isoformat(),
        "error": error,
    }
    (run_dir / "status.json").write_text(json.dumps(status, indent=2))


def run_step(cmd: list[str], cwd: Path, step_name: str) -> int:
    """Run a subprocess step, streaming output to stdout."""
    print(f"\n{'='*60}", flush=True)
    print(f"  Step: {step_name}", flush=True)
    print(f"  Command: {' '.join(str(c) for c in cmd)}", flush=True)
    print(f"  Working dir: {cwd}", flush=True)
    print(f"{'='*60}\n", flush=True)

    result = subprocess.run(cmd, cwd=str(cwd))

    if result.returncode != 0:
        # Exit code 3 = portal blocking (VPN needs rotation)
        if result.returncode == 3:
            print(f"\n[WARN] Portal blocking detected (exit code 3). VPN rotation needed.", flush=True)
        raise RuntimeError(f"{step_name} failed with exit code {result.returncode}")

    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="MRI Pipeline Orchestrator")
    parser.add_argument("--run-dir", required=True, help="Directory for this run's output")
    parser.add_argument("--molecule", required=True, help="Active substance name")
    parser.add_argument("--max-products", type=int, default=10000, help="Max products to process")
    parser.add_argument("--mode", choices=["new_search", "new_upload", "resume"], required=True)
    parser.add_argument("--core-db", default=None, help="Path to uploaded core database Excel")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save run config for history
    config = {
        "molecule": args.molecule,
        "max_products": args.max_products,
        "mode": args.mode,
        "core_db": args.core_db,
        "started_at": datetime.now().isoformat(),
    }
    (run_dir / "run_config.json").write_text(json.dumps(config, indent=2))

    try:
        # ── Step 1: Core Database ──────────────────────────────────
        write_status(run_dir, "core_database", 1)

        core_db_path = run_dir / f"{args.molecule}_core_database.xlsx"

        if args.mode == "new_upload":
            # User uploaded an Excel — copy it as the core database
            src = Path(args.core_db)
            if not src.exists():
                raise FileNotFoundError(f"Uploaded core DB not found: {src}")
            shutil.copy2(src, core_db_path)
            print(f"[OK] Core database copied from upload: {src.name}", flush=True)

        elif args.mode == "new_search":
            # Step 1a: Search the MRI portal
            search_results = run_dir / "search_results.json"
            run_step(
                ["node", str(SCRIPTS_DIR / "src" / "search_molecule_stealth_v14.js"),
                 args.molecule, str(args.max_products)],
                cwd=run_dir,
                step_name="Portal Search",
            )

            # Step 1b: Download core database from search results
            run_step(
                ["node", str(SCRIPTS_DIR / "download_and_merge_products.js"),
                 str(search_results), str(core_db_path), str(args.max_products)],
                cwd=run_dir,
                step_name="Core Database Download",
            )

        elif args.mode == "resume":
            # Resume: core DB should already exist in run_dir
            if not core_db_path.exists():
                # Try alternative naming
                alt = run_dir / f"{args.molecule}_database.xlsx"
                if alt.exists():
                    core_db_path = alt
                elif args.core_db and Path(args.core_db).exists():
                    core_db_path = Path(args.core_db)
                else:
                    raise FileNotFoundError(
                        f"No core database found in {run_dir} for resume"
                    )
            print(f"[OK] Resuming with existing core database: {core_db_path.name}", flush=True)

        # ── Step 2: PAR Downloads ──────────────────────────────────
        write_status(run_dir, "par_download", 2)

        run_step(
            ["node", str(SCRIPTS_DIR / "process_molecule_v10.js"),
             args.molecule, str(args.max_products)],
            cwd=run_dir,
            step_name="PAR Document Downloads",
        )

        # ── Step 3: Bioequivalence Extraction ──────────────────────
        write_status(run_dir, "extraction", 3)

        molecule_dir = run_dir / args.molecule
        if molecule_dir.exists() and any(molecule_dir.rglob("*.pdf")):
            run_step(
                ["python3", str(SCRIPTS_DIR / "src" / "extract_bioequivalence.py"),
                 str(molecule_dir)],
                cwd=run_dir,
                step_name="Bioequivalence Extraction",
            )
        else:
            print(f"[SKIP] No PDFs found in {molecule_dir}, skipping BE extraction", flush=True)

        # ── Done ───────────────────────────────────────────────────
        write_status(run_dir, "complete", 3)
        print(f"\n{'='*60}", flush=True)
        print(f"  Pipeline complete for {args.molecule}", flush=True)
        print(f"  Results in: {run_dir}", flush=True)
        print(f"{'='*60}\n", flush=True)

    except Exception as e:
        write_status(run_dir, "failed", 0, error=str(e))
        print(f"\n[ERROR] Pipeline failed: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
