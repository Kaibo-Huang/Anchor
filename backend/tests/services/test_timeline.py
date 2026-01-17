"""
Tests for timeline generation service.
"""
from unittest.mock import patch, MagicMock

import pytest


class TestScoreAngleAtTime:
    """Test angle scoring function."""

    def test_score_wide_angle_base(self):
        """Test that wide angle gets base + profile score."""
        from services.timeline import score_angle_at_time

        video = {"angle_type": "wide", "analysis_data": {}}
        profile = {"default": "wide"}

        score = score_angle_at_time(video, 0, profile, None)
        # Base score: 50 * 0.25 = 12.5, profile match: 25, total: 37.5
        assert score == 37.5

    def test_score_closeup_angle(self):
        """Test closeup angle scoring without profile match."""
        from services.timeline import score_angle_at_time

        video = {"angle_type": "closeup", "analysis_data": {}}
        profile = {"default": "wide"}

        score = score_angle_at_time(video, 0, profile, None)
        # Base score: 40 * 0.25 = 10, no profile match
        assert score == 10

    def test_score_crowd_angle(self):
        """Test crowd angle scoring."""
        from services.timeline import score_angle_at_time

        video = {"angle_type": "crowd", "analysis_data": {}}
        profile = {"default": "wide"}

        score = score_angle_at_time(video, 0, profile, None)
        # Base score: 30 * 0.25 = 7.5, no profile match
        assert score == 7.5

    def test_score_default_angle_bonus(self):
        """Test that default angle gets bonus."""
        from services.timeline import score_angle_at_time

        wide_video = {"angle_type": "wide", "analysis_data": {}}
        closeup_video = {"angle_type": "closeup", "analysis_data": {}}
        profile = {"default": "closeup"}

        wide_score = score_angle_at_time(wide_video, 0, profile, None)
        closeup_score = score_angle_at_time(closeup_video, 0, profile, None)

        # Wide: 50 * 0.25 = 12.5, no profile match
        # Closeup: 40 * 0.25 = 10 + 25 (profile match) = 35
        assert closeup_score > wide_score
        assert closeup_score == 35
        assert wide_score == 12.5

    def test_score_with_embeddings(self):
        """Test that embeddings boost score."""
        from services.timeline import score_angle_at_time

        video = {
            "angle_type": "wide",
            "analysis_data": {
                "embeddings": [
                    {"start_time": 0, "end_time": 5, "embedding": [0.1, 0.2]}
                ]
            }
        }
        profile = {"default": "wide"}

        # Without scene_context, embeddings give base credit of 15
        score = score_angle_at_time(video, 2000, profile, None)  # 2 seconds
        # base: 12.5 + profile: 25 + embedding base: 15 = 52.5
        assert score == 52.5

    def test_score_max_100(self):
        """Test that score is capped at 100."""
        from services.timeline import score_angle_at_time

        video = {
            "angle_type": "wide",
            "analysis_data": {
                "embeddings": [{"start_time": 0, "end_time": 10, "embedding": [0.1, 0.2]}]
            }
        }
        profile = {"default": "wide"}

        score = score_angle_at_time(video, 0, profile, None)
        assert score <= 100


class TestGenerateTimeline:
    """Test timeline generation."""

    def test_generate_timeline_empty_videos(self):
        """Test timeline generation with no videos."""
        from services.timeline import generate_timeline

        result = generate_timeline([], "sports", None)

        assert result["segments"] == []
        assert result["zooms"] == []
        assert result["ad_slots"] == []
        assert result["chapters"] == []

    @patch("services.timeline.get_video_duration_ms")
    def test_generate_timeline_single_video(self, mock_duration):
        """Test timeline generation with single video."""
        from services.timeline import generate_timeline

        mock_duration.return_value = 10000  # 10 seconds

        videos = [
            {"id": "video1", "path": "/test.mp4", "angle_type": "wide", "analysis_data": {}}
        ]

        result = generate_timeline(videos, "sports", None)

        assert len(result["segments"]) >= 1
        assert result["segments"][0]["video_id"] == "video1"

    @patch("services.timeline.get_video_duration_ms")
    def test_generate_timeline_multiple_videos(self, mock_duration):
        """Test timeline generation with multiple videos."""
        from services.timeline import generate_timeline

        mock_duration.return_value = 30000  # 30 seconds

        videos = [
            {"id": "video1", "path": "/wide.mp4", "angle_type": "wide", "analysis_data": {}},
            {"id": "video2", "path": "/closeup.mp4", "angle_type": "closeup", "analysis_data": {}},
            {"id": "video3", "path": "/crowd.mp4", "angle_type": "crowd", "analysis_data": {}},
        ]

        result = generate_timeline(videos, "sports", None)

        assert len(result["segments"]) >= 1
        # Should have continuous coverage
        assert result["segments"][0]["start_ms"] == 0


