"""FFmpeg rendering service for video composition and output."""

import os
import platform
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

import ffmpeg

from config import VideoConfig, MUSIC_MIX_PROFILES

# Number of parallel segment extractions (balance between speed and system load)
MAX_PARALLEL_EXTRACTIONS = 4


# Hardware acceleration settings
# On macOS, use VideoToolbox for ~5-10x faster encoding
# Falls back to libx264 if hardware encoder fails
_HWACCEL_AVAILABLE: bool | None = None


def _check_hwaccel_available() -> bool:
    """Check if hardware acceleration is available."""
    global _HWACCEL_AVAILABLE
    if _HWACCEL_AVAILABLE is not None:
        return _HWACCEL_AVAILABLE

    if platform.system() != "Darwin":
        _HWACCEL_AVAILABLE = False
        return False

    # Check if h264_videotoolbox encoder is available
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        _HWACCEL_AVAILABLE = "h264_videotoolbox" in result.stdout
        if _HWACCEL_AVAILABLE:
            print("[Render] Hardware acceleration available: h264_videotoolbox")
        return _HWACCEL_AVAILABLE
    except Exception:
        _HWACCEL_AVAILABLE = False
        return False


def _get_video_codec() -> str:
    """Get the best available video codec."""
    if _check_hwaccel_available():
        return "h264_videotoolbox"
    return "libx264"


def _get_encoding_params(use_hw: bool = True) -> dict:
    """Get encoding parameters based on available hardware.

    Args:
        use_hw: Whether to attempt hardware encoding

    Returns:
        Dict of ffmpeg output parameters
    """
    if use_hw and _check_hwaccel_available():
        # VideoToolbox parameters - uses bitrate instead of CRF
        return {
            "vcodec": "h264_videotoolbox",
            "video_bitrate": "8M",  # 8 Mbps for high quality
            "acodec": "aac",
            "pix_fmt": "yuv420p",
            "movflags": "+faststart",
        }
    else:
        # Software encoding with libx264
        return {
            "vcodec": "libx264",
            "crf": 18,
            "acodec": "aac",
            "pix_fmt": "yuv420p",
            "movflags": "+faststart",
        }


def _extract_single_segment(task: dict) -> tuple[int, str | None, str | None]:
    """Extract a single segment using stream copy (fast) with re-encode fallback.

    Returns:
        Tuple of (index, segment_path or None, error message or None)
    """
    index = task["index"]
    video_path = task["video_path"]
    segment_path = task["segment_path"]
    start_sec = task["start_sec"]
    duration_sec = task["duration_sec"]

    # Try stream copy first (10-100x faster than re-encoding)
    try:
        (
            ffmpeg
            .input(video_path, ss=start_sec, t=duration_sec)
            .output(segment_path, vcodec="copy", acodec="copy", movflags="+faststart")
            .overwrite_output()
            .run(quiet=True)
        )
        return (index, segment_path, None)
    except ffmpeg.Error:
        # Stream copy failed, fall back to re-encoding with hardware acceleration
        try:
            enc_params = _get_encoding_params()
            (
                ffmpeg
                .input(video_path, ss=start_sec, t=duration_sec)
                .output(segment_path, **enc_params)
                .overwrite_output()
                .run(quiet=True)
            )
            return (index, segment_path, None)
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode()[:200] if hasattr(e, 'stderr') and e.stderr else str(e)
            return (index, None, error_msg)


