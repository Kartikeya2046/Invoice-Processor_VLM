# Agent Handoff — AI Document Extraction System
**Date:** June 22, 2026
**Repo:** https://github.com/Kartikeya2046/Invoice-Processor_VLM
**Branch:** `main`

---

## Project Overview

Enterprise pipeline that replaces an old OCR + Mistral approach with a VLM-based document extraction system. The system classifies, extracts, and validates fields from **Invoices** and **Bills of Entry (BOE)** using **Qwen2.5-VL-3B-Instruct (AWQ INT4)** served via vLLM, plus a hybrid rule-based + SLM validation layer, wired into an async Celery pipeline with webhook delivery.

**Stack:** FastAPI · PostgreSQL · Redis · Celery · vLLM (Qwen2.5-VL-3B AWQ INT4) · Docker Compose · Ollama (remote, Lightning AI)

---

## Build Plan — Final Status

| Phase | Title | Status |
|---|---|---|
| 1 | Infrastructure & scaffold | ✅ Complete |
| 2 | VLM integration (Qwen2.5-VL) | ✅ Complete |
| 3 | Invoice & BOE extractors | ✅ Complete |
| 5 | Validators & confidence scoring (hybrid rules + SLM) | ✅ Complete |
| 6 | FastAPI routes + Celery workers | ✅ Complete |
| 7 | Production hardening | ✅ Complete |
| 8 | Frontend | ⬜ Not started |
| 9 | Cloud deployment | ⬜ Not started |

---

## What Was Built — Phase by Phase

### Phase 1 — Infrastructure & Scaffold
- Docker Compose stack with 6 containers: `api`, `worker`, `postgres`, `redis`, `flower`, `vllm`
- PostgreSQL schema via `database/migrations/001_initial_schema.sql`
- FastAPI `api/main.py` with `/health` endpoint

### Phase 2 — VLM Integration
- `models/vlm_client.py` — HTTP client for vLLM OpenAI-compatible endpoint
- `classifiers/vlm_classifier/__init__.py` — classifies documents as `invoice` or `bill_of_entry`

### Phase 3 — Invoice & BOE Extractors
- `extractors/invoice/` — extracts: `invoice_number`, `invoice_date`, `supplier`, `quantity`, `unit_price`, `po_number`, `cgst`, `sgst`
- `extractors/bill_of_entry/` — extracts: `boe_number`, `boe_date`, `igst`, `cust_duty`, `sbcess`

### Phase 5 — Hybrid Validation
- Rule-based validators for each field type
- SLM validator via remote Ollama (Qwen2.5:3b on Lightning AI)
- Merge layer combining rule + SLM results
- Confidence scoring and `requires_review` flagging
- `validators/` directory

### Phase 6 — FastAPI Routes + Celery Workers
**Architecture:** `POST /documents` returns 202 immediately, dispatches `chain(extract_task, validate_task)`. On completion, `webhook_task` POSTs result to `callback_url` with exponential backoff retry.

**Components built:**
- `core/celery_app.py` — Celery app with explicit task imports
- `core/db.py` — shared `get_db_url()` and DB helpers
- `core/json_utils.py` — `ExtractionJSONEncoder` for `date`/`datetime`/`Decimal`
- `tasks/extract_task.py` — classify + extract via vLLM
- `tasks/validate_task.py` — rule + SLM validation
- `tasks/webhook_task.py` — delivers result to `callback_url`, retries on non-2xx
- `api/routes/documents.py` — all 4 routes
- `database/migrations/002_phase6_pipeline.sql` — adds pipeline columns to `documents`

**Routes:**
- `POST /documents` — submit document
- `GET /documents/review` — review queue
- `GET /documents/{document_id}` — full detail
- `GET /documents/{document_id}/status` — status polling

### Phase 7 — Production Hardening
- `core/auth.py` — API key auth via `X-API-Key` header
- `~/on_start.sh` on Lightning AI — auto-installs Ollama and binds to `0.0.0.0:11434` on every session start
- `docker-compose.yml` — fixed `SLM_ENDPOINT` default to Lightning AI URL
- `scripts/migrate.ps1` — applies all migrations in order, idempotent
- `docs/API.md` — full API reference documentation
- All test scripts updated to include `X-API-Key` header

---

## Current Architecture

