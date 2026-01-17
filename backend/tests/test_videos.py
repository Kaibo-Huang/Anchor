"""
Tests for the videos API router.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestVideoUpload:
    """Test video upload endpoints."""

    def test_get_upload_url_success(self, client: TestClient, mock_supabase, mock_s3, sample_event):
        """Test getting presigned upload URL."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": sample_event["id"]}]
        )

        response = client.post(
            f"/api/events/{sample_event['id']}/videos",
            json={
                "filename": "game_footage.mp4",
                "content_type": "video/mp4",
                "angle_type": "wide",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "video_id" in data
        assert "upload_url" in data
        assert "s3_key" in data
        assert data["upload_url"].startswith("https://")

    def test_get_upload_url_closeup(self, client: TestClient, mock_supabase, mock_s3, sample_event):
        """Test upload URL with closeup angle type."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": sample_event["id"]}]
        )

        response = client.post(
            f"/api/events/{sample_event['id']}/videos",
            json={
                "filename": "closeup.mov",
                "content_type": "video/quicktime",
                "angle_type": "closeup",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "mov" in data["s3_key"]

    def test_get_upload_url_event_not_found(self, client: TestClient, mock_supabase_empty, mock_s3):
        """Test upload URL for non-existent event."""
        response = client.post(
            "/api/events/nonexistent-id/videos",
            json={"filename": "test.mp4", "angle_type": "wide"},
        )
        assert response.status_code == 404

    def test_get_upload_url_invalid_angle(self, client: TestClient, mock_supabase, mock_s3, sample_event):
        """Test upload URL with invalid angle type."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": sample_event["id"]}]
        )

        response = client.post(
            f"/api/events/{sample_event['id']}/videos",
            json={"filename": "test.mp4", "angle_type": "invalid_angle"},
        )
        assert response.status_code == 422  # Validation error


class TestMarkVideoUploaded:
    """Test mark video uploaded endpoint."""

    def test_mark_uploaded_success(self, client: TestClient, mock_supabase, sample_event, sample_video):
        """Test marking video as uploaded."""
        mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_video]
        )

        response = client.post(
            f"/api/events/{sample_event['id']}/videos/{sample_video['id']}/uploaded"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Video marked as uploaded"
        assert data["video_id"] == sample_video["id"]

    def test_mark_uploaded_not_found(self, client: TestClient, mock_supabase, sample_event):
        """Test marking non-existent video as uploaded."""
        mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        response = client.post(
            f"/api/events/{sample_event['id']}/videos/nonexistent-id/uploaded"
        )
        assert response.status_code == 404


class TestListVideos:
    """Test list videos endpoint."""

    def test_list_videos_success(self, client: TestClient, mock_supabase, sample_event, sample_video):
        """Test listing videos for an event."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_video, {**sample_video, "id": "video-2", "angle_type": "closeup"}]
        )

        response = client.get(f"/api/events/{sample_event['id']}/videos")

        assert response.status_code == 200
        data = response.json()
        assert len(data["videos"]) == 2
        assert data["videos"][0]["angle_type"] == "wide"
        assert data["videos"][1]["angle_type"] == "closeup"

    def test_list_videos_empty(self, client: TestClient, mock_supabase, sample_event):
        """Test listing videos when none exist."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        response = client.get(f"/api/events/{sample_event['id']}/videos")

        assert response.status_code == 200
        assert response.json()["videos"] == []


class TestMusicUpload:
    """Test music upload endpoints."""

    def test_get_music_upload_url_success(self, client: TestClient, mock_supabase, mock_s3, sample_event):
        """Test getting presigned URL for music upload."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": sample_event["id"]}]
        )

        response = client.post(
            f"/api/events/{sample_event['id']}/music/upload",
            json={"filename": "team_anthem.mp3", "content_type": "audio/mpeg"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "upload_url" in data
        assert "s3_key" in data
        assert "music" in data["s3_key"]

    def test_get_music_upload_url_wav(self, client: TestClient, mock_supabase, mock_s3, sample_event):
        """Test music upload with WAV file."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": sample_event["id"]}]
        )

        response = client.post(
            f"/api/events/{sample_event['id']}/music/upload",
            json={"filename": "song.wav", "content_type": "audio/wav"},
        )

        assert response.status_code == 200
        assert "wav" in response.json()["s3_key"]

    def test_get_music_upload_url_event_not_found(self, client: TestClient, mock_supabase_empty, mock_s3):
        """Test music upload for non-existent event."""
        response = client.post(
            "/api/events/nonexistent-id/music/upload",
            json={"filename": "song.mp3"},
        )
        assert response.status_code == 404


class TestMusicAnalyze:
    """Test music analysis endpoint."""

    def test_analyze_music_success(self, client: TestClient, mock_supabase, mock_celery_tasks, sample_event):
        """Test starting music analysis."""
        sample_event_with_music = {**sample_event, "music_url": "s3://bucket/music.mp3"}
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[sample_event_with_music]
        )

        with patch("routers.videos.analyze_music_task", mock_celery_tasks["analyze_music"]):
            response = client.post(f"/api/events/{sample_event['id']}/music/analyze")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Music analysis started"
        assert "task_id" in data

    def test_analyze_music_no_music(self, client: TestClient, mock_supabase, sample_event):
        """Test analyzing when no music uploaded."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{**sample_event, "music_url": None}]
        )

        response = client.post(f"/api/events/{sample_event['id']}/music/analyze")
        assert response.status_code == 400
        assert "No music uploaded" in response.json()["detail"]

    def test_analyze_music_event_not_found(self, client: TestClient, mock_supabase_empty):
        """Test analyzing music for non-existent event."""
        response = client.post("/api/events/nonexistent-id/music/analyze")
        assert response.status_code == 400  # Returns 400 because no music_url
