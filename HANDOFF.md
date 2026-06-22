# Agent Handoff — AI Document Extraction System

## Project Overview
Enterprise pipeline that replaces an old OCR + Mistral approach with a VLM-based document extraction system. The system classifies, extracts, and validates fields from **Invoices** and **Bills of Entry (BOE)** using **Qwen2.5-VL-3B-Instruct (AWQ INT4)** served via vLLM, plus a hybrid rule-based + SLM validation layer, now wired into an async Celery pipeline with webhook delivery.

**Stack:** FastAPI · PostgreSQL · Redis · Celery · vLLM (Qwen2.5-VL-3B AWQ INT4) · Docker Compose · Ollama (remote, Lightning AI)
**Repo:** https://github.com/Kartikeya2046/Invoice-Processor_VLM
**Branch:** `main`

### Why rebuilt from scratch
The old OCR + Mistral architecture was tightly coupled — adding new document types or changing extraction logic required touching multiple fragile components at once, with no confidence scoring or structured validation. Rather than patch it, the system was redesigned with independent, replaceable components (classification → extraction → validation → async orchestration).

### Why not LangChain
The pipeline is a fixed linear sequence (classify → extract → validate) — no need for LangChain's agent/chain abstractions. Direct `httpx` calls to vLLM and Ollama are faster and easier to debug than adding a dependency layer with no functional benefit.

---

## Current Status

### ✅ Phase 1 — Infrastructure & Scaffold: COMPLETE
- Docker Compose stack — now 6 containers with the addition of `worker` (see Phase 6)
- PostgreSQL schema migrated via `database/migrations/001_initial_schema.sql`
- FastAPI `main.py` with `/health` endpoint working

### ✅ Phase 2 — VLM Integration: COMPLETE
- `models/vlm_client.py`, `classifiers/vlm_classifier/__init__.py` — all tests pass

### ✅ Phase 3 — Invoice & BOE Extractors: COMPLETE
- `extractors/invoice/` and `extractors/bill_of_entry/` — all tests pass

### ✅ Phase 5 — Hybrid Validation (Rules + SLM): COMPLETE
- Rule-based + SLM (Qwen2.5:3b via remote Ollama) validators, merge layer, confidence scoring — all tests pass

### ✅ Phase 6 — FastAPI Routes + Celery Workers: COMPLETE
**Architecture:** `POST /documents` returns 202 immediately and dispatches a Celery `chain(extract_task, validate_task)`. Each stage updates `documents.status` in Postgres. On completion or failure, `webhook_task` POSTs a result payload to the caller-supplied `callback_url`, with exponential-backoff retry (up to `WEBHOOK_MAX_RETRIES`, base `WEBHOOK_RETRY_BACKOFF_BASE`).

**Why two chained tasks, not one:** extraction (local vLLM, ~5-6s) and validation (remote Ollama on flaky Lightning AI, ~30-90s) have different latency and failure profiles. Chaining them separately means a Lightning AI hiccup doesn't force re-running the GPU-bound extraction, and Flower shows which stage actually failed.

**Built components:**
- `core/celery_app.py` — flat file, Celery app config. **Autodiscovery was abandoned in favor of explicit imports** (`from tasks import extract_task, validate_task, webhook_task`) — see Key Learnings.
- `core/db.py` — shared `get_db_url()` (and related DB helpers), extracted out of `tasks/` to break circular imports (see Key Learnings).
- `core/json_utils.py` — `ExtractionJSONEncoder`, handles `date`/`datetime`/`Decimal` for any manual `json.dumps()` call outside FastAPI's own response serialization.
- `tasks/extract_task.py`, `tasks/validate_task.py`, `tasks/webhook_task.py` — the three chained/dispatched tasks.
- `api/routes/documents.py` — `POST /documents`, `GET /documents/review`, `GET /documents/{document_id}`, `GET /documents/{document_id}/status`, registered in that order (specific routes before parameterized).
- `database/migrations/002_phase6_pipeline.sql` — adds `status`, `callback_url`, `failed_stage`, `failure_reason`, `webhook_delivered`, `webhook_attempts` to `documents`.
- `docker-compose.yml` — new `worker` service, `celery -A core.celery_app worker --concurrency=2` (concurrency capped deliberately given 6GB VRAM shared with vLLM).

