import os
import uuid
import asyncpg
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from celery import chain
from core.config import settings
from tasks.extract_task import extract_task
from tasks.validate_task import validate_task
from core.db import get_db_url

router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/pdf", "application/pdf"}

async def get_db():
    db_url = get_db_url()
    conn = await asyncpg.connect(db_url)
    try:
        yield conn
    finally:
        await conn.close()

@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    callback_url: Optional[str] = Form(None)
):
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed types: {ALLOWED_MIME_TYPES}")
        
    doc_id = str(uuid.uuid4())
    job_id = f"job-{doc_id[:8]}"
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}_{file.filename}")
    
    file_bytes = await file.read()
    with open(file_path, "wb") as f:
        f.write(file_bytes)
        
    # Insert to db
    db_url = get_db_url()
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(
            """
            INSERT INTO documents 
            (id, job_id, original_path, file_name, file_size_bytes, mime_type, workflow, status, callback_url) 
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            doc_id, job_id, file_path, file.filename, len(file_bytes), file.content_type, 'default', 'pending', callback_url
        )
    finally:
        await conn.close()
        
    # Kick off Celery chain
    # Note validate_task.s(document_id=doc_id) receives extract_task's result as its first positional argument automatically.
    chain(
        extract_task.s(doc_id),
        validate_task.s(document_id=doc_id)
    ).apply_async()
    
    return {"document_id": doc_id, "status": "pending"}

@router.get("")
async def list_documents(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Status filter"),
    document_type: Optional[str] = Query(None, description="Filter by document_type (invoice or bill_of_entry)")
):
    db_url = get_db_url()
    conn = await asyncpg.connect(db_url)
    
    try:
        query = """
            SELECT d.id as document_id, d.file_name, d.document_type, d.status, d.created_at,
                   e.overall_confidence, e.requires_review
            FROM documents d
            LEFT JOIN extractions e ON d.id = e.document_id
            WHERE 1=1
        """
        params = []
        param_idx = 1
        
        if status:
            query += f" AND d.status = ${param_idx}"
            params.append(status)
            param_idx += 1
            
        if document_type:
            query += f" AND d.document_type = ${param_idx}"
            params.append(document_type)
            param_idx += 1
            
        # Count total
        count_query = f"SELECT COUNT(*) FROM ({query}) AS sub"
        total_count = await conn.fetchval(count_query, *params)
        
        # Paginate
        query += f" ORDER BY d.created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([limit, offset])
        
        rows = await conn.fetch(query, *params)
        
        results = []
        for row in rows:
            results.append({
                "document_id": str(row["document_id"]),
                "file_name": row["file_name"],
                "document_type": row["document_type"],
                "status": row["status"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "overall_confidence": float(row["overall_confidence"]) if row["overall_confidence"] is not None else None,
                "requires_review": row["requires_review"]
            })
            
        return {
            "items": results,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }
    finally:
        await conn.close()

@router.get("/review")
async def get_review_queue(
    doc_type: Optional[str] = Query(None, description="Filter by document_type"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    status: str = Query("completed", description="Status filter (default: completed)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    # Route matching requires_review=True documents
    db_url = get_db_url()
    conn = await asyncpg.connect(db_url)
    
    try:
        query = """
            SELECT d.id as document_id, d.document_type, e.overall_confidence, e.id as extraction_id
            FROM documents d
            JOIN extractions e ON d.id = e.document_id
            WHERE d.status = $1 AND e.requires_review = TRUE
        """
        params = [status]
        param_idx = 2
        
        if doc_type:
            query += f" AND d.document_type = ${param_idx}"
            params.append(doc_type)
            param_idx += 1
            
        if date_from:
            query += f" AND d.created_at >= ${param_idx}::timestamp"
            params.append(date_from)
            param_idx += 1
            
        if date_to:
            query += f" AND d.created_at <= ${param_idx}::timestamp + interval '1 day'"
            params.append(date_to)
            param_idx += 1
            
        # Count total
        count_query = f"SELECT COUNT(*) FROM ({query}) AS sub"
        total_count = await conn.fetchval(count_query, *params)
        
        # Paginate
        query += f" ORDER BY d.created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([limit, offset])
        
        rows = await conn.fetch(query, *params)
        
        results = []
        for row in rows:
            # Get flagged fields
            flagged_fields = await conn.fetch(
                "SELECT field_name FROM field_confidences WHERE extraction_id = $1 AND confidence < 0.75",
                row["extraction_id"]
            )
            results.append({
                "document_id": str(row["document_id"]),
                "document_type": row["document_type"],
                "overall_confidence": float(row["overall_confidence"]) if row["overall_confidence"] else 0.0,
                "flagged_fields": [f["field_name"] for f in flagged_fields]
            })
            
        return {
            "items": results,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }
    finally:
        await conn.close()

@router.get("/{document_id}")
async def get_document(document_id: uuid.UUID):
    db_url = get_db_url()
    conn = await asyncpg.connect(db_url)
    try:
        doc = await conn.fetchrow(
            "SELECT id, file_name, document_type, status, created_at, updated_at, failed_stage, failure_reason FROM documents WHERE id = $1",
            document_id
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
            
        result = dict(doc)
        result["id"] = str(result["id"])
        result["created_at"] = result["created_at"].isoformat() if result["created_at"] else None
        result["updated_at"] = result["updated_at"].isoformat() if result["updated_at"] else None
        
        # Get extraction info if available
        ext = await conn.fetchrow("SELECT id, overall_confidence, requires_review FROM extractions WHERE document_id = $1", document_id)
        if ext:
            fields = await conn.fetch(
                "SELECT field_name, extracted_value as value, confidence, validation_error as flag FROM field_confidences WHERE extraction_id = $1",
                ext["id"]
            )
            result["extraction_result"] = {
                "overall_confidence": float(ext["overall_confidence"]) if ext["overall_confidence"] else 0.0,
                "requires_review": ext["requires_review"],
                "fields": [dict(f) for f in fields]
            }
        else:
            result["extraction_result"] = None
            
        return result
    finally:
        await conn.close()

@router.get("/{document_id}/status")
async def get_document_status(document_id: uuid.UUID):
    db_url = get_db_url()
    conn = await asyncpg.connect(db_url)
    try:
        doc = await conn.fetchrow(
            "SELECT id, status, failed_stage, failure_reason, webhook_delivered FROM documents WHERE id = $1",
            document_id
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
            
        return {
            "document_id": str(doc["id"]),
            "status": doc["status"],
            "failed_stage": doc["failed_stage"],
            "failure_reason": doc["failure_reason"],
            "webhook_delivered": doc["webhook_delivered"]
        }
    finally:
        await conn.close()
