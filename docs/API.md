# Document Extraction API

Base URL: `http://localhost:8000`
Authentication: All `/documents` endpoints require `X-API-Key` header.

---

## Endpoints

### Health Check
```
GET /health
```
No authentication required.

**Response 200**
```json
{ "status": "ok" }
```

---

### Submit Document
```
POST /documents
```
Upload a document for extraction. Returns immediately with a document ID. Processing happens asynchronously.

**Headers**
| Header | Value |
|--------|-------|
| X-API-Key | your api key |
| Content-Type | multipart/form-data |

**Form Fields**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | file | yes | PNG, JPEG, or PDF |
| callback_url | string | no | URL to POST results to when processing completes |

**Response 200**
```json
{
  "document_id": "62d89a7e-c5a1-4200-b0dc-1e0f009f679c",
  "status": "pending"
}
```

**Response 400** — unsupported file type

---

### Get Document Status
```
GET /documents/{document_id}/status
```

**Response 200**
```json
{
  "document_id": "62d89a7e-c5a1-4200-b0dc-1e0f009f679c",
  "status": "completed",
  "failed_stage": null,
  "failure_reason": null,
  "webhook_delivered": true
}
```

**Status values**
| Value | Meaning |
|-------|---------|
| pending | queued, not yet picked up |
| extracting | VLM extraction in progress |
| validating | SLM validation in progress |
| completed | pipeline finished successfully |
| failed | pipeline failed, see failed_stage and failure_reason |

---

### Get Document Detail
```
GET /documents/{document_id}
```

**Response 200**
```json
{
  "id": "62d89a7e-c5a1-4200-b0dc-1e0f009f679c",
  "file_name": "invoice.png",
  "document_type": "invoice",
  "status": "completed",
  "created_at": "2026-06-22T11:30:00",
  "updated_at": "2026-06-22T11:32:00",
  "failed_stage": null,
  "failure_reason": null,
  "extraction_result": {
    "overall_confidence": 0.9625,
    "requires_review": false,
    "fields": [
      {
        "field_name": "invoice_number",
        "value": "R202209-12",
        "confidence": 1.0,
        "flag": null
      }
    ]
  }
}
```

`extraction_result` is `null` if processing has not completed or failed.

**Document types:** `invoice`, `bill_of_entry`

**Invoice fields:** `invoice_number`, `invoice_date`, `supplier`, `quantity`, `unit_price`, `po_number`, `cgst`, `sgst`

**Bill of Entry fields:** `boe_number`, `boe_date`, `igst`, `cust_duty`, `sbcess`

---

### Get Review Queue
```
GET /documents/review
```
Returns documents flagged for human review (`requires_review: true`).

**Query Parameters**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| doc_type | string | none | Filter by `invoice` or `bill_of_entry` |
| date_from | string | none | YYYY-MM-DD |
| date_to | string | none | YYYY-MM-DD |
| status | string | completed | Document status filter |
| limit | int | 20 | Max results (1-100) |
| offset | int | 0 | Pagination offset |

**Response 200**
```json
{
  "items": [
    {
      "document_id": "a573bcf9-28bd-40d8-a1ce-3ee89d9665af",
      "document_type": "bill_of_entry",
      "overall_confidence": 0.88,
      "flagged_fields": ["sbcess"]
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

---

## Webhook Payload

If `callback_url` was provided, the API POSTs this payload when processing completes or fails.

**On success**
```json
{
  "document_id": "62d89a7e-c5a1-4200-b0dc-1e0f009f679c",
  "status": "completed",
  "document_type": "invoice",
  "overall_confidence": 0.9625,
  "requires_review": false,
  "fields": [...]
}
```

**On failure**
```json
{
  "document_id": "62d89a7e-c5a1-4200-b0dc-1e0f009f679c",
  "status": "failed",
  "failed_stage": "extraction",
  "failure_reason": "could not classify document type"
}
```

Webhook delivery retries up to 4 times with exponential backoff (2s, 4s, 8s, 16s). After all retries exhausted, the failure is logged and no further attempts are made.

---

## Error Responses

| Status | Meaning |
|--------|---------|
| 400 | Bad request (unsupported file type) |
| 403 | Missing or invalid API key |
| 404 | Document not found |

---

## Notes

- Processing is async. Poll `GET /documents/{id}/status` or use `callback_url`.
- Typical latency: ~5s extraction + 30-140s SLM validation depending on load.
- `slm_validation_unavailable: true` in logs means SLM was unreachable and rule-only validation was used.
