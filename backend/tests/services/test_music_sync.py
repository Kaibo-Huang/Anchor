"""
Tests for music synchronization service.
"""
from unittest.mock import patch, MagicMock

import pytest
import numpy as np


class TestAlignCutsToBeats:
    """Test beat alignment function."""

    def test_align_empty_segments(self):
        """Test alignment with no segments."""
        from services.music_sync import align_cuts_to_beats

        result = align_cuts_to_beats([], [1000, 2000, 3000])
        assert result == []

    def test_align_empty_beats(self):
        """Test alignment with no beats."""
        from services.music_sync import align_cuts_to_beats

        segments = [{"start_ms": 1000, "video_id": "a"}]
        result = align_cuts_to_beats(segments, [])

        assert result == segments

    def test_align_within_tolerance(self):
        """Test alignment when segment is within tolerance."""
        from services.music_sync import align_cuts_to_beats

        segments = [{"start_ms": 1050, "video_id": "a"}]  # 50ms from beat
        beats = [1000, 2000, 3000]

        result = align_cuts_to_beats(segments, beats, tolerance_ms=200)

        assert result[0]["start_ms"] == 1000  # Snapped to beat
        assert result[0]["beat_synced"] is True

    def test_align_outside_tolerance(self):
        """Test alignment when segment is outside tolerance."""
        from services.music_sync import align_cuts_to_beats

        segments = [{"start_ms": 1500, "video_id": "a"}]  # 500ms from nearest beat
        beats = [1000, 2000, 3000]

        result = align_cuts_to_beats(segments, beats, tolerance_ms=200)

        assert result[0]["start_ms"] == 1500  # Not snapped
        assert result[0]["beat_synced"] is False

    def test_align_multiple_segments(self):
        """Test alignment of multiple segments."""
        from services.music_sync import align_cuts_to_beats

        segments = [
            {"start_ms": 1050, "video_id": "a"},  # Within tolerance
            {"start_ms": 2500, "video_id": "b"},  # Outside tolerance
            {"start_ms": 2990, "video_id": "c"},  # Within tolerance
        ]
        beats = [1000, 2000, 3000]

        result = align_cuts_to_beats(segments, beats, tolerance_ms=200)

        assert result[0]["beat_synced"] is True
        assert result[1]["beat_synced"] is False
        assert result[2]["beat_synced"] is True
        assert result[2]["start_ms"] == 3000

    def test_align_preserves_other_fields(self):
        """Test that alignment preserves other segment fields."""
        from services.music_sync import align_cuts_to_beats

        segments = [{
            "start_ms": 1050,
            "video_id": "a",
            "end_ms": 5000,
            "custom_field": "value",
        }]
        beats = [1000]

        result = align_cuts_to_beats(segments, beats, tolerance_ms=200)

        assert result[0]["video_id"] == "a"
        assert result[0]["end_ms"] == 5000
        assert result[0]["custom_field"] == "value"


class TestCreateDuckingFilter:
    """Test audio ducking filter generation."""

    def test_ducking_filter_empty(self):
        """Test filter with no segments."""
        from services.music_sync import create_ducking_filter

        result = create_ducking_filter({}, [], [])
        assert result == "anull"  # FFmpeg passthrough

    def test_ducking_filter_speech(self):
        """Test filter with speech segments."""
        from services.music_sync import create_ducking_filter
        from config import VideoConfig

        speech_segments = [
            {"start_sec": 10, "end_sec": 20},
            {"start_sec": 30, "end_sec": 40},
        ]

        result = create_ducking_filter({}, speech_segments, [])

        assert "volume=" in result
        assert f"{VideoConfig.MUSIC_DUCK_SPEECH_VOLUME}" in result
        assert "between(t,10,20)" in result
        assert "between(t,30,40)" in result

    def test_ducking_filter_action(self):
        """Test filter with high action moments."""
        from services.music_sync import create_ducking_filter
        from config import VideoConfig

        action_timeline = [
            {"start_sec": 15, "end_sec": 25, "intensity": 9},  # High
            {"start_sec": 35, "end_sec": 45, "intensity": 5},  # Low - should be ignored
        ]

        result = create_ducking_filter({}, [], action_timeline)

        assert f"{VideoConfig.MUSIC_BOOST_ACTION_VOLUME}" in result
        assert "between(t,15,25)" in result
        assert "between(t,35,45)" not in result  # Low intensity ignored

    def test_ducking_filter_ads(self):
        """Test filter mutes during ads."""
        from services.music_sync import create_ducking_filter

        ad_slots = [
            {"timestamp_ms": 60000, "duration_ms": 4000},  # 60-64 seconds
        ]

        result = create_ducking_filter({}, [], [], ad_slots)

        assert "volume=0" in result


