"""FFmpeg rendering service for video composition and output."""

import os
import subprocess
import tempfile
from typing import Literal

import ffmpeg

from config import VideoConfig, MUSIC_MIX_PROFILES


def render_final_video(
    video_paths: list[dict],
    timeline: dict,
    output_path: str,
    music_path: str | None = None,
    event_type: str = "sports",
    sponsor_name: str | None = None,
    generated_ads: list[dict] | None = None,
) -> None:
    """Render the final video from timeline and source videos.

    Args:
        video_paths: List of dicts with id, path, sync_offset_ms
        timeline: Timeline with segments, zooms, ad_slots, chapters
        output_path: Path to write output video
        music_path: Optional path to music file
        event_type: Event type for audio mixing profile
        sponsor_name: Optional sponsor name for overlays
        generated_ads: Optional list of generated Veo ads with video_path and timestamp_ms
    """
    print(f"[Render] ========== STARTING FINAL VIDEO RENDER ==========")
    print(f"[Render] Source videos: {len(video_paths)}")
    print(f"[Render] Output path: {output_path}")
    print(f"[Render] Music: {'Yes' if music_path else 'No'}")
    print(f"[Render] Sponsor: {sponsor_name or 'None'}")
    print(f"[Render] Ads: {len(generated_ads) if generated_ads else 0}")

    # Create video ID to path mapping
    video_map = {v["id"]: v for v in video_paths}

    segments = timeline.get("segments", [])
    if not segments:
        print(f"[Render] ERROR: No segments in timeline")
        raise ValueError("No segments in timeline")

    print(f"[Render] Timeline has {len(segments)} segments")

    # Create temp directory for intermediate files
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"[Render] Working in temp directory: {tmpdir}")

        # Extract and prepare each segment
        print(f"[Render] ---------- EXTRACTING SEGMENTS ----------")
        segment_files = []

        # Log which videos are being used
        video_usage = {}
        for seg in segments:
            vid = seg["video_id"]
            video_usage[vid] = video_usage.get(vid, 0) + 1
        print(f"[Render] Video usage in timeline: {video_usage}")

        for i, segment in enumerate(segments):
            video = video_map.get(segment["video_id"])
            if not video:
                print(f"[Render] WARNING: Video not found for segment {i}: {segment['video_id']}")
                print(f"[Render] Available videos: {list(video_map.keys())}")
                continue

            # Calculate times with sync offset
            sync_offset = video.get("sync_offset_ms", 0)
            start_sec = (segment["start_ms"] - sync_offset) / 1000
            duration_sec = (segment["end_ms"] - segment["start_ms"]) / 1000

            # Clamp start to valid range
            if start_sec < 0:
                # Adjust duration to compensate for clamping
                duration_sec = duration_sec + start_sec  # start_sec is negative, so this reduces duration
                start_sec = 0

            # Skip segments that are too short (< 0.5 seconds)
            if duration_sec < 0.5:
                print(f"[Render] WARNING: Skipping segment {i} - duration too short ({duration_sec:.2f}s)")
                continue

            segment_path = os.path.join(tmpdir, f"segment_{i:04d}.mp4")

            print(f"[Render] Extracting segment {i + 1}/{len(segments)} from video '{segment['video_id']}': {start_sec:.2f}s for {duration_sec:.2f}s (sync_offset={sync_offset}ms)")

            # Extract segment with FFmpeg
            try:
                (
                    ffmpeg
                    .input(video["path"], ss=start_sec, t=duration_sec)
                    .output(segment_path, vcodec="libx264", acodec="aac", crf=18,
                            pix_fmt="yuv420p", movflags="+faststart")
                    .overwrite_output()
                    .run(quiet=True)
                )
                segment_files.append(segment_path)
                # Verify segment was created and has content
                seg_size = os.path.getsize(segment_path)
                print(f"[Render] Segment {i + 1} extracted successfully ({seg_size / 1024:.1f} KB)")
            except ffmpeg.Error as e:
                print(f"[Render] ERROR extracting segment {i}: {e}")
                if hasattr(e, 'stderr') and e.stderr:
                    print(f"[Render] FFmpeg stderr: {e.stderr.decode()[:500]}")
                continue

        if not segment_files:
            print(f"[Render] ERROR: No segments extracted")
            raise ValueError("No segments extracted")

        print(f"[Render] Total segments extracted: {len(segment_files)}")

        # Apply zooms to segments
        zooms = timeline.get("zooms", [])
        if zooms:
            print(f"[Render] ---------- APPLYING ZOOMS ----------")
            print(f"[Render] Applying {len(zooms)} zoom effects...")
            segment_files = apply_zooms_to_segments(segment_files, segments, zooms, tmpdir)
        else:
            print(f"[Render] No zoom effects to apply")

        # Concatenate segments with crossfades
        print(f"[Render] ---------- CONCATENATING SEGMENTS ----------")
        concat_path = os.path.join(tmpdir, "concat.mp4")
        print(f"[Render] Concatenating {len(segment_files)} segments with crossfades...")
        concatenate_with_crossfades(segment_files, concat_path)
        print(f"[Render] Concatenation complete")

        # Insert generated ads if provided
        if generated_ads:
            print(f"[Render] ---------- INSERTING ADS ----------")
            print(f"[Render] Inserting {len(generated_ads)} ads into video...")
            ads_inserted_path = os.path.join(tmpdir, "with_ads.mp4")
            insert_ads_into_video(concat_path, generated_ads, ads_inserted_path, tmpdir)
            concat_path = ads_inserted_path
            print(f"[Render] Ads inserted successfully")

        # Add sponsor overlays if provided
        if sponsor_name:
            print(f"[Render] ---------- ADDING SPONSOR OVERLAYS ----------")
            print(f"[Render] Adding sponsor overlays for: {sponsor_name}")
            overlay_path = os.path.join(tmpdir, "overlay.mp4")
            add_sponsor_overlays(concat_path, overlay_path, sponsor_name, timeline)
            concat_path = overlay_path
            print(f"[Render] Sponsor overlays added")

        # Mix music if provided
        if music_path:
            print(f"[Render] ---------- MIXING MUSIC ----------")
            print(f"[Render] Mixing music with event type profile: {event_type}")
            mix_path = os.path.join(tmpdir, "mixed.mp4")
            mix_audio(concat_path, music_path, mix_path, event_type)
            concat_path = mix_path
            print(f"[Render] Music mix complete")

        # Final copy to output
        print(f"[Render] ---------- FINALIZING OUTPUT ----------")
        print(f"[Render] Copying final video to: {output_path}")
        (
            ffmpeg
            .input(concat_path)
            .output(output_path, vcodec="copy", acodec="copy")
            .overwrite_output()
            .run(quiet=True)
        )

        output_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[Render] Final video size: {output_size:.1f} MB")
        print(f"[Render] ========== RENDER COMPLETE ==========")


