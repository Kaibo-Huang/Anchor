"""Celery worker for async video processing tasks.

This module re-exports from worker_optimized to use the parallel processing version.
The optimized worker includes:
1. Parallel video downloads and compression using ThreadPoolExecutor
2. Parallel TwelveLabs indexing wait (instead of sequential)
3. Reduced polling intervals (5s -> 2s)
4. Batched database updates to reduce round trips
"""

# Re-export everything from the optimized worker
from worker_optimized import (
    celery,
    analyze_videos_task,
    generate_video_task,
    sync_store_products_task,
    analyze_music_task,
    generate_highlight_reel_task,
    create_subtle_placements_task,
)

__all__ = [
    "celery",
    "analyze_videos_task",
    "generate_video_task",
    "sync_store_products_task",
    "analyze_music_task",
    "generate_highlight_reel_task",
    "create_subtle_placements_task",
]
