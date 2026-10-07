# Project LOG — MRI

## GOAL
Port the MRI_Jan2026 CLI tool (EU MRI Portal PAR downloader + bioequivalence extractor) into a Dockerized web application for the ClinDevDep Hub at `mri.clindevdep.com`.

## Instructions
- Project: MRI
- Created: 2026-03-24
- Task: app-port
- Languages: [python, javascript, shell]
- Tags: [docker, hub-app, playwright, vpn]
- Computer: clindevdep-T470
- Status: active
- GitHub: https://github.com/clindevdep/MRI
- Source project: https://github.com/clindevdep/MRI_Jan2026
- Template (v20): https://github.com/clindevdep/MRI_Mar2026

## Architecture
- **Container:** Docker (node:22-bookworm-slim + Python 3.12 + uv + Playwright Chromium)
- **VPN:** All traffic routed through Gluetun (`network_mode: "service:gluetun"`)
- **Port:** 8502 (exposed on Gluetun container)
- **Subdomain:** mri.clindevdep.com (Traefik + OAuth)
- **Data:** Persistent volume at `/home/clindevdep/docker/appdata/mri/`

## Rollback (v26 → v25) — current
- **Git:** pre-v26 state tagged `v25-stable` (commit `7e4c549`, branch `v21-swe-pk`); v26 work on branch
  `v26-par-batches`. Source snapshot: `/home/clindevdep/AI/MRI_backups/mri_v25-stable_7e4c549_20261007.tar.gz`.
- **Image:** `mri:v25-stable-rollback` (= `mri:v25-ui-fixes` @ `29de6bc0139b`). Live v26 = `mri:v26-par-batches`.
- **Revert container** (`DOCKER_HOST=unix:///var/run/docker.sock`; check no run is active first):
  `docker tag mri:v25-stable-rollback docker-mri:latest && docker rm -f mri && docker run -d --name mri --network container:gluetun --restart unless-stopped --security-opt no-new-privileges:true -v /home/clindevdep/docker/appdata/mri:/data -e TZ=Europe/Berlin -e ENABLE_PROXY=false --label com.docker.compose.project=docker --label com.docker.compose.service=mri mri:v25-stable-rollback`
- Data compatibility: v26 only *adds* fields (`scope`, `par_limit`, `sessions`, `resumed_from`) and two
  statuses (`core_complete`, `batch_complete`). v25 ignores the fields; a run left in a v26-only status shows
  as a plain step label in v25 and can still be resumed there (v25 auto-detects from the trackers).

## Rollback (v20 stable → v21 work) — historical
- **Git:** stable state tagged `v20-stable` (commit `e32669b`); v21 work on branch `v21-swe-pk`.
  Revert code: `git checkout v20-stable` (or `git checkout main`).
- **Image:** the last-known-good image is tagged `mri:v20` (= `docker-mri:latest` @ `81f940ef45ea`).
  Revert container: re-point the mri service to `mri:v20` and recreate
  (`DOCKER_HOST=unix:///var/run/docker.sock`; container uses `network_mode: service:gluetun`).
- New v21 image is built under a **separate tag** and only cut over after verification.

## Pipeline (aligned to RUN_v20.sh from MRI_Mar2026)
1. **Core DB acquisition** — three modes:
   - **automatic**: search MRI portal by molecule name → download extended info
   - **basic** (recommended): user uploads basic MRI export .xlsx → convert to JSON → download extended info
   - **full**: user uploads pre-compiled full database → skip extended info
   - Auto-retry with stagnation detection (10 rounds, partial-core continuation)
2. **PAR download** — Playwright stealth browsers with Solo ID fingerprinting → PDF documents
   - Tracker-based resume (download_tracker.json)
   - Auto-retry with randomized retry order
3. **BE extraction** — pdfplumber parses PDFs → bioequivalence CSV
4. **Finalization** — PAR collection (flat folder), run report

## TODO

### Stage 1: Backend (Docker + Pipeline)
- [x] 1.1 Project scaffolding, git init, GitHub repo
- [x] 1.2 package.json + pyproject.toml
- [x] 1.3 Copy & patch JS scripts from MRI_Oct2025
- [x] 1.4 Dockerfile (multi-runtime)
- [x] 1.5 orchestrator.py (Python replacement for RUN.sh)
- [x] 1.6 Docker Compose + Gluetun routing
- [x] 1.7 Align scripts to RUN_v20.sh (MRI_Mar2026 template)
- [x] 1.8 Build & test backend container

### Stage 2: WebUI (Streamlit)
- [x] 2.1 Streamlit skeleton (app.py + .streamlit/config.toml)
- [x] 2.2 Core modules (runner.py, tracker.py, config.py)
- [x] 2.3 New Run page (mode selection, file upload, launch)
- [x] 2.4 Progress page (live status, tracker stats, log tail, auto-refresh)
- [x] 2.5 Results page (browse PARs, BE CSV table, database preview, downloads)
- [x] 2.6 History page (all runs, resume button)
- [x] 2.7 Dockerfile CMD updated for Streamlit
- [x] 2.8 Docker build + Streamlit health check verified
- [ ] 2.9 End-to-end workflow test with real data

### Stage 3: Hub Integration
- [x] 3.1 Traefik rule (app-mri.yml) — mri.clindevdep.com with chain-oauth
- [x] 3.2 Glance widget added to dashboard
- [x] 3.3 DNS — managed by Traefik wildcard cert (no Cloudflare record needed)
- [x] 3.4 Stack deployed — MRI container healthy, Traefik router enabled

### Future: Automatic VPN Rotation
- [ ] 4.1 Integrate Gluetun control server API (localhost:8000) for programmatic VPN rotation
  - On 3 consecutive download timeouts → stop VPN via API → auto-heal reconnects to new server → verify new IP → resume
  - Replaces current manual VPN restart workflow
  - Gluetun API: `PUT /v1/vpn/status {"status":"stopped"}` triggers auto-heal to random server
  - `GET /v1/publicip/ip` to verify new IP after reconnect
  - MRI container reaches API at localhost:8000 (shared network stack)
  - Requires: enable Gluetun HTTP_CONTROL_SERVER_AUTH env var
- [ ] 4.2 **IMPORTANT: Test geo-restriction** — verify that non-EU VPN exit countries are NOT rejected by MRI portal (mri.cts-mrp.eu). If so, must configure SERVER_COUNTRIES in Gluetun to EU-only pool
- [ ] 4.3 Patch process_molecule_v10.js: replace exit-on-block (code 3) with rotate-and-retry loop
- [ ] 4.4 End-to-end test: full molecule download with automatic rotation