def concatenate_with_crossfades(
    segment_files: list[str],
    output_path: str,
    crossfade_duration: float = 0.5,
) -> None:
    """Concatenate video segments using concat demuxer (simple, reliable).

    Args:
        segment_files: List of paths to segment files
        output_path: Path to write concatenated output
        crossfade_duration: Duration of crossfade in seconds (currently unused - using simple concat)
    """
    import tempfile

    if len(segment_files) == 1:
        # No concatenation needed
        (
            ffmpeg
            .input(segment_files[0])
            .output(output_path, vcodec="copy", acodec="copy")
            .overwrite_output()
            .run(quiet=True)
        )
        return

    # Use concat demuxer - simpler and more reliable than xfade filter
    # Create a temporary file listing all segments
    concat_list_path = output_path + ".txt"
    with open(concat_list_path, "w") as f:
        for segment in segment_files:
            f.write(f"file '{segment}'\n")

    try:
        (
            ffmpeg
            .input(concat_list_path, format="concat", safe=0)
            .output(output_path, vcodec="libx264", acodec="aac", crf=18,
                    pix_fmt="yuv420p", movflags="+faststart")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        print(f"[Render] FFmpeg stderr: {e.stderr.decode() if e.stderr else 'no stderr'}")
        raise
    finally:
        # Clean up temp file
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


def apply_zooms_to_segments(
    segment_files: list[str],
    segments: list[dict],
    zooms: list[dict],
    tmpdir: str,
) -> list[str]:
    """Apply Ken Burns zoom effects to segments containing zoom moments.

    Args:
        segment_files: List of segment file paths
        segments: Timeline segments
        zooms: Zoom moments from timeline
        tmpdir: Temp directory for intermediate files

    Returns:
        Updated list of segment files (some may be replaced with zoomed versions)
    """
    if not zooms:
        return segment_files

    result_files = list(segment_files)

    for zoom in zooms:
        # Find which segment contains this zoom
        zoom_start = zoom["start_ms"]
        zoom_duration = zoom.get("duration_ms", 3000) / 1000
        zoom_factor = zoom.get("zoom_factor", VideoConfig.ZOOM_FACTOR_MED)

        for i, segment in enumerate(segments):
            if segment["start_ms"] <= zoom_start < segment["end_ms"]:
                # Apply zoom to this segment
                zoomed_path = os.path.join(tmpdir, f"zoomed_{i:04d}.mp4")

                # Time within segment
                segment_offset = (zoom_start - segment["start_ms"]) / 1000

                try:
                    apply_ken_burns_zoom(
                        input_path=result_files[i],
                        output_path=zoomed_path,
                        start_sec=segment_offset,
                        duration_sec=zoom_duration,
                        zoom_factor=zoom_factor,
                    )
                    result_files[i] = zoomed_path
                except Exception as e:
                    print(f"Failed to apply zoom: {e}")

                break

    return result_files


def apply_ken_burns_zoom(
    input_path: str,
    output_path: str,
    start_sec: float,
    duration_sec: float,
    zoom_factor: float,
) -> None:
    """Apply Ken Burns zoom effect using FFmpeg zoompan filter.

    Args:
        input_path: Input video path
        output_path: Output video path
        start_sec: When to start zoom within video (currently applies to entire segment)
        duration_sec: Duration of zoom effect
        zoom_factor: Maximum zoom level (e.g., 1.5 = 150%)
    """
    # Get input properties
    probe = ffmpeg.probe(input_path)
    video_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
    if not video_streams:
        raise ValueError(f"No video stream found in {input_path}")

    video_info = video_streams[0]
    # Parse frame rate (handles "30/1" or "30000/1001" format)
    fps_parts = video_info["r_frame_rate"].split("/")
    fps = int(fps_parts[0]) / int(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])

    # Calculate frames
    ease_frames = int(0.3 * fps)
    hold_frames = max(1, int((duration_sec - 0.6) * fps))
    total_frames = ease_frames * 2 + hold_frames

    # Build zoompan expression with ease-in, hold, ease-out
    zoom_expr = (
        f"if(lte(on,{ease_frames}),"
        f"1+({zoom_factor - 1}/{ease_frames})*on,"
        f"if(lte(on,{ease_frames + hold_frames}),"
        f"{zoom_factor},"
        f"{zoom_factor}-({zoom_factor - 1}/{ease_frames})*(on-{ease_frames + hold_frames})))"
    )

    # Apply zoom with proper fps setting
    # Note: zoompan outputs at specified fps, we match input fps
    input_stream = ffmpeg.input(input_path)
    (
        input_stream
        .filter("zoompan",
                z=zoom_expr,
                d=total_frames,
                x="iw/2-(iw/zoom/2)",
                y="ih/2-(ih/zoom/2)",
                s="1920x1080",
                fps=fps)
        .output(output_path, vcodec="libx264", acodec="aac", crf=18,
                pix_fmt="yuv420p", movflags="+faststart")
        .overwrite_output()
        .run(quiet=True)
    )


