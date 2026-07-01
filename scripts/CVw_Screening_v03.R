#!/usr/bin/env Rscript
# CVw screening + pooled sample size — runnable adaptation of CVw_Screening_v02.R
# (Jirka's CVfromCI / sampleN.TOST / CVpooled logic preserved verbatim).
#
# v03 changes vs v02: no setwd(); input/output are arguments; emits JSON on
# stdout for the app; also computes a pooled sample size from the pooled CVw and
# passes through the reported CVw for cross-checking against the calculated CVw.
#
# Usage:
#   Rscript CVw_Screening_v03.R <input.csv> <out_dir> [targetpowers] [theta0] [alpha]
#     targetpowers: comma list, default "0.8,0.9"
#
# Input CSV columns (created by the app from the aggregated PK data):
#   PK, Ntotal, Point, lower, upper, Design, lowBElimit, PlannedDesign,
#   Incl.to.PoolCVw, ReportedCVw, Product, Source
#   - Point may be "NA"; lower/upper/Point are ratios (e.g. 0.90, 1.00, 0.95)
#   - Design/PlannedDesign per known.designs(); Incl.to.PoolCVw = "Y"/"N"
#
# Output (stdout JSON):
#   { "targetpowers": [...],
#     "per_study": [ {PK, Product, Ntotal, CVw_calc, CVw_reported, "N-Pwr80%":.., ...}, ... ],
#     "pooled":    { "<PK>": {cvw_pooled, n_studies, "N-Pwr80%":.., ...}, ... } }

suppressMessages({
  library(jsonlite)
  library(PowerTOST)
})

fail <- function(msg) {
  cat(toJSON(list(error = unbox(msg)), auto_unbox = TRUE))
  quit(status = 1)
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) fail("usage: CVw_Screening_v03.R <input.csv> <out_dir> [targetpowers] [theta0] [alpha]")

input_csv   <- args[1]
out_dir     <- args[2]
targetpower <- if (length(args) >= 3) as.numeric(strsplit(args[3], ",")[[1]]) else c(.8, .9)
theta0      <- if (length(args) >= 4) as.numeric(args[4]) else 0.95
alpha       <- if (length(args) >= 5) as.numeric(args[5]) else 0.05

if (!file.exists(input_csv)) fail(paste("input not found:", input_csv))

tab <- tryCatch(
  read.csv(input_csv, header = TRUE, sep = ",", skip = 0, as.is = TRUE, na.strings = "NA"),
  error = function(e) fail(paste("cannot read csv:", conditionMessage(e)))
)
if (nrow(tab) == 0) fail("input csv has no rows")

power_names <- vapply(targetpower, function(tp) paste0("N-Pwr", tp * 100, "%"), character(1))

# ── Per-study CVw (from CI) + sample size per target power ────────────────────
res <- as.data.frame(matrix(ncol = length(targetpower), nrow = nrow(tab)))
colnames(res) <- power_names
CVcol <- rep(NA_real_, nrow(tab))

for (r in seq_len(nrow(tab))) {
  n      <- tab[r, "Ntotal"]
  point  <- tab[r, "Point"]
  lower  <- tab[r, "lower"]
  upper  <- tab[r, "upper"]
  design <- tab[r, "Design"]

  CV <- tryCatch({
    if (is.na(point)) {
      CVfromCI(lower = lower, upper = upper, n = n, design = design, alpha = alpha)
    } else {
      CVfromCI(pe = point, lower = lower, upper = upper, n = n, design = design, alpha = alpha)
    }
  }, error = function(e) NA_real_)
  CVcol[r] <- CV
  if (is.na(CV)) next

  theta1 <- tab[r, "lowBElimit"]
  theta2 <- 1 / theta1
  pdesign <- tab[r, "PlannedDesign"]

  for (a in seq_along(targetpower)) {
    y <- tryCatch(
      sampleN.TOST(alpha = alpha, targetpower = targetpower[a], logscale = TRUE,
                   theta1 = theta1, theta2 = theta2, theta0 = theta0,
                   CV = CV, design = pdesign, details = FALSE, print = FALSE,
                   robust = FALSE, imax = 1000),
      error = function(e) NULL
    )
    res[r, a] <- if (is.null(y)) NA_integer_ else as.integer(y[, 7])
  }
}

tab$CVw <- round(CVcol * 100, 0)
result <- cbind(tab, res)

# Write the full result table (parity with v02's SS-result.csv)
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
write.csv(result, file = file.path(out_dir, "SS-result.csv"), row.names = FALSE)

# ── Pooled CVw by PK (only rows flagged Incl.to.PoolCVw == "Y") ────────────────
pooled_out <- list()
if ("Incl.to.PoolCVw" %in% names(result)) {
  cvpool <- result[!is.na(result$CVw) & toupper(result$Incl.to.PoolCVw) == "Y", ]
  for (pk in unique(cvpool$PK)) {
    sub <- cvpool[cvpool$PK == pk, c("CVw", "Ntotal", "PlannedDesign")]
    names(sub) <- c("CV", "n", "design")
    sub$CV <- sub$CV / 100  # CVpooled expects CV as ratio
    if (nrow(sub) < 1) next
    pres <- tryCatch(
      CVpooled(sub, alpha = alpha, logscale = TRUE, robust = FALSE),
      error = function(e) NULL
    )
    if (is.null(pres)) next
    cvw_pooled <- as.numeric(pres$CV)

    # Pooled sample size from the pooled CVw (uses the first row's BE limit/design)
    theta1 <- cvpool[cvpool$PK == pk, "lowBElimit"][1]
    theta2 <- 1 / theta1
    pdesign <- cvpool[cvpool$PK == pk, "PlannedDesign"][1]
    entry <- list(cvw_pooled = unbox(round(cvw_pooled * 100, 1)),
                  n_studies = unbox(nrow(sub)))
    for (a in seq_along(targetpower)) {
      y <- tryCatch(
        sampleN.TOST(alpha = alpha, targetpower = targetpower[a], logscale = TRUE,
                     theta1 = theta1, theta2 = theta2, theta0 = theta0,
                     CV = cvw_pooled, design = pdesign, print = FALSE, robust = FALSE),
        error = function(e) NULL
      )
      entry[[power_names[a]]] <- unbox(if (is.null(y)) NA_integer_ else as.integer(y[, 7]))
    }
    pooled_out[[as.character(pk)]] <- entry
  }
}

# ── Per-study JSON (incl. reported-vs-calculated CVw cross-check) ──────────────
per_study <- lapply(seq_len(nrow(result)), function(r) {
  item <- list(
    PK = unbox(as.character(result[r, "PK"])),
    Product = unbox(if ("Product" %in% names(result)) as.character(result[r, "Product"]) else NA),
    Ntotal = unbox(result[r, "Ntotal"]),
    CVw_calc = unbox(result[r, "CVw"]),
    CVw_reported = unbox(if ("ReportedCVw" %in% names(result)) result[r, "ReportedCVw"] else NA),
    Incl = unbox(if ("Incl.to.PoolCVw" %in% names(result)) as.character(result[r, "Incl.to.PoolCVw"]) else NA)
  )
  for (a in seq_along(targetpower)) item[[power_names[a]]] <- unbox(result[r, power_names[a]])
  item
})

cat(toJSON(list(
  targetpowers = targetpower,
  theta0 = unbox(theta0),
  per_study = per_study,
  pooled = pooled_out
), auto_unbox = FALSE, na = "null"))
