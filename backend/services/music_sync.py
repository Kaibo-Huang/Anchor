"""Music analysis and beat synchronization service."""

import numpy as np
import librosa

from config import VideoConfig


def analyze_music_track(audio_path: str) -> dict:
    """Extract beat timings and intensity for sync with video.

    Args:
        audio_path: Path to audio file (MP3, WAV, M4A)

    Returns:
        Music metadata dict with tempo, beats, intensity curve
    """
    # Load audio
    y, sr = librosa.load(audio_path, sr=22050, mono=True)

    # Detect beats
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times_ms = (librosa.frames_to_time(beat_frames, sr=sr) * 1000).tolist()

    # Analyze intensity (RMS energy)
    rms = librosa.feature.rms(y=y)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    # Find intro/outro (low energy sections)
    intro_end_ms = find_intro_end(rms, sr) * 1000
    outro_start_ms = find_outro_start(rms, sr, len(y)) * 1000

    # Normalize and sample intensity curve
    intensity_curve = rms / (rms.max() + 1e-8)
    # Downsample to ~1 value per second
    samples_per_sec = sr / 512  # hop_length for rms
    step = max(1, int(samples_per_sec))
    intensity_curve = intensity_curve[::step].tolist()

    return {
        "tempo_bpm": float(tempo) if isinstance(tempo, np.ndarray) else float(tempo[0]) if hasattr(tempo, '__iter__') else float(tempo),
        "beat_times_ms": beat_times_ms,
        "intro_end_ms": float(intro_end_ms),
        "outro_start_ms": float(outro_start_ms),
        "duration_ms": int(len(y) / sr * 1000),
        "intensity_curve": intensity_curve,
    }


def find_intro_end(rms: np.ndarray, sr: int, threshold_percentile: int = 30) -> float:
    """Find the end of the intro (where energy consistently rises).

    Args:
        rms: RMS energy array
        sr: Sample rate
        threshold_percentile: Percentile threshold for "low energy"

    Returns:
        Time in seconds where intro ends
    """
    threshold = np.percentile(rms, threshold_percentile)

    # Find first point where energy consistently exceeds threshold
    window_size = int(sr / 512 * 2)  # 2 second window
    for i in range(len(rms) - window_size):
        if np.mean(rms[i:i + window_size]) > threshold:
            return i * 512 / sr

    return 0.0


def find_outro_start(rms: np.ndarray, sr: int, total_samples: int, threshold_percentile: int = 30) -> float:
    """Find the start of the outro (where energy consistently drops).

    Args:
        rms: RMS energy array
        sr: Sample rate
        total_samples: Total number of audio samples
        threshold_percentile: Percentile threshold for "low energy"

    Returns:
        Time in seconds where outro starts
    """
    threshold = np.percentile(rms, threshold_percentile)
    total_duration = total_samples / sr

    # Find last point where energy consistently exceeds threshold (working backwards)
    window_size = int(sr / 512 * 2)  # 2 second window
    for i in range(len(rms) - 1, window_size, -1):
        if np.mean(rms[i - window_size:i]) > threshold:
            return i * 512 / sr

    return total_duration


def align_cuts_to_beats(
    timeline_segments: list[dict],
    beat_times_ms: list[float],
    tolerance_ms: int = None,
) -> list[dict]:
    """Snap angle switches to nearest beat.

    Args:
        timeline_segments: List of segments with start_ms
        beat_times_ms: List of beat timestamps in milliseconds
        tolerance_ms: Maximum distance to snap (default from config)

    Returns:
        Updated segments with beat-aligned start times
    """
    if tolerance_ms is None:
        tolerance_ms = VideoConfig.MUSIC_BEAT_SYNC_TOLERANCE_MS

    if not beat_times_ms:
        return timeline_segments

    beat_array = np.array(beat_times_ms)
    synced_segments = []

    for segment in timeline_segments:
        start_ms = segment["start_ms"]

        # Find nearest beat
        distances = np.abs(beat_array - start_ms)
        nearest_idx = np.argmin(distances)
        nearest_beat = beat_times_ms[nearest_idx]
        distance = distances[nearest_idx]

        # Snap if within tolerance
        if distance <= tolerance_ms:
            segment = segment.copy()
            segment["start_ms"] = int(nearest_beat)
            segment["beat_synced"] = True
        else:
            segment = segment.copy()
            segment["beat_synced"] = False

        synced_segments.append(segment)

    return synced_segments


