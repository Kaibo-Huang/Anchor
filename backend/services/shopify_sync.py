"""Shopify product sync service for brand-level integration."""

from typing import Any

import httpx

from config import get_settings
from services.encryption import decrypt
from services.supabase_client import get_supabase


def fetch_shopify_products(
    shop_domain: str,
    access_token: str,
    limit: int = 250,
) -> list[dict[str, Any]]:
    """Fetch products from Shopify Admin API with pagination.

    Args:
        shop_domain: The shop domain (e.g., "brand.myshopify.com")
        access_token: Decrypted access token
        limit: Max products per page (max 250)

    Returns:
        List of product dictionaries from Shopify
    """
    settings = get_settings()
    all_products = []
    page_info = None

    with httpx.Client(timeout=30.0) as client:
        while True:
            params = {"limit": min(limit, 250), "status": "active"}
            if page_info:
                params["page_info"] = page_info

            response = client.get(
                f"https://{shop_domain}/admin/api/{settings.shopify_api_version}/products.json",
                headers={
                    "X-Shopify-Access-Token": access_token,
                    "Content-Type": "application/json",
                },
                params=params,
            )

            if response.status_code != 200:
                raise Exception(f"Shopify API error: {response.status_code} - {response.text}")

            data = response.json()
            products = data.get("products", [])
            all_products.extend(products)

            # Check for pagination
            link_header = response.headers.get("Link", "")
            if 'rel="next"' in link_header:
                # Extract page_info from Link header
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        # Format: <url?page_info=xxx>; rel="next"
                        page_info = part.split("page_info=")[1].split(">")[0]
                        break
            else:
                break

    return all_products


def transform_shopify_product(
    product: dict[str, Any],
    shop_domain: str,
) -> dict[str, Any]:
    """Transform Shopify product to our format.

    Args:
        product: Raw Shopify product data
        shop_domain: Shop domain for building checkout URLs

    Returns:
        Transformed product dictionary
    """
    variant = product["variants"][0] if product.get("variants") else {}
    image = product["images"][0] if product.get("images") else {}

    # Build checkout URL
    checkout_url = None
    if variant.get("id"):
        checkout_url = f"https://{shop_domain}/cart/{variant['id']}:1"

    return {
        "shopify_product_id": str(product["id"]),
        "title": product["title"],
        "description": product.get("body_html", ""),
        "price": float(variant.get("price", "0.00")),
        "currency": "USD",  # Shopify doesn't return currency in product endpoint
        "image_url": image.get("src"),
        "checkout_url": checkout_url,
        "status": "active" if product.get("status") == "active" else "inactive",
        "raw_data": product,
    }


def sync_store_products(store_id: str) -> dict[str, Any]:
    """Sync all products for a store from Shopify to local cache.

    Args:
        store_id: UUID of the shopify_stores record

    Returns:
        Sync result with counts
    """
    supabase = get_supabase()

    # Get store details
    store_result = supabase.table("shopify_stores").select("*").eq("id", store_id).single().execute()
    if not store_result.data:
        raise ValueError(f"Store not found: {store_id}")

    store = store_result.data
    shop_domain = store["shop_domain"]
    access_token = decrypt(store["access_token"])

    # Fetch products from Shopify
    shopify_products = fetch_shopify_products(shop_domain, access_token)

    # Transform and upsert products
    synced_count = 0
    for product in shopify_products:
        transformed = transform_shopify_product(product, shop_domain)
        transformed["store_id"] = store_id
        transformed["synced_at"] = "now()"

        # Upsert product
        supabase.table("shopify_products").upsert(
            transformed,
            on_conflict="store_id,shopify_product_id",
        ).execute()
        synced_count += 1

    # Mark products not in this sync as inactive
    current_product_ids = [str(p["id"]) for p in shopify_products]
    if current_product_ids:
        supabase.table("shopify_products").update(
            {"status": "inactive"}
        ).eq("store_id", store_id).not_.in_("shopify_product_id", current_product_ids).execute()

    # Update store last_sync_at
    supabase.table("shopify_stores").update(
        {"last_sync_at": "now()"}
    ).eq("id", store_id).execute()

    return {
        "store_id": store_id,
        "shop_domain": shop_domain,
        "products_synced": synced_count,
    }


def get_store_products(
    store_id: str,
    limit: int = 50,
    offset: int = 0,
    status: str = "active",
) -> list[dict[str, Any]]:
    """Get cached products for a store.

    Args:
        store_id: UUID of the shopify_stores record
        limit: Max products to return
        offset: Pagination offset
        status: Filter by status

    Returns:
        List of product dictionaries
    """
    supabase = get_supabase()

    result = (
        supabase.table("shopify_products")
        .select("id,shopify_product_id,title,description,price,currency,image_url,checkout_url,synced_at")
        .eq("store_id", store_id)
        .eq("status", status)
        .order("title")
        .range(offset, offset + limit - 1)
        .execute()
    )

    return result.data or []


def get_event_brand_products(event_id: str) -> list[dict[str, Any]]:
    """Get all brand products associated with an event.

    Args:
        event_id: UUID of the event

    Returns:
        List of products with store info
    """
    supabase = get_supabase()

    result = (
        supabase.table("event_brand_products")
        .select(
            "id,display_order,is_primary,"
            "store:shopify_stores(id,shop_domain,shop_name),"
            "product:shopify_products(id,title,description,price,currency,image_url,checkout_url)"
        )
        .eq("event_id", event_id)
        .order("display_order")
        .execute()
    )

    return result.data or []


def add_event_brand_products(
    event_id: str,
    store_id: str,
    product_ids: list[str],
    set_primary: bool = False,
) -> list[dict[str, Any]]:
    """Add brand products to an event.

    Args:
        event_id: UUID of the event
        store_id: UUID of the store
        product_ids: List of shopify_products UUIDs to add
        set_primary: If True, clear existing primary and set these as primary

    Returns:
        Created association records
    """
    supabase = get_supabase()

    if set_primary:
        # Clear existing primary flags for this event
        supabase.table("event_brand_products").update(
            {"is_primary": False}
        ).eq("event_id", event_id).execute()

    # Get current max display_order
    existing = (
        supabase.table("event_brand_products")
        .select("display_order")
        .eq("event_id", event_id)
        .order("display_order", desc=True)
        .limit(1)
        .execute()
    )
    next_order = (existing.data[0]["display_order"] + 1) if existing.data else 0

    # Insert new associations
    created = []
    for i, product_id in enumerate(product_ids):
        result = supabase.table("event_brand_products").upsert(
            {
                "event_id": event_id,
                "store_id": store_id,
                "product_id": product_id,
                "display_order": next_order + i,
                "is_primary": set_primary and i == 0,
            },
            on_conflict="event_id,product_id",
        ).execute()
        if result.data:
            created.extend(result.data)

    return created


def remove_event_brand_product(event_id: str, association_id: str) -> bool:
    """Remove a brand product association from an event.

    Args:
        event_id: UUID of the event
        association_id: UUID of the event_brand_products record

    Returns:
        True if deleted, False if not found
    """
    supabase = get_supabase()

    result = (
        supabase.table("event_brand_products")
        .delete()
        .eq("id", association_id)
        .eq("event_id", event_id)
        .execute()
    )

    return len(result.data or []) > 0
