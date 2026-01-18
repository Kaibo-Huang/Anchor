"""Timeline generation service for multi-angle video switching."""

from typing import Literal

import numpy as np
from scipy.spatial.distance import cosine

from config import (
    VideoConfig,
    SWITCHING_PROFILES,
    MIN_SEGMENT_DURATION_BY_EVENT,
    HYSTERESIS_THRESHOLD,
    SPEAKER_SCORE_MULTIPLIERS,
)
from services.twelvelabs_service import search_videos, create_text_embedding


def generate_timeline(
    videos: list[dict],
    event_type: Literal["sports", "ceremony", "performance", "speech", "lecture"],
    index_id: str | None = None,
    max_duration_ms: int | None = None,
) -> dict:
    """Generate a timeline with angle switching, zooms, and chapters.

    Uses a two-pass approach:
    1. Score all moments across all videos
    2. Select the best moments within the duration budget

    Implements hysteresis to prevent jittery switching and uses event-specific
    minimum segment durations (e.g., 10s for speeches vs 4s for sports).

    Args:
        videos: List of video dicts with id, path, angle_type, analysis_data, sync_offset_ms
        event_type: Type of event for switching profile (sports, ceremony, performance, speech, lecture)
        index_id: TwelveLabs index ID for analysis queries
        max_duration_ms: Optional override for maximum output duration

    Returns:
        Timeline dict with segments, zooms, ad_slots, chapters
    """
    # Get event-specific minimum segment duration
    min_segment_ms = MIN_SEGMENT_DURATION_BY_EVENT.get(
        event_type, VideoConfig.MIN_SEGMENT_DURATION_MS
    )
    print(f"[Timeline] Event type: {event_type}, min segment duration: {min_segment_ms/1000:.0f}s")

    profile = SWITCHING_PROFILES.get(event_type, SWITCHING_PROFILES["ceremony"])

    if not videos:
        return {"segments": [], "zooms": [], "ad_slots": [], "chapters": []}

    # Calculate duration limits
    source_duration_ms = get_video_duration_ms(videos[0]["path"])
    target_duration_ms = min(
        max_duration_ms or VideoConfig.MAX_TOTAL_DURATION_MS,
        source_duration_ms
    )

    print(f"[Timeline] Source duration: {source_duration_ms/1000:.0f}s, Target: {target_duration_ms/1000:.0f}s")

    # Build scene context timeline for embedding-based scoring
    scene_contexts = build_scene_contexts(videos, index_id, event_type)

    # Pass 1: Score all moments across all videos (with speaker prioritization for speech events)
    all_moments = score_all_moments(videos, source_duration_ms, profile, index_id, scene_contexts, event_type)
    total_windows = source_duration_ms // 2000

    print(f"[Timeline] Scored {len(all_moments)} moments ({total_windows} windows x {len(videos)} videos)")

    # Pass 2: Select best moments within duration budget
    selected_moments = select_best_moments(
        all_moments,
        target_duration_ms,
        VideoConfig.MIN_SEGMENT_QUALITY_SCORE
    )

    print(f"[Timeline] Selected {len(selected_moments)}/{total_windows} moments (quality threshold: {VideoConfig.MIN_SEGMENT_QUALITY_SCORE})")

    # Build variable-length segments from selected moments with hysteresis
    segments = build_variable_segments(selected_moments, event_type, min_segment_ms)

    # Ensure angle diversity - all videos should be represented
    segments = _ensure_angle_diversity(segments, videos)

    # Calculate actual output duration
    total_duration_ms = sum(s["end_ms"] - s["start_ms"] for s in segments) if segments else 0

    # Log segment duration statistics
    if segments:
        durations = [(s["end_ms"] - s["start_ms"]) / 1000 for s in segments]
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        print(f"[Timeline] Segment durations: min={min_duration:.1f}s, max={max_duration:.1f}s, avg={avg_duration:.1f}s")

    print(f"[Timeline] Final: {len(segments)} segments, {total_duration_ms/1000:.0f}s total, {len(set(s['video_id'] for s in segments))} videos used")

    # Generate zoom moments (within the selected timeline)
    zooms = generate_zoom_moments(videos, total_duration_ms, index_id)

    # Generate ad slots with multi-factor scoring
    ad_slots = generate_ad_slots(
        videos=videos,
        duration_ms=total_duration_ms,
        profile=profile,
        index_id=index_id,
        scene_contexts=scene_contexts,
    )

    # Generate chapters
    chapters = generate_chapters(videos, total_duration_ms, event_type, index_id)

    return {
        "segments": segments,
        "zooms": zooms,
        "ad_slots": ad_slots,
        "chapters": chapters,
    }


