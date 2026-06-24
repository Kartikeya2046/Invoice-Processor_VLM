-- Add page-level tracking for multi-page PDF support
ALTER TABLE extractions ADD COLUMN IF NOT EXISTS page_number INTEGER DEFAULT NULL;
ALTER TABLE field_confidences ADD COLUMN IF NOT EXISTS page_number INTEGER DEFAULT NULL;

COMMENT ON COLUMN extractions.page_number IS 'NULL = final merged result for the whole document. A non-null value = a raw per-page extraction snapshot taken before merging, kept for audit/debugging.';
COMMENT ON COLUMN field_confidences.page_number IS 'NULL = field value from the final merged result. A non-null value = which page this specific field value/confidence was extracted from, before merge.';

CREATE INDEX IF NOT EXISTS idx_extractions_document_id_page_number ON extractions(document_id, page_number);
CREATE INDEX IF NOT EXISTS idx_field_confidences_extraction_id_page_number ON field_confidences(extraction_id, page_number);