def create_ducking_filter(
    music_metadata: dict,
    speech_segments: list[dict],
    action_intensity_timeline: list[dict],
    ad_slots: list[dict] = None,
) -> str:
    """Create FFmpeg volume filter string for audio ducking.

    Lowers music during speech, boosts during action, mutes during ads.

    Args:
        music_metadata: Music metadata from analyze_music_track
        speech_segments: List of dicts with start_sec, end_sec
        action_intensity_timeline: List of dicts with start_sec, end_sec, intensity
        ad_slots: Optional list of ad slots to mute during

    Returns:
        FFmpeg volume filter string
    """
    filters = []

    # Duck to 20% during speech
    for seg in speech_segments:
        filters.append(
            f"volume={VideoConfig.MUSIC_DUCK_SPEECH_VOLUME}:"
            f"enable='between(t,{seg['start_sec']},{seg['end_sec']})'"
        )

    # Boost during high action
    for moment in action_intensity_timeline:
        if moment.get("intensity", 0) >= 8:
            filters.append(
                f"volume={VideoConfig.MUSIC_BOOST_ACTION_VOLUME}:"
                f"enable='between(t,{moment['start_sec']},{moment['end_sec']})'"
            )

    # Mute during ads
    if ad_slots:
        for ad in ad_slots:
            start_sec = ad["timestamp_ms"] / 1000 - 0.5
            end_sec = (ad["timestamp_ms"] + ad.get("duration_ms", 4000)) / 1000 + 0.5
            filters.append(
                f"volume=0:enable='between(t,{start_sec},{end_sec})'"
            )

    return ",".join(filters) if filters else "anull"


def get_audio_mix_strategy(
    event_type: str,
    has_commentary: bool,
    has_crowd_noise: bool,
) -> dict:
    """Determine optimal music/event audio balance.

    Args:
        event_type: Type of event
        has_commentary: Whether event has speech/commentary
        has_crowd_noise: Whether event has crowd audio

    Returns:
        Mix strategy dict with volume levels and settings
    """
    if event_type == "ceremony" and has_commentary:
        return {
            "music_base_volume": 0.3,
            "event_volume": 1.0,
            "duck_during_speech": True,
            "boost_on_action": False,
            "fade_in_duration_sec": VideoConfig.MUSIC_FADE_IN_SEC + 1,
            "fade_out_duration_sec": VideoConfig.MUSIC_FADE_OUT_SEC + 1,
        }
    elif event_type == "sports" and has_crowd_noise:
        return {
            "music_base_volume": 0.5,
            "event_volume": 0.8,
            "duck_during_speech": True,
            "boost_on_action": True,
            "fade_in_duration_sec": VideoConfig.MUSIC_FADE_IN_SEC,
            "fade_out_duration_sec": VideoConfig.MUSIC_FADE_OUT_SEC,
        }
    elif event_type == "performance":
        return {
            "music_base_volume": 0.2,
            "event_volume": 1.0,
            "duck_during_speech": False,
            "boost_on_action": False,
            "fade_in_duration_sec": VideoConfig.MUSIC_FADE_IN_SEC + 2,
            "fade_out_duration_sec": VideoConfig.MUSIC_FADE_OUT_SEC + 2,
        }
    else:
        return {
            "music_base_volume": 0.4,
            "event_volume": 1.0,
            "duck_during_speech": True,
            "boost_on_action": False,
            "fade_in_duration_sec": VideoConfig.MUSIC_FADE_IN_SEC,
            "fade_out_duration_sec": VideoConfig.MUSIC_FADE_OUT_SEC,
        }
