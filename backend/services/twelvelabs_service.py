"""TwelveLabs service for video understanding, search, and embeddings."""

from functools import lru_cache
from typing import Any, Literal

from twelvelabs import TwelveLabs

from config import get_settings


@lru_cache
def get_twelvelabs_client() -> TwelveLabs:
    """Get TwelveLabs client singleton."""
    settings = get_settings()
    return TwelveLabs(api_key=settings.twelvelabs_api_key)


def create_index(index_name: str) -> str:
    """Create a TwelveLabs index for video analysis.

    Args:
        index_name: Unique name for the index (e.g., "event_{event_id}")

    Returns:
        Index ID
    """
    client = get_twelvelabs_client()

    # Import from top-level twelvelabs module
    from twelvelabs import IndexesCreateRequestModelsItem

    index = client.indexes.create(
        index_name=index_name,
        models=[
            IndexesCreateRequestModelsItem(
                model_name="marengo2.7",
                model_options=["visual", "audio"],
            ),
            IndexesCreateRequestModelsItem(
                model_name="pegasus1.2",
                model_options=["visual", "audio"],
            ),
        ],
    )

    return index.id


def index_video(index_id: str, video_url: str, wait: bool = True) -> Any:
    """Index a video in TwelveLabs for analysis.

    Args:
        index_id: The index to add the video to
        video_url: Public URL or presigned S3 URL for the video
        wait: Whether to wait for indexing to complete

    Returns:
        Task object with indexing status
    """
    client = get_twelvelabs_client()

    task = client.tasks.create(
        index_id=index_id,
        video_url=video_url,
    )

    if wait:
        task.wait_for_done(sleep_interval=5)

    return task


def search_videos(
    index_id: str,
    query: str,
    search_options: list[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Search for moments in indexed videos using natural language.

    Args:
        index_id: Index to search in
        query: Natural language query (e.g., "player scoring a goal", "person in red jersey")
        search_options: List of search modes (default: ["visual", "audio"])
        limit: Maximum number of results

    Returns:
        List of search results with video_id, start, end, confidence
    """
    client = get_twelvelabs_client()

    if search_options is None:
        search_options = ["visual", "audio"]

    results = client.search.query(
        index_id=index_id,
        query_text=query,
        options=search_options,
        page_limit=limit,
    )

    # Transform results to our format
    moments = []
    for clip in results.data:
        moments.append({
            "video_id": clip.video_id,
            "start": clip.start,
            "end": clip.end,
            "confidence": clip.confidence,
            "metadata": clip.metadata if hasattr(clip, "metadata") else {},
        })

    return moments


def create_video_embeddings(video_url: str) -> list[dict]:
    """Create embeddings for a video using Marengo retrieval model.

    Args:
        video_url: URL of the video to embed

    Returns:
        List of segment embeddings with start_time, end_time, embedding vector
    """
    client = get_twelvelabs_client()

    task = client.embed.task.create(
        model_name="Marengo-retrieval-2.7",
        video_url=video_url,
    )
    task.wait_for_done()

    # Extract embeddings from completed task
    embeddings = []
    if hasattr(task, "video_embeddings") and task.video_embeddings:
        for segment in task.video_embeddings:
            embeddings.append({
                "start_time": segment.start_offset_sec if hasattr(segment, "start_offset_sec") else 0,
                "end_time": segment.end_offset_sec if hasattr(segment, "end_offset_sec") else 0,
                "embedding": segment.embedding if hasattr(segment, "embedding") else [],
            })

    return embeddings


def create_text_embedding(text: str) -> list[float]:
    """Create an embedding for text (for vibe matching).

    Args:
        text: Text description to embed (e.g., "fast movement, intense action")

    Returns:
        Embedding vector (1024 dimensions)
    """
    client = get_twelvelabs_client()

    result = client.embed.create(
        model_name="Marengo-retrieval-2.7",
        text=text,
    )

    return result.embedding if hasattr(result, "embedding") else []


# Pre-defined vibe anchors for identity matching
VIBE_DESCRIPTIONS = {
    "high_energy": "fast movement, intense action, crowd cheering, celebration, excitement",
    "emotional": "heartfelt moment, tears of joy, hugging, emotional reaction, meaningful",
    "calm": "peaceful, relaxed, slow motion, gentle movement, serene",
}


def get_vibe_embedding(vibe: Literal["high_energy", "emotional", "calm"]) -> list[float]:
    """Get pre-computed vibe anchor embedding for identity matching.

    Args:
        vibe: One of "high_energy", "emotional", "calm"

    Returns:
        Embedding vector for the vibe
    """
    description = VIBE_DESCRIPTIONS.get(vibe)
    if not description:
        raise ValueError(f"Unknown vibe: {vibe}")

    return create_text_embedding(description)


def get_video_analysis(index_id: str, video_id: str) -> dict:
    """Get detailed analysis for a specific video.

    Args:
        index_id: Index containing the video
        video_id: ID of the video to analyze

    Returns:
        Analysis data including scenes, objects, actions
    """
    client = get_twelvelabs_client()

    # Get video details
    video = client.indexes.videos.retrieve(index_id=index_id, video_id=video_id)

    return {
        "video_id": video.id,
        "duration": video.metadata.duration if hasattr(video.metadata, "duration") else 0,
        "filename": video.metadata.filename if hasattr(video.metadata, "filename") else "",
        "status": video.status,
    }


def delete_index(index_id: str) -> None:
    """Delete a TwelveLabs index and all its videos.

    Args:
        index_id: Index to delete
    """
    client = get_twelvelabs_client()
    client.indexes.delete(index_id=index_id)
