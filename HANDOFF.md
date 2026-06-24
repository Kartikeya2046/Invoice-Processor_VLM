# Agent Handoff — AI Document Extraction System

**Date:** June 23, 2026
**Repo:** https://github.com/Kartikeya2046/Invoice-Processor_VLM
**Branch:** main
**Builds on:** Handoff dated June 22, 2026 (Phases 1–7 complete at that point)

---

## Summary of today's session

Today's session covered two tracks:

1. **Phase 8 (Frontend)** — built and shipped. React dashboard with upload, document list, and detail view, talking to the existing backend.
2. **PDF support** — discovered mid-session that PDFs were never actually supported end-to-end despite being accepted at the API layer. This opened into a real sub-phase of work (multi-page extraction + merge), tracked here as **Phase 8.5**, currently **in progress, Step D not yet verified**.

Cloud deployment (Phase 9 / Oracle VM) was scoped and researched today but **not started** — deliberately deferred until Phase 8.5 is complete, since deploying an unfinished merge engine would just move today's bugs onto a less convenient machine.

---

## Build Plan — Status as of today

| Phase | Title | Status |
|---|---|---|
| 1 | Infrastructure & scaffold | ✅ Complete (prior session) |
| 2 | VLM integration (Qwen2.5-VL) | ✅ Complete (prior session) |
| 3 | Invoice & BOE extractors | ✅ Complete (prior session) |
| 5 | Validators & confidence scoring | ✅ Complete (prior session) |
| 6 | FastAPI routes + Celery workers | ✅ Complete (prior session) |
| 7 | Production hardening | ✅ Complete (prior session) |
| **8** | **Frontend** | ✅ **Complete (today)** |
| **8.5** | **Multi-page PDF support (new, added today)** | 🔶 **In progress — Steps A–C done, Step D built but not yet verified** |
| 9 | Cloud deployment | ⬜ Not started — scoped today, execution deferred until 8.5 is verified |

---

## Phase 8 — Frontend (completed today)

### What was built

New `frontend/` directory at repo root. Vite + React (JavaScript), plain CSS, no UI library.

```
frontend/
  src/
    api/client.js          — centralized fetch wrapper, injects X-API-Key from env on every call
    components/
      UploadZone.jsx        — drag-drop + "Upload Files" + "Upload Folder" (webkitdirectory)
      DocumentList.jsx      — lists all documents, polls in-progress ones every 5s
      DocumentDetail.jsx    — renders extracted fields, confidence, flags for selected doc
      StatusBadge.jsx       — pending/extracting/validating/completed/failed pill
    pages/Dashboard.jsx     — composes the above
  .env / .env.example       — VITE_API_BASE_URL, VITE_API_KEY
```

### Required backend addition

`GET /documents` did not exist before today — only `/documents/review` (flagged-only) and `/documents/{id}` (single doc). Added to `api/routes/documents.py`:
- Paginated list of ALL documents regardless of `requires_review`, ordered by `created_at DESC`.
- Registered before the parameterized `/documents/{id}` route, following the existing route-ordering convention (this codebase already hit a route-ordering bug once before, with `/review` being swallowed by `/{id}`).

### Bugs hit and fixed during Phase 8

**CORS blocking all browser → API calls.**
- Symptom: `GET /health` worked fine when hit directly in the browser, but every `/documents/*` call failed in the console with `No 'Access-Control-Allow-Origin' header is present`.
- Root cause: `/health` is a plain request with no custom headers, so the browser never sends a CORS preflight for it. Every `/documents/*` call sends `X-API-Key`, a non-standard header, which forces an `OPTIONS` preflight — and FastAPI had zero CORS middleware configured, so it never answered the preflight correctly.
- Fix: added `CORSMiddleware` in `api/main.py`, with `allow_origins` sourced from a new `ALLOWED_ORIGINS` setting in `core/config.py` (comma-separated string parsed to a list, defaulting to `http://localhost:5173`) rather than hardcoded — so adding the production frontend's URL later is a config change, not a code change.
- Verified: real browser upload + list load confirmed working post-fix, not just a simulated curl preflight check.

