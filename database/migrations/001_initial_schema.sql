-- 1. documents table
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id VARCHAR NOT NULL UNIQUE,
    original_path VARCHAR NOT NULL,
    file_name VARCHAR NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    mime_type VARCHAR NOT NULL,
    workflow VARCHAR NOT NULL,
    document_type VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'queued',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Trigger function for auto-updating updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for documents table
CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 2. extractions table
CREATE TABLE extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    extracted_json JSONB,
    raw_vlm_output TEXT,
    overall_confidence DECIMAL(5,4),
    requires_review BOOLEAN DEFAULT FALSE,
    is_approved BOOLEAN,
    approved_by VARCHAR,
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. field_confidences table
CREATE TABLE field_confidences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,
    field_name VARCHAR NOT NULL,
    extracted_value TEXT,
    confidence DECIMAL(5,4),
    is_valid BOOLEAN,
    validation_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. processing_metadata table
CREATE TABLE processing_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    preprocessing_ms INTEGER,
    classification_ms INTEGER,
    extraction_ms INTEGER,
    validation_ms INTEGER,
    total_ms INTEGER,
    vlm_model VARCHAR,
    slm_model VARCHAR,
    page_count INTEGER,
    celery_task_id VARCHAR,
    worker_hostname VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. audit_logs table
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    event_type VARCHAR NOT NULL,
    event_data JSONB,
    actor VARCHAR,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_document_type ON documents(document_type);
CREATE INDEX idx_documents_created_at ON documents(created_at);

CREATE INDEX idx_extractions_document_id ON extractions(document_id);

CREATE INDEX idx_field_confidences_extraction_id ON field_confidences(extraction_id);
CREATE INDEX idx_field_confidences_field_name ON field_confidences(field_name);

CREATE INDEX idx_processing_metadata_document_id ON processing_metadata(document_id);

CREATE INDEX idx_audit_logs_document_id ON audit_logs(document_id);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
