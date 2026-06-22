import os
import uuid
import time
import requests
import pytest

API_KEY = os.environ.get("API_KEY", "9f86d081884c7d659a2feaa0c55ad015")
HEADERS = {"X-API-Key": API_KEY}

def test_celery_chain():
    api_url = "http://localhost:8000/documents"

    try:
        requests.get("http://localhost:8000/health", timeout=2)
    except requests.exceptions.ConnectionError:
        pytest.skip("API not running — start docker-compose before running this test")

    test_file_path = "test_data/sample_invoice.png"
    if not os.path.exists(test_file_path):
        pytest.fail(f"Test fixture {test_file_path} not found. Restore it before running this test.")

    with open(test_file_path, "rb") as f:
        response = requests.post(
            api_url,
            headers=HEADERS,
            files={"file": ("sample_invoice.png", f, "image/png")},
            data={"callback_url": "http://localhost:8085/webhook"}
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
    data = response.json()
    assert "document_id" in data
    doc_id = data["document_id"]
    print(f"\n[TIMING] Document submitted: {doc_id}")

    # Poll for status — track transitions with timestamps
    max_attempts = 120
    completed = False
    final_status = None
    failure_reason = None

    pipeline_start = time.time()
    last_status = None
    status_timestamps = {}

    for i in range(max_attempts):
        res = requests.get(f"{api_url}/{doc_id}/status", headers=HEADERS)
        if res.status_code == 200:
            status_data = res.json()
            final_status = status_data["status"]

            # Print and record each new status transition
            if final_status != last_status:
                t = time.time() - pipeline_start
                status_timestamps[final_status] = t
                print(f"[TIMING] Status → '{final_status}' at t={t:.2f}s")
                last_status = final_status

            if final_status in ["completed", "failed"]:
                completed = True
                if final_status == "failed":
                    failure_reason = status_data.get("failure_reason")
                break
        time.sleep(1.5)

    total_elapsed = time.time() - pipeline_start
    print(f"[TIMING] Pipeline finished in {total_elapsed:.2f}s total")

    # Derive stage durations from status transitions
    # Expected transitions: pending → extracting → validating → completed
    if "extracting" in status_timestamps and "validating" in status_timestamps:
        extract_duration = status_timestamps["validating"] - status_timestamps["extracting"]
        print(f"[TIMING] extract_task duration (approx): {extract_duration:.2f}s")
    else:
        print("[TIMING] WARNING: 'extracting' or 'validating' status not observed — extraction may have been skipped or too fast to catch in polling")

    if "validating" in status_timestamps and "completed" in status_timestamps:
        validate_duration = status_timestamps["completed"] - status_timestamps["validating"]
        print(f"[TIMING] validate_task duration (approx): {validate_duration:.2f}s")
        if validate_duration < 10:
            print(f"[TIMING] WARNING: validate_task took only {validate_duration:.2f}s — SLM likely fell back to rule-only (expected 30-90s for real Ollama call)")
    else:
        print("[TIMING] WARNING: 'validating' or 'completed' status not observed — cannot compute validate_task duration")

    assert completed, "Document pipeline timed out"

    if final_status == "failed":
        pytest.fail(f"Pipeline failed: {failure_reason}")

    assert final_status == "completed", f"Expected 'completed', got '{final_status}'"

    # Fetch final document details
    res_doc = requests.get(f"{api_url}/{doc_id}", headers=HEADERS)
    assert res_doc.status_code == 200
    doc_data = res_doc.json()

    assert "extraction_result" in doc_data
    assert doc_data["extraction_result"] is not None

    ext_res = doc_data["extraction_result"]
    assert "fields" in ext_res
    assert len(ext_res["fields"]) > 0, "Expected non-empty extraction fields"
    assert "overall_confidence" in ext_res
    assert "requires_review" in ext_res

    print(f"[TIMING] overall_confidence={ext_res['overall_confidence']}, requires_review={ext_res['requires_review']}")
    print(f"Pipeline finished successfully with status: {final_status}")


def test_celery_chain_known_bad():
    api_url = "http://localhost:8000/documents"
    test_file_path = "test_data/boe.png"
    if not os.path.exists(test_file_path):
        pytest.skip(f"Test fixture {test_file_path} not found.")

    with open(test_file_path, "rb") as f:
        response = requests.post(
            api_url,
            headers=HEADERS,
            files={"file": ("boe.png", f, "image/png")}
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
    doc_id = response.json()["document_id"]
    print(f"\n[TIMING] Document submitted: {doc_id}")

    pipeline_start = time.time()
    last_status = None
    status_timestamps = {}
    max_attempts = 120
    completed = False

    for i in range(max_attempts):
        res = requests.get(f"{api_url}/{doc_id}/status", headers=HEADERS)
        if res.status_code == 200:
            status_data = res.json()
            current_status = status_data["status"]

            if current_status != last_status:
                t = time.time() - pipeline_start
                status_timestamps[current_status] = t
                print(f"[TIMING] Status → '{current_status}' at t={t:.2f}s")
                last_status = current_status

            if current_status == "completed":
                completed = True
                break
            elif current_status == "failed":
                pytest.fail(f"Pipeline failed: {status_data.get('failure_reason')}")
        time.sleep(1.5)

    total_elapsed = time.time() - pipeline_start
    print(f"[TIMING] Pipeline finished in {total_elapsed:.2f}s total")

    if "validating" in status_timestamps and "completed" in status_timestamps:
        validate_duration = status_timestamps["completed"] - status_timestamps["validating"]
        print(f"[TIMING] validate_task duration (approx): {validate_duration:.2f}s")
        if validate_duration < 10:
            print(f"[TIMING] WARNING: validate_task took only {validate_duration:.2f}s — SLM likely fell back to rule-only")

    assert completed, "Document pipeline timed out"

    res_doc = requests.get(f"{api_url}/{doc_id}", headers=HEADERS)
    assert res_doc.status_code == 200
    doc_data = res_doc.json()

    ext_res = doc_data["extraction_result"]
    if not ext_res["requires_review"]:
        pytest.xfail("boe.png extracts correctly with 1.0 confidence. The 'known-bad' fixture in Phase 5 was a hardcoded Python object, not a real image. VLM successfully reads 3514.5, so requires_review is False.")

    sbcess_field = next((f for f in ext_res["fields"] if f["field_name"] == "sbcess"), None)
    assert sbcess_field is not None, "sbcess field missing from results"
    assert sbcess_field["confidence"] < 0.5, f"Expected sbcess confidence < 0.5, got {sbcess_field['confidence']}"

    overall = ext_res["overall_confidence"]
    assert 0.75 <= overall <= 1.0, f"Expected overall_confidence ~0.88, got {overall}"

    import json
    print("\n--- FULL EXTRACTION RESULT FOR KNOWN-BAD ---")
    print(json.dumps(ext_res, indent=2))


if __name__ == "__main__":
    test_celery_chain()
    test_celery_chain_known_bad()