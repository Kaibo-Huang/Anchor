"""
Pytest configuration and fixtures for Anchor backend tests.
"""
import os
from typing import Generator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# Set test environment variables before importing app
os.environ.update({
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_KEY": "test-key",
    "AWS_ACCESS_KEY_ID": "test-access-key",
    "AWS_SECRET_ACCESS_KEY": "test-secret-key",
    "S3_BUCKET": "test-bucket",
    "REDIS_URL": "redis://localhost:6379",
    "SHOPIFY_API_KEY": "test-shopify-key",
    "SHOPIFY_API_SECRET": "test-shopify-secret",
    "SHOPIFY_API_VERSION": "2024-01",
    "TWELVELABS_API_KEY": "test-twelvelabs-key",
    "GOOGLE_API_KEY": "test-google-key",
    "ENCRYPTION_KEY": "owS2jbTMv6SHeGD3p26TcfoFRoNDUETWggBeg_Rjq3c=",  # Valid Fernet key
    "BASE_URL": "http://localhost:8000",
    "FRONTEND_URL": "http://localhost:3000",
})

from main import app
from services.supabase_client import get_supabase


# Sample data for tests
SAMPLE_EVENT_ID = str(uuid4())
SAMPLE_VIDEO_ID = str(uuid4())
SAMPLE_REEL_ID = str(uuid4())


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI app."""
    with TestClient(app) as c:
        yield c


def _clear_supabase_cache():
    """Clear the lru_cache for get_supabase."""
    get_supabase.cache_clear()


@pytest.fixture
def mock_supabase():
    """Mock Supabase client for database operations."""
    _clear_supabase_cache()

    # Patch in all modules that import get_supabase
    with patch("routers.events.get_supabase") as mock_events, \
         patch("routers.videos.get_supabase") as mock_videos, \
         patch("routers.reels.get_supabase") as mock_reels, \
         patch("routers.shopify.get_supabase") as mock_shopify, \
         patch("services.supabase_client.get_supabase") as mock_service:

        supabase = MagicMock()

        # Apply mock to all patched locations
        for mock in [mock_events, mock_videos, mock_reels, mock_shopify, mock_service]:
            mock.return_value = supabase

        # Default successful responses
        supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": SAMPLE_EVENT_ID, "name": "Test Event", "event_type": "sports", "status": "created"}]
        )
        supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": SAMPLE_EVENT_ID, "name": "Test Event", "event_type": "sports", "status": "created"}]
        )
        supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": SAMPLE_EVENT_ID}]
        )

        yield supabase


@pytest.fixture
def mock_supabase_empty():
    """Mock Supabase client that returns empty results."""
    _clear_supabase_cache()

    with patch("routers.events.get_supabase") as mock_events, \
         patch("routers.videos.get_supabase") as mock_videos, \
         patch("routers.reels.get_supabase") as mock_reels, \
         patch("routers.shopify.get_supabase") as mock_shopify, \
         patch("services.supabase_client.get_supabase") as mock_service:

        supabase = MagicMock()

        for mock in [mock_events, mock_videos, mock_reels, mock_shopify, mock_service]:
            mock.return_value = supabase

        supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

        yield supabase


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch("routers.shopify.get_redis") as mock_shopify, \
         patch("services.redis_client.get_redis") as mock_service:
        redis = MagicMock()
        mock_shopify.return_value = redis
        mock_service.return_value = redis

        redis.get.return_value = SAMPLE_EVENT_ID.encode()
        redis.setex.return_value = True
        redis.delete.return_value = 1

        yield redis


@pytest.fixture
def mock_s3():
    """Mock S3 operations."""
    with patch("routers.videos.generate_presigned_upload_url") as mock_videos, \
         patch("services.s3_client.generate_presigned_upload_url") as mock_service:
        mock_videos.return_value = "https://test-bucket.s3.amazonaws.com/presigned-url"
        mock_service.return_value = "https://test-bucket.s3.amazonaws.com/presigned-url"
        yield mock_videos


@pytest.fixture
def mock_celery_tasks():
    """Mock Celery tasks to prevent actual task execution."""
    with patch("worker.analyze_videos_task") as analyze_mock, \
         patch("worker.generate_video_task") as generate_mock, \
         patch("worker.analyze_music_task") as music_mock, \
         patch("worker.generate_highlight_reel_task") as reel_mock:

        # Create task result mocks
        for task_mock in [analyze_mock, generate_mock, music_mock, reel_mock]:
            task_result = MagicMock()
            task_result.id = str(uuid4())
            task_mock.delay.return_value = task_result

        yield {
            "analyze_videos": analyze_mock,
            "generate_video": generate_mock,
            "analyze_music": music_mock,
            "generate_highlight_reel": reel_mock,
        }


@pytest.fixture
def sample_event():
    """Sample event data for testing."""
    return {
        "id": SAMPLE_EVENT_ID,
        "name": "Championship Game",
        "event_type": "sports",
        "status": "created",
        "user_id": None,
        "shopify_store_url": None,
        "sponsor_name": None,
        "master_video_url": None,
        "music_url": None,
    }


@pytest.fixture
def sample_event_analyzed():
    """Sample analyzed event data."""
    return {
        "id": SAMPLE_EVENT_ID,
        "name": "Championship Game",
        "event_type": "sports",
        "status": "analyzed",
        "user_id": None,
        "shopify_store_url": None,
        "sponsor_name": None,
        "master_video_url": None,
        "music_url": None,
        "twelvelabs_index_id": "test-index-id",
    }


@pytest.fixture
def sample_video():
    """Sample video data."""
    return {
        "id": SAMPLE_VIDEO_ID,
        "event_id": SAMPLE_EVENT_ID,
        "original_url": f"s3://test-bucket/events/{SAMPLE_EVENT_ID}/videos/{SAMPLE_VIDEO_ID}.mp4",
        "angle_type": "wide",
        "status": "uploaded",
        "sync_offset_ms": 0,
        "analysis_data": None,
    }


@pytest.fixture
def sample_reel():
    """Sample reel data."""
    return {
        "id": SAMPLE_REEL_ID,
        "event_id": SAMPLE_EVENT_ID,
        "query": "me",
        "vibe": "high_energy",
        "output_url": "https://test-bucket.s3.amazonaws.com/reels/test.mp4",
        "moments": [{"start": 0, "end": 5000}],
        "duration_sec": 30,
        "status": "completed",
    }


@pytest.fixture
def sample_shopify_products():
    """Sample Shopify products response."""
    return {
        "products": [
            {
                "id": 123456,
                "title": "Test Product",
                "body_html": "A great product",
                "variants": [{"id": 789, "price": "29.99", "currency_code": "USD"}],
                "images": [{"src": "https://cdn.shopify.com/test.jpg"}],
            }
        ]
    }


SAMPLE_STORE_ID = str(uuid4())
SAMPLE_PRODUCT_ID = str(uuid4())


@pytest.fixture
def sample_store():
    """Sample Shopify store data."""
    return {
        "id": SAMPLE_STORE_ID,
        "shop_domain": "test-brand.myshopify.com",
        "shop_name": "Test Brand",
        "status": "active",
        "installed_at": "2024-01-15T10:00:00Z",
        "last_sync_at": "2024-01-15T10:05:00Z",
        "scopes": "read_products,read_product_listings,read_files",
    }


@pytest.fixture
def sample_cached_product():
    """Sample cached Shopify product data."""
    return {
        "id": SAMPLE_PRODUCT_ID,
        "store_id": SAMPLE_STORE_ID,
        "shopify_product_id": "123456",
        "title": "Test Product",
        "description": "A great product",
        "price": 29.99,
        "currency": "USD",
        "image_url": "https://cdn.shopify.com/test.jpg",
        "checkout_url": "https://test-brand.myshopify.com/cart/789:1",
        "status": "active",
        "synced_at": "2024-01-15T10:05:00Z",
    }


@pytest.fixture
def sample_event_brand_product():
    """Sample event-brand product association."""
    return {
        "id": str(uuid4()),
        "event_id": SAMPLE_EVENT_ID,
        "store_id": SAMPLE_STORE_ID,
        "product_id": SAMPLE_PRODUCT_ID,
        "display_order": 0,
        "is_primary": True,
    }