**Test coverage, all independently re-verified against the live stack (not just exit codes — see Key Learnings on what counts as proof):**
- `scripts/test_celery_chain.py` — full chain through real vLLM + real Lightning AI SLM. Verified pass took 92.32s, with `validate_task` alone logging 87.71s — consistent with known SLM latency, confirming the SLM was actually called rather than short-circuited.
- `scripts/test_webhook_delivery.py` — dispatches through the **real Docker worker** (not an in-process function call — see Key Learnings on why that doesn't work for retry testing), against a real local listener that fails twice then succeeds. Confirmed 3 real POSTs (500, 500, 200) with measured gaps of 2.06s and 4.06s, matching `WEBHOOK_RETRY_BACKOFF_BASE=2.0` exponential backoff (`2.0×2^0`, `2.0×2^1`) almost exactly. `webhook_attempts=3`, `webhook_delivered=True` confirmed via direct DB read.
- `scripts/test_route_ordering.py` — confirms `GET /documents/review` resolves to the review handler, not the `{document_id}` parameterized route. Clean pass, 1.00s runtime.

---

## Known Issue — Latency (carried forward, now load-bearing rather than theoretical)
- VLM extraction: ~5-6s/doc (confirmed again in live Phase 6 testing: 2.03s classify + 3.20s extract)
- SLM validation: 30-90s/call depending on Lightning AI's shared-hardware load (87.71s observed in one real run — higher than the 30-50s range noted in Phase 5, worth monitoring as a range rather than a fixed number)
- This is **why Phase 6's async design is correct and necessary** — confirmed empirically, not just architecturally: a synchronous request path would mean the client waits up to ~95s+ per document.

---

## What's Next — Phase 7: Shadow Mode & Production Cutover
Not yet scoped. Known open items carried into it:
- **Confirm Phase 1–5's own test scripts (`test_invoice_extractor.py`, `test_boe_extractor.py`, `test_validators.py`, etc.) still pass against a real, migrated Postgres volume.** Discovered during Phase 6 debugging that the `docextract_postgres` container had **zero tables** — no migration had ever been applied to it — meaning it's unconfirmed whether earlier phases' "all tests passing" claims were ever exercised against a real database, versus mocked DB layers or a different now-gone Postgres volume. This should be checked explicitly before Phase 7's shadow-mode cutover, not discovered mid-cutover.
- `GET /documents/review`'s actual query against `extractions`/`field_confidences` for `requires_review=True` documents has not yet been exercised with real flagged data end-to-end (the happy-path known-good test fixture used in `test_celery_chain.py` scored 0.9625 confidence and did not require review — worth a dedicated test with a known-bad fixture to confirm the review queue actually surfaces it).
- Webhook delivery's "after max retries exhausted, log and let it die quietly in Celery's bookkeeping" path (the dead-letter case) has not been tested — only the eventual-success retry path has real evidence behind it.

---

## How to Run

```powershell
cd D:\Downloads\intern\Invoice_Processor_v2\document-extraction
docker-compose up -d
docker-compose ps   # confirm all 6 services: api, postgres, redis, flower, vllm, worker

# Phase 6 tests — run from Windows host, need PYTHONPATH and SLM_ENDPOINT set even for
# tests that mostly talk to the real Docker stack, since Settings() validates eagerly on import
$env:PYTHONPATH="."
$env:SLM_ENDPOINT="http://localhost"
pytest scripts/test_celery_chain.py -v -s          # ~90s+, hits real vLLM + real Ollama
pytest scripts/test_webhook_delivery.py -v -s      # ~10s, hits real Docker worker
pytest scripts/test_route_ordering.py -v -s        # ~1s, route resolution only

# Logs
docker-compose logs -f worker
docker-compose logs -f api
```

### ⚠️ Required first step EVERY session: verify Ollama on Lightning AI
(Unchanged from Phase 5 — see below for a **newly confirmed fourth symptom** of the existing binding-reversion failure mode.)

```bash
which ollama
curl http://localhost:11434/api/tags
ss -tlnp | grep 11434
```

If bound to `127.0.0.1` instead of `0.0.0.0`:
```bash
sudo systemctl edit ollama
# [Service]
# Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl daemon-reload
sudo systemctl restart ollama
sleep 2
curl http://localhost:11434/api/tags
```

Then verify the public tunnel:
```powershell
curl -v https://11434-01kvfdrbbe002xwhcqng7rhh8e.cloudspaces.litng.ai/api/tags
```

**Newly observed symptom (Phase 6 session) of the same binding-reversion failure:** a `curl` to the public cloudspace URL can return a clean `HTTP/2 403` with `content-length: 0` — not a timeout, not a connection error — when the underlying binding is `127.0.0.1`-only. This looked at first like a separate Lightning AI access-control/Ports-panel issue, but was fully resolved by the same `OLLAMA_HOST=0.0.0.0:11434` systemd fix already documented above. **Don't chase the Ports panel UI before re-checking the binding** — check `ss -tlnp | grep 11434` from inside the Studio terminal first; a 403 from the public URL is consistent with this same root cause, not necessarily a new one.

---

## Folder Structure (relevant Phase 6 additions)
```
document-extraction/
├── core/
│   ├── celery_app.py            # Celery app — explicit task imports, NOT autodiscover_tasks()
│   ├── db.py                    # get_db_url(), shared DB helpers — moved here to break circular imports
│   ├── json_utils.py            # ExtractionJSONEncoder (date/datetime/Decimal)
│   └── config.py                # Settings — now includes CELERY_BROKER_URL, CELERY_RESULT_BACKEND,
│                                 #   WEBHOOK_MAX_RETRIES, WEBHOOK_RETRY_BACKOFF_BASE, WEBHOOK_TIMEOUT
├── tasks/
│   ├── __init__.py
│   ├── extract_task.py          # classify+extract via vLLM, chains to validate_task
│   ├── validate_task.py         # rule+SLM validation via existing Phase 5 validators
│   └── webhook_task.py          # delivers result/failure payload to callback_url, retries on non-2xx
├── api/routes/documents.py      # POST /documents, GET /review, GET /{id}, GET /{id}/status
├── database/migrations/
│   ├── 001_initial_schema.sql
│   └── 002_phase6_pipeline.sql  # status, callback_url, failed_stage, failure_reason,
│                                 #   webhook_delivered, webhook_attempts on documents
├── scripts/
│   ├── test_celery_chain.py     # real end-to-end, real vLLM + real Ollama
│   ├── test_webhook_delivery.py # real worker dispatch + real listener, retry/backoff verified
│   └── test_route_ordering.py   # FastAPI TestClient, route resolution only
└── docker-compose.yml           # +worker service, concurrency=2
```

---

## Build Plan Summary
| Phase | Title | Status |
|---|---|---|
| 1 | Infrastructure & scaffold | ✅ Complete |
| 2 | VLM integration (Qwen2.5-VL) | ✅ Complete |
| 3 | Invoice & BOE extractors | ✅ Complete |
| 5 | Validators & confidence scoring (hybrid rules + SLM) | ✅ Complete |
| 6 | FastAPI routes + Celery workers | ✅ Complete |
| 7 | Shadow mode & production cutover | ⬜ Next — unscoped |

---

## Key Learnings & Principles (Phase 6 additions)

- **A passing test is not evidence — a passing test whose timing, log output, or DB state corroborates the claim is evidence.** This phase produced multiple false "PASSED" results that were actually silent no-ops, swallowed exceptions, or partial executions: a chain test that caught `ConnectionError` and returned normally (silent skip reported as pass), a chain test that "passed" in 6.67s when the real SLM call alone takes 30-90s (validation had silently failed and fallen back to rule-only), and a webhook retry test that called the task function directly instead of through a real worker, making genuine retry behavior structurally untestable while still reporting a pass. **The fix pattern every time was the same: read the actual test code, not the summary of it, and check whether the timing/log output is even physically consistent with the claim before trusting a green checkmark.**

- **Two distinct circular-import bugs occurred in `tasks/` in one session, both from the same root mistake: a shared helper (`get_db_url`, then later `update_status_async`) was defined inside a task module instead of a shared `core/` module.** Any time a task module needs to import something from a sibling task module, that's a signal the shared logic is in the wrong place. Fixed permanently by moving both into `core/db.py`. **Rule going forward: shared helpers never live in `tasks/`, full stop — `tasks/` modules may import from `core/`, never from each other** (except where a Celery chain's return-value passing makes that unnecessary).

