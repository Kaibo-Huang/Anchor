"""Timeline generation service for multi-angle video switching."""

from typing import Literal

import numpy as np
from scipy.spatial.distance import cosine

from config import VideoConfig, SWITCHING_PROFILES
from services.twelvelabs_service import search_videos, create_text_embedding


def generate_timeline(
    videos: list[dict],
    event_type: Literal["sports", "ceremony", "performance"],
    index_id: str | None = None,
) -> dict:
    """Generate a timeline with angle switching, zooms, and chapters.

    Uses embedding-based scoring to intelligently select the best angle at each
    moment, combined with profile rules for event-specific behavior.

    Args:
        videos: List of video dicts with id, path, angle_type, analysis_data, sync_offset_ms
        event_type: Type of event for switching profile
        index_id: TwelveLabs index ID for analysis queries

    Returns:
        Timeline dict with segments, zooms, ad_slots, chapters
    """
    profile = SWITCHING_PROFILES.get(event_type, SWITCHING_PROFILES["sports"])

    # Get video duration from first video
    if not videos:
        return {"segments": [], "zooms": [], "ad_slots": [], "chapters": []}

    # Build scene context timeline for embedding-based scoring
    scene_contexts = build_scene_contexts(videos, index_id, event_type)

    # Build segments - score each angle every 2 seconds
    duration_ms = get_video_duration_ms(videos[0]["path"])
    segments = []
    current_video = None
    segment_start = 0

    for t_ms in range(0, duration_ms, 2000):  # 2 second intervals
        # Get scene context for this timestamp
        scene_context = get_scene_context_at_time(scene_contexts, t_ms)

        # Score each angle at this timestamp
        best_video = None
        best_score = -1

        for video in videos:
            score = score_angle_at_time(
                video=video,
                time_ms=t_ms,
                profile=profile,
                index_id=index_id,
                scene_context=scene_context,
            )

            if score > best_score:
                best_score = score
                best_video = video

        # Check if we should switch
        if best_video and best_video["id"] != current_video:
            # Enforce minimum duration
            if current_video is None or (t_ms - segment_start) >= VideoConfig.MIN_ANGLE_DURATION_MS:
                if current_video is not None:
                    segments.append({
                        "start_ms": segment_start,
                        "end_ms": t_ms,
                        "video_id": current_video,
                    })

                current_video = best_video["id"]
                segment_start = t_ms

    # Add final segment
    if current_video:
        segments.append({
            "start_ms": segment_start,
            "end_ms": duration_ms,
            "video_id": current_video,
        })

    # Generate zoom moments
    zooms = generate_zoom_moments(videos, duration_ms, index_id)

    # Generate ad slots with multi-factor scoring
    ad_slots = generate_ad_slots(
        videos=videos,
        duration_ms=duration_ms,
        profile=profile,
        index_id=index_id,
        scene_contexts=scene_contexts,
    )

    # Generate chapters
    chapters = generate_chapters(videos, duration_ms, event_type, index_id)

    return {
        "segments": segments,
        "zooms": zooms,
        "ad_slots": ad_slots,
        "chapters": chapters,
    }


def score_angle_at_time(
    video: dict,
    time_ms: int,
    profile: dict,
    index_id: str | None,
    scene_context: dict | None = None,
) -> float:
    """Score an angle's suitability at a given time using embeddings.

    Uses embedding similarity to match angles to scene context, combined with
    profile rules for intelligent angle switching.

    Args:
        video: Video dict with angle_type and analysis_data
        time_ms: Timestamp in milliseconds
        profile: Switching profile for event type
        index_id: TwelveLabs index for queries
        scene_context: Optional context with current scene embeddings

    Returns:
        Score from 0-100
    """
    angle_type = video.get("angle_type", "other")
    analysis = video.get("analysis_data", {})

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

    total_score = base_score + profile_score + embedding_score
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
