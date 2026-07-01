#!/usr/bin/env python3
"""
Aggregate PK / bioequivalence study data for a run.

Reads the per-run ``<molecule>_bioequivalence.csv`` produced by
``extract_bioequivalence.py`` (one row per PK parameter per study), normalises
the free-text numeric columns into clean numeric fields, de-duplicates, and
writes three artefacts next to it:

  - ``<molecule>_pk_studies.csv``    — normalised, analysis-ready study rows
  - ``<molecule>_pk_summary.json``   — per-PK-parameter counts + reported-CV stats
  - ``<molecule>_CVw_Screening.csv`` — input for CVw_Screening_v03.R (defined
    column format). CVw is *calculated* from the CI + N there, so rows are kept
    whenever CI limits and N are present, even if no CV was reported in the PAR.

Usage:
    python aggregate_pk_data.py /data/runs/<run>/<molecule>_bioequivalence.csv
"""

import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

# Defaults for the CVw screening input (overridable later in the UI).
DEFAULT_DESIGN = "2x2"
DEFAULT_BE_LIMIT = 0.80


def _to_float(value):
    """Parse a numeric value from possibly messy text ('35.5', '99.5%', '')."""
    if value is None:
        return math.nan
    s = str(value).strip().replace("%", "").replace(",", ".")
    m = re.search(r"-?\d+\.?\d*", s)
    return float(m.group()) if m else math.nan


def _to_int(value):
    f = _to_float(value)
    return int(f) if not math.isnan(f) else None


def _as_ratio(value):
    """Normalise a point estimate to a ratio (0.995), accepting percent (99.5)."""
    f = _to_float(value)
    if math.isnan(f):
        return math.nan
    return f / 100.0 if f > 2 else f


def _parse_ci(value):
    """Return (lower, upper) as ratios from '90 - 110' / '0.90-1.10' style text."""
    if value is None:
        return (math.nan, math.nan)
    nums = re.findall(r"\d+\.?\d*", str(value))
    if len(nums) < 2:
        return (math.nan, math.nan)
    lo, hi = float(nums[0]), float(nums[1])
    if lo > 2 or hi > 2:  # percent form
        lo, hi = lo / 100.0, hi / 100.0
    return (lo, hi)


def _pk_group(param):
    """Map a reported PK parameter to a pooling group (Cmax / AUC / AUCinf / ...)."""
    p = str(param or "").lower().replace(" ", "")
    if "cmax" in p:
        return "Cmax"
    if "auc" in p and ("inf" in p or "∞" in p or "∾" in p):
        return "AUCinf"
    if "auc" in p and "tau" in p:
        return "AUCtau"
    if "auc" in p:
        return "AUC"
    return str(param)


def aggregate(be_csv: Path) -> dict:
    df = pd.read_csv(be_csv)
    if df.empty:
        raise ValueError(f"No rows in {be_csv}")

    out = pd.DataFrame()
    out["Product"] = df.get("Product name")
    out["Strength"] = df.get("Strength")
    out["Food"] = df.get("Food")
    out["PK_parameter"] = df.get("PK parameter")
    out["PK_group"] = out["PK_parameter"].map(_pk_group)
    out["N"] = df.get("N").map(_to_int) if "N" in df else None
    out["GMR"] = df.get("Ratio").map(_as_ratio) if "Ratio" in df else math.nan
    ci = df.get("CI").map(_parse_ci) if "CI" in df else None
    out["CI_lower"] = [c[0] for c in ci] if ci is not None else math.nan
    out["CI_upper"] = [c[1] for c in ci] if ci is not None else math.nan
    out["CV_pct"] = df.get("CV").map(_to_float) if "CV" in df else math.nan
    out["Source"] = df.get("Source")

    # Keep rows usable for CVfromCI (needs CI + N). Reported CV is optional.
    out = out.dropna(subset=["CI_lower", "CI_upper", "N"])
    out = out.drop_duplicates(
        subset=["Product", "Strength", "PK_parameter", "CI_lower", "CI_upper", "N"]
    ).reset_index(drop=True)
    out["N"] = out["N"].astype("Int64")  # nullable int → shows 34, not 34.0

    base = be_csv.with_name(be_csv.name.replace("_bioequivalence.csv", ""))

    studies_csv = Path(f"{base}_pk_studies.csv")
    out.to_csv(studies_csv, index=False)

    # CVw screening input (defined column format for CVw_Screening_v03.R)
    cvw = pd.DataFrame({
        "PK": out["PK_group"],
        "Ntotal": out["N"],
        "Point": out["GMR"],
        "lower": out["CI_lower"],
        "upper": out["CI_upper"],
        "Design": DEFAULT_DESIGN,
        "lowBElimit": DEFAULT_BE_LIMIT,
        "PlannedDesign": DEFAULT_DESIGN,
        "Incl.to.PoolCVw": "Y",
        "ReportedCVw": out["CV_pct"],
        "Product": out["Product"],
        "Source": out["Source"],
    })
    cvw_csv = Path(f"{base}_CVw_Screening.csv")
    cvw.to_csv(cvw_csv, index=False, na_rep="NA")

    # Per-PK-group summary (counts + reported-CV stats where available)
    summary = {"total_studies": int(len(out)), "parameters": {}}
    for param, grp in out.groupby("PK_group"):
        reported = grp["CV_pct"].dropna()
        summary["parameters"][str(param)] = {
            "n_studies": int(len(grp)),
            "n_reported_cv": int(len(reported)),
            "reported_cv_median": round(float(reported.median()), 2) if len(reported) else None,
            "reported_cv_max": round(float(reported.max()), 2) if len(reported) else None,
        }
    summary_json = Path(f"{base}_pk_summary.json")
    summary_json.write_text(json.dumps(summary, indent=2))

    print(f"  ✓ {studies_csv.name}: {len(out)} normalised study rows")
    print(f"  ✓ {cvw_csv.name}: CVw screening input ({len(cvw)} rows)")
    print(f"  ✓ {summary_json.name}: {len(summary['parameters'])} PK group(s)")
    return summary


def main():
    if len(sys.argv) < 2:
        print("Usage: python aggregate_pk_data.py <molecule>_bioequivalence.csv")
        sys.exit(1)
    be_csv = Path(sys.argv[1])
    if not be_csv.exists():
        print(f"Error: not found: {be_csv}")
        sys.exit(1)
    aggregate(be_csv)


if __name__ == "__main__":
    main()
