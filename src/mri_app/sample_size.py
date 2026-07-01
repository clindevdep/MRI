"""Wrapper around CVw_Screening_v03.R (Jirka's CVw screening + pooled sample size).

Builds the defined-format screening CSV from study rows, invokes the R script,
and parses its JSON result. The R script owns the statistics (CVfromCI /
sampleN.TOST / CVpooled); this module only marshals data in and out.
"""

import csv
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Column order expected by CVw_Screening_v03.R
CVW_COLUMNS = [
    "PK", "Ntotal", "Point", "lower", "upper", "Design", "lowBElimit",
    "PlannedDesign", "Incl.to.PoolCVw", "ReportedCVw", "Product", "Source",
]


def _scripts_dir() -> Path:
    """Locate the scripts/ directory (container default, host fallback)."""
    env = os.getenv("MRI_SCRIPTS_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    container = Path("/app/scripts")
    if container.is_dir():
        return container
    return Path(__file__).resolve().parents[2] / "scripts"


CVW_SCRIPT = _scripts_dir() / "CVw_Screening_v03.R"


class SampleSizeError(RuntimeError):
    """Raised when the CVw screening / sample-size calculation cannot complete."""


def _fmt(value):
    """Render a value for the CSV; None/blank → 'NA' (R na.strings)."""
    if value is None or value == "":
        return "NA"
    return value


def run_cvw_screening(
    studies: list[dict],
    targetpowers: list[float] | None = None,
    theta0: float = 0.95,
    alpha: float = 0.05,
    timeout: int = 120,
) -> dict:
    """Run the CVw screening on the given study rows.

    Each study dict may provide: PK, Ntotal, Point, lower, upper, Design,
    lowBElimit, PlannedDesign, Incl.to.PoolCVw ('Y'/'N'), ReportedCVw, Product,
    Source. Missing numeric fields become 'NA'.

    Returns the parsed JSON:
      {targetpowers, theta0, per_study:[...], pooled:{<PK>:{cvw_pooled,n_studies,N-Pwr..%}}}
    """
    rscript = shutil.which("Rscript")
    if not rscript:
        raise SampleSizeError("Rscript not found on PATH (is R installed in the image?)")
    if not CVW_SCRIPT.exists():
        raise SampleSizeError(f"R script not found: {CVW_SCRIPT}")
    if not studies:
        raise SampleSizeError("no studies provided for screening")

    targetpowers = targetpowers or [0.80, 0.90]
    tp_arg = ",".join(str(p) for p in targetpowers)

    work = Path(tempfile.mkdtemp(prefix="cvw_"))
    try:
        input_csv = work / "CVw_Screening.csv"
        with input_csv.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CVW_COLUMNS)
            writer.writeheader()
            for s in studies:
                writer.writerow({c: _fmt(s.get(c)) for c in CVW_COLUMNS})

        try:
            proc = subprocess.run(
                [rscript, str(CVW_SCRIPT), str(input_csv), str(work), tp_arg, str(theta0), str(alpha)],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise SampleSizeError(f"CVw screening timed out after {timeout}s") from exc

        out = (proc.stdout or "").strip()
        if not out:
            raise SampleSizeError(
                f"R script produced no output (exit {proc.returncode}). stderr: {proc.stderr.strip()[:500]}"
            )
        try:
            result = json.loads(out)
        except json.JSONDecodeError as exc:
            raise SampleSizeError(f"could not parse R output as JSON: {out[:500]}") from exc
        if isinstance(result, dict) and result.get("error"):
            raise SampleSizeError(str(result["error"]))
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def study_from_row(row, incl: bool, design: str = "2x2", low_be_limit: float = 0.80) -> dict:
    """Build a screening study dict from a normalised pk_studies row (pandas Series)."""
    import math

    def num(v):
        try:
            f = float(v)
            return None if math.isnan(f) else f
        except (TypeError, ValueError):
            return None

    return {
        "PK": row.get("PK_group") or row.get("PK_parameter"),
        "Ntotal": int(row["N"]) if num(row.get("N")) else None,
        "Point": num(row.get("GMR")),
        "lower": num(row.get("CI_lower")),
        "upper": num(row.get("CI_upper")),
        "Design": design,
        "lowBElimit": low_be_limit,
        "PlannedDesign": design,
        "Incl.to.PoolCVw": "Y" if incl else "N",
        "ReportedCVw": num(row.get("CV_pct")),
        "Product": row.get("Product"),
        "Source": row.get("Source"),
    }
