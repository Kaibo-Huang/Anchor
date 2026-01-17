"""Sponsor overlay service for power plays and branding."""

import os
import tempfile

import ffmpeg

from config import VideoConfig


# Sponsor power play templates
SPONSOR_TEMPLATES = {
    "goal": "{sponsor} GOAL CAM!",
    "highlight": "{sponsor} Play of the Game",
    "replay": "{sponsor} Instant Replay",
    "timeout": "{sponsor} Timeout",
    "intro": "Presented by {sponsor}",
    "outro": "Brought to you by {sponsor}",
}


def create_lower_third_overlay(
    text: str,
    output_path: str,
    duration: float = 4.0,
    width: int = 500,
    height: int = 80,
    bg_color: str = "black@0.7",
    text_color: str = "white",
) -> None:
    """Create a lower-third overlay PNG with transparency.

    Args:
        text: Text to display
        output_path: Output PNG path
        duration: Duration in seconds (for video overlay)
        width: Overlay width
        height: Overlay height
        bg_color: Background color with opacity
        text_color: Text color
    """
    # Create overlay using FFmpeg
    (
        ffmpeg
        .input(f"color=c={bg_color}:s={width}x{height}:d={duration}", f="lavfi")
        .filter("drawtext",
                text=text,
                fontsize=36,
                fontcolor=text_color,
                x="(w-text_w)/2",
                y="(h-text_h)/2",
                borderw=2,
                bordercolor="black")
        .output(output_path, vcodec="libx264", pix_fmt="yuva420p", t=duration)
        .overwrite_output()
        .run(quiet=True)
    )


def apply_sponsor_overlay(
    video_path: str,
    output_path: str,
    sponsor_name: str,
    overlay_type: str,
    start_time: float,
    duration: float = 4.0,
    position: str = "bottom_left",
) -> None:
    """Apply a sponsor overlay to a video.

    Args:
        video_path: Input video path
        output_path: Output video path
        sponsor_name: Sponsor name to display
        overlay_type: Type of overlay (goal, highlight, etc.)
        start_time: When to show overlay (seconds)
        duration: How long to show overlay (seconds)
        position: Where to place overlay (bottom_left, bottom_right, top_left, top_right)
    """
    # Get overlay text
    template = SPONSOR_TEMPLATES.get(overlay_type, "{sponsor}")
    text = template.format(sponsor=sponsor_name)

    # Position coordinates
    positions = {
        "bottom_left": ("20", "H-100"),
        "bottom_right": ("W-520", "H-100"),
        "top_left": ("20", "20"),
        "top_right": ("W-520", "20"),
    }
    x, y = positions.get(position, positions["bottom_left"])

    # Apply overlay with enable filter for timing
    video = ffmpeg.input(video_path)

    video_with_overlay = (
        video.video
        .filter("drawtext",
                text=text,
                fontsize=36,
                fontcolor="white",
                borderw=2,
                bordercolor="black",
                box=1,
                boxcolor="black@0.6",
                boxborderw=10,
                x=x,
                y=y,
                enable=f"between(t,{start_time},{start_time + duration})")
    )

    (
        ffmpeg
        .output(video_with_overlay, video.audio, output_path,
                vcodec="libx264", acodec="copy", crf=18)
        .overwrite_output()
        .run(quiet=True)
    )


def apply_multiple_overlays(
    video_path: str,
    output_path: str,
    overlays: list[dict],
) -> None:
    """Apply multiple sponsor overlays to a video.

    Args:
        video_path: Input video path
        output_path: Output video path
        overlays: List of overlay dicts with sponsor_name, type, start_time, duration, position
    """
    if not overlays:
        # No overlays, just copy
        (
            ffmpeg
            .input(video_path)
            .output(output_path, vcodec="copy", acodec="copy")
            .overwrite_output()
            .run(quiet=True)
        )
        return

    video = ffmpeg.input(video_path)
    video_stream = video.video

    for overlay in overlays:
        template = SPONSOR_TEMPLATES.get(overlay.get("type", "highlight"), "{sponsor}")
        text = template.format(sponsor=overlay["sponsor_name"])

        positions = {
            "bottom_left": ("20", "H-100"),
            "bottom_right": ("W-520", "H-100"),
            "top_left": ("20", "20"),
            "top_right": ("W-520", "20"),
        }
        position = overlay.get("position", "bottom_left")
        x, y = positions.get(position, positions["bottom_left"])

        start = overlay.get("start_time", 0)
        duration = overlay.get("duration", 4.0)

        video_stream = video_stream.filter(
            "drawtext",
            text=text,
            fontsize=36,
            fontcolor="white",
            borderw=2,
            bordercolor="black",
            box=1,
            boxcolor="black@0.6",
            boxborderw=10,
            x=x,
            y=y,
            enable=f"between(t,{start},{start + duration})",
        )

    (
        ffmpeg
        .output(video_stream, video.audio, output_path,
                vcodec="libx264", acodec="copy", crf=18)
        .overwrite_output()
        .run(quiet=True)
    )


def generate_intro_card(
    title: str,
    sponsor_name: str,
    output_path: str,
    duration: float = 3.0,
    event_type: str = "sports",
) -> None:
    """Generate an intro card with event title and sponsor.

    Args:
        title: Event title
        sponsor_name: Sponsor name
        output_path: Output video path
        duration: Duration in seconds
        event_type: Event type for styling
    """
    # Color schemes by event type
    colors = {
        "sports": "#1a237e",  # Dark blue
        "ceremony": "#311b92",  # Deep purple
        "performance": "#b71c1c",  # Dark red
    }
    bg_color = colors.get(event_type, colors["sports"])

    sponsor_text = f"Presented by {sponsor_name}" if sponsor_name else ""

    (
        ffmpeg
        .input(f"color=c={bg_color}:s=1920x1080:d={duration}", f="lavfi")
        .filter("drawtext",
                text=title,
                fontsize=72,
                fontcolor="white",
                x="(w-text_w)/2",
                y="(h-text_h)/2-50")
        .filter("drawtext",
                text=sponsor_text,
                fontsize=36,
                fontcolor="white@0.8",
                x="(w-text_w)/2",
                y="(h-text_h)/2+50")
        .output(output_path, vcodec="libx264", pix_fmt="yuv420p", t=duration)
        .overwrite_output()
        .run(quiet=True)
    )


def generate_outro_card(
    sponsor_name: str,
    output_path: str,
    duration: float = 3.0,
) -> None:
    """Generate an outro card with sponsor branding.

    Args:
        sponsor_name: Sponsor name
        output_path: Output video path
        duration: Duration in seconds
    """
    text = f"Brought to you by {sponsor_name}" if sponsor_name else "Thanks for watching"

    (
        ffmpeg
        .input("color=c=black:s=1920x1080:d=" + str(duration), f="lavfi")
        .filter("drawtext",
                text=text,
                fontsize=48,
                fontcolor="white",
                x="(w-text_w)/2",
                y="(h-text_h)/2")
        .output(output_path, vcodec="libx264", pix_fmt="yuv420p", t=duration)
        .overwrite_output()
        .run(quiet=True)
    )
