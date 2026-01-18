-- Migration: Disable Row Level Security
-- WARNING: This removes all RLS protection. Use only for development/hackathon.

-- Disable RLS on core tables
ALTER TABLE events DISABLE ROW LEVEL SECURITY;
ALTER TABLE videos DISABLE ROW LEVEL SECURITY;
ALTER TABLE timelines DISABLE ROW LEVEL SECURITY;
ALTER TABLE custom_reels DISABLE ROW LEVEL SECURITY;

-- Disable RLS on Shopify tables
ALTER TABLE shopify_stores DISABLE ROW LEVEL SECURITY;
ALTER TABLE shopify_products DISABLE ROW LEVEL SECURITY;
ALTER TABLE event_brand_products DISABLE ROW LEVEL SECURITY;
