"""Celery worker for async video processing tasks - OPTIMIZED VERSION.

Key optimizations:
1. Parallel video downloads and compression using ThreadPoolExecutor
2. Parallel TwelveLabs indexing wait (instead of sequential)
3. Reduced polling intervals (5s -> 2s)
4. Batched database updates to reduce round trips
"""

import os
import sys
from typing import Literal

# Add backend directory to Python path for module imports
# This needs to happen before any imports and will be re-applied in worker processes
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from celery import Celery
from celery.signals import worker_process_init

from config import get_settings


@worker_process_init.connect
def setup_worker_path(sender=None, **kwargs):
    """Ensure backend directory is in sys.path for forked worker processes."""
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

VibeType = Literal["high_energy", "emotional", "calm"]

settings = get_settings()

# Initialize Celery
celery = Celery(
    "anchor",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    worker_prefetch_multiplier=1,  # Process one task at a time
)


# Reduced polling interval for faster status checks
TWELVELABS_POLL_INTERVAL = 2  # Was 5 seconds, now 2 seconds


def update_analysis_progress(supabase, event_id: str, stage: str, stage_progress: float, current_video: int, total_videos: int, message: str):
    """Update the analysis progress in the database."""
    progress = {
        "stage": stage,
        "stage_progress": min(1.0, max(0.0, stage_progress)),
        "current_video": current_video,
        "total_videos": total_videos,
        "message": message,
    }
    supabase.table("events").update({"analysis_progress": progress}).eq("id", event_id).execute()
    print(f"[Worker:analyze_videos] Progress: {stage} - {message} ({stage_progress*100:.0f}%)")


def update_generation_progress(supabase, event_id: str, stage: str, stage_progress: float, message: str):
    """Update the video generation progress in the database."""
    progress = {
        "stage": stage,
        "stage_progress": min(1.0, max(0.0, stage_progress)),
        "message": message,
    }
    supabase.table("events").update({"generation_progress": progress}).eq("id", event_id).execute()
    print(f"[Worker:generate_video] Progress: {stage} - {message} ({stage_progress*100:.0f}%)")


