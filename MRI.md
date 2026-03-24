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
- [ ] 1.2 package.json + pyproject.toml
- [ ] 1.3 Copy & patch JS scripts from MRI_Oct2025
- [ ] 1.4 Dockerfile (multi-runtime)
- [ ] 1.5 orchestrator.py (Python replacement for RUN.sh)
- [ ] 1.6 Docker Compose + Gluetun routing
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

## Test Results
_(will be populated as tests are run)_

## LOG

### 2026-03-24
{clindevdep-T470; Claude; 2026-03-24_0700} Project initialization
- Created project structure at ~/AI/MRI/
- Source: MRI_Jan2026 CLI tool (RUN.sh orchestrating Node.js + Python scripts)
- Plan: Backend first → WebUI → Hub integration
- All traffic through Gluetun VPN container
