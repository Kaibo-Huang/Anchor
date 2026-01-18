"""TwelveLabs service for video understanding, search, and embeddings."""

from functools import lru_cache
from typing import Any, Literal

from twelvelabs import TwelveLabs

from config import get_settings


@lru_cache
def get_twelvelabs_client() -> TwelveLabs:
    """Get TwelveLabs client singleton."""
    settings = get_settings()
    print(f"[TwelveLabs] Initializing TwelveLabs client...")
    return TwelveLabs(api_key=settings.twelvelabs_api_key)


def create_index(index_name: str) -> str:
    """Create a TwelveLabs index for video analysis, or return existing one.

    Args:
        index_name: Unique name for the index (e.g., "event_{event_id}")

    Returns:
        Index ID
    """
    print(f"[TwelveLabs] Creating index: {index_name}")
    client = get_twelvelabs_client()

    # Import from top-level twelvelabs module
    from twelvelabs import IndexesCreateRequestModelsItem
    from twelvelabs.core.api_error import ApiError

    print(f"[TwelveLabs] Configuring models: marengo2.7 (visual+audio), pegasus1.2 (visual+audio)")
    try:
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
        print(f"[TwelveLabs] Index created successfully: {index.id}")
        return index.id
    except ApiError as e:
        if e.status_code == 409 and "already_exists" in str(e.body):
            # Index already exists, find and return it
            print(f"[TwelveLabs] Index already exists, retrieving...")
            indexes = client.indexes.list()
            for idx in indexes:
                if idx.index_name == index_name:
                    print(f"[TwelveLabs] Found existing index: {idx.id}")
                    return idx.id
            raise ValueError(f"Index {index_name} exists but could not be found")
        raise


def index_video(index_id: str, video_url: str, wait: bool = True) -> Any:
    """Index a video in TwelveLabs for analysis.

    Args:
        index_id: The index to add the video to
        video_url: Public URL or presigned S3 URL for the video
        wait: Whether to wait for indexing to complete

    Returns:
        Task object with indexing status
    """
    print(f"[TwelveLabs] Indexing video in index: {index_id}")
    print(f"[TwelveLabs] Video URL: {video_url[:80]}...")
    client = get_twelvelabs_client()

    print(f"[TwelveLabs] Creating indexing task...")
    task = client.tasks.create(
        index_id=index_id,
        video_url=video_url,
    )
    task_id = task.id if hasattr(task, 'id') else None
    print(f"[TwelveLabs] Task created: {task_id}")

    if wait and task_id:
        print(f"[TwelveLabs] Waiting for indexing to complete (polling every 2s)...")
        # Use client.tasks.wait_for_done() instead of task.wait_for_done()
        completed_task = client.tasks.wait_for_done(task_id=task_id, sleep_interval=2)
        print(f"[TwelveLabs] Indexing complete! Video ID: {completed_task.video_id if hasattr(completed_task, 'video_id') else 'N/A'}")
        return completed_task
    else:
        print(f"[TwelveLabs] Task submitted (not waiting for completion)")

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
    print(f"[TwelveLabs] Searching videos in index: {index_id}")
    print(f"[TwelveLabs] Query: '{query}'")
    client = get_twelvelabs_client()

    if search_options is None:
        search_options = ["visual", "audio"]

    print(f"[TwelveLabs] Search options: {search_options}, limit: {limit}")
    results = client.search.query(
        index_id=index_id,
        query_text=query,
        search_options=search_options,
        page_limit=limit,
    )

    # Transform results to our format
    # Note: results is a SyncPager, iterate directly over it
    # Confidence is a string: "high", "medium", "low"
    confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
    moments = []
    for clip in results:
        # Convert confidence string to numeric score
        confidence_str = str(clip.confidence).lower()
        confidence_score = confidence_map.get(confidence_str, 0.5)

        moments.append({
            "video_id": clip.video_id,
            "start": float(clip.start),
            "end": float(clip.end),
            "confidence": confidence_score,
            "metadata": clip.metadata if hasattr(clip, "metadata") else {},
        })

    print(f"[TwelveLabs] Search returned {len(moments)} moments")
    if moments:
        print(f"[TwelveLabs] Top result: {moments[0]['start']:.1f}s-{moments[0]['end']:.1f}s (confidence: {moments[0]['confidence']:.2f})")

    return moments