def add_sponsor_overlays(
    input_path: str,
    output_path: str,
    sponsor_name: str,
    timeline: dict,
) -> None:
    """Add sponsor lower-third overlays at key moments.

    Args:
        input_path: Input video path
        output_path: Output video path
        sponsor_name: Sponsor name to display
        timeline: Timeline with chapters for overlay placement
    """
    # Find moments for sponsor overlays (use chapters as trigger points)
    chapters = timeline.get("chapters", [])
    overlays = []

    for chapter in chapters:
        if chapter.get("type") == "highlight":
            timestamp_sec = chapter["timestamp_ms"] / 1000
            text = f"{sponsor_name} HIGHLIGHT"
            overlays.append((timestamp_sec, text))

    if not overlays:
        # No overlays needed, just copy
        (
            ffmpeg
            .input(input_path)
            .output(output_path, vcodec="copy", acodec="copy")
            .overwrite_output()
            .run(quiet=True)
        )
        return

    # Build filter for drawtext overlays
    video = ffmpeg.input(input_path)

    for timestamp, text in overlays:
        # Show for 4 seconds
        video = video.filter(
            "drawtext",
            text=text,
            fontsize=36,
            fontcolor="white",
            borderw=2,
            bordercolor="black",
            x="20",
            y="h-60",
            enable=f"between(t,{timestamp},{timestamp + 4})",
        )

    (
        ffmpeg
        .output(video, ffmpeg.input(input_path).audio, output_path,
                vcodec="libx264", acodec="aac", crf=18,
                pix_fmt="yuv420p", movflags="+faststart")
        .overwrite_output()
        .run(quiet=True)
    )


