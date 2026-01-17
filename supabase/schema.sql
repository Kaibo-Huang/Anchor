-- Anchor Database Schema
-- Run this in Supabase SQL Editor to set up tables and RLS policies

-- Events table
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    name TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('sports', 'ceremony', 'performance')),
    status TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'uploading', 'analyzing', 'analyzed', 'generating', 'completed', 'failed')),
    shopify_store_url TEXT,
    shopify_access_token TEXT,  -- Encrypted with Fernet
    sponsor_name TEXT,
    master_video_url TEXT,
    music_url TEXT,
    music_metadata JSONB,
    twelvelabs_index_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Videos table
CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    original_url TEXT NOT NULL,
    angle_type TEXT NOT NULL CHECK (angle_type IN ('wide', 'closeup', 'crowd', 'goal_angle', 'stage', 'other')),
    sync_offset_ms INTEGER DEFAULT 0,
    analysis_data JSONB,
    twelvelabs_video_id TEXT,
    status TEXT NOT NULL DEFAULT 'uploading' CHECK (status IN ('uploading', 'uploaded', 'analyzing', 'analyzed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Timelines table
CREATE TABLE IF NOT EXISTS timelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id) ON DELETE CASCADE UNIQUE,
    segments JSONB NOT NULL DEFAULT '[]',
    zooms JSONB NOT NULL DEFAULT '[]',
    ad_slots JSONB NOT NULL DEFAULT '[]',
    chapters JSONB NOT NULL DEFAULT '[]',
    beat_synced BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Custom reels table
CREATE TABLE IF NOT EXISTS custom_reels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    vibe TEXT NOT NULL CHECK (vibe IN ('high_energy', 'emotional', 'calm')),
    output_url TEXT,
    moments JSONB,
    duration_sec INTEGER,
    status TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_videos_event_id ON videos(event_id);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_custom_reels_event_id ON custom_reels(event_id);
CREATE INDEX IF NOT EXISTS idx_custom_reels_status ON custom_reels(status);

-- Enable RLS
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE videos ENABLE ROW LEVEL SECURITY;
ALTER TABLE timelines ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_reels ENABLE ROW LEVEL SECURITY;

-- RLS Policies (simple: users can only access their own events)
-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Users can manage own events" ON events;
DROP POLICY IF EXISTS "Users can manage videos in own events" ON videos;
DROP POLICY IF EXISTS "Users can manage timelines in own events" ON timelines;
DROP POLICY IF EXISTS "Users can manage reels in own events" ON custom_reels;

-- Create policies
CREATE POLICY "Users can manage own events" ON events
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage videos in own events" ON videos
    FOR ALL USING (event_id IN (SELECT id FROM events WHERE user_id = auth.uid()));

CREATE POLICY "Users can manage timelines in own events" ON timelines
    FOR ALL USING (event_id IN (SELECT id FROM events WHERE user_id = auth.uid()));

CREATE POLICY "Users can manage reels in own events" ON custom_reels
    FOR ALL USING (event_id IN (SELECT id FROM events WHERE user_id = auth.uid()));

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for events updated_at
DROP TRIGGER IF EXISTS events_updated_at ON events;
CREATE TRIGGER events_updated_at
    BEFORE UPDATE ON events
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Sample music_metadata JSONB structure:
-- {
--   "tempo_bpm": 128.5,
--   "beat_times_ms": [0, 468, 937, ...],
--   "intro_end_ms": 2500,
--   "outro_start_ms": 175000,
--   "duration_ms": 180000,
--   "intensity_curve": [0.2, 0.3, 0.8, ...]
-- }

-- Sample analysis_data JSONB structure:
-- {
--   "twelvelabs_video_id": "abc123",
--   "embeddings": [
--     {"start_time": 0, "end_time": 5, "embedding": [0.1, 0.2, ...]},
--     ...
--   ]
-- }

-- Sample segments JSONB structure:
-- [
--   {"start_ms": 0, "end_ms": 4000, "video_id": "uuid1"},
--   {"start_ms": 4000, "end_ms": 8000, "video_id": "uuid2"},
--   ...
-- ]

-- Sample chapters JSONB structure:
-- [
--   {"timestamp_ms": 0, "title": "Start", "type": "section"},
--   {"timestamp_ms": 60000, "title": "Goal", "type": "highlight"},
--   ...
-- ]
