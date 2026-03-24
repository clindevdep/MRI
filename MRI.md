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

## Test Results
_(will be populated as tests are run)_

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
