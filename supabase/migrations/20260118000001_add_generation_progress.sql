-- Migration: Add generation_progress field to events table
-- This field tracks real-time progress during video generation

ALTER TABLE events ADD COLUMN IF NOT EXISTS generation_progress JSONB;

-- Add comment for documentation
COMMENT ON COLUMN events.generation_progress IS 'Real-time video generation progress tracking with stage, progress percentage, and status message';
