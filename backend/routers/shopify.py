import hashlib
import hmac
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from config import get_settings
from services.encryption import encrypt, decrypt
from services.supabase_client import get_supabase
from services.redis_client import get_redis

router = APIRouter()


class ShopDomain(BaseModel):
    shop: str


@router.get("/api/events/{event_id}/shopify/auth-url")
async def get_shopify_auth_url(event_id: str, shop: str):
    """Generate Shopify OAuth URL."""
    settings = get_settings()

    # Validate shop domain
    if not shop.endswith(".myshopify.com"):
        raise HTTPException(status_code=400, detail="Invalid shop domain")

    # Generate nonce for security
    nonce = secrets.token_urlsafe(16)

    # Store nonce + event_id in Redis (10 min expiry)
    redis = get_redis()
    redis.setex(f"shopify_oauth:{nonce}", 600, event_id)

    # Build OAuth URL
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
async def shopify_oauth_callback(
    request: Request,
    code: str,
    shop: str,
    state: str,
    hmac: str | None = None,
):
    """Handle Shopify OAuth callback."""
    settings = get_settings()
    redis = get_redis()
    supabase = get_supabase()

    # Verify HMAC if provided
    if hmac and not verify_shopify_hmac(dict(request.query_params), settings.shopify_api_secret):
        raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    # Verify nonce
    event_id = redis.get(f"shopify_oauth:{state}")
    if not event_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    event_id = event_id.decode() if isinstance(event_id, bytes) else event_id

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

    # Store encrypted token in database
    supabase.table("events").update(
        {
            "shopify_store_url": f"https://{shop}",
            "shopify_access_token": encrypt(access_token),
        }
    ).eq("id", event_id).execute()

    # Clean up nonce
    redis.delete(f"shopify_oauth:{state}")

    # Redirect to frontend
    return RedirectResponse(f"{settings.frontend_url}/events/{event_id}?shopify=connected")


@router.get("/api/events/{event_id}/shopify/products")
async def get_shopify_products(event_id: str, limit: int = 10):
    """Fetch products from connected Shopify store."""
    settings = get_settings()
    supabase = get_supabase()

    # Get event with Shopify credentials
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

    # Decrypt access token
    access_token = decrypt(event["shopify_access_token"])
    shop_url = event["shopify_store_url"]

    # Fetch products from Shopify
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

    # Transform to our format
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
async def disconnect_shopify(event_id: str):
    """Disconnect Shopify store from event."""
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


def verify_shopify_hmac(params: dict, secret: str) -> bool:
    """Verify Shopify HMAC signature for security."""
    provided_hmac = params.pop("hmac", None)
    if not provided_hmac:
        return False

    # Build sorted query string
    sorted_params = sorted(params.items())
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

    # Calculate HMAC
    computed_hmac = hmac.new(
        secret.encode(), query_string.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_hmac, provided_hmac)