def _extract_segments_parallel(tasks: list[dict]) -> tuple[list[str], list[int]]:
    """Extract multiple segments in parallel.

    Args:
        tasks: List of extraction task dicts

    Returns:
        Tuple of (list of segment paths in order, list of task indices that succeeded)
    """
    results = {}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_EXTRACTIONS) as executor:
        futures = {executor.submit(_extract_single_segment, task): task for task in tasks}

        completed = 0
        total = len(tasks)
        for future in as_completed(futures):
            completed += 1
            index, segment_path, error = future.result()
            if segment_path:
                results[index] = segment_path
                seg_size = os.path.getsize(segment_path) / 1024
                print(f"[Render] Segment {completed}/{total} extracted ({seg_size:.1f} KB)")
            else:
                print(f"[Render] ERROR extracting segment {index}: {error}")

    # Return paths and indices in order
    sorted_indices = sorted(results.keys())
    return [results[i] for i in sorted_indices], sorted_indices


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
    print(f"[Render] Hardware acceleration: {'h264_videotoolbox' if _check_hwaccel_available() else 'disabled (using libx264)'}")
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
        print(f"[Render] ---------- EXTRACTING SEGMENTS (PARALLEL) ----------")

        # Log which videos are being used
        video_usage = {}
        for seg in segments:
            vid = seg["video_id"]
            video_usage[vid] = video_usage.get(vid, 0) + 1
        print(f"[Render] Video usage in timeline: {video_usage}")

        # Prepare extraction tasks
        extraction_tasks = []
        segment_index_map = {}  # Maps extraction task index to original segment index
        task_idx = 0

        for i, segment in enumerate(segments):
            video = video_map.get(segment["video_id"])
            if not video:
                print(f"[Render] WARNING: Video not found for segment {i}: {segment['video_id']}")
                continue

            # Calculate times with sync offset
            # sync_offset is when this video's audio matches the reference video
            # So we need to subtract it to find the correct position in this video
            sync_offset = video.get("sync_offset_ms", 0)
            segment_start_ms = segment["start_ms"]
            segment_end_ms = segment["end_ms"]

            # Calculate actual position in source video
            start_sec = (segment_start_ms - sync_offset) / 1000
            end_sec = (segment_end_ms - sync_offset) / 1000

            # Handle edge cases where sync offset pushes us before video start
            if start_sec < 0:
                start_sec = 0
            if end_sec <= 0:
                print(f"[Render] WARNING: Segment {i} ends before video start (sync_offset={sync_offset}ms), skipping")
                continue

            duration_sec = end_sec - start_sec

            # Skip segments that are too short
            if duration_sec < 0.5:
                print(f"[Render] WARNING: Segment {i} too short ({duration_sec:.2f}s), skipping")
                continue

            segment_path = os.path.join(tmpdir, f"segment_{i:04d}.mp4")
            extraction_tasks.append({
                "index": task_idx,
                "original_segment_index": i,  # Track original segment index for zooms
                "video_path": video["path"],
                "segment_path": segment_path,
                "start_sec": start_sec,
                "duration_sec": duration_sec,
            })
            segment_index_map[task_idx] = i
            task_idx += 1

        print(f"[Render] Extracting {len(extraction_tasks)} segments using {MAX_PARALLEL_EXTRACTIONS} parallel workers...")

        # Extract segments in parallel using stream copy (much faster)
        segment_files, extracted_indices = _extract_segments_parallel(extraction_tasks)

        if not segment_files:
            print(f"[Render] ERROR: No segments extracted")
            raise ValueError("No segments extracted")

        # Check if any segments failed - if so, we have gaps in the timeline
        if len(segment_files) != len(extraction_tasks):
            failed_count = len(extraction_tasks) - len(segment_files)
            print(f"[Render] WARNING: {failed_count} segments failed to extract - output may have gaps!")

        print(f"[Render] Total segments extracted: {len(segment_files)}")

        # Build mapping from original segment index to extracted file index
        original_to_extracted = {}
        for extracted_idx, task_idx in enumerate(extracted_indices):
            original_seg_idx = segment_index_map.get(task_idx)
            if original_seg_idx is not None:
                original_to_extracted[original_seg_idx] = extracted_idx

        # Apply zooms to segments
        zooms = timeline.get("zooms", [])
        if zooms:
            print(f"[Render] ---------- APPLYING ZOOMS ----------")
            print(f"[Render] Applying {len(zooms)} zoom effects...")
            segment_files = apply_zooms_to_segments(
                segment_files, segments, zooms, tmpdir, original_to_extracted
            )
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