- **`Celery.autodiscover_tasks()` is fragile for this project's plain-package layout and was abandoned in favor of explicit imports.** `core/celery_app.py` now does `from tasks import extract_task, validate_task, webhook_task` directly rather than relying on autodiscovery, which kept failing with `ModuleNotFoundError: No module named 'tasks'` inside the container despite the same import succeeding standalone outside Docker. Explicit imports are also more robust given this project's recurring history with package/flat-file ambiguity (see Phase 2 and Phase 5 learnings) — there's no discovery mechanism left to get confused by.

- **Inside Docker Compose, service-to-service networking uses the Compose service name, never `localhost`.** `core/db.py`'s fallback `DATABASE_URL` default (and the actual `.env` value) pointed at `localhost:5432`, which inside the `api`/`worker` containers refers to the container itself, not the `postgres` service — producing `OSError: Connect call failed ('127.0.0.1', 5432)`. Fixed by setting `.env`'s `DATABASE_URL` host segment to `postgres` (the Compose service name) and removing the `localhost` fallback entirely in favor of raising a clear error if the env var is missing. **Any new env var added to `.env` that points at another container in this stack must use the service name, never `localhost` — this applies equally to `REDIS_URL` and any future inter-service URL.**

- **Real Python objects from extraction/DB round-trips (`datetime.date`, `decimal.Decimal`) are not JSON-serializable by default, and this only surfaces once data flows through a real network call — not in earlier phases' more isolated tests.** Hit twice independently: once in `models/slm_client.py` building the Ollama request payload (`invoice_date` as `datetime.date`), once in `tasks/webhook_task.py` building the outbound webhook payload (a `Decimal` field, likely from a Postgres `NUMERIC` column via asyncpg). Both call sites also used `requests`'/`httpx`'s convenience `json=` parameter, which doesn't accept a custom encoder — fixed by switching to manual `json.dumps(payload, cls=ExtractionJSONEncoder)` passed as `content=`/raw string. **`core/json_utils.py`'s `ExtractionJSONEncoder` is now the single shared encoder for any future manual JSON serialization of extraction data — do not write a second ad-hoc encoder.** Note: `Decimal` is converted to `float` for outbound JSON, which is fine for webhook/SLM payloads but would lose precision if any future code re-parses that JSON and does further financial math on the result — flag that separately if it ever comes up.

