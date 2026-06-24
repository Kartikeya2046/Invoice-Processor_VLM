-- Add page_image_paths for storing rendered PDF images
ALTER TABLE processing_metadata ADD COLUMN IF NOT EXISTS page_image_paths JSONB DEFAULT '[]'::jsonb;
COMMENT ON COLUMN processing_metadata.page_image_paths IS 'Array of local file paths for each rendered page of the document (or single image).';