def _get_video_duration(path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    probe = ffmpeg.probe(path)
    return float(probe["format"]["duration"])


def _normalize_segment(input_path: str, output_path: str) -> None:
    """Normalize a segment to consistent format for concatenation with crossfades.

    Ensures all segments have:
    - Same resolution (1920x1080)
    - Same frame rate (30fps)
    - Same audio sample rate (48000Hz)
    - Same pixel format (yuv420p)
    """
    enc_params = _get_encoding_params()
    enc_params["ar"] = 48000  # Consistent audio sample rate

    try:
        # Check if input has audio stream
        probe = ffmpeg.probe(input_path)
        has_audio = any(s["codec_type"] == "audio" for s in probe.get("streams", []))

        input_stream = ffmpeg.input(input_path)

        # Apply video filters
        video = (
            input_stream.video
            .filter("scale", w=1920, h=1080, force_original_aspect_ratio="decrease")
            .filter("pad", w=1920, h=1080, x="(ow-iw)/2", y="(oh-ih)/2")
            .filter("fps", fps=30)
            .filter("format", pix_fmts="yuv420p")
        )

        if has_audio:
            # Get audio stream (will be resampled by ar parameter)
            audio = input_stream.audio
            # Output with both streams
            (
                ffmpeg
                .output(video, audio, output_path, **enc_params)
                .overwrite_output()
                .run(quiet=True)
            )
        else:
            # Video only - generate silent audio to ensure consistent format
            # This prevents issues when concatenating with segments that have audio
            silent_audio = ffmpeg.input("anullsrc=r=48000:cl=stereo", f="lavfi", t=_get_video_duration(input_path))
            enc_params_no_ar = {k: v for k, v in enc_params.items() if k != "ar"}
            (
                ffmpeg
                .output(video, silent_audio, output_path, **enc_params_no_ar, ar=48000)
                .overwrite_output()
                .run(quiet=True)
            )
            print("[Render] Added silent audio to segment without audio track")

    except ffmpeg.Error as e:
        print(f"[Render] Normalization failed: {e.stderr.decode() if e.stderr else 'no stderr'}")
        # Fall back to just copying
        import shutil
        shutil.copy(input_path, output_path)


def concatenate_with_crossfades(
    segment_files: list[str],
    output_path: str,
    crossfade_duration: float = 0.5,
) -> None:
    """Concatenate video segments with actual crossfade transitions using xfade filter.

    This properly blends segments together for smooth visual transitions.
    Requires re-encoding but produces professional-quality output.

    Args:
        segment_files: List of paths to segment files
        output_path: Path to write concatenated output
        crossfade_duration: Duration of crossfade in seconds
    """
    if len(segment_files) == 1:
        # No concatenation needed - just copy
        (
            ffmpeg
            .input(segment_files[0])
            .output(output_path, vcodec="copy", acodec="copy")
            .overwrite_output()
            .run(quiet=True)
        )
        return

    print(f"[Render] Concatenating {len(segment_files)} segments with crossfade transitions...")

    # First, normalize all segments to ensure compatible formats
    tmpdir = os.path.dirname(segment_files[0])
    normalized_files = []

    print("[Render] Normalizing segments for crossfade compatibility...")
    for i, seg_path in enumerate(segment_files):
        normalized_path = os.path.join(tmpdir, f"normalized_{i:04d}.mp4")
        _normalize_segment(seg_path, normalized_path)
        normalized_files.append(normalized_path)
        print(f"[Render] Normalized segment {i + 1}/{len(segment_files)}")

    # Get durations of all normalized segments
    durations = []
    for f in normalized_files:
        durations.append(_get_video_duration(f))

    print(f"[Render] Segment durations: {[f'{d:.2f}s' for d in durations]}")

    # Build xfade filter chain using ffmpeg-python
    # For N segments, we need N-1 xfade transitions
    try:
        if len(normalized_files) == 2:
            # Simple case: two segments with one crossfade
            offset = durations[0] - crossfade_duration
            if offset < 0:
                offset = 0

            stream1 = ffmpeg.input(normalized_files[0])
            stream2 = ffmpeg.input(normalized_files[1])

            # Video crossfade
            video = ffmpeg.filter(
                [stream1.video, stream2.video],
                "xfade",
                transition="fade",
                duration=crossfade_duration,
                offset=offset
            )

            # Audio crossfade
            audio = ffmpeg.filter(
                [stream1.audio, stream2.audio],
                "acrossfade",
                d=crossfade_duration
            )

            enc_params = _get_encoding_params()
            (
                ffmpeg
                .output(video, audio, output_path, **enc_params)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        else:
            # Multiple segments: use filter_complex with chained xfades
            # This is complex with ffmpeg-python, so we'll use subprocess directly
            _concatenate_multiple_with_xfade(normalized_files, durations, output_path, crossfade_duration)

        print("[Render] Crossfade concatenation complete")

    except Exception as e:
        # Handle both ffmpeg.Error (has stderr) and other exceptions
        error_msg = str(e)
        if isinstance(e, ffmpeg.Error):
            stderr = getattr(e, 'stderr', None)
            if stderr:
                error_msg = stderr.decode()
        print(f"[Render] Crossfade failed: {error_msg[:300]}")
        print("[Render] Falling back to simple concatenation...")
        # Use normalized files if available, otherwise original
        fallback_files = normalized_files if normalized_files else segment_files
        _concatenate_simple(fallback_files, output_path)


def _concatenate_multiple_with_xfade(
    files: list[str],
    durations: list[float],
    output_path: str,
    crossfade_duration: float,
) -> None:
    """Concatenate multiple segments with xfade using raw ffmpeg command.

    Uses filter_complex to chain xfade filters for both video and audio
    to keep them in sync.
    """
    n = len(files)

    # Build input arguments
    inputs = []
    for f in files:
        inputs.extend(["-i", f])

    # Build filter_complex string
    # Chain xfades for video: [0:v][1:v]xfade -> [v0], [v0][2:v]xfade -> [v1], etc.
    # Chain acrossfade for audio: [0:a][1:a]acrossfade -> [a0], [a0][2:a]acrossfade -> [a1], etc.
    # This keeps video and audio durations in sync

    video_filters = []
    audio_filters = []

    # For chained xfades, offset is when crossfade starts in the LEFT input's timeline
    # First xfade: offset = duration[0] - crossfade
    # After first xfade, output duration = duration[0] + duration[1] - crossfade
    # Second xfade offset = (output duration) - crossfade
    # etc.

    current_output_duration = durations[0]

    for i in range(n - 1):
        offset = current_output_duration - crossfade_duration
        if offset < 0:
            offset = 0

        if i == 0:
            # First xfade/acrossfade: combine inputs 0 and 1
            video_filters.append(
                f"[0:v][1:v]xfade=transition=fade:duration={crossfade_duration}:offset={offset:.3f}[v{i}]"
            )
            audio_filters.append(
                f"[0:a][1:a]acrossfade=d={crossfade_duration}:c1=tri:c2=tri[a{i}]"
            )
        else:
            # Chain from previous result with next input
            video_filters.append(
                f"[v{i-1}][{i+1}:v]xfade=transition=fade:duration={crossfade_duration}:offset={offset:.3f}[v{i}]"
            )
            audio_filters.append(
                f"[a{i-1}][{i+1}:a]acrossfade=d={crossfade_duration}:c1=tri:c2=tri[a{i}]"
            )

        # Update output duration: previous output + next segment - crossfade overlap
        current_output_duration = current_output_duration + durations[i + 1] - crossfade_duration

    # Combine all filters (video first, then audio)
    filter_complex = ";".join(video_filters + audio_filters)

    # Final output labels
    final_video = f"[v{n-2}]"
    final_audio = f"[a{n-2}]"

    # Build full command
    enc_params = _get_encoding_params()
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", final_video,
        "-map", final_audio,
        "-vcodec", enc_params.get("vcodec", "libx264"),
        "-acodec", enc_params.get("acodec", "aac"),
        "-pix_fmt", enc_params.get("pix_fmt", "yuv420p"),
        "-movflags", "+faststart",
    ]

    # Add video-specific encoding params
    if "crf" in enc_params:
        cmd.extend(["-crf", str(enc_params["crf"])])
    elif "video_bitrate" in enc_params:
        cmd.extend(["-b:v", enc_params["video_bitrate"]])

    cmd.append(output_path)

    print(f"[Render] Running xfade command with {n} inputs...")
    print(f"[Render] Filter complex: {filter_complex[:300]}...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[Render] FFmpeg stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg xfade failed: {result.stderr[:500]}")


def _concatenate_simple(segment_files: list[str], output_path: str) -> None:
    """Simple concatenation fallback using concat demuxer."""
    concat_list_path = output_path + ".txt"
    with open(concat_list_path, "w") as f:
        for segment in segment_files:
            f.write(f"file '{segment}'\n")

    try:
        enc_params = _get_encoding_params()
        (
            ffmpeg
            .input(concat_list_path, format="concat", safe=0)
            .output(output_path, **enc_params)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    finally:
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


def apply_zooms_to_segments(
    segment_files: list[str],
    segments: list[dict],
    zooms: list[dict],
    tmpdir: str,
    original_to_extracted: dict[int, int] | None = None,
) -> list[str]:
    """Apply Ken Burns zoom effects to segments containing zoom moments.

    Args:
        segment_files: List of segment file paths
        segments: Timeline segments
        zooms: Zoom moments from timeline
        tmpdir: Temp directory for intermediate files
        original_to_extracted: Mapping from original segment index to extracted file index

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

        for seg_idx, segment in enumerate(segments):
            if segment["start_ms"] <= zoom_start < segment["end_ms"]:
                # Use mapping if available, otherwise fall back to direct index
                if original_to_extracted is not None:
                    if seg_idx not in original_to_extracted:
                        print(f"[Render] Zoom target segment {seg_idx} was not extracted, skipping zoom")
                        break
                    file_idx = original_to_extracted[seg_idx]
                else:
                    file_idx = seg_idx
                    if file_idx >= len(result_files):
                        print(f"[Render] Zoom target index {file_idx} out of range, skipping zoom")
                        break

                # Apply zoom to this segment
                zoomed_path = os.path.join(tmpdir, f"zoomed_{seg_idx:04d}.mp4")

                # Time within segment
                segment_offset = (zoom_start - segment["start_ms"]) / 1000

                try:
                    apply_ken_burns_zoom(
                        input_path=result_files[file_idx],
                        output_path=zoomed_path,
                        start_sec=segment_offset,
                        duration_sec=zoom_duration,
                        zoom_factor=zoom_factor,
                    )
                    result_files[file_idx] = zoomed_path
                    print(f"[Render] Applied zoom to segment {seg_idx} (file idx {file_idx})")
                except Exception as e:
                    print(f"[Render] Failed to apply zoom to segment {seg_idx}: {e}")

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
        .output(output_path, **_get_encoding_params())
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

    enc_params = _get_encoding_params()
    (
        ffmpeg
        .output(video, ffmpeg.input(input_path).audio, output_path, **enc_params)
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

    enc_params = _get_encoding_params()
    (
        ffmpeg
        .output(video.video, mixed, output_path, **enc_params)
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
            enc_params = _get_encoding_params()
            (
                ffmpeg
                .input(clip["path"], ss=start, t=duration)
                .output(clip_path, **enc_params)
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
    enc_params = _get_encoding_params()
    # Remove acodec for title card (no audio source)
    enc_params_no_audio = {k: v for k, v in enc_params.items() if k != "acodec"}
    (
        ffmpeg
        .input(f"color=c={bg_color}:s=1920x1080:d={duration}", f="lavfi")
        .filter("drawtext",
                text=title,
                fontsize=72,
                fontcolor="white",
                x="(w-text_w)/2",
                y="(h-text_h)/2")
        .output(output_path, t=duration, **enc_params_no_audio)
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
                enc_params = _get_encoding_params()
                (
                    ffmpeg
                    .input(video_path, ss=current_pos, t=segment_duration)
                    .output(segment_path, **enc_params)
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
            enc_params = _get_encoding_params()
            (
                ffmpeg
                .input(video_path, ss=current_pos)
                .output(final_segment_path, **enc_params)
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
        enc_params = _get_encoding_params()
        enc_params["ar"] = 44100  # Ensure consistent audio sample rate
        (
            ffmpeg
            .input(input_path)
            .filter("scale", w=target_width, h=target_height, force_original_aspect_ratio="decrease")
            .filter("pad", w=target_width, h=target_height, x="(ow-iw)/2", y="(oh-ih)/2")
            .filter("fps", fps=target_fps)
            .output(output_path, **enc_params)
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
        enc_params = _get_encoding_params()
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
            .output(output_path, **enc_params)
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        print(f"Error adding product callout: {e}")
        import shutil
        shutil.copy(video_path, output_path)