class TestGetAudioMixStrategy:
    """Test audio mix strategy determination."""

    def test_mix_strategy_ceremony_with_commentary(self):
        """Test mix strategy for ceremony with commentary."""
        from services.music_sync import get_audio_mix_strategy

        result = get_audio_mix_strategy("ceremony", has_commentary=True, has_crowd_noise=False)

        assert result["music_base_volume"] == 0.3
        assert result["event_volume"] == 1.0
        assert result["duck_during_speech"] is True
        assert result["boost_on_action"] is False

    def test_mix_strategy_sports_with_crowd(self):
        """Test mix strategy for sports with crowd."""
        from services.music_sync import get_audio_mix_strategy

        result = get_audio_mix_strategy("sports", has_commentary=False, has_crowd_noise=True)

        assert result["music_base_volume"] == 0.5
        assert result["event_volume"] == 0.8
        assert result["duck_during_speech"] is True
        assert result["boost_on_action"] is True

    def test_mix_strategy_performance(self):
        """Test mix strategy for performance."""
        from services.music_sync import get_audio_mix_strategy

        result = get_audio_mix_strategy("performance", has_commentary=False, has_crowd_noise=False)

        assert result["music_base_volume"] == 0.2
        assert result["event_volume"] == 1.0
        assert result["duck_during_speech"] is False
        assert result["boost_on_action"] is False

    def test_mix_strategy_default(self):
        """Test default mix strategy."""
        from services.music_sync import get_audio_mix_strategy

        result = get_audio_mix_strategy("unknown_type", has_commentary=False, has_crowd_noise=False)

        assert result["music_base_volume"] == 0.4
        assert result["event_volume"] == 1.0


class TestAnalyzeMusicTrack:
    """Test music track analysis."""

    @patch("services.music_sync.librosa")
    def test_analyze_music_returns_metadata(self, mock_librosa):
        """Test that analysis returns expected metadata structure."""
        from services.music_sync import analyze_music_track

        # Mock librosa functions
        mock_librosa.load.return_value = (np.random.randn(22050 * 30), 22050)  # 30 sec audio
        mock_librosa.beat.beat_track.return_value = (120, np.array([0, 10, 20, 30]))
        mock_librosa.frames_to_time.return_value = np.array([0, 0.5, 1.0, 1.5])
        mock_librosa.feature.rms.return_value = np.random.rand(1, 100)
        mock_librosa.onset.onset_strength.return_value = np.random.rand(100)

        result = analyze_music_track("/test/music.mp3")

        assert "tempo_bpm" in result
        assert "beat_times_ms" in result
        assert "intro_end_ms" in result
        assert "outro_start_ms" in result
        assert "duration_ms" in result
        assert "intensity_curve" in result

    @patch("services.music_sync.librosa")
    def test_analyze_music_tempo(self, mock_librosa):
        """Test tempo detection."""
        from services.music_sync import analyze_music_track

        mock_librosa.load.return_value = (np.random.randn(22050 * 10), 22050)
        mock_librosa.beat.beat_track.return_value = (120.5, np.array([0, 10]))
        mock_librosa.frames_to_time.return_value = np.array([0, 0.5])
        mock_librosa.feature.rms.return_value = np.random.rand(1, 50)
        mock_librosa.onset.onset_strength.return_value = np.random.rand(50)

        result = analyze_music_track("/test/music.mp3")

        assert result["tempo_bpm"] == pytest.approx(120.5, rel=0.01)


class TestFindIntroEnd:
    """Test intro detection."""

    def test_find_intro_end_low_start(self):
        """Test intro detection with low energy start."""
        from services.music_sync import find_intro_end

        # Create RMS with low start, then high
        rms = np.concatenate([
            np.ones(50) * 0.1,  # Low energy intro
            np.ones(100) * 0.8,  # High energy main
        ])

        result = find_intro_end(rms, 22050)
        # Should detect intro ending around frame 50
        assert result >= 0

    def test_find_intro_end_immediate_start(self):
        """Test intro detection when song starts immediately."""
        from services.music_sync import find_intro_end

        # All high energy
        rms = np.ones(100) * 0.8

        result = find_intro_end(rms, 22050)
        assert result == 0  # No intro


class TestFindOutroStart:
    """Test outro detection."""

    def test_find_outro_start_fade_out(self):
        """Test outro detection with fadeout."""
        from services.music_sync import find_outro_start

        # High energy then low
        rms = np.concatenate([
            np.ones(100) * 0.8,
            np.ones(50) * 0.1,
        ])

        result = find_outro_start(rms, 22050, 22050 * 30)
        # Should detect outro starting around frame 100
        assert result > 0