```
POST /documents (FastAPI)
    → saves file to /uploads
    → inserts row to documents (status=pending)
    → dispatches Celery chain

extract_task (Celery worker)
    → status = extracting
    → classify via vLLM (Qwen2.5-VL-3B AWQ, ~1-2s)
    → extract fields via vLLM (~2-3s)
    → saves extraction to DB
    → chains to validate_task

validate_task (Celery worker)
    → status = validating
    → rule-based validation
    → SLM validation via remote Ollama on Lightning AI (~30-140s)
    → merges results, computes confidence, sets requires_review
    → saves to DB
    → status = completed
    → dispatches webhook_task

webhook_task (Celery worker)
    → POSTs result to callback_url
    → retries up to 4 times (2s, 4s, 8s, 16s exponential backoff)
    → on exhaustion: logs and dies quietly
```

---

## Bugs Fixed & Mistakes Made

### Silent test failures — the most recurring problem
Multiple tests reported `PASSED` while actually being no-ops or partial executions:
- A chain test caught `ConnectionError` and returned normally — silent skip reported as pass
- A chain test "passed" in 6.67s when the real SLM call takes 30-90s — validation had silently failed and fallen back to rule-only
- A webhook retry test called the task function directly instead of through a real worker — retry behavior was structurally untestable but still reported pass

**Fix pattern:** Always corroborate a green test with timing, log output, or direct DB inspection. A 4s validate_task is always a silent fallback, never a real SLM call.

**Instrumentation added:** `test_celery_chain.py` now logs every status transition with timestamps and computes `extract_task` and `validate_task` durations. A WARNING fires if `validate_task` finishes in under 10s.

---

### Lightning AI Ollama binding reversion
**Symptom:** Every Lightning AI session restart wiped the filesystem, removing Ollama entirely and requiring manual reinstall + systemd override each session. A `403` from the public cloudspace URL was the observable symptom — looked like an access control issue but was actually the binding reverting to `127.0.0.1`-only.

**Diagnosis:** `ss -tlnp | grep 11434` shows `127.0.0.1:11434` instead of `0.0.0.0:11434`.

**Fix:** `~/on_start.sh` on Lightning AI — runs automatically on session start, installs Ollama, writes the systemd override, restarts the service (restart, not start — critical because the install script starts Ollama immediately at 127.0.0.1 before the override is written), then pulls the model.

**Key detail:** The override must be written and `systemctl restart ollama` called AFTER `ollama install.sh` completes, not before. The install script starts the service immediately — if you only call `enable + start` without `restart`, the override is never picked up.

---

### `SLM_ENDPOINT` being overridden by Windows shell env var
**Symptom:** Worker container was using `SLM_ENDPOINT=http://localhost` instead of the Lightning AI URL, causing `Connection refused` on every SLM call. SLM silently fell back to rule-only validation. Validate_task completed in ~3s instead of 30-90s.

**Root cause:** `$env:SLM_ENDPOINT="http://localhost"` had been set in the PowerShell session for running tests. Docker Compose picks up shell environment variables and they override `.env` file values. The variable persisted across restarts.

**Fix 1 (immediate):** `Remove-Item Env:SLM_ENDPOINT` in PowerShell, then `docker-compose restart worker`.

**Fix 2 (permanent):** Changed `docker-compose.yml` to use `SLM_ENDPOINT=${SLM_ENDPOINT:-https://11434-...cloudspaces.litng.ai}` with a hardcoded fallback default so the container always gets the right URL even if the shell var is unset.

**Rule going forward:** Any env var in `docker-compose.yml` that points at an external service should have a hardcoded fallback default, not a bare `${VAR}` substitution with no default.

---

### Two circular import bugs in `tasks/`
**Symptom:** `ImportError` on worker startup.

**Root cause (both times):** A shared helper (`get_db_url`, then `update_status_async`) was defined inside a task module. When another task module tried to import it, circular imports occurred.

**Fix:** Moved all shared helpers to `core/db.py`. Rule established: `tasks/` modules may import from `core/`, never from each other.

---

### `Celery.autodiscover_tasks()` failing inside Docker
**Symptom:** `ModuleNotFoundError: No module named 'tasks'` inside the container despite the import working outside Docker.

**Fix:** Abandoned autodiscovery in favor of explicit imports in `core/celery_app.py`:
```python
from tasks import extract_task, validate_task, webhook_task
```

---

### Docker Compose inter-service networking
**Symptom:** `OSError: Connect call failed ('127.0.0.1', 5432)` — worker couldn't reach Postgres.

**Root cause:** `DATABASE_URL` was using `localhost:5432` as the host. Inside a container, `localhost` refers to the container itself, not the `postgres` service.