def mix_audio(
    video_path: str,
    music_path: str,
    output_path: str,
    event_type: str,
) -> None:
    """Mix music with video audio using event-specific profile.

    Args:
        video_path: Input video path
        music_path: Music file path
        output_path: Output video path
        event_type: Event type for mixing profile
    """
    profile = MUSIC_MIX_PROFILES.get(event_type, MUSIC_MIX_PROFILES["sports"])
    music_vol = profile["music_volume"]
    event_vol = profile["event_volume"]

    # Get video duration
    probe = ffmpeg.probe(video_path)
    duration = float(probe["format"]["duration"])

    video = ffmpeg.input(video_path)
    music = ffmpeg.input(music_path)

    # Apply volume and fades to music
    music_audio = (
        music.audio
        .filter("volume", music_vol)
        .filter("afade", t="in", d=VideoConfig.MUSIC_FADE_IN_SEC)
        .filter("afade", t="out", d=VideoConfig.MUSIC_FADE_OUT_SEC, st=duration - VideoConfig.MUSIC_FADE_OUT_SEC)
    )

    # Apply volume to event audio
    event_audio = video.audio.filter("volume", event_vol)

    # Mix
    mixed = ffmpeg.filter([music_audio, event_audio], "amix", inputs=2, duration="first")

    (
        ffmpeg
        .output(video.video, mixed, output_path, vcodec="libx264", acodec="aac", crf=18,
                pix_fmt="yuv420p", movflags="+faststart")
        .overwrite_output()
        .run(quiet=True)
    )


def render_highlight_reel(
    clips: list[dict],
    output_path: str,
    title: str,
    music_path: str | None = None,
    vibe: Literal["high_energy", "emotional", "calm"] = "high_energy",
) -> None:
    """Render a highlight reel from selected clips.

    Args:
        clips: List of dicts with path, start, end
        output_path: Path to write output
        title: Title for intro card
        music_path: Optional music file
        vibe: Vibe for styling
    """
    print(f"[Render:Reel] ========== RENDERING HIGHLIGHT REEL ==========")
    print(f"[Render:Reel] Title: '{title}'")
    print(f"[Render:Reel] Vibe: {vibe}")
    print(f"[Render:Reel] Clips: {len(clips)}")
    print(f"[Render:Reel] Music: {'Yes' if music_path else 'No'}")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Generate title card
        print(f"[Render:Reel] Generating title card...")
        title_path = os.path.join(tmpdir, "title.mp4")
        generate_title_card(title, vibe, title_path)
        print(f"[Render:Reel] Title card generated")

        # Extract clips
        print(f"[Render:Reel] ---------- EXTRACTING CLIPS ----------")
        clip_files = [title_path]
        for i, clip in enumerate(clips):
            clip_path = os.path.join(tmpdir, f"clip_{i:04d}.mp4")
            start = clip["start"]
            duration = clip["end"] - clip["start"]

            print(f"[Render:Reel] Extracting clip {i + 1}/{len(clips)}: {start:.1f}s - {clip['end']:.1f}s ({duration:.1f}s)")
            (
                ffmpeg
                .input(clip["path"], ss=start, t=duration)
                .output(clip_path, vcodec="libx264", acodec="aac", crf=18,
                        pix_fmt="yuv420p", movflags="+faststart")
                .overwrite_output()
                .run(quiet=True)
            )
            clip_files.append(clip_path)
            print(f"[Render:Reel] Clip {i + 1} extracted")

        # Concatenate with crossfades
        print(f"[Render:Reel] ---------- CONCATENATING CLIPS ----------")
        concat_path = os.path.join(tmpdir, "concat.mp4")
        print(f"[Render:Reel] Concatenating {len(clip_files)} clips (including title)...")
        concatenate_with_crossfades(clip_files, concat_path, crossfade_duration=0.5)
        print(f"[Render:Reel] Concatenation complete")

        # Add music if provided
        if music_path:
            print(f"[Render:Reel] ---------- ADDING MUSIC ----------")
            print(f"[Render:Reel] Mixing music...")
            mix_audio(concat_path, music_path, output_path, "sports")
            print(f"[Render:Reel] Music added")
        else:
            print(f"[Render:Reel] Copying to output (no music)...")
            (
                ffmpeg
                .input(concat_path)
                .output(output_path, vcodec="copy", acodec="copy")
                .overwrite_output()
                .run(quiet=True)
            )

        output_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[Render:Reel] Output size: {output_size:.1f} MB")
        print(f"[Render:Reel] ========== HIGHLIGHT REEL COMPLETE ==========")


