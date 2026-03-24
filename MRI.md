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

## Architecture
- **Container:** Docker (node:22-bookworm-slim + Python 3.12 + uv + Playwright Chromium)
- **VPN:** All traffic routed through Gluetun (`network_mode: "service:gluetun"`)
- **Port:** 8502 (exposed on Gluetun container)
- **Subdomain:** mri.clindevdep.com (Traefik + OAuth)
- **Data:** Persistent volume at `/home/clindevdep/docker/appdata/mri/`

## Pipeline (from MRI_Jan2026)
1. **Core DB acquisition** — search MRI portal OR manual Excel upload → product metadata
2. **PAR download** — Playwright stealth browsers with Solo ID fingerprinting → PDF documents
3. **BE extraction** — pdfplumber parses PDFs → bioequivalence CSV

## TODO

### Stage 1: Backend (Docker + Pipeline)
- [x] 1.1 Project scaffolding, git init, GitHub repo
- [x] 1.2 package.json + pyproject.toml
- [x] 1.3 Copy & patch JS scripts from MRI_Oct2025
- [x] 1.4 Dockerfile (multi-runtime)
- [x] 1.5 orchestrator.py (Python replacement for RUN.sh)
- [x] 1.6 Docker Compose + Gluetun routing
- [ ] 1.7 Build & test backend container

### Stage 2: WebUI (Streamlit)
- [ ] 2.1 Streamlit skeleton (multi-tab app)
- [ ] 2.2 Core modules (runner.py, tracker.py, config.py)
- [ ] 2.3 Search page
- [ ] 2.4 Downloads page (live progress)
- [ ] 2.5 Results page (browse PARs + CSV)
- [ ] 2.6 History page
- [ ] 2.7 Test full workflow

### Stage 3: Hub Integration
- [ ] 3.1 Traefik rule (app-mri.yml)
- [ ] 3.2 Glance widget
- [ ] 3.3 Cloudflare DNS
- [ ] 3.4 Final end-to-end test

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