**Fix:** Use the Compose service name (`postgres`) as the host in `DATABASE_URL`. Rule: any URL in `.env` pointing at another container must use the service name, never `localhost`.

---

### `datetime.date` and `Decimal` not JSON-serializable
**Symptom:** `TypeError` when building Ollama request payload and webhook payload — `invoice_date` was a `datetime.date`, numeric fields from Postgres were `Decimal`.

**Root cause:** `requests`/`httpx` `json=` parameter doesn't accept a custom encoder.

**Fix:** `core/json_utils.py` — `ExtractionJSONEncoder` handles `date`/`datetime`/`Decimal`. All manual `json.dumps()` calls use `cls=ExtractionJSONEncoder` and pass result as `content=` rather than `json=`.

---

### Postgres volume had zero tables
**Symptom (discovered mid-Phase 6):** `docextract_postgres` container had no tables at all — neither migration had ever been applied.

**Root cause:** No migration runner existed. The `.sql` files sat in `database/migrations/` with no documented apply step.

**Fix (immediate):** Applied manually via:
```powershell
Get-Content file.sql | docker exec -i docextract_postgres psql -U postgres -d docextract
```
Note: PowerShell does not support bash's `<` stdin redirection — use `Get-Content | docker exec -i`.

**Fix (permanent):** `scripts/migrate.ps1` — applies all migrations in order, idempotent (safe to run on an already-migrated DB).

---

### Route ordering bug
**Symptom:** `GET /documents/review` was being matched by the `GET /documents/{document_id}` parameterized route, treating `"review"` as a document ID.

**Fix:** Registered specific routes before parameterized routes in `api/routes/documents.py`:
```python
# Correct order:
GET /documents/review      # specific — registered first
GET /documents/{id}        # parameterized — registered after
GET /documents/{id}/status
```

---

### `.env` committed to GitHub
**Discovered:** `.env` containing `API_KEY` and `SLM_ENDPOINT` was publicly visible in the repo.

**Fix:** Added `.env` and `uploads/` to `.gitignore`. `.env.example` already existed as the correct pattern.

---

### PowerShell `curl` is not real curl
**Symptom:** `curl -X`, `-H`, `-F` flags failing — PowerShell's `curl` is an alias for `Invoke-WebRequest` which uses completely different syntax.

**Fix:** Use `Invoke-RestMethod` with `-Method`, `-Headers @{}`, and manual multipart body construction. For file uploads specifically, `-Form` requires PowerShell 7+ — on older versions, build the multipart body manually.

---

## Test Suite — Current State

All tests pass against the live Docker stack. Run with:

```powershell
$env:PYTHONPATH="."
$env:SLM_ENDPOINT="http://localhost"   # dummy value — Settings() validates on import but worker uses .env
$env:API_KEY="9f86d081884c7d659a2feaa0c55ad015"
pytest scripts/test_document_detail_and_status.py scripts/test_review_queue.py scripts/test_route_ordering.py scripts/test_celery_chain.py scripts/test_failure_paths.py scripts/test_webhook_delivery.py -v -s
```

| Test | What it proves |
|---|---|
| `test_document_detail_and_status` | `GET /documents/{id}` and `GET /documents/{id}/status` return correct shapes |
| `test_review_queue` | `GET /documents/review` surfaces flagged documents from real DB |
| `test_route_ordering` | `/review` resolves to review handler, not `/{id}` |
| `test_celery_chain` | Full pipeline end-to-end with real vLLM + real Ollama. Validates timing — expect ~5s extract, 30-140s validate |
| `test_celery_chain_known_bad` | XFAIL — `boe.png` extracts at 1.0 confidence, no low-confidence fixture exists for real VLM |
| `test_failure_paths` | Extraction failure path and webhook exhaustion (dead-letter) path |
| `test_webhook_delivery` | Real retry/backoff — 3 POSTs (500, 500, 200), gaps 2s and 4s, DB confirms `webhook_attempts=3` |

**Critical check for `test_celery_chain`:** If `validate_task duration` is under 10s, the SLM fell back to rule-only. Check worker logs for `403 Forbidden` or `Connection refused` on the Lightning AI URL.

---

## Latency Profile (confirmed empirically)

| Stage | Duration |
|---|---|
| Classification (vLLM) | ~1-2s |
| Extraction (vLLM) | ~2-3s |
| Validation (SLM, invoice) | 30-140s depending on Lightning AI load |
| Validation (SLM, BOE) | 25-50s |
| Total pipeline | ~35-145s |