def generate_title_card(
    title: str,
    vibe: str,
    output_path: str,
    duration: float = 2.0,
) -> None:
    """Generate a title card video.

    Args:
        title: Title text
        vibe: Vibe for color scheme
        output_path: Output video path
        duration: Duration in seconds
    """
    vibe_colors = {
        "high_energy": "#FF5722",
        "emotional": "#3F51B5",
        "calm": "#4CAF50",
    }
    bg_color = vibe_colors.get(vibe, "#333333")

    # Use FFmpeg to generate title card
    (
        ffmpeg
        .input(f"color=c={bg_color}:s=1920x1080:d={duration}", f="lavfi")
        .filter("drawtext",
                text=title,
                fontsize=72,
                fontcolor="white",
                x="(w-text_w)/2",
                y="(h-text_h)/2")
        .output(output_path, vcodec="libx264", pix_fmt="yuv420p", t=duration)
        .overwrite_output()
        .run(quiet=True)
    )


def insert_ads_into_video(
    video_path: str,
    ads: list[dict],
    output_path: str,
    tmpdir: str,
    crossfade_duration: float = 0.5,
) -> None:
    """Insert generated ads into video at specified timestamps with crossfade transitions.

    This creates a seamless TV commercial break feel by:
    1. Splitting the video at each ad insertion point
    2. Inserting the ad with xfade transitions on both sides
    3. Reassembling the final video

    Args:
        video_path: Path to the main video
        ads: List of ad dicts with timestamp_ms, video_path, duration_ms
        output_path: Path to write output video
        tmpdir: Temp directory for intermediate files
        crossfade_duration: Duration of crossfade transitions in seconds
    """
    if not ads:
        # No ads to insert, just copy
        (
            ffmpeg
            .input(video_path)
            .output(output_path, vcodec="copy", acodec="copy")
            .overwrite_output()
            .run(quiet=True)
        )
        return

    # Sort ads by timestamp
    sorted_ads = sorted(ads, key=lambda a: a["timestamp_ms"])

    # Get video duration
    probe = ffmpeg.probe(video_path)
    video_duration = float(probe["format"]["duration"])

    # Build list of all segments (video parts + ads)
    all_segments = []
    current_pos = 0

    for i, ad in enumerate(sorted_ads):
        insert_time = ad["timestamp_ms"] / 1000

        # Skip if insert time is past video end
        if insert_time >= video_duration:
            continue

        # Extract segment before this ad
        if insert_time > current_pos:
            segment_path = os.path.join(tmpdir, f"pre_ad_{i:02d}.mp4")
            segment_duration = insert_time - current_pos

            try:
                (
                    ffmpeg
                    .input(video_path, ss=current_pos, t=segment_duration)
                    .output(segment_path, vcodec="libx264", acodec="aac", crf=18,
                            pix_fmt="yuv420p", movflags="+faststart")
                    .overwrite_output()
                    .run(quiet=True)
                )
                all_segments.append({
                    "path": segment_path,
                    "type": "video",
                })
            except ffmpeg.Error as e:
                print(f"Error extracting pre-ad segment {i}: {e}")

        # Add the ad
        ad_path = ad.get("video_path")
        if ad_path and os.path.exists(ad_path):
            # Normalize ad video to match main video specs
            normalized_ad_path = os.path.join(tmpdir, f"ad_{i:02d}_normalized.mp4")
            normalize_ad_video(ad_path, normalized_ad_path)

            all_segments.append({
                "path": normalized_ad_path,
                "type": "ad",
                "product_title": ad.get("product_title", ""),
            })

        # Update position (skip over the ad duration in the timeline)
        current_pos = insert_time

    # Extract remaining video after last ad
    if current_pos < video_duration:
        final_segment_path = os.path.join(tmpdir, "post_ads.mp4")
        try:
            (
                ffmpeg
                .input(video_path, ss=current_pos)
                .output(final_segment_path, vcodec="libx264", acodec="aac", crf=18,
                        pix_fmt="yuv420p", movflags="+faststart")
                .overwrite_output()
                .run(quiet=True)
            )
            all_segments.append({
                "path": final_segment_path,
                "type": "video",
            })
        except ffmpeg.Error as e:
            print(f"Error extracting final segment: {e}")

    if not all_segments:
        raise ValueError("No segments created for ad insertion")

    # Concatenate all segments with crossfades
    segment_paths = [s["path"] for s in all_segments]
    concatenate_with_crossfades(segment_paths, output_path, crossfade_duration)


