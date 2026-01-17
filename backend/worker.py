"""Celery worker for async video processing tasks."""

from typing import Literal

from celery import Celery

from config import get_settings

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


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def analyze_videos_task(self, event_id: str):
    """Analyze all videos in an event using TwelveLabs.

    Steps:
    1. Create TwelveLabs index for the event
    2. Index all videos
    3. Run analysis and store results
    4. Generate embeddings for vibe matching
    """
    from services.supabase_client import get_supabase
    from services.twelvelabs_service import (
        create_index,
        index_video,
        create_video_embeddings,
    )
    from services.s3_client import generate_presigned_download_url, parse_s3_uri

    supabase = get_supabase()

    try:
        # Get event and videos
        _event = supabase.table("events").select("*").eq("id", event_id).single().execute()
        videos = supabase.table("videos").select("*").eq("event_id", event_id).eq("status", "uploaded").execute()

        if not videos.data:
            raise ValueError("No uploaded videos found")

        # Create TwelveLabs index
        index_id = create_index(f"event_{event_id}")

        # Store index ID
        supabase.table("events").update({"twelvelabs_index_id": index_id}).eq("id", event_id).execute()

        # Index each video
        for video in videos.data:
            # Update video status
            supabase.table("videos").update({"status": "analyzing"}).eq("id", video["id"]).execute()

            # Get presigned URL for S3 video
            bucket, key = parse_s3_uri(video["original_url"])
            video_url = generate_presigned_download_url(bucket, key, expires_in=7200)

            # Index video in TwelveLabs
            task = index_video(index_id, video_url, wait=True)

            # Generate embeddings
            embeddings = create_video_embeddings(video_url)

            # Store analysis data
            analysis_data = {
                "twelvelabs_video_id": task.video_id if hasattr(task, "video_id") else None,
                "embeddings": embeddings,
            }

            supabase.table("videos").update({
                "status": "analyzed",
                "analysis_data": analysis_data,
                "twelvelabs_video_id": task.video_id if hasattr(task, "video_id") else None,
            }).eq("id", video["id"]).execute()

        # Update event status
        supabase.table("events").update({"status": "analyzed"}).eq("id", event_id).execute()

        return {"status": "success", "event_id": event_id, "videos_analyzed": len(videos.data)}

    except Exception as e:
        # Update status to failed
        supabase.table("events").update({
            "status": "failed",
        }).eq("id", event_id).execute()

        # Retry on transient errors
        if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
            raise self.retry(exc=e)

        raise


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
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

    import tempfile
    import os

    settings = get_settings()
    supabase = get_supabase()

    try:
        # Get event data
        event = supabase.table("events").select("*").eq("id", event_id).single().execute()
        videos = supabase.table("videos").select("*").eq("event_id", event_id).eq("status", "analyzed").execute()

        if not videos.data:
            raise ValueError("No analyzed videos found")

        event_data = event.data

        # Create temp directory for processing
        with tempfile.TemporaryDirectory() as tmpdir:
            # Download videos
            video_paths = []
            for video in videos.data:
                bucket, key = parse_s3_uri(video["original_url"])
                local_path = os.path.join(tmpdir, f"{video['id']}.mp4")
                download_file(bucket, key, local_path)
                video_paths.append({
                    "id": video["id"],
                    "path": local_path,
                    "angle_type": video["angle_type"],
                    "analysis_data": video.get("analysis_data", {}),
                })

            # Sync videos by audio
            sync_offsets = sync_videos([v["path"] for v in video_paths])
            for i, video in enumerate(video_paths):
                video["sync_offset_ms"] = sync_offsets[i]

            # Generate timeline
            timeline = generate_timeline(
                videos=video_paths,
                event_type=event_data["event_type"],
                index_id=event_data.get("twelvelabs_index_id"),
            )

            # Store timeline
            supabase.table("timelines").upsert({
                "event_id": event_id,
                "segments": timeline["segments"],
                "zooms": timeline.get("zooms", []),
                "ad_slots": timeline.get("ad_slots", []),
                "chapters": timeline.get("chapters", []),
            }).execute()

            # Download music if present
            music_path = None
            if event_data.get("music_url"):
                bucket, key = parse_s3_uri(event_data["music_url"])
                music_path = os.path.join(tmpdir, "music.mp3")
                download_file(bucket, key, music_path)

            # Generate Veo ads if brand products are connected and we have ad slots
            generated_ads = None
            ad_slots = timeline.get("ad_slots", [])
            if ad_slots:
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
                        print(f"[Worker] Using {len(products)} products from event_brand_products")

                    # Fall back to legacy model if no brand products
                    elif event_data.get("shopify_access_token"):
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
                        print(f"[Worker] Using {len(products)} products from legacy Shopify connection")

                    if products:
                        # Generate Veo ads for each slot
                        generated_ads = generate_ads_for_slots(
                            products=products,
                            ad_slots=ad_slots,
                            event_type=event_data["event_type"],
                            sponsor_name=event_data.get("sponsor_name"),
                        )
                        print(f"[Worker] Generated {len(generated_ads)} Veo ads")
                except Exception as e:
                    print(f"[Worker] Failed to generate Veo ads: {e}")
                    # Continue without ads - not a fatal error

            # Render final video
            output_path = os.path.join(tmpdir, "output.mp4")
            render_final_video(
                video_paths=video_paths,
                timeline=timeline,
                output_path=output_path,
                music_path=music_path,
                event_type=event_data["event_type"],
                sponsor_name=event_data.get("sponsor_name"),
                generated_ads=generated_ads,
            )

            # Upload to S3
            settings = get_settings()
            s3_key = f"events/{event_id}/output/final.mp4"
            master_url = upload_file(output_path, settings.s3_bucket, s3_key, "video/mp4")

            # Update event
            supabase.table("events").update({
                "status": "completed",
                "master_video_url": master_url,
            }).eq("id", event_id).execute()

        return {"status": "success", "event_id": event_id, "master_video_url": master_url}

    except Exception as e:
        supabase.table("events").update({"status": "failed"}).eq("id", event_id).execute()

        if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
            raise self.retry(exc=e)

        raise


