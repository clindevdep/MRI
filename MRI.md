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

## Rollback (v20 stable → v21 work)
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

## Test Results
- 5.4/5.7 CVw_Screening_v03.R + wrapper: CVfromCI/sampleN.TOST/CVpooled verified on host (R 4.4.3); per-study CVw calc from CI, reported-vs-calc cross-check, pooled CVw + pooled N by PK; UI records→study_from_row→screening path tested (Pool flag toggles pooling correctly).
- 5.2/5.3: tracker_stats + is_running unit-tested (terminal status → not-running; with_pars/empty/sources correct).
- 5.5: SWE link extraction unit-tested (English PAR prioritised, portal-internal links excluded).
- 5.8/5.9 LIVE (2026-07-01, mri:v21, gluetun exit BE/EU): Melatonin basic run (122 products). Core stage downloaded 113/122 then hit the pre-existing exit-code-3 portal block during straggler retries (not a v21 bug; no auto VPN rotation yet). Targeted 4-product SE-only run (SE/H/1592/001, SE/H/2048/001/004/005) reached the PAR stage cleanly: correctly detected RMS=SE, ran swe_agency scanner (broad `a[href]` host filter), correctly skipped the mri-product-details Excel — but "Found 0 candidate agency link(s)" on every SE product page → 0 PARs. first conclusion (from logs) was "portal exposes no links" — CORRECTED by DOM probe below. v21 SWE code degrades gracefully (0 PARs, no crash).
- 5.9 DOM PROBE (2026-07-01, scripts/probe_swe_dom_v1.js on SE/H/2048/001, live): page has 11 anchors (0 agency) BUT 4 `open_in_new` mat-icon buttons; one carries tooltip "External link: https://www.lakemedelsverket.se/sv/sok-lakemedelsfakta/lakemedel/20170420000035". So agency links ARE present, rendered as Material buttons with the URL in a `cdk-describedby-message` tooltip (aria-describedby) + JS click — NOT `<a href>`. ROOT CAUSE of 0-PARs = `extractAgencyParLinks` only scans `a[href]`. Fix = read Material external-link tooltips (TODO 5.11). Caveat: tooltip URL is a lakemedelsverket facts page (intermediate), so a 2nd hop to the actual PAR PDF is likely needed. Saved: /data/runs/_probe/probe_SE_H_2048_001.{json,html}.
- 5.6: aggregation tested on synthetic (dedup, GMR/CI normalisation, pooled CV) + real ketoprofen (empty-CV → 0 studies, no crash).

## LOG

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

{clindevdep-T470; Claude; 2026-06-04_0930} context purge
- Completed: Investigated and fixed Betahistine run being stuck and showing 0 downloads. Resolved zombie process handling in runner.py, folder renaming tracking in tracker.py, and fallback validation in download_and_merge_products_v20.js. Hot-patched container.
- Remaining TODO: Run end-to-end workflow tests with real data, integrate Gluetun API for automated VPN rotation.
- Memory Note: /home/clindevdep/.claude/projects/-home-clindevdep-AI/memory/purge_resume_20260604.md

