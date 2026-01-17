"""Shopify integration endpoints for brand-level store management."""

import hashlib
import hmac
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from config import get_settings
from services.encryption import encrypt, decrypt
from services.supabase_client import get_supabase
from services.redis_client import get_redis
from services.shopify_sync import (
    get_store_products,
    get_event_brand_products,
    add_event_brand_products,
    remove_event_brand_product,
)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class AddBrandProductsRequest(BaseModel):
    store_id: str
    product_ids: list[str]
    set_primary: bool = False


class StoreResponse(BaseModel):
    id: str
    shop_domain: str
    shop_name: str | None
    status: str
    installed_at: str
    last_sync_at: str | None
    product_count: int | None = None


class ProductResponse(BaseModel):
    id: str
    title: str
    description: str | None
    price: float
    currency: str
    image_url: str | None
    checkout_url: str | None


# ============================================================================
# Store Management Endpoints (Brand-facing)
# ============================================================================


@router.get("/api/shopify/install")
async def get_shopify_install_url(shop: str):
    """Generate OAuth install URL for brands to install the app.

    This is the main entry point for brand stores to install the app.
    The flow is: Brand clicks install link -> OAuth -> Callback -> Store created

    Args:
        shop: Shopify store domain (e.g., "brand-name.myshopify.com")

    Returns:
        install_url: URL to redirect the brand to for OAuth
    """
    settings = get_settings()

    # Validate shop domain
    if not shop.endswith(".myshopify.com"):
        raise HTTPException(status_code=400, detail="Invalid shop domain")

    # Generate nonce for security
    nonce = secrets.token_urlsafe(16)

    # Store nonce in Redis (10 min expiry) - no event_id for store-level install
    redis = get_redis()
    redis.setex(f"shopify_install:{nonce}", 600, shop)

    # Build OAuth URL
    params = {
        "client_id": settings.shopify_api_key,
        "scope": "read_products,read_product_listings,read_files",
        "redirect_uri": f"{settings.base_url}/api/shopify/callback",
        "state": nonce,
    }

    install_url = f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"

    return {"install_url": install_url, "shop": shop}


@router.get("/api/shopify/callback")
async def shopify_install_callback(
    request: Request,
    code: str,
    shop: str,
    state: str,
    hmac: str | None = None,
):
    """Handle Shopify OAuth callback after brand installs the app.

    Creates or updates the store record with the access token.
    Triggers an async product sync task.

    Args:
        code: OAuth authorization code
        shop: Shop domain
        state: Nonce for verification
        hmac: HMAC signature for verification
    """
    settings = get_settings()
    redis = get_redis()
    supabase = get_supabase()

    # Verify HMAC if provided
    if hmac and not verify_shopify_hmac(dict(request.query_params), settings.shopify_api_secret):
        raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    # Verify nonce
    stored_shop = redis.get(f"shopify_install:{state}")
    if not stored_shop:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    stored_shop = stored_shop.decode() if isinstance(stored_shop, bytes) else stored_shop
    if stored_shop != shop:
        raise HTTPException(status_code=400, detail="Shop domain mismatch")

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": settings.shopify_api_key,
                "client_secret": settings.shopify_api_secret,
                "code": code,
            },
        )

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to get access token")

        data = response.json()
        access_token = data["access_token"]
        scopes = data.get("scope", "read_products,read_product_listings,read_files")

    # Get shop info for display name
    shop_name = None
    async with httpx.AsyncClient() as client:
        shop_response = await client.get(
            f"https://{shop}/admin/api/{settings.shopify_api_version}/shop.json",
            headers={"X-Shopify-Access-Token": access_token},
        )
        if shop_response.status_code == 200:
            shop_data = shop_response.json().get("shop", {})
            shop_name = shop_data.get("name")

    # Upsert store record (handles reinstalls)
    result = supabase.table("shopify_stores").upsert(
        {
            "shop_domain": shop,
            "shop_name": shop_name,
            "access_token": encrypt(access_token),
            "scopes": scopes,
            "status": "active",
            "installed_at": "now()",
        },
        on_conflict="shop_domain",
    ).execute()

    store_id = result.data[0]["id"] if result.data else None

    # Clean up nonce
    redis.delete(f"shopify_install:{state}")

    # Trigger async product sync
    if store_id:
        from worker import sync_store_products_task
        sync_store_products_task.delay(store_id)

    # Redirect to frontend success page
    return RedirectResponse(f"{settings.frontend_url}/brands/connected?shop={shop}")


