-- Migration: Shopify Brand-Level Install
-- Creates tables for store-level Shopify integration (decoupled from events)

-- 1. shopify_stores: Store brand connections independently
CREATE TABLE IF NOT EXISTS shopify_stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_domain TEXT NOT NULL UNIQUE,           -- "brand-name.myshopify.com"
    shop_name TEXT,                              -- Display name
    access_token TEXT NOT NULL,                  -- Encrypted (Fernet)
    scopes TEXT NOT NULL,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'disconnected', 'revoked')),
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    last_sync_at TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. shopify_products: Local product cache
CREATE TABLE IF NOT EXISTS shopify_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID REFERENCES shopify_stores(id) ON DELETE CASCADE,
    shopify_product_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price DECIMAL(10, 2),
    currency TEXT DEFAULT 'USD',
    image_url TEXT,
    checkout_url TEXT,
    status TEXT DEFAULT 'active',
    raw_data JSONB,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(store_id, shopify_product_id)
);

-- 3. event_brand_products: Many-to-many association between events and brand products
CREATE TABLE IF NOT EXISTS event_brand_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    store_id UUID REFERENCES shopify_stores(id) ON DELETE CASCADE,
    product_id UUID REFERENCES shopify_products(id) ON DELETE SET NULL,
    display_order INTEGER DEFAULT 0,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(event_id, product_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_shopify_stores_shop_domain ON shopify_stores(shop_domain);
CREATE INDEX IF NOT EXISTS idx_shopify_stores_status ON shopify_stores(status);
CREATE INDEX IF NOT EXISTS idx_shopify_products_store_id ON shopify_products(store_id);
CREATE INDEX IF NOT EXISTS idx_shopify_products_status ON shopify_products(status);
CREATE INDEX IF NOT EXISTS idx_event_brand_products_event_id ON event_brand_products(event_id);
CREATE INDEX IF NOT EXISTS idx_event_brand_products_store_id ON event_brand_products(store_id);

-- Enable RLS
ALTER TABLE shopify_stores ENABLE ROW LEVEL SECURITY;
ALTER TABLE shopify_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_brand_products ENABLE ROW LEVEL SECURITY;

-- RLS Policies for shopify_stores (publicly readable, write via service role only)
DROP POLICY IF EXISTS "Anyone can view active stores" ON shopify_stores;
DROP POLICY IF EXISTS "Service role can manage stores" ON shopify_stores;

CREATE POLICY "Anyone can view active stores" ON shopify_stores
    FOR SELECT USING (status = 'active');

-- Note: Store creation/updates happen via service role (backend API)
-- The backend uses the service role key, not anon key

-- RLS Policies for shopify_products (publicly readable)
DROP POLICY IF EXISTS "Anyone can view active products" ON shopify_products;

CREATE POLICY "Anyone can view active products" ON shopify_products
    FOR SELECT USING (status = 'active');

-- RLS Policies for event_brand_products (tied to event ownership)
DROP POLICY IF EXISTS "Users can manage brand products for own events" ON event_brand_products;

CREATE POLICY "Users can manage brand products for own events" ON event_brand_products
    FOR ALL USING (event_id IN (SELECT id FROM events WHERE user_id = auth.uid()));

-- Data migration: Migrate existing event Shopify connections to new tables
-- This is a safe migration that doesn't delete the old columns yet

-- Step 1: Insert existing stores (ON CONFLICT handles duplicates)
INSERT INTO shopify_stores (shop_domain, access_token, scopes, status, installed_at)
SELECT DISTINCT
    REPLACE(REPLACE(shopify_store_url, 'https://', ''), 'http://', ''),
    shopify_access_token,
    'read_products,read_product_listings,read_files',
    'active',
    created_at
FROM events
WHERE shopify_store_url IS NOT NULL
  AND shopify_access_token IS NOT NULL
ON CONFLICT (shop_domain) DO NOTHING;

-- Step 2: Create associations for existing connections
INSERT INTO event_brand_products (event_id, store_id, is_primary)
SELECT
    e.id,
    s.id,
    true
FROM events e
JOIN shopify_stores s ON s.shop_domain = REPLACE(REPLACE(e.shopify_store_url, 'https://', ''), 'http://', '')
WHERE e.shopify_store_url IS NOT NULL
ON CONFLICT (event_id, product_id) DO NOTHING;

-- Note: Old columns (shopify_store_url, shopify_access_token) on events table are kept
-- for backward compatibility. They can be removed in a future migration.