@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def sync_store_products_task(self, store_id: str):
    """Sync products from Shopify store to local cache.

    Called after a store installs the app or when manually triggered.
    Fetches all active products and upserts them into shopify_products table.
    """
    from services.shopify_sync import sync_store_products

    try:
        result = sync_store_products(store_id)
        return {
            "status": "success",
            "store_id": store_id,
            "products_synced": result["products_synced"],
        }

    except Exception as e:
        # Retry on transient errors
        if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
            raise self.retry(exc=e)

        # Log and re-raise for permanent errors
        print(f"[Worker] Failed to sync store {store_id}: {e}")
        raise


@celery.task(bind=True, max_retries=2)
def analyze_music_task(self, event_id: str):
    """Analyze uploaded music for beats and tempo."""
    from services.supabase_client import get_supabase
    from services.s3_client import download_file, parse_s3_uri
    from services.music_sync import analyze_music_track

    import tempfile
    import os

    supabase = get_supabase()

    try:
        # Get event
        event = supabase.table("events").select("music_url").eq("id", event_id).single().execute()

        if not event.data.get("music_url"):
            raise ValueError("No music uploaded")

        # Download music
        with tempfile.TemporaryDirectory() as tmpdir:
            bucket, key = parse_s3_uri(event.data["music_url"])
            music_path = os.path.join(tmpdir, "music.mp3")
            download_file(bucket, key, music_path)

            # Analyze
            metadata = analyze_music_track(music_path)

            # Store metadata
            supabase.table("events").update({
                "music_metadata": metadata
            }).eq("id", event_id).execute()

        return {"status": "success", "event_id": event_id, "metadata": metadata}

    except Exception as e:
        if "rate limit" in str(e).lower():
            raise self.retry(exc=e)
        raise


@celery.task(bind=True, max_retries=2)
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

    import tempfile
    import os

    supabase = get_supabase()

    try:
        # Get event
        event = supabase.table("events").select("*").eq("id", event_id).single().execute()
        event_data = event.data

        if not event_data.get("twelvelabs_index_id"):
            raise ValueError("Event not analyzed yet")

        # Search for moments
        moments = search_videos(
            index_id=event_data["twelvelabs_index_id"],
            query=query,
            limit=20,
        )

        if not moments:
            supabase.table("custom_reels").update({
                "status": "failed",
            }).eq("id", reel_id).execute()
            return {"status": "failed", "reason": "No matching moments found"}

        # Get vibe embedding for ranking
        vibe_embedding = get_vibe_embedding(vibe)

        # Get video embeddings and rank
        videos = supabase.table("videos").select("*").eq("event_id", event_id).execute()
        video_map = {v["twelvelabs_video_id"]: v for v in videos.data if v.get("twelvelabs_video_id")}

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

        # Sort by score and select clips
        scored_moments.sort(key=lambda m: m["final_score"], reverse=True)

        selected_clips = []
        total_duration = 0
        for moment in scored_moments:
            clip_duration = moment["end"] - moment["start"]
            if total_duration + clip_duration <= duration:
                selected_clips.append(moment)
                total_duration += clip_duration
            if total_duration >= duration:
                break

        if not selected_clips:
            supabase.table("custom_reels").update({"status": "failed"}).eq("id", reel_id).execute()
            return {"status": "failed", "reason": "Could not select clips"}

        # Render
        settings = get_settings()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Download clip segments
            clip_paths = []
            for i, clip in enumerate(selected_clips):
                bucket, key = parse_s3_uri(clip["original_url"])
                video_path = os.path.join(tmpdir, f"source_{i}.mp4")
                download_file(bucket, key, video_path)
                clip_paths.append({
                    "path": video_path,
                    "start": clip["start"],
                    "end": clip["end"],
                })

            # Download music if available
            music_path = None
            if event_data.get("music_url"):
                bucket, key = parse_s3_uri(event_data["music_url"])
                music_path = os.path.join(tmpdir, "music.mp3")
                download_file(bucket, key, music_path)

            # Render reel
            output_path = os.path.join(tmpdir, "reel.mp4")
            render_highlight_reel(
                clips=clip_paths,
                output_path=output_path,
                title=f"{query.title()} Highlights",
                music_path=music_path,
                vibe=vibe,
            )

            # Upload
            s3_key = f"events/{event_id}/reels/{reel_id}.mp4"
            reel_url = upload_file(output_path, settings.s3_bucket, s3_key, "video/mp4")

        # Update reel record
        supabase.table("custom_reels").update({
            "status": "completed",
            "output_url": reel_url,
            "moments": selected_clips,
            "duration_sec": int(total_duration),
        }).eq("id", reel_id).execute()

        return {
            "status": "success",
            "reel_id": reel_id,
            "reel_url": reel_url,
            "moments_count": len(selected_clips),
        }

    except Exception as e:
        supabase.table("custom_reels").update({"status": "failed"}).eq("id", reel_id).execute()

        if "rate limit" in str(e).lower():
            raise self.retry(exc=e)
        raise