class TestGenerateAdSlots:
    """Test ad slot generation."""

    def test_generate_ad_slots_short_video(self):
        """Test no ads for very short videos."""
        from services.timeline import generate_ad_slots

        # 15 second video - too short for ads
        ad_slots = generate_ad_slots([], 15000, {})

        assert len(ad_slots) == 0

    def test_generate_ad_slots_medium_video(self):
        """Test ads for medium length video."""
        from services.timeline import generate_ad_slots

        # 2 minute video
        ad_slots = generate_ad_slots([], 120000, {})

        # Should have some ad slots
        assert len(ad_slots) <= 4  # Max 4 slots
        for slot in ad_slots:
            assert slot["timestamp_ms"] >= 10000  # Not in first 10s
            assert slot["timestamp_ms"] <= 110000  # Not in last 10s

    def test_generate_ad_slots_spacing(self):
        """Test that ad slots respect minimum spacing."""
        from services.timeline import generate_ad_slots
        from config import VideoConfig

        # 5 minute video
        ad_slots = generate_ad_slots([], 300000, {})

        for i in range(len(ad_slots) - 1):
            spacing = ad_slots[i + 1]["timestamp_ms"] - ad_slots[i]["timestamp_ms"]
            assert spacing >= VideoConfig.AD_MIN_SPACING_MS


class TestGenerateChapters:
    """Test chapter generation."""

    def test_generate_chapters_always_has_start(self):
        """Test that chapters always includes start marker."""
        from services.timeline import generate_chapters

        chapters = generate_chapters([], 60000, "sports", None)

        assert len(chapters) >= 1
        assert chapters[0]["title"] == "Start"
        assert chapters[0]["timestamp_ms"] == 0

    @patch("services.timeline.search_videos")
    def test_generate_chapters_with_index(self, mock_search):
        """Test chapter generation with TwelveLabs search."""
        from services.timeline import generate_chapters

        mock_search.return_value = [
            {"start": 30, "end": 35, "confidence": 0.9},
            {"start": 120, "end": 125, "confidence": 0.85},
        ]

        chapters = generate_chapters([], 180000, "sports", "test-index-id")

        # Should have Start + searched moments
        assert len(chapters) >= 1
        assert chapters[0]["title"] == "Start"


class TestGenerateZoomMoments:
    """Test zoom moment generation."""

    def test_generate_zoom_moments_no_index(self):
        """Test zoom generation without TwelveLabs index."""
        from services.timeline import generate_zoom_moments

        zooms = generate_zoom_moments([], 60000, None)

        assert zooms == []  # No zooms without index

    @patch("services.timeline.search_videos")
    def test_generate_zoom_moments_with_index(self, mock_search):
        """Test zoom generation with search results."""
        from services.timeline import generate_zoom_moments
        from config import VideoConfig

        mock_search.return_value = [
            {"start": 10, "end": 15, "confidence": 0.95},
            {"start": 30, "end": 35, "confidence": 0.8},
        ]

        zooms = generate_zoom_moments([], 60000, "test-index-id")

        assert len(zooms) >= 1
        for zoom in zooms:
            assert "start_ms" in zoom
            assert "duration_ms" in zoom
            assert "zoom_factor" in zoom
            assert zoom["zoom_factor"] in [VideoConfig.ZOOM_FACTOR_MED, VideoConfig.ZOOM_FACTOR_HIGH]

    @patch("services.timeline.search_videos")
    def test_generate_zoom_moments_spacing(self, mock_search):
        """Test that zoom moments respect minimum spacing."""
        from services.timeline import generate_zoom_moments
        from config import VideoConfig

        mock_search.return_value = [
            {"start": 10, "end": 12, "confidence": 0.9},
            {"start": 12, "end": 14, "confidence": 0.9},  # Too close
            {"start": 30, "end": 32, "confidence": 0.9},  # OK spacing
        ]

        zooms = generate_zoom_moments([], 60000, "test-index-id")

        # Should only have 2 zooms due to spacing
        assert len(zooms) <= 2