def _ensure_angle_diversity(segments: list[dict], videos: list[dict]) -> list[dict]:
    """Ensure all videos are represented in the timeline.

    If a video is missing, split the longest segment to include it.

    Args:
        segments: Current segments list
        videos: All available videos

    Returns:
        Updated segments with all videos represented
    """
    if not segments or len(videos) <= 1:
        return segments

    used_video_ids = {s["video_id"] for s in segments}
    all_video_ids = {v["id"] for v in videos}
    missing_videos = all_video_ids - used_video_ids

    if not missing_videos:
        return segments

    print(f"[Timeline] WARNING: {len(missing_videos)} videos not used, forcing inclusion")

    for missing_id in missing_videos:
        if not segments:
            break

        # Find longest segment to split
        longest_idx = max(range(len(segments)), key=lambda i: segments[i]["end_ms"] - segments[i]["start_ms"])
        longest = segments[longest_idx]
        seg_duration = longest["end_ms"] - longest["start_ms"]

        # Only split if segment is long enough
        if seg_duration >= VideoConfig.MIN_SEGMENT_DURATION_MS * 2:
            mid_point = longest["start_ms"] + seg_duration // 2
            insert_end = min(mid_point + VideoConfig.MIN_SEGMENT_DURATION_MS, longest["end_ms"])

            new_segments = []
            for i, seg in enumerate(segments):
                if i == longest_idx:
                    if mid_point > seg["start_ms"]:
                        new_segments.append({
                            "start_ms": seg["start_ms"],
                            "end_ms": mid_point,
                            "video_id": seg["video_id"],
                        })
                    new_segments.append({
                        "start_ms": mid_point,
                        "end_ms": insert_end,
                        "video_id": missing_id,
                    })
                    if insert_end < seg["end_ms"]:
                        new_segments.append({
                            "start_ms": insert_end,
                            "end_ms": seg["end_ms"],
                            "video_id": seg["video_id"],
                        })
                else:
                    new_segments.append(seg)
            segments = new_segments
            print(f"[Timeline] Inserted missing video {missing_id} at {mid_point}ms")

    return segments


