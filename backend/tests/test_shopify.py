"""
Tests for the Shopify API router.
"""
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient
import httpx


class TestShopifyAuthUrl:
    """Test Shopify OAuth URL generation."""

    def test_get_auth_url_success(self, client: TestClient, mock_redis, sample_event):
        """Test generating Shopify auth URL."""
        with patch("routers.shopify.get_redis", return_value=mock_redis):
            response = client.get(
                f"/api/events/{sample_event['id']}/shopify/auth-url",
                params={"shop": "test-store.myshopify.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "test-store.myshopify.com" in data["auth_url"]
        assert "oauth/authorize" in data["auth_url"]

    def test_get_auth_url_invalid_domain(self, client: TestClient, mock_redis, sample_event):
        """Test auth URL with invalid shop domain."""
        response = client.get(
            f"/api/events/{sample_event['id']}/shopify/auth-url",
            params={"shop": "invalid-domain.com"},
        )
        assert response.status_code == 400
        assert "Invalid shop domain" in response.json()["detail"]

    def test_get_auth_url_missing_shop(self, client: TestClient, sample_event):
        """Test auth URL without shop parameter."""
        response = client.get(f"/api/events/{sample_event['id']}/shopify/auth-url")
        assert response.status_code == 422  # Missing required query param


class TestShopifyCallback:
    """Test Shopify OAuth callback."""

    @pytest.mark.asyncio
    async def test_callback_success(self, client: TestClient, mock_redis, mock_supabase, sample_event):
        """Test successful OAuth callback."""
        # Mock Redis to return event_id
        mock_redis.get.return_value = sample_event["id"].encode()

        # Mock httpx for token exchange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "shpat_test_token"}

        with patch("routers.shopify.get_redis", return_value=mock_redis), \
             patch("routers.shopify.get_supabase", return_value=mock_supabase), \
             patch("httpx.AsyncClient") as mock_client:

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            response = client.get(
                "/api/auth/shopify/callback",
                params={
                    "code": "test_auth_code",
                    "shop": "test-store.myshopify.com",
                    "state": "valid_nonce",
                },
                follow_redirects=False,
            )

        # Should redirect to frontend
        assert response.status_code == 307

    def test_callback_invalid_state(self, client: TestClient, mock_redis, sample_event):
        """Test callback with invalid/expired state."""
        mock_redis.get.return_value = None  # State not found

        with patch("routers.shopify.get_redis", return_value=mock_redis):
            response = client.get(
                "/api/auth/shopify/callback",
                params={
                    "code": "test_code",
                    "shop": "test-store.myshopify.com",
                    "state": "invalid_nonce",
                },
            )

        assert response.status_code == 400
        assert "Invalid or expired state" in response.json()["detail"]


class TestShopifyProducts:
    """Test Shopify products endpoint."""

    @pytest.mark.asyncio
    async def test_get_products_success(self, client: TestClient, mock_supabase, sample_event, sample_shopify_products):
        """Test fetching products from connected store."""
        # Setup event with Shopify connected
        event_with_shopify = {
            **sample_event,
            "shopify_store_url": "https://test-store.myshopify.com",
            "shopify_access_token": "encrypted_token",
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[event_with_shopify]
        )

        # Mock Shopify API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_shopify_products

        with patch("routers.shopify.get_supabase", return_value=mock_supabase), \
             patch("routers.shopify.decrypt", return_value="decrypted_token"), \
             patch("httpx.AsyncClient") as mock_client:

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            response = client.get(f"/api/events/{sample_event['id']}/shopify/products")

        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert len(data["products"]) == 1
        assert data["products"][0]["title"] == "Test Product"
        assert data["products"][0]["price"] == "29.99"

    def test_get_products_not_connected(self, client: TestClient, mock_supabase, sample_event):
        """Test getting products when Shopify not connected."""
        # Event without Shopify token
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{**sample_event, "shopify_access_token": None}]
        )

        with patch("routers.shopify.get_supabase", return_value=mock_supabase):
            response = client.get(f"/api/events/{sample_event['id']}/shopify/products")

        assert response.status_code == 400
        assert "not connected" in response.json()["detail"]

    def test_get_products_event_not_found(self, client: TestClient, mock_supabase_empty):
        """Test getting products for non-existent event."""
        with patch("routers.shopify.get_supabase", return_value=mock_supabase_empty.return_value):
            response = client.get("/api/events/nonexistent-id/shopify/products")
        assert response.status_code == 404


class TestShopifyDisconnect:
    """Test Shopify disconnect endpoint."""

    def test_disconnect_success(self, client: TestClient, mock_supabase, sample_event):
        """Test disconnecting Shopify store."""
        with patch("routers.shopify.get_supabase", return_value=mock_supabase):
            response = client.delete(f"/api/events/{sample_event['id']}/shopify")

        assert response.status_code == 200
        assert response.json()["message"] == "Shopify disconnected"

    def test_disconnect_not_found(self, client: TestClient, mock_supabase, sample_event):
        """Test disconnecting from non-existent event."""
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with patch("routers.shopify.get_supabase", return_value=mock_supabase):
            response = client.delete(f"/api/events/{sample_event['id']}/shopify")

        assert response.status_code == 404


class TestVerifyHmac:
    """Test HMAC verification helper."""

    def test_verify_hmac_valid(self):
        """Test HMAC verification with valid signature."""
        from routers.shopify import verify_shopify_hmac
        import hashlib
        import hmac as hmac_lib

        secret = "test_secret"
        params = {"code": "abc", "shop": "test.myshopify.com", "state": "xyz"}

        # Calculate expected HMAC
        sorted_params = sorted(params.items())
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)
        expected_hmac = hmac_lib.new(
            secret.encode(), query_string.encode(), hashlib.sha256
        ).hexdigest()

        params_with_hmac = {**params, "hmac": expected_hmac}
        assert verify_shopify_hmac(params_with_hmac, secret) is True

    def test_verify_hmac_invalid(self):
        """Test HMAC verification with invalid signature."""
        from routers.shopify import verify_shopify_hmac

        params = {"code": "abc", "shop": "test.myshopify.com", "hmac": "invalid_hmac"}
        assert verify_shopify_hmac(params, "secret") is False

    def test_verify_hmac_missing(self):
        """Test HMAC verification with missing signature."""
        from routers.shopify import verify_shopify_hmac

        params = {"code": "abc", "shop": "test.myshopify.com"}
        assert verify_shopify_hmac(params, "secret") is False