### Verified working (real evidence, not self-report)
- Upload via drag-drop, "Upload Files," and "Upload Folder" — folder upload correctly filters unsupported extensions and reports a skip count.
- Document list polls in-progress documents every 5s, stops polling on `completed`/`failed`.
- Document detail renders extracted fields, humanized field names, confidence percentages, amber-highlighted flags.
- `GET /documents` confirmed against the live DB returning real paginated data (47 documents).

---

## Phase 8.5 — Multi-page PDF support (in progress)

### Why this became a separate phase

Mid-session, attempting to upload a real PDF produced:
```
Failed Stage: extraction
Reason: Client error during classify: Client error '400 Bad Request' for url 'http://vllm:8001/v1/chat/completions'
```

Root cause: Qwen2.5-VL-3B over vLLM's `/v1/chat/completions` expects an image (base64 PNG/JPEG), not raw PDF bytes. The API layer's documented PDF support (per `docs/API.md`) was never backed by actual pipeline support — PDF had never been tested end-to-end before today.

Further discussion established that the user's real-world PDFs are multi-page, with fields split across pages in a non-trivial way:
- Identity fields (`invoice_number`, `invoice_date`, `supplier`, company name) — page 1
- Tax/duty fields (`cgst`, `sgst`, `igst`, `cust_duty`, `sbcess`) — last page
- `quantity` / `unit_price` — can legitimately span **multiple pages as distinct line items**, not one value per document

This ruled out a simple "extract page 1 only" shortcut and required a real per-page extraction + merge design, split into verifiable steps given this project's documented history of silent test failures.

### Design decisions locked in this session

- **Field split:** scalar fields (one true value per document) vs. list fields (`quantity`, `unit_price` — legitimately multiple values, collected not merged).
- **Scalar merge rule:** field present on 1 page = full confidence. Pages agree (after normalization) = full confidence. Pages disagree = `requires_review`, both/all conflicting values surfaced with page attribution — never silently average or pick a winner without flagging it.
- **Disagreement detection is normalized, not exact-string:** dates parsed to date objects, numbers parsed to `Decimal`, strings trimmed/case-folded — before comparing. Chosen deliberately over exact-match after discussion, since VLM output formatting (date format, trailing `.00`) varies across pages even when the underlying value is identical; exact-match would flood the review queue with false conflicts.
- **`requires_review` ownership (Option 2, chosen by user after tradeoff discussion):** the merge layer sets `requires_review = True` immediately upon detecting a real conflict, before `validate_task` runs. `validate_task` must OR its own computed value with the existing one — **hard requirement: `requires_review` may only go False→True, never True→False.** This guards against a merge-detected conflict being silently erased by a more lenient downstream conclusion.
- **Confidence does not exist at the extraction stage, for any document** (confirmed via diagnostic, see Step C below) — it has always been produced exclusively by `validate_task`, for single-page documents too. This was initially mistaken for a Step C bug; diagnosis proved it's pipeline-original behavior, not a regression.

### Steps completed and verified

**Step A — Schema migration (`database/migrations/003_page_support.sql`)**
- Added nullable `page_number INTEGER` to both `extractions` and `field_confidences`. `NULL` = final merged result; non-null = raw per-page snapshot (kept for audit, per project principle of preferring evidence on disk over trusting logs).
- Added matching indexes on `(document_id, page_number)` and `(extraction_id, page_number)`.
- **Important standing gotcha discovered:** `scripts/migrate.ps1` uses a **hardcoded `$migrations` array**, not directory auto-discovery. Every new migration file must be manually added to this array or it silently never runs. Antigravity correctly added `003_page_support.sql` to the array — without this edit, the migration file would have sat in the folder doing nothing despite looking like part of the codebase. **Action item for Phase 9:** the Oracle VM's fresh Postgres volume needs this script run with the full, current array, in order.
- Idempotency required a fix: original migration used plain `ADD COLUMN`/`CREATE INDEX`, which would error on re-run. Fixed to `ADD COLUMN IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`.
- Verified via real `\d extractions` / `\d field_confidences` output (columns present) and `pytest` (`test_document_detail_and_status.py`, `test_review_queue.py` both passed, 92.93s — timing itself is evidence of a real SLM call, not a silent fallback).