This is why async design is mandatory — synchronous would mean the client waits 2+ minutes per document.

---

## Smoke Test Results (June 22, 2026)

| Fixture | Result | Notes |
|---|---|---|
| `sample_invoice.png` | ✅ completed, confidence=0.9625 | `po_number` correctly flagged null at 0.7 |
| `boe.png` | ✅ completed, confidence=1.0 | All 5 fields clean |
| `boe_corrupted_sbcess.png` | ✅ completed, confidence=0.88, requires_review=True | `sbcess` flagged at 0.4 — rule caught bad data |
| `garbage.png` | ✅ failed | Correctly rejected as unknown document type |

---

## Operational Notes

### Every session checklist (Lightning AI)
The `~/on_start.sh` script handles this automatically on session start. If for any reason Ollama is not working, verify:

```bash
ss -tlnp | grep 11434   # must show 0.0.0.0:11434, not 127.0.0.1
curl http://localhost:11434/api/tags
```

If bound to `127.0.0.1`:
```bash
bash ~/on_start.sh
```

From Windows, verify public tunnel:
```powershell
Invoke-RestMethod -Uri "https://11434-01kvfdrbbe002xwhcqng7rhh8e.cloudspaces.litng.ai/api/tags"
```

A `403` from the public URL = binding is `127.0.0.1`. Do not chase the Ports panel UI — fix the binding first.

### Applying migrations to a fresh Postgres volume
```powershell
.\scripts\migrate.ps1
```

Safe to run on an already-migrated DB — idempotent.

### Starting the stack
```powershell
docker-compose up -d
docker-compose ps   # confirm all 6 services running
```

---

## What's Next

### Phase 8 — Frontend
Build a UI that talks to the API. Contract is in `docs/API.md`.

**Key flows the frontend needs to handle:**
- File upload (`POST /documents`) with API key header
- Status polling (`GET /documents/{id}/status`) — pipeline takes 35-145s, frontend must poll or use webhook
- Document detail view (`GET /documents/{id}`) — show extracted fields, confidence scores, flags
- Review queue (`GET /documents/review`) — list flagged documents for human review, support filters by doc_type and date range
- Error states — `status: failed` with `failure_reason`

**Auth:** Include `X-API-Key: <key>` header on all `/documents` requests. `/health` does not require auth.

**Suggested tech:** Any — React, Vue, plain HTML. The API is REST+JSON, no special requirements.

### Phase 9 — Cloud Deployment
Move the Docker Compose stack from localhost to a real server.

**What needs to change:**
- Choose a cloud provider (AWS, GCP, DigitalOcean, etc.)
- Set up a VM with Docker and Docker Compose
- Copy the stack and `.env` to the server
- Update `docs/API.md` base URL to the real public URL
- Add API key auth to any public-facing reverse proxy (nginx)
- Decide on document storage — currently files are written to local `/uploads`, needs a persistent volume or object storage (S3/GCS) for production
- Migrate Lightning AI Ollama to a persistent VM — the current Lightning AI setup is fine for development but has no uptime guarantee

**Open question:** Keep self-hosting Ollama on a GPU VM, or switch to a hosted model API for SLM validation? Hosted API (e.g. Together AI, Groq) eliminates the Lightning AI dependency entirely and gives predictable latency — worth evaluating before committing to a GPU VM.

---

## Guiding Principles (established across all phases)

- **A PASSED test is not evidence — timing, logs, and DB state are evidence.** A validate_task finishing in 3s when the real SLM takes 30-90s is a failed test that reported green.
- **Shared helpers never live in `tasks/`** — they go in `core/`. Tasks may import from `core/`, never from each other.
- **Explicit imports over autodiscovery** — `core/celery_app.py` imports tasks explicitly. Autodiscovery failed inside Docker and was abandoned.
- **Inter-container URLs use the Compose service name, never `localhost`** — applies to DATABASE_URL, REDIS_URL, and any future service URL.
- **Docker Compose shell env vars override `.env` file values** — always check `docker-compose exec <service> env` when a container is using unexpected values.
- **PowerShell `curl` is `Invoke-WebRequest`, not real curl** — use `Invoke-RestMethod` with PowerShell-native syntax.
- **A 403 from Lightning AI's public URL = binding reversion, not an access control issue** — check `ss -tlnp | grep 11434` before investigating anything else.