@router.get("/api/shopify/stores")
async def list_stores(
    status: str = Query("active", description="Filter by status"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
):
    """List all available brand stores.

    Returns stores that have installed the app, allowing event organizers
    to browse and select products from these stores.
    """
    supabase = get_supabase()

    query = (
        supabase.table("shopify_stores")
        .select("id,shop_domain,shop_name,status,installed_at,last_sync_at")
    )

    if status:
        query = query.eq("status", status)

    result = query.order("shop_name").range(offset, offset + limit - 1).execute()

    # Get product counts for each store
    stores = []
    for store in result.data or []:
        count_result = (
            supabase.table("shopify_products")
            .select("id", count="exact")
            .eq("store_id", store["id"])
            .eq("status", "active")
            .execute()
        )
        store["product_count"] = count_result.count or 0
        stores.append(store)

    return {"stores": stores}


@router.get("/api/shopify/stores/{store_id}")
async def get_store(store_id: str):
    """Get store details including product count."""
    supabase = get_supabase()

    store_result = (
        supabase.table("shopify_stores")
        .select("id,shop_domain,shop_name,status,installed_at,last_sync_at")
        .eq("id", store_id)
        .single()
        .execute()
    )

    if not store_result.data:
        raise HTTPException(status_code=404, detail="Store not found")

    store = store_result.data

    # Get product count
    count_result = (
        supabase.table("shopify_products")
        .select("id", count="exact")
        .eq("store_id", store_id)
        .eq("status", "active")
        .execute()
    )
    store["product_count"] = count_result.count or 0

    return store


@router.post("/api/shopify/stores/{store_id}/sync")
async def trigger_store_sync(store_id: str):
    """Trigger product sync for a store.

    This is called manually to refresh the product cache, or can be
    triggered by webhooks (future enhancement).
    """
    supabase = get_supabase()

    # Verify store exists
    store_result = supabase.table("shopify_stores").select("id,status").eq("id", store_id).single().execute()
    if not store_result.data:
        raise HTTPException(status_code=404, detail="Store not found")

    if store_result.data["status"] != "active":
        raise HTTPException(status_code=400, detail="Store is not active")

    # Trigger async sync
    from worker import sync_store_products_task
    task = sync_store_products_task.delay(store_id)

    return {"message": "Sync started", "task_id": task.id, "store_id": store_id}


@router.get("/api/shopify/stores/{store_id}/products")
async def list_store_products(
    store_id: str,
    limit: int = Query(50, le=250),
    offset: int = Query(0, ge=0),
):
    """Get cached products for a store."""
    products = get_store_products(store_id, limit=limit, offset=offset)
    return {"products": products}


# ============================================================================
# Event-Brand Association Endpoints (Organizer-facing)
# ============================================================================


@router.get("/api/events/{event_id}/brands")
async def get_event_brands(event_id: str):
    """Get all brand products associated with an event.

    Returns products from all brand stores that have been selected
    for use in this event's video ads.
    """
    products = get_event_brand_products(event_id)
    return {"brand_products": products}


@router.post("/api/events/{event_id}/brands")
async def add_event_brands(event_id: str, request: AddBrandProductsRequest):
    """Add brand products to an event.

    Allows event organizers to select which products from which stores
    should be featured in the video ads.
    """
    supabase = get_supabase()

    # Verify event exists
    event_result = supabase.table("events").select("id").eq("id", event_id).single().execute()
    if not event_result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    # Verify store exists and is active
    store_result = (
        supabase.table("shopify_stores")
        .select("id,status")
        .eq("id", request.store_id)
        .single()
        .execute()
    )
    if not store_result.data:
        raise HTTPException(status_code=404, detail="Store not found")
    if store_result.data["status"] != "active":
        raise HTTPException(status_code=400, detail="Store is not active")

    # Add products
    created = add_event_brand_products(
        event_id=event_id,
        store_id=request.store_id,
        product_ids=request.product_ids,
        set_primary=request.set_primary,
    )

    return {"message": "Products added", "associations": created}


@router.delete("/api/events/{event_id}/brands/{association_id}")
async def remove_event_brand(event_id: str, association_id: str):
    """Remove a brand product from an event."""
    deleted = remove_event_brand_product(event_id, association_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Association not found")

    return {"message": "Product removed"}


# ============================================================================
# Legacy Endpoints (Backward Compatibility)
# ============================================================================


@router.get("/api/events/{event_id}/shopify/auth-url")
async def get_shopify_auth_url_legacy(event_id: str, shop: str):
    """Legacy: Generate Shopify OAuth URL for per-event connection.

    DEPRECATED: Use /api/shopify/install for store-level installation.
    This endpoint is kept for backward compatibility during migration.
    """
    settings = get_settings()

    if not shop.endswith(".myshopify.com"):
        raise HTTPException(status_code=400, detail="Invalid shop domain")

    nonce = secrets.token_urlsafe(16)

    redis = get_redis()
    redis.setex(f"shopify_oauth:{nonce}", 600, event_id)

    params = {
        "client_id": settings.shopify_api_key,
        "scope": "read_products,read_product_listings,read_files",
        "redirect_uri": f"{settings.base_url}/api/auth/shopify/callback",
        "state": nonce,
        "grant_options[]": "per-user",
    }

    auth_url = f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"

    return {"auth_url": auth_url}


@router.get("/api/auth/shopify/callback")
async def shopify_oauth_callback_legacy(
    request: Request,
    code: str,
    shop: str,
    state: str,
    hmac: str | None = None,
):
    """Legacy: Handle Shopify OAuth callback for per-event connection.

    DEPRECATED: New installations should use /api/shopify/callback.
    """
    settings = get_settings()
    redis = get_redis()
    supabase = get_supabase()

    if hmac and not verify_shopify_hmac(dict(request.query_params), settings.shopify_api_secret):
        raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    event_id = redis.get(f"shopify_oauth:{state}")
    if not event_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    event_id = event_id.decode() if isinstance(event_id, bytes) else event_id

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": settings.shopify_api_key,
                "client_secret": settings.shopify_api_secret,
                "code": code,
            },
        )

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to get access token")

        data = response.json()
        access_token = data["access_token"]

    # Store on event (legacy)
    supabase.table("events").update(
        {
            "shopify_store_url": f"https://{shop}",
            "shopify_access_token": encrypt(access_token),
        }
    ).eq("id", event_id).execute()

    # Also create store-level record for migration path
    supabase.table("shopify_stores").upsert(
        {
            "shop_domain": shop,
            "access_token": encrypt(access_token),
            "scopes": "read_products,read_product_listings,read_files",
            "status": "active",
        },
        on_conflict="shop_domain",
    ).execute()

    redis.delete(f"shopify_oauth:{state}")

    return RedirectResponse(f"{settings.frontend_url}/events/{event_id}?shopify=connected")