- **A Celery task's retry behavior (`self.retry(...)`) cannot be tested by calling the task function directly in a script.** `self.retry()` only does something meaningful when the task is actually running inside a worker process consuming from a real broker — called directly, it just raises a `Retry` exception once and stops, making it impossible to observe a second attempt. The only way to test retry/backoff behavior for real is to dispatch via `.delay()`/`.apply_async()` against the actual running worker container and observe the real outcome (DB state, real listener hits) — `unittest.mock.patch` in the test process also cannot reach into a separate worker container's process space, so any test needing to control what a task "sees" must do so via real shared state (a real DB row), not in-process mocking.

- **A Postgres volume can silently have zero schema applied even after multiple "phases complete" with "all tests passing."** Discovered mid-Phase-6 that `docextract_postgres` had no tables at all — neither `001_initial_schema.sql` nor `002_phase6_pipeline.sql` had ever been run against it, and there was no existing migration-runner convention, just raw `.sql` files sitting in `database/migrations/` with no documented "how do I actually apply these" step. Applied manually via `Get-Content file.sql | docker exec -i docextract_postgres psql -U postgres -d docextract` (note: PowerShell does not support bash's `<` stdin redirection — use `Get-Content | docker exec -i ...` instead). **Open question carried into Phase 7: were Phase 1–5's DB-touching tests ever actually run against a real, populated Postgres, or did they pass against mocks/a different volume?** Worth confirming explicitly rather than assuming.

- **A `403` with `content-length: 0` from Lightning AI's public cloudspace edge proxy is consistent with the already-documented `127.0.0.1`-binding failure mode, not necessarily a new Ports-panel/access-control issue.** When the Ollama binding reverts to localhost-only, the edge proxy can reach no real upstream to authorize against and falls back to a bare 403 rather than a more obviously diagnostic timeout or connection error. Check `ss -tlnp | grep 11434` from inside the Studio terminal before investigating the Ports panel UI.

---

**Guiding principle for all future phases:** Follow the build plan as the skeleton. Fill gaps with decisions that match the actual deployed environment. Treat a "PASSED" test result as a claim to be corroborated — via timing, log output, or direct DB/state inspection — not as proof on its own, especially for anything crossing a process, container, or network boundary.