"""Video compression utilities for TwelveLabs size limits."""

import os
import subprocess
import tempfile


# TwelveLabs limit is 2GB, we target 1.5GB to be safe
MAX_SIZE_BYTES = 1.8 * 1024 * 1024 * 1024  # 1.8GB threshold to trigger compression
TARGET_SIZE_BYTES = 1.5 * 1024 * 1024 * 1024  # 1.5GB target after compression


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def get_file_size(path: str) -> int:
    """Get file size in bytes."""
    return os.path.getsize(path)


def compress_video_for_twelvelabs(
    input_path: str,
    output_path: str = None,
    target_size_gb: float = 1.5,
) -> str:
    """Compress video to fit within TwelveLabs size limit.

    Uses two-pass encoding for optimal quality at target size.

    Args:
        input_path: Path to input video
        output_path: Path for output (default: input_path with _compressed suffix)
        target_size_gb: Target file size in GB (default 1.5GB)

    Returns:
        Path to compressed video (or original if already small enough)
    """
    input_size = get_file_size(input_path)
    input_size_gb = input_size / (1024 * 1024 * 1024)

    print(f"[VideoCompress] Input size: {input_size_gb:.2f} GB")

    # If already under threshold, return original
    if input_size < MAX_SIZE_BYTES:
        print(f"[VideoCompress] Video is under {MAX_SIZE_BYTES / (1024**3):.1f}GB, no compression needed")
        return input_path

    print(f"[VideoCompress] Video exceeds limit, compressing to ~{target_size_gb}GB...")

    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_compressed{ext}"

    # Get video duration
    duration = get_video_duration(input_path)
    print(f"[VideoCompress] Video duration: {duration:.1f} seconds")

    # Calculate target bitrate (in kbps)
    # Formula: bitrate = (target_size_in_bits) / duration
    # Leave 10% for audio
    target_size_bits = target_size_gb * 1024 * 1024 * 1024 * 8
    audio_bitrate = 128  # kbps
    video_bitrate = int((target_size_bits / duration - audio_bitrate * 1000) / 1000)

    # Ensure reasonable bitrate (min 1000 kbps)
    video_bitrate = max(video_bitrate, 1000)

    print(f"[VideoCompress] Target video bitrate: {video_bitrate} kbps")
    print(f"[VideoCompress] Audio bitrate: {audio_bitrate} kbps")

    # Use Apple VideoToolbox hardware encoder for 10x faster encoding on Mac
    # Falls back to libx264 if VideoToolbox unavailable
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "h264_videotoolbox",  # Hardware encoder on Apple Silicon
        "-b:v", f"{video_bitrate}k",  # VideoToolbox uses bitrate, not CRF
        "-c:a", "aac",
        "-b:a", f"{audio_bitrate}k",
        "-movflags", "+faststart",
        "-y",
        output_path
    ]

    print(f"[VideoCompress] Running FFmpeg compression with VideoToolbox...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Fall back to libx264 if VideoToolbox fails
    if result.returncode != 0:
        print(f"[VideoCompress] VideoToolbox failed, falling back to libx264...")
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",  # Fastest software encoding
            "-crf", "23",
            "-maxrate", f"{video_bitrate}k",
            "-bufsize", f"{video_bitrate * 2}k",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate}k",
            "-movflags", "+faststart",
            "-y",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[VideoCompress] FFmpeg error: {result.stderr}")
            raise RuntimeError(f"FFmpeg compression failed: {result.stderr}")

    output_size = get_file_size(output_path)
    output_size_gb = output_size / (1024 * 1024 * 1024)
    compression_ratio = input_size / output_size

    print(f"[VideoCompress] Output size: {output_size_gb:.2f} GB")
    print(f"[VideoCompress] Compression ratio: {compression_ratio:.1f}x")

    # If still too large, try again with lower quality
    if output_size > MAX_SIZE_BYTES:
        print(f"[VideoCompress] Still too large, trying aggressive compression...")
        return compress_video_aggressive(input_path, output_path, target_size_gb * 0.8)

    return output_path


def compress_video_aggressive(
    input_path: str,
    output_path: str,
    target_size_gb: float,
) -> str:
    """More aggressive compression for stubborn files."""
    duration = get_video_duration(input_path)

    # Lower resolution and more aggressive bitrate
    target_size_bits = target_size_gb * 1024 * 1024 * 1024 * 8
    audio_bitrate = 96
    video_bitrate = int((target_size_bits / duration - audio_bitrate * 1000) / 1000)
    video_bitrate = max(video_bitrate, 500)

    print(f"[VideoCompress] Aggressive mode - bitrate: {video_bitrate} kbps")

    # Try VideoToolbox first, fall back to libx264
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "h264_videotoolbox",
        "-b:v", f"{video_bitrate}k",
        "-vf", "scale=-2:720",  # Scale to 720p max
        "-c:a", "aac",
        "-b:a", f"{audio_bitrate}k",
        "-movflags", "+faststart",
        "-y",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Fall back to libx264
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-maxrate", f"{video_bitrate}k",
            "-bufsize", f"{video_bitrate * 2}k",
            "-vf", "scale=-2:720",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate}k",
            "-movflags", "+faststart",
            "-y",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg aggressive compression failed: {result.stderr}")

    output_size_gb = get_file_size(output_path) / (1024 * 1024 * 1024)
    print(f"[VideoCompress] Aggressive output size: {output_size_gb:.2f} GB")

    return output_path