### Stage 5: v21 — SWE PARs, PK aggregation, sample size (branch v21-swe-pk)
- [x] 5.0 Rollback net: tag `v20-stable`, branch `v21-swe-pk`, image `mri:v20`
- [x] 5.1 App opens on Progress tab (Session dashboard folded into Home.py, Progress tab first)
- [x] 5.2 Correct progress eval: source-aware stats (with_pars/empty), composite progress bar
- [x] 5.3 Fix stuck "running" spinner (is_running terminal-status short-circuit)
- [x] 5.4 CVw screening + pooled sample size: user's CVw_Screening_v02.R (Jirka) → runnable CVw_Screening_v03.R (arg-driven, JSON out) + sample_size.py wrapper + Sample Size tab
- [x] 5.5 SWE agency PAR download (scripts/src/swe_agency_v1.js, RMS=SE link-following in process_molecule_v10.js)
- [x] 5.6 PK aggregation (scripts/src/aggregate_pk_data.py → _pk_studies.csv + _CVw_Screening.csv + summary; orchestrator step; selectable Results table)
- [x] 5.7 Integrate CVw_Screening (replaces earlier PowerTOST stub): CVfromCI + sampleN.TOST + CVpooled; reported-vs-calculated CVw cross-check
- [x] 5.8 Build `mri:v21` (adds R+PowerTOST+jsonlite), deploy, cut over from mri:v20 — DONE 2026-07-01, live container healthy on v21
- [x] 5.9 Live verify: Melatonin SE — SWE code runs cleanly; DOM probe proved the agency links ARE on the page as Angular-Material `open_in_new` buttons (URL in tooltip, not `<a href>`) → scanner selector gap. FIXED (5.11).
- [x] 5.11 SWE 2-hop fix — `collectSwedishAgencyPARs()` reads Material tooltip landing URLs (portal → lakemedelsverket facts page) then scans that page for docetp PAR/sPAR PDFs (filtered to PAR/sPAR, English first). LIVE-VERIFIED on mri:v21: SE/H/2048/001/004/005 each download ENG PAR (253KB) + ENG sPAR (29KB) valid PDFs. Diagnostics: `scripts/probe_swe_dom_v1.js`, `scripts/probe_facts_v1.js`. (SE/H/1592/001 → 0: genuine absence, no agency link on its portal page.)
- [ ] 5.10 (optional) VLM PDF-digest extraction via Full-texts bridge / Legion for robust PK parsing

### Stage 6: v23 — PAR stage restored after portal Angular change
- [x] 6.1 Diagnose 0-PAR runs (every run since 2026-08-03): root cause is the Solo ID context forcing
  navigation-only headers (`Sec-Fetch-Dest: document`, `Sec-Fetch-Mode: navigate`,
  `Upgrade-Insecure-Requests`, HTML-only `Accept`) onto *every* request, including the portal's Angular
  module + OData XHRs → page never leaves its loading spinner → `text=Documents` matches nothing →
  "Documents tab not found" → 0 PARs, reported as 614/614 completed with 0 failures. NOT portal blocking,
  NOT geo (exit was Riga/LV, EU), NOT a missing tab. Same trap v22 documented for the core stage.
- [x] 6.2 Fix headers in `scripts/src/solo_id_v10.js` + shared `scripts/src/advanced_stealth.js`
  (`getRealisticHeaders`, also used by automatic-mode search and the legacy core downloader).
- [x] 6.3 Fix attachment scan: `mat-icon:has-text("archive")` also matched the page toolbar's
  "Download excel" button (serves no file → a 20s download timeout per product, logged as "Failed").
  Scan is now scoped to the document list (`mat-list-item`, labelled "<documentType> | <documentName>")
  and only PubAR/PAR rows are clicked; SPC/PL/Labelling are no longer downloaded just to be discarded.
  Saved files validated as real `%PDF`.
- [x] 6.4 Build `mri:v23-par-dom-fix` (442f420d61c4), smoke-test, deploy, live-verify in production.
- [x] 6.5 **FIXED in v24** (was a pre-existing bug, separate from the PAR fix): `mvtnorm` + `cubature`
  were MISSING from the v22/v23 images, so `library(PowerTOST)` failed → Sample Size / CVw screening was
  dead from the 2026-08-04 v22 image until 2026-10-05. Root cause: **PPM no longer publishes
  bookworm/R-4.2 binaries** — every snapshot (latest, 2026-07-01, 2026-06-01, 2026-03-01) now resolves to
  `src/contrib`, so mvtnorm (Fortran) and cubature/Rcpp (C++) fell back to a source build and failed in
  this deliberately compiler-less image, and `install.packages()` only *warns*. R itself never changed
  (4.2.2 Patched in both v21 and v23). Fix: take the compiled deps from Debian bookworm
  (`r-cran-mvtnorm` 1.1-3, `r-cran-cubature` 2.0.4.6, `r-cran-rcpp` 1.0.10, `r-cran-jsonlite` 1.8.4 —
  prebuilt against R 4.2.2, so still NO toolchain) and install only PowerTOST (`NeedsCompilation=no`)
  from source, plus a build-time assertion that all four load and `CVfromCI` runs.
- [ ] 6.6 Re-run the molecules that returned 0 PARs under the broken code (Rivaroxaban 614 products,
  Ketoconazole, Bilastine, Pancreatine, LisDexAmfetamine).
- [x] 6.7 **UI (v25, user-reported):** (a) removed the empty blue box between the "New Run" title and the
  "Source mode" subtitle — a `.mode-panel` `<div>` opened and closed in two separate `st.markdown()` calls
  can never wrap the radio, so it rendered as an empty bordered box; (b) "Start Pipeline" now leaves the
  user on the Progress tab **of the run just started** — `start_pipeline` writes `run_config.json` before
  spawning the orchestrator (previously only `pid`, and `list_runs()` skips dirs without a config, so the
  new run was invisible and the selection request was discarded), and the run selector keeps its value
  under its own key instead of an `index` that the 3s auto-refresh kept resetting.

### Stage 7: v26 — run scope switch + PAR batches (branch v26-par-batches)
- [x] 7.0 Rollback net: git tag `v25-stable`, image `mri:v25-stable-rollback`, source tarball in `~/AI/MRI_backups/`
- [x] 7.1 New Run: "Full run" / "Core base generation only" switch (default Full run; disabled for Core
  Database uploads). Core-only runs end in `core_complete`; "Download PARs" continues straight to PARs.