def normalize_ad_video(
    input_path: str,
    output_path: str,
    target_width: int = 1920,
    target_height: int = 1080,
    target_fps: int = 30,
) -> None:
    """Normalize ad video to match main video specifications.

    Ensures consistent resolution, frame rate, and codec settings.

    Args:
        input_path: Path to ad video
        output_path: Path to write normalized video
        target_width: Target width in pixels
        target_height: Target height in pixels
        target_fps: Target frame rate
    """
    try:
        (
            ffmpeg
            .input(input_path)
            .filter("scale", w=target_width, h=target_height, force_original_aspect_ratio="decrease")
            .filter("pad", w=target_width, h=target_height, x="(ow-iw)/2", y="(oh-ih)/2")
            .filter("fps", fps=target_fps)
            .output(output_path, vcodec="libx264", acodec="aac", crf=18, ar=44100,
                    pix_fmt="yuv420p", movflags="+faststart")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        print(f"Error normalizing ad video: {e}")
        # Fall back to simple copy
        import shutil
        shutil.copy(input_path, output_path)


def add_product_callout(
    video_path: str,
    output_path: str,
    product_title: str,
    price: str | None = None,
    position: str = "bottom_right",
) -> None:
    """Add a product callout overlay to an ad video.

    Shows product name and optional price in a styled overlay.

    Args:
        video_path: Path to ad video
        output_path: Path to write output
        product_title: Product name to display
        price: Optional price string
        position: Overlay position (bottom_right, bottom_left, bottom_center)
    """
    # Build text
    text = product_title
    if price:
        text += f"\\n${price}"

    # Position coordinates
    positions = {
        "bottom_right": ("W-tw-30", "H-th-30"),
        "bottom_left": ("30", "H-th-30"),
        "bottom_center": ("(W-tw)/2", "H-th-30"),
    }
    x, y = positions.get(position, positions["bottom_right"])

    try:
        (
            ffmpeg
            .input(video_path)
            .filter("drawtext",
                    text=text,
                    fontsize=28,
                    fontcolor="white",
                    borderw=2,
                    bordercolor="black@0.8",
                    x=x,
                    y=y,
                    box=1,
                    boxcolor="black@0.5",
                    boxborderw=10)
            .output(output_path, vcodec="libx264", acodec="aac", crf=18,
                    pix_fmt="yuv420p", movflags="+faststart")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        print(f"Error adding product callout: {e}")
        import shutil
        shutil.copy(video_path, output_path)
