"""Audio synchronization service for multi-angle video alignment."""

import numpy as np
import librosa
from scipy.signal import correlate


def extract_audio_fingerprint(audio_path: str, sr: int = 22050) -> np.ndarray:
    """Extract audio fingerprint using onset strength envelope.

    Args:
        audio_path: Path to audio/video file
        sr: Sample rate

    Returns:
        Onset strength envelope array
    """
    # Load audio
    y, sr = librosa.load(audio_path, sr=sr, mono=True)

    # Compute onset strength envelope
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    return onset_env


def find_audio_offset(reference_path: str, target_path: str) -> int:
    """Find the offset in milliseconds to align target audio with reference.

    Uses cross-correlation of onset strength envelopes for robust alignment.

    Args:
        reference_path: Path to reference audio/video
        target_path: Path to target audio/video to align

    Returns:
        Offset in milliseconds (positive = target starts later)
    """
    sr = 22050
    hop_length = 512

    # Extract fingerprints
    ref_onset = extract_audio_fingerprint(reference_path, sr)
    target_onset = extract_audio_fingerprint(target_path, sr)

    # Normalize
    ref_onset = (ref_onset - np.mean(ref_onset)) / (np.std(ref_onset) + 1e-8)
    target_onset = (target_onset - np.mean(target_onset)) / (np.std(target_onset) + 1e-8)

    # Cross-correlation
    correlation = correlate(ref_onset, target_onset, mode="full")

    # Find peak
    peak_idx = np.argmax(correlation)

    # Convert to time offset
    offset_frames = peak_idx - len(target_onset) + 1
    offset_seconds = offset_frames * hop_length / sr
    offset_ms = int(offset_seconds * 1000)

    return offset_ms


def sync_videos(video_paths: list[str]) -> list[int]:
    """Sync multiple videos using audio correlation.

    Uses the first video as reference, aligns all others to it.

    Args:
        video_paths: List of paths to video files

    Returns:
        List of sync offsets in milliseconds (first video is always 0)
    """
    if not video_paths:
        return []

    if len(video_paths) == 1:
        return [0]

    reference = video_paths[0]
    offsets = [0]  # Reference has 0 offset

    for target in video_paths[1:]:
        try:
            offset = find_audio_offset(reference, target)
            offsets.append(offset)
        except Exception as e:
            # If audio sync fails, default to 0 offset
            print(f"Audio sync failed for {target}: {e}")
            offsets.append(0)

    return offsets


def get_audio_duration(audio_path: str) -> float:
    """Get duration of audio/video file in seconds.

    Args:
        audio_path: Path to audio/video file

    Returns:
        Duration in seconds
    """
    return librosa.get_duration(path=audio_path)
