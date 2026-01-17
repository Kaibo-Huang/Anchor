"""
Tests for the reels API router (highlight reel generation).
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestGenerateReel:
    """Test highlight reel generation endpoint."""

    def test_generate_reel_success(self, client: TestClient, mock_supabase, mock_celery_tasks, sample_event_analyzed):
        """Test successful reel generation request."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event_analyzed]
        )

        with patch("worker.generate_highlight_reel_task", mock_celery_tasks["generate_highlight_reel"]):
            response = client.post(
                f"/api/events/{sample_event_analyzed['id']}/reels/generate",
                json={
                    "query": "me",
                    "vibe": "high_energy",
                    "duration": 30,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "reel_id" in data
        assert data["vibe"] == "high_energy"
        assert data["status"] == "processing"

    def test_generate_reel_emotional_vibe(self, client: TestClient, mock_supabase, mock_celery_tasks, sample_event_analyzed):
        """Test reel generation with emotional vibe."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event_analyzed]
        )

        with patch("worker.generate_highlight_reel_task", mock_celery_tasks["generate_highlight_reel"]):
            response = client.post(
                f"/api/events/{sample_event_analyzed['id']}/reels/generate",
                json={
                    "query": "me celebrating",
                    "vibe": "emotional",
                    "duration": 45,
                },
            )

        assert response.status_code == 200
        assert response.json()["vibe"] == "emotional"

    def test_generate_reel_calm_vibe(self, client: TestClient, mock_supabase, mock_celery_tasks, sample_event_analyzed):
        """Test reel generation with calm vibe."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event_analyzed]
        )

        with patch("worker.generate_highlight_reel_task", mock_celery_tasks["generate_highlight_reel"]):
            response = client.post(
                f"/api/events/{sample_event_analyzed['id']}/reels/generate",
                json={
                    "query": "peaceful moments",
                    "vibe": "calm",
                },
            )

        assert response.status_code == 200
        assert response.json()["vibe"] == "calm"

    def test_generate_reel_event_not_found(self, client: TestClient, mock_supabase_empty):
        """Test reel generation for non-existent event."""
        response = client.post(
            "/api/events/nonexistent-id/reels/generate",
            json={"query": "me", "vibe": "high_energy"},
        )
        assert response.status_code == 404

    def test_generate_reel_event_not_analyzed(self, client: TestClient, mock_supabase, sample_event):
        """Test reel generation before event is analyzed."""
        # Event is in "created" status, not "analyzed"
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event]
        )

        response = client.post(
            f"/api/events/{sample_event['id']}/reels/generate",
            json={"query": "me", "vibe": "high_energy"},
        )

        assert response.status_code == 400
        assert "must be analyzed" in response.json()["detail"]

    def test_generate_reel_invalid_vibe(self, client: TestClient, mock_supabase, sample_event_analyzed):
        """Test reel generation with invalid vibe."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event_analyzed]
        )

        response = client.post(
            f"/api/events/{sample_event_analyzed['id']}/reels/generate",
            json={"query": "me", "vibe": "invalid_vibe"},
        )
        assert response.status_code == 422  # Validation error

    def test_generate_reel_natural_language_queries(self, client: TestClient, mock_supabase, mock_celery_tasks, sample_event_analyzed):
        """Test various natural language query formats."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event_analyzed]
        )

        queries = [
            "me",
            "player 23",
            "guy in yellow pants",
            "my best moments",
            "celebrations",
            "scoring goals",
        ]

        for query in queries:
            with patch("worker.generate_highlight_reel_task", mock_celery_tasks["generate_highlight_reel"]):
                response = client.post(
                    f"/api/events/{sample_event_analyzed['id']}/reels/generate",
                    json={"query": query, "vibe": "high_energy"},
                )
            assert response.status_code == 200, f"Failed for query: {query}"


class TestListReels:
    """Test list reels endpoint."""

    def test_list_reels_success(self, client: TestClient, mock_supabase, sample_event, sample_reel):
        """Test listing reels for an event."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[sample_reel, {**sample_reel, "id": "reel-2", "query": "celebrations"}]
        )

        response = client.get(f"/api/events/{sample_event['id']}/reels")

        assert response.status_code == 200
        data = response.json()
        assert len(data["reels"]) == 2
        assert data["reels"][0]["query"] == "me"

    def test_list_reels_empty(self, client: TestClient, mock_supabase, sample_event):
        """Test listing reels when none exist."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[]
        )

        response = client.get(f"/api/events/{sample_event['id']}/reels")

        assert response.status_code == 200
        assert response.json()["reels"] == []

    def test_list_reels_mixed_status(self, client: TestClient, mock_supabase, sample_event, sample_reel):
        """Test listing reels with various statuses."""
        reels = [
            {**sample_reel, "status": "completed"},
            {**sample_reel, "id": "reel-2", "status": "processing"},
            {**sample_reel, "id": "reel-3", "status": "failed"},
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=reels
        )

        response = client.get(f"/api/events/{sample_event['id']}/reels")

        assert response.status_code == 200
        data = response.json()
        statuses = [r["status"] for r in data["reels"]]
        assert "completed" in statuses
        assert "processing" in statuses
        assert "failed" in statuses


class TestGetReel:
    """Test get single reel endpoint."""

    def test_get_reel_success(self, client: TestClient, mock_supabase, sample_event, sample_reel):
        """Test getting a specific reel."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_reel]
        )

        response = client.get(f"/api/events/{sample_event['id']}/reels/{sample_reel['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_reel["id"]
        assert data["query"] == "me"
        assert data["output_url"] is not None

    def test_get_reel_not_found(self, client: TestClient, mock_supabase, sample_event):
        """Test getting non-existent reel."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        response = client.get(f"/api/events/{sample_event['id']}/reels/nonexistent-id")
        assert response.status_code == 404

    def test_get_reel_processing(self, client: TestClient, mock_supabase, sample_event, sample_reel):
        """Test getting a reel that's still processing."""
        processing_reel = {**sample_reel, "status": "processing", "output_url": None}
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[processing_reel]
        )

        response = client.get(f"/api/events/{sample_event['id']}/reels/{sample_reel['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert data["output_url"] is None