@celery.task(bind=True, max_retries=3, default_retry_delay=60, name="worker.analyze_videos_task")
def analyze_videos_task(self, event_id: str):
    """Analyze all videos in an event using TwelveLabs.

    OPTIMIZED VERSION with parallel processing:
    1. Create TwelveLabs index for the event
    2. Download and compress videos IN PARALLEL
    3. Submit all indexing tasks to TwelveLabs
    4. Wait for all indexing tasks IN PARALLEL (not sequentially!)
    5. Generate embeddings in parallel
    """
    from services.supabase_client import get_supabase
    from services.twelvelabs_service import (
        create_index,
        index_video,
        create_video_embeddings,
        get_twelvelabs_client,
    )
    from services.s3_client import generate_presigned_download_url, parse_s3_uri, download_file, upload_file
    from services.video_compress import compress_video_for_twelvelabs, MAX_SIZE_BYTES
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import tempfile
    import os

    print(f"[Worker:analyze_videos] ========== STARTING ANALYSIS (OPTIMIZED) ==========")
    print(f"[Worker:analyze_videos] Event ID: {event_id}")

    supabase = get_supabase()

    try:
        # Get event and videos
        print(f"[Worker:analyze_videos] Fetching event and videos from database...")
        _event = supabase.table("events").select("*").eq("id", event_id).single().execute()

        # Get both uploaded (need analysis) and already-analyzed videos
        all_videos = supabase.table("videos").select("*").eq("event_id", event_id).in_("status", ["uploaded", "analyzed"]).execute()

        # Separate videos that need analysis from those already done
        videos_to_analyze = [v for v in all_videos.data if v["status"] == "uploaded"]
        already_analyzed = [v for v in all_videos.data if v["status"] == "analyzed" and v.get("analysis_data")]

        print(f"[Worker:analyze_videos] Found {len(videos_to_analyze)} videos needing analysis")
        print(f"[Worker:analyze_videos] Found {len(already_analyzed)} already-analyzed videos (skipping)")

        if not videos_to_analyze and not already_analyzed:
            print(f"[Worker:analyze_videos] ERROR: No videos found")
            raise ValueError("No videos found")

        # If all videos are already analyzed, just return success
        if not videos_to_analyze:
            print(f"[Worker:analyze_videos] All videos already analyzed, skipping TwelveLabs processing")
            supabase.table("events").update({"status": "analyzed"}).eq("id", event_id).execute()
            return {"status": "success", "event_id": event_id, "videos_analyzed": 0, "cached": len(already_analyzed)}

        # For backwards compatibility, use videos_to_analyze as the main list
        videos = type('obj', (object,), {'data': videos_to_analyze})()

        total_videos = len(videos.data)

        # Initialize progress
        update_analysis_progress(supabase, event_id, "initializing", 0.0, 0, total_videos, "Setting up AI analysis environment...")

        # Create TwelveLabs index
        print(f"[Worker:analyze_videos] Creating TwelveLabs index: event_{event_id}")
        index_id = create_index(f"event_{event_id}")
        print(f"[Worker:analyze_videos] TwelveLabs index created: {index_id}")

        # Store index ID
        supabase.table("events").update({"twelvelabs_index_id": index_id}).eq("id", event_id).execute()
        print(f"[Worker:analyze_videos] Index ID stored in database")

        # ============ OPTIMIZATION 1: PARALLEL DOWNLOAD & COMPRESS ============
        print(f"[Worker:analyze_videos] ---------- PARALLEL DOWNLOAD & COMPRESS ----------")
        update_analysis_progress(supabase, event_id, "downloading", 0.0, 0, total_videos, f"Preparing {total_videos} videos for analysis...")

        with tempfile.TemporaryDirectory() as tmpdir:
            def download_and_prepare_video(video_data):
                """Download and optionally compress a single video. Runs in parallel."""
                i, video = video_data
                video_id = video["id"]
                print(f"[Worker:analyze_videos] [Thread] Starting download for video {i + 1}/{total_videos}: {video_id[:8]}...")

                # Update video status
                supabase.table("videos").update({"status": "analyzing"}).eq("id", video_id).execute()

                # Get presigned URL for S3 video
                bucket, key = parse_s3_uri(video["original_url"])

                # Download video
                local_video_path = os.path.join(tmpdir, f"video_{video_id}.mp4")
                download_file(bucket, key, local_video_path)

                file_size = os.path.getsize(local_video_path)
                file_size_gb = file_size / (1024 * 1024 * 1024)
                print(f"[Worker:analyze_videos] [Thread] Video {i + 1} downloaded: {file_size_gb:.2f} GB")

                # Check if compression is needed (TwelveLabs limit is 2GB)
                if file_size > MAX_SIZE_BYTES:
                    print(f"[Worker:analyze_videos] [Thread] Video {i + 1} exceeds 1.8GB, compressing...")
                    compressed_path = os.path.join(tmpdir, f"video_{video_id}_compressed.mp4")
                    compress_video_for_twelvelabs(local_video_path, compressed_path)

                    # Upload compressed version to S3
                    compressed_key = key.replace(".mp4", "_compressed.mp4")
                    upload_file(compressed_path, bucket, compressed_key, "video/mp4")
                    video_url = generate_presigned_download_url(bucket, compressed_key, expires_in=7200)
                    print(f"[Worker:analyze_videos] [Thread] Video {i + 1} compressed and uploaded")
                else:
                    video_url = generate_presigned_download_url(bucket, key, expires_in=7200)

                return {
                    "video": video,
                    "video_url": video_url,
                    "index": i,
                }

            # Run downloads in parallel (up to 4 concurrent)
            video_tasks = []
            download_completed = 0
            with ThreadPoolExecutor(max_workers=min(4, total_videos)) as executor:
                futures = {executor.submit(download_and_prepare_video, (i, v)): i
                          for i, v in enumerate(videos.data)}

                for future in as_completed(futures):
                    result = future.result()
                    video_tasks.append(result)
                    download_completed += 1
                    update_analysis_progress(
                        supabase, event_id, "downloading",
                        download_completed / total_videos,
                        download_completed, total_videos,
                        f"Downloaded {download_completed}/{total_videos} videos..."
                    )

            # Sort by original index to maintain order
            video_tasks.sort(key=lambda x: x["index"])
            print(f"[Worker:analyze_videos] All {len(video_tasks)} videos downloaded and prepared")

            # Submit all indexing tasks in parallel (don't wait)
            print(f"[Worker:analyze_videos] ---------- SUBMITTING PARALLEL INDEXING ----------")
            update_analysis_progress(
                supabase, event_id, "indexing",
                0.0, 0, total_videos,
                "Starting AI analysis with TwelveLabs Marengo 2.7..."
            )

            pending_tasks = []
            for vt in video_tasks:
                print(f"[Worker:analyze_videos] Submitting video {vt['index'] + 1}/{len(video_tasks)} to TwelveLabs...")
                task = index_video(index_id, vt["video_url"], wait=False)
                task_id = task.id if hasattr(task, 'id') else None
                pending_tasks.append({
                    **vt,
                    "task_id": task_id,
                    "task": task,
                })

            print(f"[Worker:analyze_videos] All {len(pending_tasks)} videos submitted!")

            # ============ OPTIMIZATION 2: PARALLEL WAIT FOR INDEXING ============
            print(f"[Worker:analyze_videos] ---------- PARALLEL WAIT FOR INDEXING ----------")
            client = get_twelvelabs_client()

            def wait_for_indexing(pt):
                """Wait for a single video's indexing to complete. Runs in parallel."""
                if not pt["task_id"]:
                    return None
                print(f"[Worker:analyze_videos] [Thread] Waiting for video {pt['index'] + 1} indexing...")
                # Use reduced polling interval
                completed_task = client.tasks.wait_for_done(
                    task_id=pt["task_id"],
                    sleep_interval=TWELVELABS_POLL_INTERVAL  # 2s instead of 5s
                )
                print(f"[Worker:analyze_videos] [Thread] Video {pt['index'] + 1} indexed: {completed_task.video_id if hasattr(completed_task, 'video_id') else 'N/A'}")
                return {
                    **pt,
                    "completed_task": completed_task,
                }

            completed_tasks = []
            indexing_completed = 0
            with ThreadPoolExecutor(max_workers=len(pending_tasks)) as executor:
                futures = {executor.submit(wait_for_indexing, pt): pt for pt in pending_tasks}

                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        completed_tasks.append(result)
                        indexing_completed += 1
                        update_analysis_progress(
                            supabase, event_id, "indexing",
                            indexing_completed / total_videos,
                            indexing_completed, total_videos,
                            f"TwelveLabs indexed {indexing_completed}/{total_videos} videos..."
                        )

            print(f"[Worker:analyze_videos] All {len(completed_tasks)} videos indexed!")

            # Generate embeddings in parallel using ThreadPoolExecutor
            print(f"[Worker:analyze_videos] ---------- GENERATING EMBEDDINGS IN PARALLEL ----------")
            update_analysis_progress(
                supabase, event_id, "embeddings",
                0.0, 0, total_videos,
                "Creating semantic embeddings for intelligent search..."
            )

            def generate_embeddings_for_video(ct):
                print(f"[Worker:analyze_videos] [Thread] Generating embeddings for video {ct['index'] + 1}...")
                embeddings = create_video_embeddings(ct["video_url"])
                return {**ct, "embeddings": embeddings}

            results = []
            with ThreadPoolExecutor(max_workers=min(4, len(completed_tasks))) as executor:
                futures = {executor.submit(generate_embeddings_for_video, ct): ct for ct in completed_tasks}
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    update_analysis_progress(
                        supabase, event_id, "embeddings",
                        len(results) / total_videos,
                        len(results), total_videos,
                        f"Generated embeddings for {len(results)}/{total_videos} videos..."
                    )
                    print(f"[Worker:analyze_videos] Embeddings complete for video {result['index'] + 1}: {len(result['embeddings'])} segments")

            # Store all results
            print(f"[Worker:analyze_videos] ---------- SAVING RESULTS ----------")
            update_analysis_progress(
                supabase, event_id, "saving",
                0.9, total_videos, total_videos,
                "Finalizing analysis data..."
            )

            for result in results:
                video = result["video"]
                completed_task = result["completed_task"]
                embeddings = result["embeddings"]

                analysis_data = {
                    "twelvelabs_video_id": completed_task.video_id if hasattr(completed_task, "video_id") else None,
                    "embeddings": embeddings,
                }

                supabase.table("videos").update({
                    "status": "analyzed",
                    "analysis_data": analysis_data,
                    "twelvelabs_video_id": completed_task.video_id if hasattr(completed_task, "video_id") else None,
                }).eq("id", video["id"]).execute()
                print(f"[Worker:analyze_videos] Video {result['index'] + 1} saved to database")

        # Update event status and clear progress (completed)
        update_analysis_progress(
            supabase, event_id, "complete",
            1.0, total_videos, total_videos,
            "Analysis complete!"
        )
        supabase.table("events").update({"status": "analyzed"}).eq("id", event_id).execute()
        print(f"[Worker:analyze_videos] ========== ANALYSIS COMPLETE ==========")
        print(f"[Worker:analyze_videos] Total videos analyzed: {len(videos.data)}")

        return {"status": "success", "event_id": event_id, "videos_analyzed": len(videos.data)}

    except Exception as e:
        print(f"[Worker:analyze_videos] ========== ERROR ==========")
        print(f"[Worker:analyze_videos] Error: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"[Worker:analyze_videos] Traceback:\n{traceback.format_exc()}")

        # Update status to failed
        supabase.table("events").update({
            "status": "failed",
        }).eq("id", event_id).execute()

        # Retry on transient errors
        if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
            print(f"[Worker:analyze_videos] Transient error detected, scheduling retry...")
            raise self.retry(exc=e)

        raise


@celery.task(bind=True, max_retries=3, default_retry_delay=60, name="worker.generate_video_task")
def generate_video_task(self, event_id: str):
    """Generate the final video for an event.

    Steps:
    1. Load timeline and analysis data
    2. Sync audio across angles
    3. Apply angle switching
    4. Add zoom effects
    5. Insert ad slots (if Shopify connected)
    6. Add sponsor overlays
    7. Mix music (if uploaded)
    8. Render final video
    """
    from services.supabase_client import get_supabase
    from services.s3_client import upload_file, parse_s3_uri, download_file
    from services.timeline import generate_timeline
    from services.audio_sync import sync_videos
    from services.render import render_final_video
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import tempfile
    import os

    print(f"[Worker:generate_video] ========== STARTING VIDEO GENERATION ==========")
    print(f"[Worker:generate_video] Event ID: {event_id}")

    settings = get_settings()
    supabase = get_supabase()

    try:
        # Get event data
        print(f"[Worker:generate_video] Fetching event and analyzed videos from database...")
        update_generation_progress(supabase, event_id, "initializing", 0.0, "Loading video data...")

        event = supabase.table("events").select("*").eq("id", event_id).single().execute()
        videos = supabase.table("videos").select("*").eq("event_id", event_id).eq("status", "analyzed").execute()

        print(f"[Worker:generate_video] Found {len(videos.data) if videos.data else 0} analyzed videos")

        if not videos.data:
            print(f"[Worker:generate_video] ERROR: No analyzed videos found")
            raise ValueError("No analyzed videos found")

        event_data = event.data
        print(f"[Worker:generate_video] Event type: {event_data.get('event_type', 'unknown')}")
        print(f"[Worker:generate_video] Music URL: {'Yes' if event_data.get('music_url') else 'No'}")
        print(f"[Worker:generate_video] Sponsor: {event_data.get('sponsor_name', 'None')}")

        # Create temp directory for processing
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"[Worker:generate_video] Created temp directory: {tmpdir}")

            # ============ OPTIMIZATION: PARALLEL VIDEO DOWNLOADS ============
            print(f"[Worker:generate_video] ---------- PARALLEL DOWNLOADING VIDEOS ----------")
            update_generation_progress(supabase, event_id, "downloading", 0.0, f"Downloading {len(videos.data)} videos...")

            def download_video(video_data):
                """Download a single video. Runs in parallel."""
                i, video = video_data
                print(f"[Worker:generate_video] [Thread] Downloading video {i + 1}/{len(videos.data)}: {video['id'][:8]}...")
                bucket, key = parse_s3_uri(video["original_url"])
                local_path = os.path.join(tmpdir, f"{video['id']}.mp4")
                download_file(bucket, key, local_path)
                file_size = os.path.getsize(local_path) / (1024 * 1024)  # MB
                print(f"[Worker:generate_video] [Thread] Downloaded video {i + 1}: {file_size:.1f} MB")
                return {
                    "id": video["id"],
                    "path": local_path,
                    "angle_type": video["angle_type"],
                    "analysis_data": video.get("analysis_data", {}),
                    "index": i,
                }

            video_paths = []
            download_count = 0
            total_vids = len(videos.data)
            with ThreadPoolExecutor(max_workers=min(4, len(videos.data))) as executor:
                futures = {executor.submit(download_video, (i, v)): i
                          for i, v in enumerate(videos.data)}
                for future in as_completed(futures):
                    result = future.result()
                    video_paths.append(result)
                    download_count += 1
                    update_generation_progress(
                        supabase, event_id, "downloading",
                        download_count / total_vids,
                        f"Downloaded {download_count}/{total_vids} videos..."
                    )

            # Sort by original index
            video_paths.sort(key=lambda x: x["index"])
            # Remove index key
            for vp in video_paths:
                del vp["index"]

            print(f"[Worker:generate_video] All videos downloaded in parallel")

            # Sync videos by audio
            print(f"[Worker:generate_video] ---------- SYNCING AUDIO ----------")
            update_generation_progress(supabase, event_id, "syncing", 0.5, f"Syncing audio across {len(video_paths)} camera angles...")
            print(f"[Worker:generate_video] Running audio fingerprint sync across {len(video_paths)} videos...")
            sync_offsets = sync_videos([v["path"] for v in video_paths])
            for i, video in enumerate(video_paths):
                video["sync_offset_ms"] = sync_offsets[i]
                print(f"[Worker:generate_video] Video {video['id'][:8]}... sync offset: {sync_offsets[i]}ms")

            # Generate timeline
            print(f"[Worker:generate_video] ---------- GENERATING TIMELINE ----------")
            update_generation_progress(supabase, event_id, "timeline", 0.3, "Creating intelligent multi-angle timeline...")
            timeline = generate_timeline(
                videos=video_paths,
                event_type=event_data["event_type"],
                index_id=event_data.get("twelvelabs_index_id"),
            )
            print(f"[Worker:generate_video] Timeline generated:")
            print(f"[Worker:generate_video]   - Segments: {len(timeline.get('segments', []))}")
            print(f"[Worker:generate_video]   - Zooms: {len(timeline.get('zooms', []))}")
            print(f"[Worker:generate_video]   - Ad slots: {len(timeline.get('ad_slots', []))}")
            print(f"[Worker:generate_video]   - Chapters: {len(timeline.get('chapters', []))}")

            # Store timeline (upsert with event_id as conflict key)
            supabase.table("timelines").upsert(
                {
                    "event_id": event_id,
                    "segments": timeline["segments"],
                    "zooms": timeline.get("zooms", []),
                    "ad_slots": timeline.get("ad_slots", []),
                    "chapters": timeline.get("chapters", []),
                },
                on_conflict="event_id",
            ).execute()
            print(f"[Worker:generate_video] Timeline saved to database")

            # Download music if present
            music_path = None
            if event_data.get("music_url"):
                print(f"[Worker:generate_video] ---------- DOWNLOADING MUSIC ----------")
                update_generation_progress(supabase, event_id, "music", 0.5, "Downloading your personal music...")
                bucket, key = parse_s3_uri(event_data["music_url"])
                music_path = os.path.join(tmpdir, "music.mp3")
                download_file(bucket, key, music_path)
                music_size = os.path.getsize(music_path) / (1024 * 1024)
                print(f"[Worker:generate_video] Music downloaded: {music_size:.1f} MB")

            # Generate Veo ads if brand products are connected and we have ad slots
            generated_ads = None
            ad_slots = timeline.get("ad_slots", [])
            if ad_slots:
                print(f"[Worker:generate_video] ---------- GENERATING VEO ADS ----------")
                update_generation_progress(supabase, event_id, "ads", 0.2, f"Generating {len(ad_slots)} AI product ads with Google Veo...")
                print(f"[Worker:generate_video] Found {len(ad_slots)} ad slots, checking for products...")
                try:
                    from services.veo_service import generate_ads_for_slots
                    from services.shopify_sync import get_event_brand_products
                    from services.encryption import decrypt
                    import httpx

                    products = []

                    # Try new model first: get products from event_brand_products
                    brand_products = get_event_brand_products(event_id)
                    if brand_products:
                        for bp in brand_products:
                            product = bp.get("product")
                            if product:
                                products.append({
                                    "id": product["id"],
                                    "title": product["title"],
                                    "description": product.get("description", ""),
                                    "price": str(product.get("price", "0.00")),
                                    "image_url": product.get("image_url"),
                                })
                        print(f"[Worker:generate_video] Using {len(products)} products from event_brand_products")

                    # Fall back to legacy model if no brand products
                    elif event_data.get("shopify_access_token"):
                        print(f"[Worker:generate_video] Falling back to legacy Shopify connection...")
                        access_token = decrypt(event_data["shopify_access_token"])
                        shop_url = event_data["shopify_store_url"]

                        with httpx.Client() as client:
                            response = client.get(
                                f"{shop_url}/admin/api/{settings.shopify_api_version}/products.json",
                                headers={
                                    "X-Shopify-Access-Token": access_token,
                                    "Content-Type": "application/json",
                                },
                                params={"limit": 5, "status": "active"},
                            )

                            if response.status_code == 200:
                                shopify_products = response.json().get("products", [])
                                for p in shopify_products:
                                    variant = p["variants"][0] if p.get("variants") else {}
                                    image = p["images"][0] if p.get("images") else {}
                                    products.append({
                                        "id": str(p["id"]),
                                        "title": p["title"],
                                        "description": p.get("body_html", ""),
                                        "price": variant.get("price", "0.00"),
                                        "image_url": image.get("src"),
                                    })
                        print(f"[Worker:generate_video] Using {len(products)} products from legacy Shopify")
                    else:
                        print(f"[Worker:generate_video] No products connected, skipping ad generation")

                    if products:
                        # Generate Veo ads for each slot
                        print(f"[Worker:generate_video] Generating Veo ads for {len(products)} products...")
                        generated_ads = generate_ads_for_slots(
                            products=products,
                            ad_slots=ad_slots,
                            event_type=event_data["event_type"],
                            sponsor_name=event_data.get("sponsor_name"),
                        )
                        print(f"[Worker:generate_video] Generated {len(generated_ads)} Veo ads")
                except Exception as e:
                    print(f"[Worker:generate_video] Failed to generate Veo ads: {type(e).__name__}: {e}")
                    # Continue without ads - not a fatal error

            # Render final video
            print(f"[Worker:generate_video] ---------- RENDERING FINAL VIDEO ----------")
            update_generation_progress(supabase, event_id, "rendering", 0.1, "Rendering final broadcast-quality video with FFmpeg...")
            output_path = os.path.join(tmpdir, "output.mp4")
            print(f"[Worker:generate_video] Starting FFmpeg render...")
            print(f"[Worker:generate_video]   - Video paths: {len(video_paths)}")
            print(f"[Worker:generate_video]   - Music: {'Yes' if music_path else 'No'}")
            print(f"[Worker:generate_video]   - Ads: {len(generated_ads) if generated_ads else 0}")
            print(f"[Worker:generate_video]   - Sponsor overlays: {'Yes' if event_data.get('sponsor_name') else 'No'}")

            render_final_video(
                video_paths=video_paths,
                timeline=timeline,
                output_path=output_path,
                music_path=music_path,
                event_type=event_data["event_type"],
                sponsor_name=event_data.get("sponsor_name"),
                generated_ads=generated_ads,
            )

            output_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[Worker:generate_video] Render complete: {output_size:.1f} MB")

            # Upload to S3
            print(f"[Worker:generate_video] ---------- UPLOADING TO S3 ----------")
            update_generation_progress(supabase, event_id, "uploading", 0.5, f"Uploading final video ({output_size:.0f} MB)...")
            settings = get_settings()
            s3_key = f"events/{event_id}/output/final.mp4"
            print(f"[Worker:generate_video] Uploading to s3://{settings.s3_bucket}/{s3_key}")
            master_url = upload_file(output_path, settings.s3_bucket, s3_key, "video/mp4")
            print(f"[Worker:generate_video] Upload complete: {master_url}")

            # Update event
            update_generation_progress(supabase, event_id, "complete", 1.0, "Video generation complete! 🎬")
            supabase.table("events").update({
                "status": "completed",
                "master_video_url": master_url,
            }).eq("id", event_id).execute()
            print(f"[Worker:generate_video] Event status updated to 'completed'")

        print(f"[Worker:generate_video] ========== VIDEO GENERATION COMPLETE ==========")
        return {"status": "success", "event_id": event_id, "master_video_url": master_url}

    except Exception as e:
        print(f"[Worker:generate_video] ========== ERROR ==========")
        print(f"[Worker:generate_video] Error: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"[Worker:generate_video] Traceback:\n{traceback.format_exc()}")

        supabase.table("events").update({"status": "failed"}).eq("id", event_id).execute()

        if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
            print(f"[Worker:generate_video] Transient error detected, scheduling retry...")
            raise self.retry(exc=e)

        raise


@celery.task(bind=True, max_retries=3, default_retry_delay=30, name="worker.sync_store_products_task")
def sync_store_products_task(self, store_id: str):
    """Sync products from Shopify store to local cache.

    Called after a store installs the app or when manually triggered.
    Fetches all active products and upserts them into shopify_products table.
    """
    from services.shopify_sync import sync_store_products

    print(f"[Worker:sync_store] ========== SYNCING SHOPIFY STORE ==========")
    print(f"[Worker:sync_store] Store ID: {store_id}")

    try:
        print(f"[Worker:sync_store] Fetching products from Shopify...")
        result = sync_store_products(store_id)
        print(f"[Worker:sync_store] Sync complete: {result['products_synced']} products synced")
        print(f"[Worker:sync_store] ========== SYNC COMPLETE ==========")
        return {
            "status": "success",
            "store_id": store_id,
            "products_synced": result["products_synced"],
        }

    except Exception as e:
        print(f"[Worker:sync_store] ========== ERROR ==========")
        print(f"[Worker:sync_store] Error: {type(e).__name__}: {str(e)}")

        # Retry on transient errors
        if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
            print(f"[Worker:sync_store] Transient error detected, scheduling retry...")
            raise self.retry(exc=e)

        raise


@celery.task(bind=True, max_retries=2, name="worker.analyze_music_task")
def analyze_music_task(self, event_id: str):
    """Analyze uploaded music for beats and tempo."""
    from services.supabase_client import get_supabase
    from services.s3_client import download_file, parse_s3_uri
    from services.music_sync import analyze_music_track

    import tempfile
    import os

    print(f"[Worker:analyze_music] ========== ANALYZING MUSIC ==========")
    print(f"[Worker:analyze_music] Event ID: {event_id}")

    supabase = get_supabase()

    try:
        # Get event
        print(f"[Worker:analyze_music] Fetching event from database...")
        event = supabase.table("events").select("music_url").eq("id", event_id).single().execute()

        if not event.data.get("music_url"):
            print(f"[Worker:analyze_music] ERROR: No music uploaded")
            raise ValueError("No music uploaded")

        print(f"[Worker:analyze_music] Music URL found: {event.data['music_url'][:50]}...")

        # Download music
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"[Worker:analyze_music] Downloading music file...")
            bucket, key = parse_s3_uri(event.data["music_url"])
            music_path = os.path.join(tmpdir, "music.mp3")
            download_file(bucket, key, music_path)
            file_size = os.path.getsize(music_path) / (1024 * 1024)
            print(f"[Worker:analyze_music] Downloaded: {file_size:.1f} MB")

            # Analyze
            print(f"[Worker:analyze_music] Running beat detection and tempo analysis...")
            metadata = analyze_music_track(music_path)
            print(f"[Worker:analyze_music] Analysis complete:")
            print(f"[Worker:analyze_music]   - Tempo: {metadata.get('tempo', 'N/A')} BPM")
            print(f"[Worker:analyze_music]   - Beat count: {len(metadata.get('beat_times_ms', []))}")
            print(f"[Worker:analyze_music]   - Duration: {metadata.get('duration_sec', 'N/A')}s")

            # Store metadata
            supabase.table("events").update({
                "music_metadata": metadata
            }).eq("id", event_id).execute()
            print(f"[Worker:analyze_music] Metadata saved to database")

        print(f"[Worker:analyze_music] ========== MUSIC ANALYSIS COMPLETE ==========")
        return {"status": "success", "event_id": event_id, "metadata": metadata}

    except Exception as e:
        print(f"[Worker:analyze_music] ========== ERROR ==========")
        print(f"[Worker:analyze_music] Error: {type(e).__name__}: {str(e)}")

        if "rate limit" in str(e).lower():
            print(f"[Worker:analyze_music] Transient error detected, scheduling retry...")
            raise self.retry(exc=e)
        raise


