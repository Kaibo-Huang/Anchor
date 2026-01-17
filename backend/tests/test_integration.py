"""
Integration tests for the Anchor backend.

These tests verify end-to-end workflows with mocked external services.
"""
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


class TestEventWorkflow:
    """Test the complete event workflow from creation to video generation."""

    def test_complete_event_workflow(self, client: TestClient, mock_supabase, mock_s3, mock_celery_tasks):
        """Test full workflow: create event -> upload videos -> analyze -> generate."""
        # Step 1: Create event
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "test-event-id",
                "name": "Championship Game",
                "event_type": "sports",
                "status": "created",
            }]
        )

        response = client.post(
            "/api/events",
            json={"name": "Championship Game", "event_type": "sports"},
        )
        assert response.status_code == 200
        event_id = response.json()["id"]

        # Step 2: Get upload URL and upload video
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": event_id}]
        )

        response = client.post(
            f"/api/events/{event_id}/videos",
            json={"filename": "wide_shot.mp4", "angle_type": "wide"},
        )
        assert response.status_code == 200
        assert "upload_url" in response.json()
        video_id = response.json()["video_id"]

        # Step 3: Mark video as uploaded
        mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": video_id, "status": "uploaded"}]
        )

        response = client.post(f"/api/events/{event_id}/videos/{video_id}/uploaded")
        assert response.status_code == 200

        # Step 4: Start analysis
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[{"id": event_id, "status": "created"}]),  # Get event
            MagicMock(data=[{"id": video_id, "status": "uploaded"}]),  # Get videos
        ]

        with patch("worker.analyze_videos_task", mock_celery_tasks["analyze_videos"]):
            response = client.post(f"/api/events/{event_id}/analyze")

        assert response.status_code == 200
        assert response.json()["message"] == "Analysis started"

        # Step 5: Generate final video (after analysis completes)
        # Reset side_effect before setting new return_value
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = None
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": event_id, "status": "analyzed"}]
        )

        with patch("worker.generate_video_task", mock_celery_tasks["generate_video"]):
            response = client.post(f"/api/events/{event_id}/generate")

        assert response.status_code == 200
        assert response.json()["message"] == "Video generation started"