def score_angle_at_time(
    video: dict,
    time_ms: int,
    profile: dict,
    index_id: str | None,
    scene_context: dict | None = None,
    video_index: int = 0,
    total_videos: int = 1,
    event_type: str = "sports",
) -> float:
    """Score an angle's suitability at a given time using embeddings.

    Uses embedding similarity to match angles to scene context, combined with
    profile rules for intelligent angle switching.

    For speech/ceremony events, applies speaker prioritization:
    - Closeup angles get 2x score multiplier when speaker is detected
    - Wide/audience shots are deprioritized during speech

    Args:
        video: Video dict with angle_type and analysis_data
        time_ms: Timestamp in milliseconds
        profile: Switching profile for event type
        index_id: TwelveLabs index for queries
        scene_context: Optional context with current scene embeddings
        video_index: Index of this video in the list (for tie-breaking)
        total_videos: Total number of videos (for switching logic)
        event_type: Type of event (for speaker prioritization)

    Returns:
        Score from 0-100
    """
    angle_type = video.get("angle_type", "other")
    analysis = video.get("analysis_data", {})

    # Check if this is a speech-focused event type
    is_speech_event = event_type in ("ceremony", "speech", "lecture")

    # Base score by angle type (25% of total score)
    base_scores = {
        "wide": 50,
        "closeup": 40,
        "crowd": 30,
        "goal_angle": 35,
        "stage": 45,
        "other": 25,
    }
    base_score = base_scores.get(angle_type, 25) * 0.25

    # Profile matching score (25% of total score)
    profile_score = 0
    default_angle = profile.get("default", "wide")
    if angle_type == default_angle:
        profile_score = 25  # Full profile match bonus

    # Check for scene-specific profile rules
    if scene_context:
        scene_type = scene_context.get("scene_type")
        if scene_type:
            # Map profile rules: e.g., "high_action" -> "closeup"
            preferred_angle = profile.get(scene_type)
            if preferred_angle and angle_type == preferred_angle:
                profile_score = 25  # Override default if scene matches

    # Embedding similarity score (50% of total score)
    embedding_score = 0
    embeddings = analysis.get("embeddings", [])

    # Find the embedding segment that covers this timestamp
    current_embedding = None
    for emb in embeddings:
        start_ms = emb.get("start_time", 0) * 1000
        end_ms = emb.get("end_time", 0) * 1000
        if start_ms <= time_ms <= end_ms:
            current_embedding = emb.get("embedding")
            break

    if current_embedding and scene_context:
        # Compare video embedding with scene context embeddings
        context_embedding = scene_context.get("embedding")
        if context_embedding:
            try:
                # Cosine similarity: 1 = identical, 0 = orthogonal
                similarity = 1 - cosine(current_embedding, context_embedding)
                # Scale to 0-50 range
                embedding_score = max(0, similarity) * 50
            except (ValueError, TypeError):
                # Fall back to base embedding score if comparison fails
                embedding_score = 15

        # Additional boost for high-action detection in embeddings
        action_intensity = scene_context.get("action_intensity", 5)
        if action_intensity >= 8:
            # High action: prefer closeup angles
            if angle_type == "closeup":
                embedding_score += 10
            elif angle_type == "goal_angle":
                embedding_score += 8
        elif action_intensity <= 3:
            # Low action: prefer wide shots or crowd
            if angle_type == "wide":
                embedding_score += 5
            elif angle_type == "crowd":
                embedding_score += 8
    elif current_embedding:
        # We have embeddings but no context - give base credit
        embedding_score = 15

    # Speaker prioritization for speech/ceremony events
    # Closeup on speaker should dominate 90% of the time
    speaker_multiplier = 1.0
    if is_speech_event and scene_context:
        scene_type = scene_context.get("scene_type")
        is_speaking_scene = scene_type in ("speech", "name_called", "solo", "announcement")

        if is_speaking_scene or scene_context.get("action_intensity", 5) <= 4:
            # During speech or low-action moments: strongly prefer closeup/speaker angles
            multiplier = SPEAKER_SCORE_MULTIPLIERS.get(angle_type, 1.0)
            speaker_multiplier = multiplier

            # Penalize wide/crowd shots during speech (only use for applause/transitions)
            if angle_type in ("wide", "crowd", "audience"):
                speaker_multiplier = 0.3  # Heavy penalty - only switch for applause

    # Apply softer time-based diversity bonus (not rigid rotation)
    # This encourages variety without forcing predictable 4-second switches
    # DISABLED for speech events - speaker angle should dominate
    if total_videos > 1 and not is_speech_event:
        # Use a longer interval for diversity consideration
        switch_interval_ms = 6000  # 6 second intervals (more flexible than 4s)
        time_slot = (time_ms // switch_interval_ms) % total_videos

        if time_slot == video_index:
            # Moderate diversity bonus - can be overridden by quality
            embedding_score += VideoConfig.ROTATION_BONUS_BASE  # +20
        else:
            # Light penalty - quality can still win
            embedding_score -= VideoConfig.ROTATION_PENALTY  # -10

    total_score = (base_score + profile_score + embedding_score) * speaker_multiplier
    return min(total_score, 100)


def build_scene_contexts(
    videos: list[dict],
    index_id: str | None,
    event_type: str,
) -> list[dict]:
    """Build scene context timeline from TwelveLabs analysis.

    Aggregates embeddings and scene information across all video angles
    to create a unified scene context timeline.

    Args:
        videos: List of video dicts with analysis_data
        index_id: TwelveLabs index ID
        event_type: Type of event

    Returns:
        List of scene contexts with start_ms, end_ms, embedding, scene_type, action_intensity
    """
    scene_contexts = []

    # Collect all embeddings from all videos
    all_embeddings = []
    for video in videos:
        analysis = video.get("analysis_data", {})
        embeddings = analysis.get("embeddings", [])
        for emb in embeddings:
            all_embeddings.append({
                "start_ms": int(emb.get("start_time", 0) * 1000),
                "end_ms": int(emb.get("end_time", 0) * 1000),
                "embedding": emb.get("embedding"),
                "video_id": video.get("id"),
            })

    if not all_embeddings:
        return []

    # Sort by start time
    all_embeddings.sort(key=lambda x: x["start_ms"])

    # Try to detect scene types using TwelveLabs search
    scene_type_cache = {}
    if index_id:
        # Define scene type queries based on event type
        scene_queries = {
            "sports": [
                ("high_action", "fast action, running, intense play, scoring"),
                ("ball_near_goal", "shot on goal, near the net, close to scoring"),
                ("low_action", "players standing, timeout, break in play"),
                ("celebration", "celebrating, cheering, team huddle"),
            ],
            "ceremony": [
                ("name_called", "name being announced, walking to stage"),
                ("speech", "person speaking at podium, giving speech"),
                ("applause", "audience clapping, standing ovation"),
                ("walking", "person walking, crossing stage"),
            ],
            "performance": [
                ("solo", "solo performer, single musician, spotlight"),
                ("full_band", "full band playing, ensemble performance"),
                ("crowd_singing", "audience singing along, crowd participation"),
            ],
        }

        for scene_type, query in scene_queries.get(event_type, []):
            try:
                results = search_videos(index_id, query, limit=5)
                for result in results:
                    start_ms = int(result["start"] * 1000)
                    end_ms = int(result["end"] * 1000)
                    confidence = result.get("confidence", 0.5)
                    if confidence > 0.6:
                        scene_type_cache[(start_ms, end_ms)] = {
                            "scene_type": scene_type,
                            "confidence": confidence,
                        }
            except Exception:
                pass  # Continue without scene detection if search fails

    # Build scene contexts from embeddings
    for emb in all_embeddings:
        context = {
            "start_ms": emb["start_ms"],
            "end_ms": emb["end_ms"],
            "embedding": emb.get("embedding"),
            "action_intensity": 5,  # Default medium intensity
            "scene_type": None,
        }

        # Look for scene type match
        for (start, end), scene_info in scene_type_cache.items():
            if emb["start_ms"] <= start < emb["end_ms"] or start <= emb["start_ms"] < end:
                context["scene_type"] = scene_info["scene_type"]
                # Estimate action intensity from scene type
                if scene_info["scene_type"] in ["high_action", "celebration", "solo"]:
                    context["action_intensity"] = 8
                elif scene_info["scene_type"] in ["low_action", "walking"]:
                    context["action_intensity"] = 3
                break

        scene_contexts.append(context)

    return scene_contexts


def get_scene_context_at_time(scene_contexts: list[dict], time_ms: int) -> dict | None:
    """Get the scene context for a specific timestamp.

    Args:
        scene_contexts: List of scene contexts
        time_ms: Timestamp in milliseconds

    Returns:
        Scene context dict or None if no context found
    """
    for context in scene_contexts:
        if context["start_ms"] <= time_ms < context["end_ms"]:
            return context
    return None


def calculate_engagement_score(scene_context: dict | None) -> float:
    """Calculate content engagement (0-100) for segment duration decisions.

    Higher engagement = content is interesting = can extend segment duration.
    Lower engagement = content is boring = switch sooner.

    Args:
        scene_context: Scene context with action_intensity and scene_type

    Returns:
        Engagement score from 0-100
    """
    if not scene_context:
        return 50  # Default medium engagement

    score = 50  # Base score

    # Action intensity: scale from 1-10 to -40 to +40
    action_intensity = scene_context.get("action_intensity", 5)
    score += (action_intensity - 5) * 8

    # Scene type modifiers
    engaging_scenes = ["high_action", "scoring_play", "solo", "celebration", "ball_near_goal"]
    boring_scenes = ["low_action", "pause", "timeout", "break", "walking"]

    scene_type = scene_context.get("scene_type")
    if scene_type in engaging_scenes:
        score += 15
    elif scene_type in boring_scenes:
        score -= 15

    return max(0, min(100, score))


def score_all_moments(
    videos: list[dict],
    duration_ms: int,
    profile: dict,
    index_id: str | None,
    scene_contexts: list[dict],
    event_type: str = "sports",
) -> list[dict]:
    """Score every 2-second window across all videos.

    Pass 1 of the two-pass timeline generation. Scores all potential moments
    without filtering, so we can later select the best ones.

    Args:
        videos: List of video dicts
        duration_ms: Total source duration in milliseconds
        profile: Switching profile for event type
        index_id: TwelveLabs index ID
        scene_contexts: Pre-built scene contexts
        event_type: Type of event (for speaker prioritization)

    Returns:
        List of moment dicts with time_ms, video_id, score, engagement
    """
    all_moments = []

    for t_ms in range(0, duration_ms, 2000):  # 2 second intervals
        scene_context = get_scene_context_at_time(scene_contexts, t_ms)
        engagement = calculate_engagement_score(scene_context)

        for video_idx, video in enumerate(videos):
            # Score with speaker prioritization for speech events
            score = score_angle_at_time(
                video=video,
                time_ms=t_ms,
                profile=profile,
                index_id=index_id,
                scene_context=scene_context,
                video_index=video_idx,
                total_videos=len(videos),
                event_type=event_type,
            )

            all_moments.append({
                "time_ms": t_ms,
                "video_id": video["id"],
                "video": video,
                "score": score,
                "engagement": engagement,
                "scene_context": scene_context,
            })

    return all_moments


def select_best_moments(
    all_moments: list[dict],
    target_duration_ms: int,
    min_quality: float,
) -> list[dict]:
    """Select highest-scoring moments that fit in duration budget.

    Pass 2 of the two-pass timeline generation. Greedily selects the best
    moments from Pass 1 until the duration budget is reached.

    Args:
        all_moments: All scored moments from Pass 1
        target_duration_ms: Target output duration in milliseconds
        min_quality: Minimum score threshold to include a moment

    Returns:
        Selected moments sorted by timestamp
    """
    # Group by timestamp, keep best angle per timestamp
    by_time = {}
    for m in all_moments:
        t = m["time_ms"]
        if t not in by_time or m["score"] > by_time[t]["score"]:
            by_time[t] = m

    # Sort by combined quality (score + engagement)
    sorted_moments = sorted(
        by_time.values(),
        key=lambda m: m["score"] * 0.6 + m["engagement"] * 0.4,
        reverse=True
    )

    # Greedily select until budget reached
    selected = []
    total_duration = 0
    selected_times = set()

    for moment in sorted_moments:
        if total_duration >= target_duration_ms:
            break

        # Skip if below quality threshold
        if moment["score"] < min_quality:
            continue

        selected.append(moment)
        selected_times.add(moment["time_ms"])
        total_duration += 2000  # Each moment is 2 seconds

    # Sort by time for segment building
    selected.sort(key=lambda m: m["time_ms"])

    return selected


def build_variable_segments(
    selected_moments: list[dict],
    event_type: str = "sports",
    min_segment_ms: int | None = None,
) -> list[dict]:
    """Build segments with variable durations based on content quality.

    Implements hysteresis to prevent jittery switching: only switches angles
    when a new angle is significantly better (30%+ improvement).

    Uses event-specific minimum segment durations:
    - sports: 4s (fast-paced)
    - ceremony/speech: 10s (stable, professional)
    - lecture: 12s (calm, educational)

    Args:
        selected_moments: Selected moments from Pass 2, sorted by time
        event_type: Type of event for duration rules
        min_segment_ms: Override minimum segment duration

    Returns:
        List of segment dicts with start_ms, end_ms, video_id
    """
    if not selected_moments:
        return []

    # Use event-specific minimum or provided override
    effective_min_ms = min_segment_ms or MIN_SEGMENT_DURATION_BY_EVENT.get(
        event_type, VideoConfig.MIN_SEGMENT_DURATION_MS
    )

    segments = []
    current_segment = None

    for moment in selected_moments:
        if current_segment is None:
            # Start new segment
            current_segment = {
                "start_ms": moment["time_ms"],
                "end_ms": moment["time_ms"] + 2000,
                "video_id": moment["video_id"],
                "total_score": moment["score"],
                "total_engagement": moment["engagement"],
                "moment_count": 1,
            }
        elif _can_extend_segment_with_hysteresis(current_segment, moment, effective_min_ms):
            # Extend current segment
            current_segment["end_ms"] = moment["time_ms"] + 2000
            current_segment["total_score"] += moment["score"]
            current_segment["total_engagement"] += moment["engagement"]
            current_segment["moment_count"] += 1
        else:
            # Hysteresis check: only switch if new angle is significantly better
            current_duration = current_segment["end_ms"] - current_segment["start_ms"]
            current_avg_score = current_segment["total_score"] / current_segment["moment_count"]

            # If below minimum duration, MUST extend (don't switch)
            if current_duration < effective_min_ms:
                # Force extend with current video even if different angle scored higher
                current_segment["end_ms"] = moment["time_ms"] + 2000
                current_segment["moment_count"] += 1
                continue

            # Apply hysteresis: new angle must be 30%+ better to justify switch
            if moment["score"] <= current_avg_score * (1 + HYSTERESIS_THRESHOLD):
                # New angle isn't significantly better - extend current segment
                current_segment["end_ms"] = moment["time_ms"] + 2000
                current_segment["total_score"] += moment["score"]
                current_segment["total_engagement"] += moment["engagement"]
                current_segment["moment_count"] += 1
                continue

            # New angle is significantly better - finalize current and start new
            segments.append({
                "start_ms": current_segment["start_ms"],
                "end_ms": current_segment["end_ms"],
                "video_id": current_segment["video_id"],
            })
            current_segment = {
                "start_ms": moment["time_ms"],
                "end_ms": moment["time_ms"] + 2000,
                "video_id": moment["video_id"],
                "total_score": moment["score"],
                "total_engagement": moment["engagement"],
                "moment_count": 1,
            }

    # Add final segment
    if current_segment:
        segments.append({
            "start_ms": current_segment["start_ms"],
            "end_ms": current_segment["end_ms"],
            "video_id": current_segment["video_id"],
        })

    return segments


def _can_extend_segment_with_hysteresis(
    segment: dict,
    moment: dict,
    min_segment_ms: int,
) -> bool:
    """Check if a segment should be extended, with hysteresis for stability.

    Extension is allowed if:
    - Same video ID AND contiguous in time
    - OR below minimum duration (forced extension to prevent jittery cuts)
    - AND below max duration

    Args:
        segment: Current segment being built
        moment: Candidate moment to extend with
        min_segment_ms: Event-specific minimum segment duration

    Returns:
        True if segment should be extended
    """
    current_duration = segment["end_ms"] - segment["start_ms"]

    # Stop if at maximum duration
    if current_duration >= VideoConfig.MAX_SEGMENT_DURATION_MS:
        return False

    # Must be contiguous (no gap in time)
    if moment["time_ms"] != segment["end_ms"]:
        return False

    # Same video - always extend (up to max)
    if moment["video_id"] == segment["video_id"]:
        return True

    # Different video but below minimum - force extend to prevent jitter
    if current_duration < min_segment_ms:
        return True

    return False


def _can_extend_segment(segment: dict, moment: dict) -> bool:
    """Legacy function - use _can_extend_segment_with_hysteresis instead.

    Extension is allowed if:
    - Same video ID
    - Contiguous in time (no gap)
    - Below max duration AND (high quality OR below min duration)

    Args:
        segment: Current segment being built
        moment: Candidate moment to extend with

    Returns:
        True if segment should be extended
    """
    # Must be same video
    if moment["video_id"] != segment["video_id"]:
        return False

    # Must be contiguous (no gap in time)
    if moment["time_ms"] != segment["end_ms"]:
        return False

    current_duration = segment["end_ms"] - segment["start_ms"]
    avg_score = segment["total_score"] / segment["moment_count"]
    avg_engagement = segment["total_engagement"] / segment["moment_count"]

    # Always extend if below minimum duration
    if current_duration < VideoConfig.MIN_SEGMENT_DURATION_MS:
        return True

    # Stop if at maximum duration
    if current_duration >= VideoConfig.MAX_SEGMENT_DURATION_MS:
        return False

    # Between min and max: extend only if high quality/engagement
    combined_quality = avg_score * 0.5 + avg_engagement * 0.5
    return combined_quality >= VideoConfig.HIGH_QUALITY_THRESHOLD


def get_video_duration_ms(video_path: str) -> int:
    """Get video duration in milliseconds."""
    from services.audio_sync import get_audio_duration
    return int(get_audio_duration(video_path) * 1000)


def generate_zoom_moments(
    videos: list[dict],
    duration_ms: int,
    index_id: str | None,
) -> list[dict]:
    """Generate zoom moments for key action scenes.

    Args:
        videos: List of video dicts
        duration_ms: Total duration in milliseconds
        index_id: TwelveLabs index ID

    Returns:
        List of zoom moments with start_ms, duration_ms, zoom_factor
    """
    zooms = []
    last_zoom_time = -VideoConfig.ZOOM_MIN_SPACING_SEC * 1000

    # Search for high-action moments if we have TwelveLabs index
    if index_id:
        try:
            results = search_videos(
                index_id=index_id,
                query="exciting moment, celebration, key play, climax",
                limit=10,
            )

            for moment in results:
                time_ms = int(moment["start"] * 1000)

                # Enforce spacing
                if time_ms - last_zoom_time >= VideoConfig.ZOOM_MIN_SPACING_SEC * 1000:
                    zooms.append({
                        "start_ms": time_ms,
                        "duration_ms": min(3000, int((moment["end"] - moment["start"]) * 1000)),
                        "zoom_factor": VideoConfig.ZOOM_FACTOR_HIGH if moment["confidence"] > 0.8 else VideoConfig.ZOOM_FACTOR_MED,
                    })
                    last_zoom_time = time_ms

        except Exception:
            pass  # Continue without zooms if search fails

    return zooms


def generate_ad_slots(
    videos: list[dict],
    duration_ms: int,
    profile: dict,
    index_id: str | None = None,
    scene_contexts: list[dict] | None = None,
) -> list[dict]:
    """Generate optimal ad insertion points using multi-factor scoring.

    Scores each candidate position 0-100 based on:
    - Action intensity (40 pts): Low action = good ad slot
    - Audio context (25 pts): Quiet/pause = good ad slot
    - Scene transitions (20 pts): Scene boundary = good ad slot
    - Visual complexity (15 pts): Low complexity = good ad slot

    Penalties applied for:
    - Nearby key moments (-70%)
    - Active speech (-50%)
    - High crowd energy (-60%)

    Args:
        videos: List of video dicts with analysis_data
        duration_ms: Total duration in milliseconds
        profile: Switching profile with ad_block/boost scenes
        index_id: TwelveLabs index ID for analysis
        scene_contexts: Pre-built scene contexts from timeline generation

    Returns:
        List of ad slots with timestamp_ms, score, duration_ms
    """
    # Don't place ads in first/last 10 seconds
    start_ms = 10000
    end_ms = duration_ms - 10000

    if end_ms <= start_ms:
        return []

    # Get blocked and boosted scene types from profile
    ad_block_scenes = profile.get("ad_block_scenes", [])
    ad_boost_scenes = profile.get("ad_boost_scenes", [])

    # Find key moments to avoid (goals, name announcements, etc.)
    key_moments = []
    if index_id:
        try:
            # Search for moments we should NOT interrupt
            key_queries = ["goal", "scoring", "name announced", "solo", "celebration"]
            for query in key_queries:
                results = search_videos(index_id, query, limit=5)
                for result in results:
                    if result.get("confidence", 0) > 0.7:
                        key_moments.append({
                            "start_ms": int(result["start"] * 1000),
                            "end_ms": int(result["end"] * 1000),
                        })
        except Exception:
            pass

    # Find speech segments to avoid
    speech_segments = []
    if index_id:
        try:
            results = search_videos(index_id, "person speaking, speech, announcement", limit=10)
            for result in results:
                if result.get("confidence", 0) > 0.6:
                    speech_segments.append({
                        "start_ms": int(result["start"] * 1000),
                        "end_ms": int(result["end"] * 1000),
                    })
        except Exception:
            pass

    # Find natural transition points (scene boundaries)
    transition_points = []
    if scene_contexts:
        for i, context in enumerate(scene_contexts[:-1]):
            # Scene boundary = potential transition
            transition_points.append(context["end_ms"])

    # Score candidate positions
    candidate_slots = []
    for t_ms in range(start_ms, end_ms, 5000):  # Check every 5 seconds
        score = 0

        # --- Action Intensity Score (40 pts max) ---
        # Low action = better for ads
        action_score = 40  # Default: assume low action
        if scene_contexts:
            context = get_scene_context_at_time(scene_contexts, t_ms)
            if context:
                # Invert: high action = low score
                intensity = context.get("action_intensity", 5)
                action_score = max(0, 40 - (intensity * 4))

                # Check scene type against profile
                scene_type = context.get("scene_type")
                if scene_type in ad_block_scenes:
                    action_score = 0  # Blocked scene
                elif scene_type in ad_boost_scenes:
                    action_score = 40  # Boosted scene

        score += action_score

        # --- Audio Context Score (25 pts max) ---
        audio_score = 15  # Default: medium
        # Check if in speech segment
        in_speech = any(
            seg["start_ms"] <= t_ms <= seg["end_ms"]
            for seg in speech_segments
        )
        if in_speech:
            audio_score = 0  # Don't interrupt speech
        else:
            # Bonus for quiet moments (would use audio analysis in production)
            audio_score = 20

        score += audio_score

        # --- Scene Transition Score (20 pts max) ---
        transition_score = 0
        # Bonus for being near a scene transition
        for trans_time in transition_points:
            if abs(t_ms - trans_time) < 2000:  # Within 2 seconds of transition
                transition_score = 20
                break
            elif abs(t_ms - trans_time) < 5000:  # Within 5 seconds
                transition_score = 10
                break

        score += transition_score

        # --- Visual Complexity Score (15 pts max) ---
        # Low complexity = better for ads
        # Would use frame analysis in production
        complexity_score = 10  # Default: medium

        score += complexity_score

        # --- Apply Penalties ---

        # Penalty: Near key moment (-70%)
        near_key_moment = any(
            moment["start_ms"] - 5000 <= t_ms <= moment["end_ms"] + 5000
            for moment in key_moments
        )
        if near_key_moment:
            score *= VideoConfig.AD_PENALTY_KEY_MOMENT

        # Penalty: Active speech (-50%)
        if in_speech:
            score *= VideoConfig.AD_PENALTY_SPEECH

        # Penalty: High crowd energy (-60%)
        if scene_contexts:
            context = get_scene_context_at_time(scene_contexts, t_ms)
            if context and context.get("action_intensity", 5) >= 8:
                score *= 0.4  # -60%

        candidate_slots.append({
            "timestamp_ms": t_ms,
            "score": score,
            "duration_ms": 4000,
        })

    # Sort by score and select best slots with minimum spacing
    candidate_slots.sort(key=lambda x: x["score"], reverse=True)

    selected_slots = []
    for slot in candidate_slots:
        # Check minimum spacing from existing selections
        if all(
            abs(slot["timestamp_ms"] - s["timestamp_ms"]) >= VideoConfig.AD_MIN_SPACING_MS
            for s in selected_slots
        ):
            # Check if score meets threshold
            if slot["score"] >= VideoConfig.AD_SCORE_THRESHOLD:
                selected_slots.append(slot)

            # Max 1 ad per 4 minutes
            max_ads = max(1, int((duration_ms / (4 * 60 * 1000)) * VideoConfig.AD_MAX_PER_4MIN))
            if len(selected_slots) >= max_ads:
                break

    # Sort by timestamp for output
    selected_slots.sort(key=lambda x: x["timestamp_ms"])

    return selected_slots[:4]  # Max 4 ad slots


def generate_chapters(
    videos: list[dict],
    duration_ms: int,
    event_type: str,
    index_id: str | None,
) -> list[dict]:
    """Generate chapter markers for video navigation.

    Args:
        videos: List of video dicts
        duration_ms: Total duration in milliseconds
        event_type: Type of event
        index_id: TwelveLabs index ID

    Returns:
        List of chapters with timestamp_ms, title, type
    """
    chapters = [
        {"timestamp_ms": 0, "title": "Start", "type": "section"}
    ]

    # Search for chapter-worthy moments if we have TwelveLabs
    if index_id:
        try:
            # Search for different types of moments based on event type
            queries = {
                "sports": ["goal", "halftime", "celebration"],
                "ceremony": ["speech", "award presentation", "name called"],
                "performance": ["solo", "song change", "finale"],
            }

            for query in queries.get(event_type, ["highlight"]):
                results = search_videos(index_id, query, limit=3)
                for moment in results:
                    time_ms = int(moment["start"] * 1000)
                    # Enforce minimum 1 minute spacing
                    if all(abs(time_ms - c["timestamp_ms"]) > 60000 for c in chapters):
                        chapters.append({
                            "timestamp_ms": time_ms,
                            "title": query.title(),
                            "type": "highlight",
                        })

        except Exception:
            pass

    # Sort by timestamp
    chapters.sort(key=lambda c: c["timestamp_ms"])

    return chapters
