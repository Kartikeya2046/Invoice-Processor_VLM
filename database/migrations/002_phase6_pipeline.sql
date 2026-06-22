-- Update status column default and type
ALTER TABLE documents
ALTER COLUMN status SET DEFAULT 'pending',
ALTER COLUMN status TYPE VARCHAR(20);

-- Migrate any existing 'queued' status to 'pending'
UPDATE documents SET status = 'pending' WHERE status = 'queued';

-- Add new columns for Phase 6 pipeline tracking and webhook delivery
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS callback_url TEXT NULL,
ADD COLUMN IF NOT EXISTS failed_stage VARCHAR(20) NULL,
ADD COLUMN IF NOT EXISTS failure_reason TEXT NULL,
ADD COLUMN IF NOT EXISTS webhook_delivered BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS webhook_attempts INTEGER NOT NULL DEFAULT 0;
