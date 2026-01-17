"""
Tests for the events API router.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestRootEndpoints:
    """Test root and health endpoints."""

    def test_root(self, client: TestClient):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Anchor API"
        assert data["version"] == "0.1.0"

    def test_health(self, client: TestClient):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestCreateEvent:
    """Test event creation endpoint."""

    def test_create_event_success(self, client: TestClient, mock_supabase):
        """Test successful event creation."""
        response = client.post(
            "/api/events",
            json={"name": "Championship Game", "event_type": "sports"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Event"
        assert data["event_type"] == "sports"
        assert data["status"] == "created"

    def test_create_event_ceremony(self, client: TestClient, mock_supabase):
        """Test event creation with ceremony type."""
        response = client.post(
            "/api/events",
            json={"name": "Graduation 2024", "event_type": "ceremony"},
        )
        assert response.status_code == 200

    def test_create_event_performance(self, client: TestClient, mock_supabase):
        """Test event creation with performance type."""
        response = client.post(
            "/api/events",
            json={"name": "Spring Concert", "event_type": "performance"},
        )
        assert response.status_code == 200

    def test_create_event_invalid_type(self, client: TestClient, mock_supabase):
        """Test event creation with invalid event type."""
        response = client.post(
            "/api/events",
            json={"name": "Test", "event_type": "invalid_type"},
        )
        assert response.status_code == 422  # Validation error

    def test_create_event_missing_name(self, client: TestClient, mock_supabase):
        """Test event creation without name."""
        response = client.post(
            "/api/events",
            json={"event_type": "sports"},
        )
        assert response.status_code == 422

    def test_create_event_db_failure(self, client: TestClient, mock_supabase_empty):
        """Test event creation when database insert fails."""
        response = client.post(
            "/api/events",
            json={"name": "Test", "event_type": "sports"},
        )
        assert response.status_code == 500
        assert "Failed to create event" in response.json()["detail"]


class TestGetEvent:
    """Test get event endpoint."""

    def test_get_event_success(self, client: TestClient, mock_supabase, sample_event):
        """Test successful event retrieval."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event]
        )

        response = client.get(f"/api/events/{sample_event['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_event["id"]
        assert data["name"] == sample_event["name"]

    def test_get_event_not_found(self, client: TestClient, mock_supabase_empty):
        """Test getting non-existent event."""
        response = client.get("/api/events/nonexistent-id")
        assert response.status_code == 404
        assert "Event not found" in response.json()["detail"]


class TestAnalyzeEvent:
    """Test analyze event endpoint."""

    def test_analyze_event_success(self, client: TestClient, mock_supabase, mock_celery_tasks, sample_event, sample_video):
        """Test successful event analysis start."""
        # Setup mocks
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[sample_event]),  # Event query
            MagicMock(data=[sample_video]),  # Videos query
        ]

        with patch("worker.analyze_videos_task", mock_celery_tasks["analyze_videos"]):
            response = client.post(f"/api/events/{sample_event['id']}/analyze")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Analysis started"
        assert data["video_count"] == 1
        assert "task_id" in data

    def test_analyze_event_not_found(self, client: TestClient, mock_supabase_empty):
        """Test analyzing non-existent event."""
        response = client.post("/api/events/nonexistent-id/analyze")
        assert response.status_code == 404

    def test_analyze_event_no_videos(self, client: TestClient, mock_supabase, sample_event):
        """Test analyzing event with no videos."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[sample_event]),  # Event exists
            MagicMock(data=[]),  # No videos
        ]

        response = client.post(f"/api/events/{sample_event['id']}/analyze")
        assert response.status_code == 400
        assert "No videos uploaded" in response.json()["detail"]


class TestGenerateVideo:
    """Test generate video endpoint."""

    def test_generate_video_success(self, client: TestClient, mock_supabase, mock_celery_tasks, sample_event_analyzed):
        """Test successful video generation start."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event_analyzed]
        )

        with patch("worker.generate_video_task", mock_celery_tasks["generate_video"]):
            response = client.post(f"/api/events/{sample_event_analyzed['id']}/generate")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Video generation started"
        assert "task_id" in data

    def test_generate_video_not_analyzed(self, client: TestClient, mock_supabase, sample_event):
        """Test generating video for un-analyzed event."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event]  # status is "created", not "analyzed"
        )

        response = client.post(f"/api/events/{sample_event['id']}/generate")
        assert response.status_code == 400
        assert "must be analyzed" in response.json()["detail"]

    def test_generate_video_not_found(self, client: TestClient, mock_supabase_empty):
        """Test generating video for non-existent event."""
        response = client.post("/api/events/nonexistent-id/generate")
        assert response.status_code == 404


class TestSponsor:
    """Test sponsor endpoints."""

    def test_set_sponsor_success(self, client: TestClient, mock_supabase, sample_event):
        """Test setting sponsor name."""
        response = client.post(
            f"/api/events/{sample_event['id']}/sponsor",
            json={"sponsor_name": "Acme Corp"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Sponsor updated"
        assert data["sponsor_name"] == "Acme Corp"

    def test_set_sponsor_not_found(self, client: TestClient, mock_supabase):
        """Test setting sponsor for non-existent event."""
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        response = client.post(
            "/api/events/nonexistent-id/sponsor",
            json={"sponsor_name": "Acme Corp"},
        )
        assert response.status_code == 404


class TestChapters:
    """Test chapters endpoint."""

    def test_get_chapters_success(self, client: TestClient, mock_supabase, sample_event):
        """Test getting chapter markers."""
        chapters = [
            {"title": "Kickoff", "start_time": 0},
            {"title": "Halftime", "start_time": 2700000},
            {"title": "Final Whistle", "start_time": 5400000},
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"chapters": chapters}]
        )

        response = client.get(f"/api/events/{sample_event['id']}/chapters")
        assert response.status_code == 200
        data = response.json()
        assert len(data["chapters"]) == 3
        assert data["chapters"][0]["title"] == "Kickoff"

    def test_get_chapters_empty(self, client: TestClient, mock_supabase_empty, sample_event):
        """Test getting chapters when none exist."""
        response = client.get(f"/api/events/{sample_event['id']}/chapters")
        assert response.status_code == 200
        assert response.json()["chapters"] == []