- [x] 7.2 Per-session PAR limit (default unlimited): session stops after N new **distinct** PAR PDFs
  (SHA-256 content dedup — a PAR shared by several strengths counts once). `process_molecule_v10.js
  --par-limit N` exits 4; orchestrator spreads the limit over retry rounds, runs BE extraction on what it
  has, keeps `{molecule}/` + tracker and ends in `batch_complete`. A product cut off mid-way stays pending.
- [x] 7.3 Resume: keeps the run's original config + `sessions` log; `resumed_from` carries the previous
  step past the "starting" status; restores `{molecule}/` from `_per_procedure/` for pre-v26 runs.
- [x] 7.4 Dashboard/History: new statuses, Results shown for partial runs, shared continue controls
  (`src/mri_app/run_controls.py`); UI smoke test `tests/ui_test_v26.mjs`.
- [x] 7.5 Build `mri:v26-par-batches`, test in throwaway containers, deploy live (2026-10-07).
- [ ] 7.6 User acceptance: one real batched run on a large molecule (e.g. re-run Rivaroxaban in batches — 6.6).

## Test Results
- 7.x v26 (2026-10-07, throwaway containers on gluetun, isolated volume — live data untouched):
  Cabozantinib (5 products, mode full) limit 3 → exactly 3 distinct PDFs, DK/H/3422/002+003 identical PARs
  flagged "not counted", DK/H/3456/001 left pending mid-product → `batch_complete`; resume limit 3 → 1 new,
  `complete`, 10 PDFs total (= the original unlimited run). MelSE4 basic + core-only → `core_complete`
  (4 products, no PAR stage); continue limit 2 → SWE PAR+sPAR then `batch_complete`; continue unlimited →
  004/005 SWE duplicates not counted → `complete`. Pre-v26 renamed `_per_procedure` run resumed → folder
  restored, `complete`. Bug found + fixed during testing: runner's "starting" status hid `core_complete`
  from the orchestrator (re-ran core stage) → `resumed_from`. UI (Playwright, 31 checks, 0 exceptions):
  switch default Full run, limit toggle off/unlimited by default, number input 10 when on, core hides limit,
  full-mode disables switch, Download PARs / Download next batch buttons, limit prefilled from last session,
  History labels. LIVE after deploy: New Run / History / Home render on real data, 0 exceptions, healthy.
- 6.7 LIVE (2026-10-05, `mri:v25-ui-fixes`): New Run page rendered headlessly (Playwright against a
  throwaway container on the patched source, then again against the deployed container) — **0 elements
  carry `.mode-panel`** and the DOM reads "New Run | Source mode | Select how to start the pipeline |
  Basic …", with the radio options, captions, RECOMMENDED badge and upload form unchanged. Run-visibility
  fix tested directly: `run_config.json` exists the moment `start_pipeline` returns and `list_runs()`
  reports the new run immediately (previously it appeared only once the orchestrator had booted).
  Deploy gates all passed: no `mode-panel` refs, early `run_config` write present, keyed `run_selector`
  present, `isParDocumentLabel`=2, 0 `Sec-Fetch` header keys, PowerTOST loads, Streamlit health 200.
- 6.5 LIVE (2026-10-05, `mri:v24-powertost-fix`): build-time assertion printed
  `R deps OK — PowerTOST 1.5.7 CVfromCI: 0.1929871`; image reports PowerTOST 1.5.7 / mvtnorm 1.1.3 /
  cubature 2.0.4.6. The **real** chain `Rscript CVw_Screening_v03.R /data/uploads/cvw_smoke.csv <out>`
  (5-study fixture, AUC+Cmax) returns valid JSON — per-study `CVw_calc` 20-25% with `N-Pwr80%`/`N-Pwr90%`
  plus the pooled block — both in the image and in the deployed container. The identical command errors
  with "there is no package called 'mvtnorm'" on v23, so this is a confirmed before/after. (The
  "sigma based on pe & lower CL more than 10% different" warnings come from the intentionally asymmetric
  CIs in the synthetic fixture, not from the code.) PAR download re-verified after the v24 cutover:
  `AT/H/1569/001` → 1 PAR, `AT/H/1561/005` → 0.
- 6.1-6.4 LIVE (2026-10-05, gluetun exit Riga/LV): PAR stage verified at four levels against the live
  portal with the 2-product fixture `/data/uploads/par_fix_test.xlsx` — (1) patched scripts mounted into a
  throwaway container, (2) patched row-scoped selection, (3) the baked `mri:v23-par-dom-fix` image with no
  mount, (4) inside the deployed production container. Every level: `AT/H/1569/001` → "Found 4 document(s),
  1 PAR/sPAR" → `PAR_AT_H_1569_001_003_barrierefrei.pdf` (174,061 B, valid `%PDF`, 10 pages, "Public
  Assessment Report / Scientific discussion"); `AT/H/1561/005` → "Found 3 document(s), 0 PAR/sPAR" → 0 PARs
  (genuine: it has only SPC/PL/Labelling). Document counts dropped 5→4 and 4→3, confirming the toolbar
  "Download excel" button is no longer swept into the scan. A 2-product run now takes ~41s instead of
  burning a 20s dead timeout per product.
- 6.3 `isParDocumentLabel` discriminator: 12/12 cases pass — PubAR and sPAR variants match; SPC / PL /
  Labelling / the `PRODUCT | archive Download excel` toolbar row do not; `Paracetamol_500mg_SmPC` and
  `Parecoxib_SmPC` correctly rejected (word-boundary match, so product names starting with "par" are safe).
- 6.5 R regression bounded: `library(PowerTOST)` loads in `mri:v21` (has `mvtnorm`, `cubature`, `Rcpp`) and
  fails identically in `mri:v22-portal-resilience-20260804-r2`, the pre-deploy live container, and
  `mri:v23-par-dom-fix` — i.e. pre-existing since the v22 build, not introduced by this fix.