**Step B — PDF → per-page image rendering**
- New `core/pdf_utils.py` using `pymupdf` (`fitz`) — pure-Python, no system poppler/ghostscript dependency, renders at 150 DPI.
- `POST /documents` detects PDF by MIME/extension, renders synchronously at upload time (before the Celery chain is dispatched), stores page count in the existing `processing_metadata.page_count` column.
- Corrupt/invalid PDFs return 400 before ever reaching Celery — not a silent pass-through.
- **Verified with real evidence after one round of pushback:** initial report gave only the upload response (`status: pending`) as "proof" of rendering, which is not sufficient evidence per this project's standards. Re-requested and received: real `SELECT page_count FROM processing_metadata` query showing `1` and `3` for the two test PDFs, and real `find /app/uploads` output showing the actual rendered `_page_1.png` / `_page_2.png` / `_page_3.png` files on disk.
- Regression-checked: corrupt PDF → real 400 with clear error message; normal PNG path unaffected.

**Step C — Per-page classification + extraction loop (no merging yet)**
- `tasks/extract_task.py` modified: `page_count == 1` path entirely unchanged; `page_count > 1` loops the existing classify/extract logic once per rendered page image, storing each page's result as its own `extractions` row (`page_number` = 1..N) and `field_confidences` rows.
- Placeholder added (intentionally, to keep this step's scope tight): `validate_task` temporarily pointed at page 1's extraction only, with a `# TODO Step D: replace with merged result` comment.
- **First verification round caught a real-looking but ultimately false alarm**, worth recording as a lesson: a 3-page synthetic test PDF produced 24 `field_confidences` rows with `extracted_value` and `confidence` both completely blank. Root-caused (with worker log evidence, not assumption) to a **test data defect, not a code defect** — the synthetic PDF used for testing contained only literal text like "INVOICE 1" with no actual invoice fields, so the VLM correctly returned an empty extraction. Re-tested with a corrected fixture (`test_multi_real_data.pdf`, containing real differing values: INV-1001/1002/1003, different suppliers/quantities/prices per page) and confirmed all 24 rows populated with correct, page-distinct real values — strong evidence (three genuinely different values per field, not a repeated/cached result) that the per-page loop does real independent work.
- **Second diagnostic, also real and not a false alarm but worth recording:** confirmed that `confidence` has *never* existed at the extraction stage for *any* document, single-page included — it's exclusively written by `validate_task` via `INSERT`, never `UPDATE`, into `field_confidences`. Verified by checking a real completed single-page document's full row history and reading the actual `extract_task.py` / `validate_task.py` code paths directly (pasted, not paraphrased). This was not a Step C regression; it simplified the Step D design, since "per-page confidence" was never an input the merge engine needed to reason about.

**Step D — Merge engine (built today, prompt issued, results not yet returned/verified)**
- `core/merge_utils.py`: `merge_page_extractions(page_results, document_type)` — scalar fields merged per the agreement/disagreement/normalization rules above; list fields (`quantity`, `unit_price`) collected into page-attributed arrays, never merged into one value.
- `extract_task.py`: for `page_count > 1`, inserts a new `extractions` row with `page_number = NULL` (the Step A convention for "final merged result"), sets `requires_review = True` immediately if conflicts exist, points `validate_task` at this new row (replacing the Step C placeholder).
- `validate_task.py`: required to OR its own `requires_review` computation with the existing value rather than overwriting it — hard requirement, with an explanatory code comment mandated in the prompt.
- **Verification requested but not yet received:** 7 checks specified (merged array fields correct, real conflicts correctly flagged, genuine agreement correctly NOT flagged, normalized-equal values correctly NOT flagged as conflicts, the never-downgrade guarantee proven with a real before/after query, single-page regression check, full `test_celery_chain.py` rerun). **This is the next action when work resumes.**

### Explicitly not done yet (do not assume otherwise)
- Step D's verification output has not been reviewed. Do not treat the merge engine as working until that evidence is in and checked — this project has a documented history of plausible-sounding "done" reports that turned out to be incomplete or wrong (see Step C's false alarm above, and the CORS fix which initially was only self-tested via simulated preflight before real browser verification was requested).
- Frontend (`DocumentDetail.jsx`) has NOT been updated to render list-valued fields or conflict data. It will currently render these incorrectly (likely `[object Object]` or similar) once real multi-page documents start producing merged results. This is the deliberate next step after Step D is verified — explicitly deferred, not forgotten.
- No multi-page BOE testing has been done — all Step C/D testing used invoice fixtures. BOE's field-to-page mapping was confirmed to differ from invoice's (per user, "slightly different per document type") but the specifics were never pinned down, since the invoice case was used to build and verify the general-purpose merge engine first. **Open question for next session: confirm BOE's actual page layout before assuming the same merge engine handles it correctly out of the box** — the merge logic itself is document-type-agnostic (driven by the field lists per `document_type`), so it should work, but this has not been tested with a real or synthetic multi-page BOE fixture.