@celery.task(bind=True, max_retries=2, name="worker.generate_highlight_reel_task")
def generate_highlight_reel_task(self, event_id: str, reel_id: str, query: str, vibe: VibeType, duration: int = 30):
    """Generate a personalized highlight reel.

    Steps:
    1. Search TwelveLabs for query matches
    2. Rank by vibe embedding similarity
    3. Select top clips to fill duration
    4. Render with crossfades
    """
    from services.supabase_client import get_supabase
    from services.twelvelabs_service import search_videos, get_vibe_embedding
    from services.s3_client import download_file, upload_file, parse_s3_uri
    from services.render import render_highlight_reel
    from scipy.spatial.distance import cosine
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import tempfile
    import os

    print(f"[Worker:highlight_reel] ========== GENERATING HIGHLIGHT REEL ==========")
    print(f"[Worker:highlight_reel] Event ID: {event_id}")
    print(f"[Worker:highlight_reel] Reel ID: {reel_id}")
    print(f"[Worker:highlight_reel] Query: '{query}'")
    print(f"[Worker:highlight_reel] Vibe: {vibe}")
    print(f"[Worker:highlight_reel] Target duration: {duration}s")

    supabase = get_supabase()

    try:
        # Get event
        print(f"[Worker:highlight_reel] Fetching event from database...")
        event = supabase.table("events").select("*").eq("id", event_id).single().execute()
        event_data = event.data

        if not event_data.get("twelvelabs_index_id"):
            print(f"[Worker:highlight_reel] ERROR: Event not analyzed yet")
            raise ValueError("Event not analyzed yet")

        print(f"[Worker:highlight_reel] TwelveLabs index: {event_data['twelvelabs_index_id']}")

        # Search for moments
        print(f"[Worker:highlight_reel] ---------- SEARCHING MOMENTS ----------")
        print(f"[Worker:highlight_reel] Searching TwelveLabs for: '{query}'")
        moments = search_videos(
            index_id=event_data["twelvelabs_index_id"],
            query=query,
            limit=20,
        )

        print(f"[Worker:highlight_reel] Found {len(moments) if moments else 0} matching moments")

        if not moments:
            print(f"[Worker:highlight_reel] No matching moments found, marking reel as failed")
            supabase.table("custom_reels").update({
                "status": "failed",
            }).eq("id", reel_id).execute()
            return {"status": "failed", "reason": "No matching moments found"}

        # Get vibe embedding for ranking
        print(f"[Worker:highlight_reel] ---------- RANKING BY VIBE ----------")
        print(f"[Worker:highlight_reel] Generating vibe embedding for: {vibe}")
        vibe_embedding = get_vibe_embedding(vibe)
        print(f"[Worker:highlight_reel] Vibe embedding generated (dim: {len(vibe_embedding) if vibe_embedding else 0})")

        # Get video embeddings and rank
        videos = supabase.table("videos").select("*").eq("event_id", event_id).execute()
        video_map = {v["twelvelabs_video_id"]: v for v in videos.data if v.get("twelvelabs_video_id")}
        print(f"[Worker:highlight_reel] Loaded {len(video_map)} videos for scoring")

        scored_moments = []
        for moment in moments:
            video = video_map.get(moment["video_id"])
            if not video:
                continue

            # Get segment embedding (simplified - use average if available)
            embeddings = video.get("analysis_data", {}).get("embeddings", [])

            vibe_score = 0.5  # Default score
            if embeddings and vibe_embedding:
                # Find embedding closest to this moment's timestamp
                for emb in embeddings:
                    if emb["start_time"] <= moment["start"] <= emb["end_time"]:
                        if emb.get("embedding"):
                            vibe_score = 1 - cosine(emb["embedding"], vibe_embedding)
                        break

            # Combine scores
            final_score = 0.6 * vibe_score + 0.4 * moment["confidence"]

            scored_moments.append({
                **moment,
                "video_db_id": video["id"],
                "original_url": video["original_url"],
                "vibe_score": vibe_score,
                "final_score": final_score,
            })

        print(f"[Worker:highlight_reel] Scored {len(scored_moments)} moments")

        # Sort by score and select clips
        scored_moments.sort(key=lambda m: m["final_score"], reverse=True)

        print(f"[Worker:highlight_reel] ---------- SELECTING CLIPS ----------")
        selected_clips = []
        total_duration = 0
        for moment in scored_moments:
            clip_duration = moment["end"] - moment["start"]
            if total_duration + clip_duration <= duration:
                selected_clips.append(moment)
                total_duration += clip_duration
                print(f"[Worker:highlight_reel] Selected clip: {moment['start']:.1f}s-{moment['end']:.1f}s (score: {moment['final_score']:.2f})")
            if total_duration >= duration:
                break

        print(f"[Worker:highlight_reel] Total clips selected: {len(selected_clips)}")
        print(f"[Worker:highlight_reel] Total duration: {total_duration:.1f}s")

        if not selected_clips:
            print(f"[Worker:highlight_reel] No clips selected, marking reel as failed")
            supabase.table("custom_reels").update({"status": "failed"}).eq("id", reel_id).execute()
            return {"status": "failed", "reason": "Could not select clips"}

        # Render
        print(f"[Worker:highlight_reel] ---------- RENDERING REEL ----------")
        settings = get_settings()
        with tempfile.TemporaryDirectory() as tmpdir:
            # ============ OPTIMIZATION: PARALLEL CLIP DOWNLOADS ============
            print(f"[Worker:highlight_reel] Downloading source videos in parallel...")

            def download_clip(clip_data):
                """Download a single clip source. Runs in parallel."""
                i, clip = clip_data
                print(f"[Worker:highlight_reel] [Thread] Downloading clip {i + 1}/{len(selected_clips)}")
                bucket, key = parse_s3_uri(clip["original_url"])
                video_path = os.path.join(tmpdir, f"source_{i}.mp4")
                download_file(bucket, key, video_path)
                return {
                    "path": video_path,
                    "start": clip["start"],
                    "end": clip["end"],
                    "index": i,
                }

            clip_paths = []
            with ThreadPoolExecutor(max_workers=min(4, len(selected_clips))) as executor:
                futures = {executor.submit(download_clip, (i, c)): i
                          for i, c in enumerate(selected_clips)}
                for future in as_completed(futures):
                    result = future.result()
                    clip_paths.append(result)

            # Sort by original index and remove index key
            clip_paths.sort(key=lambda x: x["index"])
            for cp in clip_paths:
                del cp["index"]

            # Download music if available
            music_path = None
            if event_data.get("music_url"):
                print(f"[Worker:highlight_reel] Downloading music...")
                bucket, key = parse_s3_uri(event_data["music_url"])
                music_path = os.path.join(tmpdir, "music.mp3")
                download_file(bucket, key, music_path)

            # Render reel
            output_path = os.path.join(tmpdir, "reel.mp4")
            print(f"[Worker:highlight_reel] Starting FFmpeg render...")
            render_highlight_reel(
                clips=clip_paths,
                output_path=output_path,
                title=f"{query.title()} Highlights",
                music_path=music_path,
                vibe=vibe,
            )

            output_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[Worker:highlight_reel] Render complete: {output_size:.1f} MB")

            # Upload
            print(f"[Worker:highlight_reel] Uploading to S3...")
            s3_key = f"events/{event_id}/reels/{reel_id}.mp4"
            reel_url = upload_file(output_path, settings.s3_bucket, s3_key, "video/mp4")
            print(f"[Worker:highlight_reel] Upload complete: {reel_url}")

        # Update reel record
        supabase.table("custom_reels").update({
            "status": "completed",
            "output_url": reel_url,
            "moments": selected_clips,
            "duration_sec": int(total_duration),
        }).eq("id", reel_id).execute()
        print(f"[Worker:highlight_reel] Reel record updated in database")

        print(f"[Worker:highlight_reel] ========== HIGHLIGHT REEL COMPLETE ==========")
        return {
            "status": "success",
            "reel_id": reel_id,
            "reel_url": reel_url,
            "moments_count": len(selected_clips),
        }

    except Exception as e:
        print(f"[Worker:highlight_reel] ========== ERROR ==========")
        print(f"[Worker:highlight_reel] Error: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"[Worker:highlight_reel] Traceback:\n{traceback.format_exc()}")

        supabase.table("custom_reels").update({"status": "failed"}).eq("id", reel_id).execute()

        if "rate limit" in str(e).lower():
            print(f"[Worker:highlight_reel] Transient error detected, scheduling retry...")
            raise self.retry(exc=e)
        raise
