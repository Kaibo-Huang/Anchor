-- Migration: Add analysis_progress field to events table
-- This field tracks real-time progress during TwelveLabs analysis

ALTER TABLE events ADD COLUMN IF NOT EXISTS analysis_progress JSONB;

-- Add comment for documentation
COMMENT ON COLUMN events.analysis_progress IS 'Real-time analysis progress tracking with stage, progress percentage, current video, and status message';