@router.get("/api/events/{event_id}/shopify/products")
async def get_shopify_products_legacy(event_id: str, limit: int = 10):
    """Legacy: Fetch products from connected Shopify store.

    DEPRECATED: Use /api/shopify/stores/{store_id}/products instead.
    """
    settings = get_settings()
    supabase = get_supabase()

    result = (
        supabase.table("events")
        .select("shopify_store_url,shopify_access_token")
        .eq("id", event_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    event = result.data[0]

    if not event.get("shopify_access_token"):
        raise HTTPException(status_code=400, detail="Shopify store not connected")

    access_token = decrypt(event["shopify_access_token"])
    shop_url = event["shopify_store_url"]

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{shop_url}/admin/api/{settings.shopify_api_version}/products.json",
            headers={
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json",
            },
            params={"limit": limit, "status": "active"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=500, detail=f"Shopify API error: {response.text}"
            )

        products = response.json().get("products", [])

    transformed = []
    for p in products:
        variant = p["variants"][0] if p.get("variants") else {}
        image = p["images"][0] if p.get("images") else {}

        transformed.append(
            {
                "id": str(p["id"]),
                "title": p["title"],
                "description": p.get("body_html", ""),
                "price": variant.get("price", "0.00"),
                "currency": variant.get("currency_code", "USD"),
                "image_url": image.get("src"),
                "checkout_url": f"{shop_url}/cart/{variant.get('id', '')}:1"
                if variant.get("id")
                else None,
            }
        )

    return {"products": transformed}


@router.delete("/api/events/{event_id}/shopify")
async def disconnect_shopify_legacy(event_id: str):
    """Legacy: Disconnect Shopify store from event."""
    supabase = get_supabase()

    result = (
        supabase.table("events")
        .update({"shopify_store_url": None, "shopify_access_token": None})
        .eq("id", event_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    return {"message": "Shopify disconnected"}


# ============================================================================
# Helper Functions
# ============================================================================


def verify_shopify_hmac(params: dict, secret: str) -> bool:
    """Verify Shopify HMAC signature for security."""
    provided_hmac = params.pop("hmac", None)
    if not provided_hmac:
        return False

    sorted_params = sorted(params.items())
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

    computed_hmac = hmac.new(
        secret.encode(), query_string.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_hmac, provided_hmac)