- 5.4/5.7 CVw_Screening_v03.R + wrapper: CVfromCI/sampleN.TOST/CVpooled verified on host (R 4.4.3); per-study CVw calc from CI, reported-vs-calc cross-check, pooled CVw + pooled N by PK; UI records→study_from_row→screening path tested (Pool flag toggles pooling correctly).
- 5.2/5.3: tracker_stats + is_running unit-tested (terminal status → not-running; with_pars/empty/sources correct).
- 5.5: SWE link extraction unit-tested (English PAR prioritised, portal-internal links excluded).
- 5.8/5.9 LIVE (2026-07-01, mri:v21, gluetun exit BE/EU): Melatonin basic run (122 products). Core stage downloaded 113/122 then hit the pre-existing exit-code-3 portal block during straggler retries (not a v21 bug; no auto VPN rotation yet). Targeted 4-product SE-only run (SE/H/1592/001, SE/H/2048/001/004/005) reached the PAR stage cleanly: correctly detected RMS=SE, ran swe_agency scanner (broad `a[href]` host filter), correctly skipped the mri-product-details Excel — but "Found 0 candidate agency link(s)" on every SE product page → 0 PARs. first conclusion (from logs) was "portal exposes no links" — CORRECTED by DOM probe below. v21 SWE code degrades gracefully (0 PARs, no crash).
- 5.9 DOM PROBE (2026-07-01, scripts/probe_swe_dom_v1.js on SE/H/2048/001, live): page has 11 anchors (0 agency) BUT 4 `open_in_new` mat-icon buttons; one carries tooltip "External link: https://www.lakemedelsverket.se/sv/sok-lakemedelsfakta/lakemedel/20170420000035". So agency links ARE present, rendered as Material buttons with the URL in a `cdk-describedby-message` tooltip (aria-describedby) + JS click — NOT `<a href>`. ROOT CAUSE of 0-PARs = `extractAgencyParLinks` only scans `a[href]`. Fix = read Material external-link tooltips (TODO 5.11). Caveat: tooltip URL is a lakemedelsverket facts page (intermediate), so a 2nd hop to the actual PAR PDF is likely needed. Saved: /data/runs/_probe/probe_SE_H_2048_001.{json,html}.
- 5.6: aggregation tested on synthetic (dedup, GMR/CI normalisation, pooled CV) + real ketoprofen (empty-CV → 0 studies, no crash).

## LOG

### 2026-10-07
{vmi1967850; Claude Opus 5.5; 2026-10-07_1130} v26 — run scope switch + per-session PAR batch limit (deployed)
- User request: (1) New Run switch "Full run" / "Core base generation only" (default Full run); (2) user-chosen
  limit on successfully downloaded independent PAR PDFs per session (default unlimited), resumable for the
  next batch; (3) backup current version for easy rollback.
- Backup: git tag `v25-stable` (7e4c549), image `mri:v25-stable-rollback` (29de6bc), source tarball
  `~/AI/MRI_backups/mri_v25-stable_7e4c549_20261007.tar.gz`. See "Rollback (v26 → v25)".
- "Independent" implemented as distinct by content (SHA-256): the portal serves the same PAR for every
  strength of a procedure (often under different filenames, e.g. `_DC.pdf` vs `_DC_2.pdf`), so counting
  files would burn the budget on duplicates. Duplicates are still saved per product, just not counted.
- Limit is exact: checked before every PDF; a product interrupted mid-way stays `pending` and is redone next
  session (already-known PDFs are not recounted).
- Commit 5acb75f on branch v26-par-batches. Image `mri:v26-par-batches` (130f54e1e896) deployed live via
  docker run (docker-mri:latest retagged in step). Not pushed yet.

### 2026-10-05
{vmi1967850; Claude Opus 5; 2026-10-05_1200} UI fixes (v25) — empty mode panel removed; Start Pipeline keeps its run
- Two user-reported behaviours on the New Run page (screenshot supplied via `~/AI/Screenshots`).
- (a) EMPTY BLUE BOX between the "New Run" title and the "Source mode" subtitle: `.mode-panel` was opened
  with `st.markdown('<div class="mode-panel">')` and closed by a *separate* `st.markdown('</div>')`.
  Streamlit renders each markdown call as its own element, so the div was emitted and closed on the spot —
  it never wrapped the radio and simply painted an empty bordered box. Removed the wrapper and its CSS.
  The two descendant rules meant to enlarge the mode labels were scoped under `.mode-panel`, so they had
  never applied to anything; dropping them changes nothing on screen (user chose to leave the labels plain).
- (b) "Start Pipeline" DID NOT LAND ON THE NEW RUN. The tab was never the problem: Progress is already the
  first `st.tabs` entry, and Streamlit 1.60 has no API to select a tab anyway. The run itself was not
  selectable — `start_pipeline` wrote only a `pid`, while `list_runs()` skips any directory without a
  `run_config.json`, and that file is written later by the orchestrator once it boots. So the just-launched
  run was missing from the dashboard, `st.session_state.pop("selected_run")` discarded the request, and the
  view fell back to whichever run sorted first. `start_pipeline` now writes `run_config.json` itself before
  spawning the orchestrator (which rewrites it with authoritative values), and Home keeps the request in
  session state until the run actually appears.
- Also fixed while in there: the run selector was driven by `index` with no `key`. Home re-runs every 3s
  while a pipeline is active, and a changing `index` rebuilds the widget — which snapped the dashboard back
  to the first run mid-run. It now holds its value under `key="run_selector"`.
- VERIFIED then DEPLOYED behind gates (no `mode-panel` refs, early `run_config` write, keyed selector, PAR
  fix intact, 0 `Sec-Fetch` keys, PowerTOST loads, Streamlit 200): built `mri:v25-ui-fixes` (29de6bc0139b),
  recreated the live container, healthy. Post-deploy render of the live page confirms 0 `.mode-panel`
  elements. `docker-mri:latest` retagged to v25. Commit `33aa049` pushed.
  ROLLBACK: `docker tag mri:v24-powertost-fix docker-mri:latest && docker rm -f mri` then the same
  `docker run` with image `mri:v24-powertost-fix`.

{vmi1967850; Claude Opus 5; 2026-10-05_1100} PowerTOST/CVw restored (v24) — PPM stopped shipping R 4.2 binaries
- Fixed TODO 6.5, the pre-existing breakage found while diagnosing the PAR bug: `library(PowerTOST)` had
  been failing since the 2026-08-04 image, so the Sample Size / CVw screening tab was dead.
- ROOT CAUSE (not an R upgrade — R is 4.2.2 Patched in both v21 and v23): Posit Package Manager no longer
  publishes bookworm/R-4.2 *binaries*. `available.packages()` now returns `src/contrib` for mvtnorm,
  cubature, Rcpp and PowerTOST on every snapshot tried (latest, 2026-07-01, 2026-06-01, 2026-03-01), and
  `getOption("pkgType")` is `source`. The image has no gfortran/C++ toolchain by design, so those three
  compiled packages failed to build — and `install.packages()` only warns, so the August build shipped a
  silently broken image. Adding the assertion made this reproduce immediately as a hard build failure.