---

## Phase 9 — Cloud Deployment (scoped today, not started)

### Decisions made
- **Backend hosting:** Oracle Cloud Free Tier, `VM.Standard.A1.Flex` (ARM, Ampere A1), 4 OCPU / 24GB RAM, Ubuntu 24.04 ARM64. Chosen specifically as a non-Railway option per user's request.
- **vLLM:** stays local on the user's RTX 3050, exposed to the cloud-hosted API via a Cloudflare Tunnel (same pattern already used for Ollama on Lightning AI). Confirmed via research that Oracle's free tier has no GPU shapes — this wasn't a fallback, it was the only viable option given the constraint.
- **SLM (Ollama):** stays on Lightning AI, unchanged.
- **Frontend hosting:** not yet decided (Vercel/Netlify are the likely default given the React/Vite stack, not yet confirmed with the user).

### Known gotchas for when this resumes (researched, not yet executed)
- Oracle's free ARM capacity is regionally constrained — **"Out of Capacity" errors are common in high-demand regions** (e.g. US East) and can take hours; Frankfurt and Singapore typically provision within minutes. Given the user's location (India), Singapore is the recommended region for both availability and latency.
- **"Home Region Trap":** the home region chosen at account setup is permanent for Always Free resources and cannot be changed later — must be chosen correctly the first time.
- Postgres/Redis/Flower images are fine on ARM64 unchanged; the custom `api` and `worker` images (built from this repo's own Dockerfiles) need to be rebuilt for `linux/arm64` via `docker buildx`, not reused from the x86 Windows/WSL2 dev images.
- Oracle ingress is blocked by default — VCN security list rules need explicit allow rules for the API port before the VM is reachable publicly.
- The `scripts/migrate.ps1` hardcoded-array gotcha (see Step A above) applies directly here: a fresh Postgres volume on the Oracle VM needs every migration 001 through the latest applied in order, and PowerShell itself won't exist on the Linux VM, so the equivalent `psql`-based apply sequence needs to be run manually or via a Linux-equivalent script.

### Deliberately deferred
Cloud deployment was not started today because deploying Phase 8.5's unfinished merge engine would mean debugging it on a remote machine instead of locally — strictly worse for iteration speed. **Recommended order when resuming: finish and verify Phase 8.5 completely (including the frontend rendering update for list/conflict fields), then move to Phase 9.**

---

## Problems encountered today — full list

1. **CORS misconfiguration** blocking all browser-to-API calls (`X-API-Key` header forces a preflight FastAPI never answered). Fixed with `CORSMiddleware` + configurable `ALLOWED_ORIGINS`.
2. **No general document-list endpoint existed.** Added `GET /documents`, following existing route-ordering and response-shape conventions.
3. **PDF upload failed with 400 at the VLM classify step** — PDFs were never actually supported end-to-end despite being documented as an accepted upload type. Root cause: vLLM's multimodal endpoint requires image bytes, not PDF bytes.
4. **Multi-page field layout is non-trivial** — fields split across page 1 / last page / many-middle-pages depending on field type, ruling out a "first/last page only" shortcut originally considered.
5. **Migration runner is a hardcoded array, not auto-discovery** — `003_page_support.sql` required a manual array edit in `scripts/migrate.ps1` or it would have silently never run. Same risk applies to all future migrations and to the eventual Oracle deployment.
6. **Migration idempotency gap** — initial `003_page_support.sql` lacked `IF NOT EXISTS`, would have errored on re-run. Fixed.
7. **False alarm: empty per-page extraction rows.** Root-caused to a synthetic test PDF containing no real field data, not a code defect — caught and resolved via worker log inspection before being mistaken for a Step C bug.
8. **Confidence-at-extraction-stage diagnostic.** Confirmed (not assumed) that `field_confidences.confidence` has never been populated at extraction time for any document — exclusively a `validate_task` output. Resolved a real ambiguity in the Step D design before it was built.
9. **`requires_review` ownership ambiguity** across two pipeline stages (merge layer vs. `validate_task`) — resolved via explicit tradeoff discussion; user chose to let the merge layer set the flag directly, with a hard never-downgrade guarantee enforced in `validate_task`'s write.
10. **Scalar field disagreement detection** — exact-string-match was considered and rejected in favor of normalized comparison (parsed dates/decimals, trimmed/case-folded strings), specifically to avoid false-positive conflicts from formatting differences (e.g. `"500"` vs `"500.00"`) flooding the review queue.
11. **API route filtering for multi-page results:** `GET /documents/{id}` and other endpoints were fetching page 1 extractions instead of the merged result. Fixed by adding a `page_number IS NULL` filter to correctly target the final merged extraction row.
12. **API serialization of list fields and conflicts:** List fields (like `quantity`, `unit_price`) were returned as stringified JSON, and the special `_conflicts` object was missing from the response. Fixed by updating `api/routes/documents.py` to safely parse stringified lists and directly extract the `_conflicts` object from the database's `extracted_json`.
13. **Subfolder file upload crashes (`FileNotFoundError`):** Uploading folders via the frontend passed subfolder paths (e.g., `folder/file.pdf`), causing crashes because parent directories didn't exist. Fixed by adding `os.makedirs(os.path.dirname(file_path), exist_ok=True)` in the upload handler.
14. **VLM Classification failures on dense invoices:** Complex, real-world supplier invoices (e.g., Mouser Electronics) were classified as "unknown" with low confidence. Fixed by updating the `classify` system prompt in `models/vlm_client.py` to explicitly describe these documents and list examples like electronics distributors.
15. **VLM Token Limit Overflow (`400 Bad Request`):** Extraction failed on complex invoices because the input prompt plus generation tokens exceeded vLLM's `2048` max model context length limit. Fixed by removing redundant Pydantic schema injection from `vlm_client.py`'s `system_prompt` and significantly shortening `INVOICE_EXTRACTION_PROMPT` in `extractors/prompts/invoice_prompt.py`, reducing the total context to ~1564 tokens and enabling successful 200 OK extractions.

---

## Guiding principles reaffirmed today (consistent with prior sessions)

- **A self-reported "done" is not evidence.** Every step in today's session required real query output, real log lines, or real file listings before being accepted — and this caught at least one genuine gap (Step C's first round, where prose claimed success but the actual `field_confidences` rows were empty) and one false alarm correctly resolved by going to the evidence (the synthetic-PDF root cause).
- **Small, isolated, separately-verified steps** — explicitly chosen by the user over one large prompt, specifically because of this project's history with silent failures. This paid off directly: Step C's bug was caught before it could be built on top of in Step D.
- **Never let a later stage silently undo an earlier stage's correct decision** — the `requires_review` never-downgrade rule is the clearest expression of this principle applied to today's new code.

---

## Immediate next steps, in order

1. **Review Step D's verification output** (7 checks specified in the Step D prompt) once Antigravity returns it. Do not proceed to frontend rendering work until this is confirmed with real evidence, per the pattern established today.
2. **Update `DocumentDetail.jsx`** to correctly render list-valued fields (`quantity`/`unit_price` as page-attributed arrays) and conflict data (`_conflicts`), once Step D is verified.
3. **Test a multi-page BOE fixture** — confirm the document-type-agnostic merge engine actually handles BOE's field layout correctly, not just invoice's.
4. **Resume Phase 9 (Oracle Cloud deployment)** only after the above are complete — provision the Singapore-region `VM.Standard.A1.Flex` instance, rebuild `api`/`worker` images for ARM64, set up the Cloudflare Tunnel for local vLLM, and run the full migration sequence (001–003+) against the fresh Postgres volume.