def create_video_embeddings(video_url: str) -> list[dict]:
    """Create embeddings for a video using Marengo retrieval model.

    Args:
        video_url: URL of the video to embed

    Returns:
        List of segment embeddings with start_time, end_time, embedding vector
    """
    print(f"[TwelveLabs] Creating video embeddings...")
    print(f"[TwelveLabs] Video URL: {video_url[:80]}...")
    client = get_twelvelabs_client()

    print(f"[TwelveLabs] Using model: Marengo-retrieval-2.7")
    task = client.embed.tasks.create(
        model_name="Marengo-retrieval-2.7",
        video_url=video_url,
    )
    task_id = task.id if hasattr(task, 'id') else None
    print(f"[TwelveLabs] Embedding task created: {task_id}, waiting for completion...")

    # Use client.embed.tasks.wait_for_done() instead of task.wait_for_done()
    if task_id:
        completed_task = client.embed.tasks.wait_for_done(task_id=task_id, sleep_interval=2)
    else:
        completed_task = task
    print(f"[TwelveLabs] Embedding task complete")

    # Extract embeddings from completed task
    embeddings = []
    if hasattr(completed_task, "video_embeddings") and completed_task.video_embeddings:
        for segment in completed_task.video_embeddings:
            embeddings.append({
                "start_time": segment.start_offset_sec if hasattr(segment, "start_offset_sec") else 0,
                "end_time": segment.end_offset_sec if hasattr(segment, "end_offset_sec") else 0,
                "embedding": segment.embedding if hasattr(segment, "embedding") else [],
            })

    print(f"[TwelveLabs] Extracted {len(embeddings)} embedding segments")
    if embeddings:
        embed_dim = len(embeddings[0].get("embedding", [])) if embeddings[0].get("embedding") else 0
        print(f"[TwelveLabs] Embedding dimension: {embed_dim}")

    return embeddings


def create_text_embedding(text: str) -> list[float]:
    """Create an embedding for text (for vibe matching).

    Args:
        text: Text description to embed (e.g., "fast movement, intense action")

    Returns:
        Embedding vector (1024 dimensions)
    """
    print(f"[TwelveLabs] Creating text embedding for: '{text[:50]}...'")
    client = get_twelvelabs_client()

    result = client.embed.create(
        model_name="Marengo-retrieval-2.7",
        text=text,
    )

    embedding = result.embedding if hasattr(result, "embedding") else []
    print(f"[TwelveLabs] Text embedding created (dim: {len(embedding)})")

    return embedding


# Pre-defined vibe anchors for identity matching
VIBE_DESCRIPTIONS = {
    "high_energy": "fast movement, intense action, crowd cheering, celebration, excitement",
    "emotional": "heartfelt moment, tears of joy, hugging, emotional reaction, meaningful",
    "calm": "peaceful, relaxed, slow motion, gentle movement, serene",
}

# Cache for vibe embeddings - these never change, so compute once and reuse
_vibe_embedding_cache: dict[str, list[float]] = {}


def get_vibe_embedding(vibe: Literal["high_energy", "emotional", "calm"]) -> list[float]:
    """Get pre-computed vibe anchor embedding for identity matching.

    Args:
        vibe: One of "high_energy", "emotional", "calm"

    Returns:
        Embedding vector for the vibe
    """
    # Check cache first
    if vibe in _vibe_embedding_cache:
        print(f"[TwelveLabs] Using cached vibe embedding for: {vibe}")
        return _vibe_embedding_cache[vibe]

    print(f"[TwelveLabs] Computing vibe embedding for: {vibe}")
    description = VIBE_DESCRIPTIONS.get(vibe)
    if not description:
        print(f"[TwelveLabs] ERROR: Unknown vibe: {vibe}")
        raise ValueError(f"Unknown vibe: {vibe}")

    print(f"[TwelveLabs] Vibe description: '{description}'")
    embedding = create_text_embedding(description)

    # Cache for future use
    _vibe_embedding_cache[vibe] = embedding
    print(f"[TwelveLabs] Cached vibe embedding for: {vibe}")

    return embedding


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