- FIX: compiled deps now come from Debian bookworm main, which packages them prebuilt against R 4.2.2 —
  `r-cran-mvtnorm` 1.1-3, `r-cran-cubature` 2.0.4.6, `r-cran-rcpp` 1.0.10, `r-cran-jsonlite` 1.8.4 — so
  the no-toolchain/fast-build design is preserved (apt is pinned to the Debian 20260316Z snapshot). Only
  PowerTOST (`NeedsCompilation=no`) is still installed from source. Kept the build-time assertion that all
  four load and `CVfromCI` computes, so a partial install can never ship quietly again.
- VERIFIED then DEPLOYED behind hard gates (PowerTOST loads + real CVw chain emits a pooled result + the
  v23 PAR fix still baked): built `mri:v24-powertost-fix` (5af2a6c462da), recreated the live container,
  healthy, Streamlit 200. Post-deploy in production: CVw chain returns per-study CVw 20-25% with N at 80/90%
  power plus the pooled block, and `AT/H/1569/001` still downloads its PAR (AT/H/1561/005 → 0).
  `docker-mri:latest` retagged to v24. Smoke fixtures kept: `/data/uploads/par_fix_test.xlsx`,
  `/data/uploads/cvw_smoke.csv`.
  ROLLBACK: `docker tag mri:v23-par-dom-fix docker-mri:latest && docker rm -f mri` then the same
  `docker run` with image `mri:v23-par-dom-fix` (PAR fix present, Sample Size still broken).
- An earlier gate run failed on a bad bind-mount in my own shell command, not the image; the gate
  correctly refused to deploy and production stayed on v23 throughout.

{vmi1967850; Claude Opus 5; 2026-10-05_1020} PAR downloads restored (v23) — portal header trap + toolbar mis-selection
- SYMPTOM: mri.clindevdep.com downloaded 0 PAR PDFs in every recent run. Rivaroxaban (2026-10-02, 614
  products) reported "Completed: 614, Failed: 0, Total PAR documents: 0" and exited 0; each product logged
  "Documents tab not immediately visible" → "Documents tab not found". Same signature in Ketoconazole
  (09-29), Bilastine (09-22), Pancreatine (08-10), LisDexAmfetamine (08-03). Regression window pinned by
  PDF counts per run: last success 2026-07-02 (MelSE4fix, 4 PDFs), first zero 2026-08-03 — i.e. it predates
  the v22 deploy, so it is the portal's change, not a v22 regression.
