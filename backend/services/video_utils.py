"""Video utility functions for frame extraction and analysis."""

import base64
import subprocess
import tempfile
import os


def extract_frame(video_path: str, time_seconds: float = 3.0) -> bytes:
    """Extract a single frame from video as JPEG bytes.

    Args:
        video_path: Path to the video file
        time_seconds: Time offset to extract frame from (default 3s to skip title cards)

    Returns:
        JPEG image bytes
    """
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(time_seconds),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",  # High quality JPEG
            "-f", "image2",
            tmp_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr.decode()}")

        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def frame_to_base64(frame_bytes: bytes) -> str:
    """Convert frame bytes to base64 string for API consumption.

    Args:
        frame_bytes: JPEG image bytes

    Returns:
        Base64 encoded string
    """
    return base64.standard_b64encode(frame_bytes).decode("utf-8")


def extract_frame_base64(video_path: str, time_seconds: float = 3.0) -> str:
    """Extract a frame and return as base64 in one step.

    Args:
        video_path: Path to the video file
        time_seconds: Time offset to extract frame from

    Returns:
        Base64 encoded JPEG string
    """
    frame_bytes = extract_frame(video_path, time_seconds)
    return frame_to_base64(frame_bytes)