class TestHighlightReelWorkflow:
    """Test the highlight reel generation workflow."""

    def test_reel_generation_workflow(self, client: TestClient, mock_supabase, mock_celery_tasks, sample_event_analyzed):
        """Test: analyzed event -> generate reel -> check status -> get result."""
        event_id = sample_event_analyzed["id"]

        # Step 1: Verify event is analyzed
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event_analyzed]
        )

        response = client.get(f"/api/events/{event_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "analyzed"

        # Step 2: Generate highlight reel
        with patch("worker.generate_highlight_reel_task", mock_celery_tasks["generate_highlight_reel"]):
            response = client.post(
                f"/api/events/{event_id}/reels/generate",
                json={
                    "query": "me scoring",
                    "vibe": "high_energy",
                    "duration": 30,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        reel_id = data["reel_id"]

        # Step 3: List reels
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[{
                "id": reel_id,
                "query": "me scoring",
                "vibe": "high_energy",
                "status": "processing",
            }]
        )

        response = client.get(f"/api/events/{event_id}/reels")
        assert response.status_code == 200
        assert len(response.json()["reels"]) >= 1

        # Step 4: Simulate completion and check result
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": reel_id,
                "query": "me scoring",
                "vibe": "high_energy",
                "status": "completed",
                "output_url": "https://s3.amazonaws.com/bucket/reels/test.mp4",
                "moments": [{"start": 0, "end": 5000}],
            }]
        )

        response = client.get(f"/api/events/{event_id}/reels/{reel_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["output_url"] is not None


class TestShopifyIntegrationWorkflow:
    """Test Shopify OAuth and product integration workflow."""

    @pytest.mark.asyncio
    async def test_shopify_connection_workflow(self, client: TestClient, mock_supabase, mock_redis, sample_event):
        """Test: get auth URL -> callback -> fetch products."""
        event_id = sample_event["id"]

        # Step 1: Get OAuth URL
        with patch("routers.shopify.get_redis", return_value=mock_redis):
            response = client.get(
                f"/api/events/{event_id}/shopify/auth-url",
                params={"shop": "test-store.myshopify.com"},
            )

        assert response.status_code == 200
        auth_url = response.json()["auth_url"]
        assert "test-store.myshopify.com" in auth_url
        assert "oauth/authorize" in auth_url

        # Step 2: Simulate OAuth callback (normally done by Shopify redirect)
        mock_redis.get.return_value = event_id.encode()

        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "shpat_test_token"}

        with patch("routers.shopify.get_redis", return_value=mock_redis), \
             patch("routers.shopify.get_supabase", return_value=mock_supabase), \
             patch("httpx.AsyncClient") as mock_client:

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_token_response
            )

            response = client.get(
                "/api/auth/shopify/callback",
                params={
                    "code": "auth_code",
                    "shop": "test-store.myshopify.com",
                    "state": "nonce",
                },
                follow_redirects=False,
            )

        # Should redirect to frontend
        assert response.status_code == 307

        # Step 3: Fetch products
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "shopify_store_url": "https://test-store.myshopify.com",
                "shopify_access_token": "encrypted_token",
            }]
        )

        mock_products_response = MagicMock()
        mock_products_response.status_code = 200
        mock_products_response.json.return_value = {
            "products": [{
                "id": 123,
                "title": "Team Jersey",
                "body_html": "Official team jersey",
                "variants": [{"id": 456, "price": "59.99"}],
                "images": [{"src": "https://cdn.shopify.com/jersey.jpg"}],
            }]
        }

        with patch("routers.shopify.get_supabase", return_value=mock_supabase), \
             patch("routers.shopify.decrypt", return_value="decrypted_token"), \
             patch("httpx.AsyncClient") as mock_client:

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_products_response
            )

            response = client.get(f"/api/events/{event_id}/shopify/products")

        assert response.status_code == 200
        products = response.json()["products"]
        assert len(products) == 1
        assert products[0]["title"] == "Team Jersey"


class TestMusicIntegrationWorkflow:
    """Test music upload and analysis workflow."""

    def test_music_workflow(self, client: TestClient, mock_supabase, mock_s3, mock_celery_tasks, sample_event):
        """Test: upload music -> analyze -> use in reel generation."""
        event_id = sample_event["id"]

        # Step 1: Get music upload URL
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": event_id}]
        )

        response = client.post(
            f"/api/events/{event_id}/music/upload",
            json={"filename": "team_anthem.mp3", "content_type": "audio/mpeg"},
        )

        assert response.status_code == 200
        assert "upload_url" in response.json()
        assert "music" in response.json()["s3_key"]

        # Step 2: Analyze music
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                **sample_event,
                "music_url": "s3://bucket/music/track.mp3",
            }]
        )

        with patch("worker.analyze_music_task", mock_celery_tasks["analyze_music"]):
            response = client.post(f"/api/events/{event_id}/music/analyze")

        assert response.status_code == 200
        assert response.json()["message"] == "Music analysis started"


class TestMultiVideoWorkflow:
    """Test handling multiple video angles."""

    def test_multi_angle_upload(self, client: TestClient, mock_supabase, mock_s3, sample_event):
        """Test uploading multiple video angles."""
        event_id = sample_event["id"]
        angles = ["wide", "closeup", "crowd", "goal_angle"]
        video_ids = []

        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": event_id}]
        )

        for angle in angles:
            response = client.post(
                f"/api/events/{event_id}/videos",
                json={
                    "filename": f"{angle}_shot.mp4",
                    "angle_type": angle,
                },
            )
            assert response.status_code == 200
            video_ids.append(response.json()["video_id"])

        # Verify all videos in list
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"id": vid, "angle_type": angle, "status": "uploaded"}
                for vid, angle in zip(video_ids, angles)
            ]
        )

        response = client.get(f"/api/events/{event_id}/videos")
        assert response.status_code == 200
        videos = response.json()["videos"]
        assert len(videos) == 4

        # Verify all angle types present
        video_angles = {v["angle_type"] for v in videos}
        assert video_angles == set(angles)