- RULED OUT: portal blocking (no 403/Access Denied, no exit code 3, 0 failures), geo-restriction (gluetun
  exit was Riga/LV = EU), core stage (614 products merged fine via v22's `portal_api_rebuilt_excel`), and
  code drift (container `process_molecule_v10.js` md5-identical to the host source).
- ROOT CAUSE: `createSoloIDBrowser` set context-level `extraHTTPHeaders` containing navigation-only values
  (`Sec-Fetch-Dest: document`, `Sec-Fetch-Mode: navigate`, `Sec-Fetch-Site: none`,
  `Upgrade-Insecure-Requests`, HTML-only `Accept`). Context headers apply to EVERY request, so the
  rewritten Angular portal could not fetch its own modules/OData calls and stayed on the loading spinner
  (`console: ERR_INVALID_ARGUMENT`; DOM had 0 anchors, 0 mat-icons). `text=Documents` therefore matched
  nothing and the stage recorded "completed, 0 PARs". Proven by probing the same product with a plain
  context: ProductSearch fires, 11 anchors, 5 archive icons, all 5 documents download as valid PDFs.
  This is exactly the trap v22 hit and worked around for its own download context only.
- SECOND DEFECT (found by DOM probe): the attachment scan `mat-icon:has-text("archive")` also matched the
  page toolbar's "Download excel" button, which serves no file — its click cost a 20s `waitForEvent`
  timeout on every product (~3.4h on a 614-product run) and was logged as a scary "Failed". Document rows
  are `mat-list-item`s labelled "<documentType> | <documentName>" (PARs typed `PubAR`), so the scan is now
  scoped to that list and only PAR/sPAR rows are clicked. Downloaded files are validated as `%PDF` instead
  of being filtered by filename, which also removes the latent "Paracetamol contains PAR" false positive.
- NOT a URL problem: the legacy `mri.cts-mrp.eu/portal/details?productnumber=…` redirects to
  `mri-production.cts-mrp.eu/details?productnumber=…` *preserving the query* and renders fine, so the
  navigation URL was left unchanged. (An earlier "path is dropped" reading was an artifact of the
  unrendered broken context.)
- The OData `Document(documentApiId='…')/Download` endpoint is NOT usable as a plain GET: the portal sends
  a custom `youdontownmev1` JWT and without it the server kills the stream (curl `http=000` / HTTP-2
  CANCEL / "socket hang up"); with the token it just returns the SPA shell. Hence the DOM click path, not
  an API rewrite. Diagnostics kept: `scripts/probe_docs_api_v{1,2,3}.js`, `probe_doc_rows_v1.js`,
  `probe_url_compare_v1.js`.
- DEPLOYED: built `mri:v23-par-dom-fix` (442f420d61c4; only the COPY layers rebuilt), smoke-tested
  (Streamlit health 200, patched code confirmed baked in), recreated the live `mri` container on it —
  healthy. Also retagged `docker-mri:latest` → v23: it was still pointing at v21 (535ec08), so a
  compose-driven recreate would have silently regressed the app by two versions.
  ROLLBACK: `docker tag mri:v22-portal-resilience-20260804-r2 docker-mri:latest && docker rm -f mri` then
  the same `docker run` with image `mri:v22-portal-resilience-20260804-r2`.
- Committed `2e5c370` on `v21-swe-pk`. NOT yet pushed (that commit plus August's `568ae61` are both ahead
  of `origin/v21-swe-pk`).
- FOUND, NOT FIXED (TODO 6.5): `mvtnorm` + `cubature` are missing from the v22/v23 images so
  `library(PowerTOST)` fails — Sample Size / CVw screening has been broken since the 2026-08-04 image.
  `mri:v21` still has them, so the August R-layer rebuild lost them silently (no verification in the
  Dockerfile). The PAR stage does not use R, so this did not block the deploy.

### 2026-08-04
{$clindevdep-T470; Claude; 2026-08-04_1548} context purge
- Event: context purge after preserving v21, implementing and deploying v22 portal-client Excel reconstruction, and correcting the r1 request-header defect in r2.
- Completed: archived 34 historical searches with checksum; preserved original source/image; unit and live VPN-routed tests passed; deployed healthy `mri:v22-portal-resilience-20260804-r2`; LisDexAmfetamine resumed and began downloading via `portal_api_rebuilt_excel`.
- Remaining: monitor active LisDexAmfetamine through pipeline completion; full end-to-end workflow test; automatic EU-safe Gluetun VPN rotation; optional VLM PDF-digest extraction.
- Memory note: `/home/clindevdep/.claude/projects/-home-clindevdep-AI-MRI_v22_portal_resilience_20260804/memory/purge_resume_20260804.md`
- Git: local commit `5540d43` created on `v21-swe-pk`; push is pending because the SSH key was denied and the GitHub CLI token is invalid.

### 2026-08-04
{clindevdep-T470; Codex; 2026-08-04_1528} v22 portal-client Excel export resilience
- Preserved v21 source separately at `/home/clindevdep/AI/MRI_preserved_20260804` and tagged the running image as `mri:preserved-20260804`; the live service was not changed.
- Exported all 34 historical `search_results.json` files from the persistent data volume to `/home/clindevdep/AI/MRI_search_exports/20260804_pre_v22/search_results_all_runs.tar.gz`, with manifest and SHA-256 checksum.
- Root cause: the MRI portal's current **Download as excel file** action is no longer a server-side file download. Its Angular client fetches expanded `ProductSearch` OData JSON, creates an XLSX locally with SheetJS, and clicks a Blob URL. Waiting for Playwright's `download` event therefore times out even though the product page/API remain available.
- v22 adds `download_and_merge_products_v22.js`: it captures the authenticated browser `ProductSearch` response while loading each details page, reproduces the portal's 20-column workbook with ExcelJS, and validates the saved workbook before marking it complete. The old download-event route remains only as a 15-second fallback, with ZIP-signature validation; the unsafe HTML-as-XLSX request fallback is removed.
- Verification: unit tests passed (row mapping and readable XLSX). A real VPN-routed one-product test for `SE/H/2822/004` completed via `portal_api_rebuilt_excel`, then successfully merged a valid 20-column core workbook.
- v22 workspace: `/home/clindevdep/AI/MRI_v22_portal_resilience_20260804`. Its code is tested separately and it is ready for a clean, separately tagged image build before any optional deployment; no active container, app volume, or preserved source was modified.

### 2026-03-24
{clindevdep-T470; Claude; 2026-03-24_0700} Project initialization
- Created project structure at ~/AI/MRI/
- Source: MRI_Jan2026 CLI tool (RUN.sh orchestrating Node.js + Python scripts)
- Plan: Backend first → WebUI → Hub integration
- All traffic through Gluetun VPN container

{clindevdep-T470; Claude; 2026-03-24_0730} Backend scaffolding complete
- package.json (Node.js ESM: playwright, stealth plugins, exceljs, dotenv, zod)
- pyproject.toml (Python: streamlit, pandas, openpyxl, pypdf, lxml, pdfplumber)
- Copied 6 scripts from MRI_Oct2025 into scripts/
- Patched: removed hardcoded dotenv paths, added --single-process Chromium flag
- Dockerfile: node:22-bookworm-slim + Python 3.12 + uv + Playwright Chromium
- orchestrator.py: Python replacement for RUN.sh (3-step pipeline with status.json)
- Docker Compose: mri.yml with network_mode: "service:gluetun"
- Gluetun: added port 8502:8502
- Master compose: added mri.yml include
- Created /home/clindevdep/docker/appdata/mri/ for persistent data

{clindevdep-T470; Claude; 2026-03-24_0800} VPN rotation research
- Gluetun has control server API on port 8000 (accessible from MRI container at localhost:8000)
- Can trigger server rotation: stop VPN → auto-heal reconnects to different random server
- No direct "switch to country X" API — picks randomly from SERVER_COUNTRIES/SERVER_CITIES pool
- **Geo-restriction concern:** MRI portal (mri.cts-mrp.eu) may reject non-EU exit IPs — must test before configuring server pool
- Planned for future update (Stage 4) — currently exit-on-block behavior preserved
- User will continue from different computer for docker build/test

{clindevdep-T470; Claude; 2026-03-24_1400} v20 alignment — scripts and orchestrator updated
- Compared current scripts (from MRI_Oct2025) with RUN_v20.sh template (MRI_Mar2026)
- Identified 10 major gaps: missing tracker, no retry, wrong output paths, missing modes, etc.
- Created `scripts/download_and_merge_products_v20.js`:
  - core_download_tracker.json for per-product status tracking
  - Resume support (skips completed products)
  - Diagnostics: HTML/screenshot/JSON per failure in core_debug_v20/
  - Fallback download via context.request.get()
  - Exit code 3 for portal blocking
- Updated `scripts/process_molecule_v10.js`:
  - Added --core, --molecule, --max flag parsing (+ legacy positional args)
  - Added download_tracker.json for PAR tracking with resume
  - Added portal blocking detection (exit code 3)
  - Flexible column detection in core DB reader
- Fixed `scripts/src/search_molecule_stealth_v14.js`:
  - Output now saves to cwd/search_results.json (was outputs/{molecule}/)
  - Removed hardcoded Surfshark VPN and IP references
  - Proxy default standardized to disabled (VPN provides rotation)
- Fixed `scripts/download_and_merge_products.js`: proxy default to disabled
- Rewrote `src/mri_app/orchestrator.py` (v20):
  - Three source modes: automatic, basic, full (+ resume)
  - convert_basic_to_json() for Mode B (basic MRI export)
  - Auto-retry with stagnation detection for both core and PAR stages
  - Tracker archiving for fresh starts
  - PAR collection folder (flat PDFs for NotebookLM)
  - Run report generation
  - Enhanced status.json with detail field for Streamlit

{clindevdep-T470; Claude; 2026-03-24_1500} Stage 2: Streamlit WebUI
- Created .streamlit/config.toml (port 8502, theme, no CORS)
- Created core modules:
  - config.py: DATA_DIR/RUNS_DIR/UPLOADS_DIR paths
  - runner.py: subprocess launcher, PID tracking, list_runs()
  - tracker.py: status.json/tracker polling, log tail reader
- Created 4 pages:
  - 1_New_Run.py: mode selection (basic/automatic/full), file upload, molecule input, Start
  - 2_Progress.py: live status bar, core/PAR tracker stats, log output, auto-refresh
  - 3_Results.py: BE CSV table, PAR file browser with downloads, database preview
  - 4_History.py: all runs with status icons, Resume button for failed runs
- app.py: home page with quick status metrics
- Updated Dockerfile: CMD → streamlit run, PYTHONPATH, .streamlit/ copy
- Docker build + health check verified (HTTP 200 on / and /_stcore/health)


### 2026-03-28
{vmi1967850; Codex; 2026-03-28_1735} Live run v012_Apix investigated after tracker count mismatch
- Verified successful completion of run v012_Apix_20260328_153108
- Observed count mismatch: core tracker reported 245 products, while PAR tracker reported 227 products
- Confirmed search_results.json and core_download_tracker.json both contained 245 procedure codes
- Confirmed merge step logged Successfully downloaded: 245 files and Merged 227 files into 227 total rows
- Confirmed PAR stage reads products from the merged core database file v012_Apix_core_database.xlsx, not from the original 245-item search result list
- Identified exact gap: 18 procedure codes were present in core_download_tracker.json but absent from the merged core database and therefore absent from download_tracker.json
- Confirmed all 18 missing items had downloaded files in core_downloads, but those files were HTML payloads saved with .xlsx extensions rather than valid Excel workbooks
- Merge log showed Excel file format cannot be determined for those 18 files, so they were excluded from the merged core database
- Conclusion: core stage currently counts fallback-downloaded HTML-as-.xlsx files as successful downloads, while PAR stage only sees rows that survive Excel merge and parsing
- Impact on v012_Apix: 245 core download successes, 227 mergeable core database rows, 227 PAR-stage products, 0 PAR tracker failures
- Follow-up candidate: tighten core downloader validation so fallback outputs are verified as real Excel files before being marked completed, or log them as invalid core artifacts explicitly


{vmi1967850; Codex; 2026-03-28_1745} Results page extended with zip downloads; WebUI lifecycle clarified
- Re-checked project log: original Stage 2 WebUI intent was a persistent dashboard with results browsing and downloads, not a one-shot job UI that exits after a run
- Confirmed live container behavior matches that design: the Streamlit WebUI stays up as the long-running service, while pipeline runs execute as background subprocesses and finish independently
- Added cached zip archive support for completed runs via new mri_app/downloads.py helper
- Added Results page download buttons for Output Folder (.zip), PAR Collection (.zip), and Full Run Bundle (.zip)
- Added configurable MRI_DATA_DIR path handling in config.py so archive generation can be exercised against the host data volume outside the container when needed
- Verified archive generation against completed run v012_Apix_20260328_153108
- Hot-patched the live mri container by copying the updated UI files into /app/src/mri_app and keeping the health check green
- Created and verified example archives under /data/archives, including v012_Apix_output_live_check.zip (~51 MB)


{vmi1967850; Codex; 2026-03-28_1752} Results page simplified to a single bundle download
- Simplified the Results page UX from multiple zip archive buttons to one primary Download All Results (.zip) button
- The single button now packages the full run directory as one archive so users do not need to choose between output folder, PAR collection, or run bundle variants
- Kept preview sections for bioequivalence data, PAR listings, database preview, and run report, but removed secondary archive choices to reduce confusion
- Hot-patched the live mri container with the simplified Results page and kept the Streamlit health check green


{vmi1967850; Claude Opus 4.7; 2026-05-27_1455} Fixed StreamlitPageNotFoundError + context purge
- Bug: clicking Start Pipeline on New Run raised `StreamlitPageNotFoundError: Could not find page: pages/2_Progress.py`
- Root cause: stale container image — `1_New_Run.py` baked into image still referenced the old page name `pages/2_Progress.py`, but pages had been renamed (Progress → Current_Session → Session) without updating the page_link/switch_page calls in the image
- Host source was already correct (1_New_Run.py:144 references `pages/2_Session.py`), but uncommitted
- Committed all pending changes as 1b7725b "Rename pages: 2_Progress→2_Session, 4_History→3_History; remove 3_Results"
- Pushed to origin/main via HTTPS + `gh auth token` (SSH deploy key bound to System repo only)
- Rebuilt docker-mri image (DOCKER_HOST=unix:///var/run/docker.sock — Deployrr socket-proxy not reachable from agent shell)
- Recreated mri container; verified Streamlit serves with 1_New_Run.py + 2_Session.py + 3_History.py
- Context purge: memory note at /home/clindevdep/.claude/projects/-home-clindevdep-AI/memory/purge_resume_20260527.md
- Pending TODO: user retest of the Posaconazole pipeline Start Pipeline flow

{vmi1967850; Claude Opus 4.8; 2026-07-01_1447} v21 feature work — SWE PARs, PK aggregation, sample size
- Branch `v21-swe-pk` off `v20-stable` (e32669b); image `mri:v20` retained for instant rollback.
- App now opens on the Progress tab: folded the Session dashboard into Home.py (Progress tab first), deleted pages/2_Session.py, repointed switch_page refs to Home.py.
- Correct progress evaluation: tracker.py tracker_stats now source-aware (with_pars/empty/processed/sources); Home progress bar is composite (core+PAR+extraction weighted).
- Fixed stuck top-right "running" spinner: runner.py is_running() short-circuits to False on terminal status.json (complete/failed/blocked) — authoritative over PID/zombie state.
- Sample size: user supplied CVw_Screening_v02.R (Jirka's CVfromCI+sampleN.TOST+CVpooled). Adapted to runnable CVw_Screening_v03.R (no setwd, arg-driven input CSV/out dir, JSON stdout, adds pooled-N-from-pooled-CVw + reported-vs-calculated CVw cross-check). Wrapped by src/mri_app/sample_size.py; Sample Size tab shows pooled CVw/N per PK + per-study cross-check. aggregate_pk_data.py now emits _CVw_Screening.csv in the defined column format and keeps rows with CI+N even when no CV was reported. Dockerfile installs R via r-base-core + Posit Package Manager *binary* packages (bookworm) for jsonlite/mvtnorm/cubature/PowerTOST — precompiled, so NO gfortran/C++ toolchain and fast build (verified in a throwaway node:22-bookworm-slim container: installs as *binary*, CVfromCI works, no compiler present).
- SWE agency: scripts/src/swe_agency_v1.js follows outbound docetp.mpa.se/Läkemedelsverket PAR links from the MRI portal page for RMS=SE procedures (prefix of procedure_code); wired into process_molecule_v10.js with entry.source/entry.rms tracking + fallback to MRI-portal archive icons.
- PK aggregation: scripts/src/aggregate_pk_data.py normalises the BE csv → _pk_studies.csv + _pk_summary.json (per-param pooled/median/max CV); orchestrator Step 3b; selectable Results table feeds the Sample Size tab.
- All changes unit-tested on host (R 4.4.3 + PowerTOST + jsonlite present). NOT yet built/deployed — pending user R script + build approval + live Melatonin SWE test.
- Plan: /home/clindevdep/.claude/plans/validated-drifting-tide.md

{vmi1967850; Claude Opus 4.8; 2026-07-01_1546} context purge
- Event: context purge before building/deploying mri:v21.
- Completed: all v21 code on branch v21-swe-pk (start-on-Progress, source-aware progress + stuck-spinner fix, SWE agency docetp link-following, PK aggregation + _CVw_Screening.csv, CVw_Screening_v03.R integration of user's v02 with sample_size.py + Sample Size tab). R install solved without Fortran via Posit PPM bookworm binaries (r-base-core). All host-tested; not yet built/deployed.
- Remaining: build mri:v21 → smoke-test → cut over from mri:v20 → live Melatonin SWE verify (docetp link-render unconfirmed; fallback needs docker exec which sandbox gated) → commit/push.
- Memory note: /home/clindevdep/.claude/projects/-home-clindevdep-AI/memory/purge_resume_20260701.md

{vmi1967850; Claude Opus 4.8; 2026-07-01_1700} Built + deployed mri:v21; live SWE finding
- BUILD: `mri:v21` (2.11GB) built via DOCKER_HOST=unix:///var/run/docker.sock. R + PowerTOST installed as Posit PPM *binaries* — confirmed no Fortran/C++ toolchain, fast build.
- SMOKE (throwaway container, port 18502): Streamlit health ok, root 200, Rscript+PowerTOST load (R 4.2.2), full Python→R CVw sample-size chain OK (pooled CVw 16.6%, N=14@80%/18@90%), app opens on Progress tab. Container removed after.
- CUTOVER: retagged docker-mri:latest → mri:v21 (mri:v20 tag + v20-stable git tag preserved for rollback); recreated live `mri` container via `docker run` (network container:gluetun, mount /data, TZ/ENABLE_PROXY env, compose grouping labels) — NOT via compose because master-stack env interpolation needs the transient /tmp/docker-build.env (gone). No Traefik labels on the container (routing is external file-provider). Live container healthy on v21, R present.
  - ROLLBACK: `docker tag mri:v20 docker-mri:latest && docker rm -f mri && docker run …` (same run cmd, image docker-mri:latest=v20).
- LIVE TEST (gluetun exit BE/EU): Melatonin basic run 122 products → core got 113/122 then pre-existing exit-code-3 portal block on straggler retries (no auto VPN rotation; NOT a v21 regression). Targeted 4-product SE-only run reached PAR stage cleanly: RMS=SE detected, swe_agency scanner ran, Excel metadata correctly skipped, but "Found 0 candidate agency link(s)" → 0 PARs. FINDING: MRI portal does not expose docetp.mpa.se links for these SE products → SWE needs a docetp on-site search fallback (TODO 5.11). Note: `docker exec` into mri worked fine this session (earlier sandbox-block note did not apply).
- gluetun SERVER_COUNTRIES is EMPTY (provider surfshark) → a VPN rotation could land non-EU (docetp 403s non-EU) — must set EU pool before relying on rotation (relates to TODO 4.2). Control API returns Unauthorized (token required).
- PENDING: commit/push v21-swe-pk; decide on docetp search fallback (5.11); optional live DOM-capture probe to 100% confirm link-absence vs selector.

{vmi1967850; Claude Opus 4.8; 2026-07-02_1420} SWE PAR download FIXED + live-verified
- Two DOM probes nailed the chain: MRI portal renders the SWE agency link as an Angular-Material `open_in_new` button with the URL in a `cdk-describedby` tooltip (not `<a href>`) → old `a[href]` scanner saw 0. Tooltip → `lakemedelsverket.se/sok-lakemedelsfakta` facts page, which lists the docetp.mpa.se PAR/sPAR PDFs as PLAIN anchors.
- Fix (swe_agency_v1.js): `extractAgencyLandingLinks()` (reads Material tooltip URLs) + `collectSwedishAgencyPARs()` (2-hop: portal tooltip → facts page → docetp PDFs, filtered to PAR/sPAR only, English first, cookie dismissal). Wired process_molecule_v10.js SE branch to it. Added scripts/probe_facts_v1.js.
- LIVE (mri:v21, hot-patched scripts, gluetun BE/EU): SE4 export → SE/H/2048/001/004/005 each downloaded ENG PAR (253KB) + ENG sPAR (29KB) valid %PDFs (6 total, 2 unique). SE/H/1592/001 → 0 (genuine: no open_in_new/agency ref on its portal page).
- Committed 1821f10 + pushed v21-swe-pk. Rebuilt mri:v21 (535ec08) with the fix baked in and REDEPLOYED (retag docker-mri:latest → 535ec08, recreate container) — live container healthy, fix baked (not hot-patched), durable across restarts. Rollback mri:v20 (81f940) intact.
- Remaining (unchanged, pre-existing): a full 122-product run still needs VPN rotation to clear the core-stage exit-code-3 block (Stage 4, unbuilt); targeted SE runs work. gluetun SERVER_COUNTRIES empty → set EU pool before relying on rotation.

{clindevdep-T470; Claude; 2026-07-02_1541} context purge
- Event: context purge after completing all v21 goals.
- Completed: mri:v21 built + deployed durably (535ec08); SWE agency PAR download FIXED and LIVE-VERIFIED (2-hop portal Material-tooltip → lakemedelsverket facts page → docetp PAR/sPAR PDFs via new collectSwedishAgencyPARs()); SE/H/2048/001/004/005 download ENG PAR+sPAR; rollback mri:v20 intact; all pushed to v21-swe-pk.
- Remaining (all optional): full-run VPN rotation (Stage 4) + gluetun EU SERVER_COUNTRIES for the core-stage block; 5.10 VLM PK extraction; merge v21-swe-pk → main + tag v21 release.
- Memory note: /home/clindevdep/.claude/projects/-home-clindevdep-AI/memory/purge_resume_20260702.md

{clindevdep-T470; Claude; 2026-06-04_0930} context purge
- Completed: Investigated and fixed Betahistine run being stuck and showing 0 downloads. Resolved zombie process handling in runner.py, folder renaming tracking in tracker.py, and fallback validation in download_and_merge_products_v20.js. Hot-patched container.
- Remaining TODO: Run end-to-end workflow tests with real data, integrate Gluetun API for automated VPN rotation.
- Memory Note: /home/clindevdep/.claude/projects/-home-clindevdep-AI/memory/purge_resume_20260604.md
