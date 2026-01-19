from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from services.supabase_client import get_supabase
from services.s3_client import generate_presigned_download_url, parse_s3_uri

router = APIRouter()


class EventCreate(BaseModel):
    name: str
    event_type: Literal["sports", "ceremony", "performance"]


class EventResponse(BaseModel):
    id: str
    name: str
    event_type: str
    status: str
    user_id: str | None = None
    shopify_store_url: str | None = None
    sponsor_name: str | None = None
    master_video_url: str | None = None
    music_url: str | None = None


class SponsorUpdate(BaseModel):
    sponsor_name: str


class SubtlePlacementRequest(BaseModel):
    product_ids: list[str] | None = None  # Specific products, or auto-select from Shopify
    max_placements: int = 3
    min_spacing_seconds: float = 60.0
    style: Literal["floating", "showcase", "dynamic", "minimal", "lifestyle"] | None = None  # None = auto


@router.get("")
async def list_events(limit: int = 50, offset: int = 0):
    """List all events, ordered by creation date (newest first)."""
    supabase = get_supabase()
    settings = get_settings()

    result = (
        supabase.table("events")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    events = []
    for event in result.data or []:
        # Generate presigned URL for master video if exists
        master_video_url = None
        if event.get("master_video_url"):
            try:
                bucket, key = parse_s3_uri(event["master_video_url"])
                master_video_url = generate_presigned_download_url(bucket, key)
            except Exception:
                master_video_url = event["master_video_url"]

        # Get first uploaded video as thumbnail preview if no master video
        thumbnail_url = None
        if not master_video_url:
            videos_result = (
                supabase.table("videos")
                .select("original_url")
                .eq("event_id", event["id"])
                .eq("status", "uploaded")
                .order("created_at")
                .limit(1)
                .execute()
            )
            if videos_result.data:
                try:
                    bucket, key = parse_s3_uri(videos_result.data[0]["original_url"])
                    thumbnail_url = generate_presigned_download_url(bucket, key)
                except Exception:
                    thumbnail_url = videos_result.data[0]["original_url"]

        events.append({
            "id": event["id"],
            "name": event["name"],
            "event_type": event["event_type"],
            "status": event["status"],
            "user_id": event.get("user_id"),
            "shopify_store_url": event.get("shopify_store_url"),
            "sponsor_name": event.get("sponsor_name"),
            "master_video_url": master_video_url,
            "thumbnail_url": thumbnail_url,
            "music_url": event.get("music_url"),
            "created_at": event.get("created_at"),
        })

    return {"events": events}


@router.post("", response_model=EventResponse)
async def create_event(event: EventCreate):
    """Create a new event."""
    supabase = get_supabase()

    event_id = str(uuid4())
    data = {
        "id": event_id,
        "name": event.name,
        "event_type": event.event_type,
        "status": "created",
    }

    result = supabase.table("events").insert(data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create event")

    return EventResponse(**result.data[0])


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(event_id: str):
    """Get event by ID."""
    supabase = get_supabase()

    result = supabase.table("events").select("*").eq("id", event_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    event_data = result.data[0]

    # Convert S3 URIs to presigned URLs for browser access
    if event_data.get("master_video_url") and event_data["master_video_url"].startswith("s3://"):
        try:
            bucket, key = parse_s3_uri(event_data["master_video_url"])
            event_data["master_video_url"] = generate_presigned_download_url(bucket, key, expires_in=3600)
        except Exception as e:
            print(f"Failed to generate presigned URL for master video: {e}")

    if event_data.get("music_url") and event_data["music_url"].startswith("s3://"):
        try:
            bucket, key = parse_s3_uri(event_data["music_url"])
            event_data["music_url"] = generate_presigned_download_url(bucket, key, expires_in=3600)
        except Exception as e:
            print(f"Failed to generate presigned URL for music: {e}")

    return EventResponse(**event_data)


@router.post("/{event_id}/analyze")
async def analyze_event(event_id: str):
    """Start TwelveLabs analysis for all videos in event."""
    supabase = get_supabase()

    # Get event
    event = supabase.table("events").select("*").eq("id", event_id).execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    # Get videos
    videos = supabase.table("videos").select("*").eq("event_id", event_id).execute()
    if not videos.data:
        raise HTTPException(status_code=400, detail="No videos uploaded yet")

    # Update status
    supabase.table("events").update({"status": "analyzing"}).eq(
        "id", event_id
    ).execute()

    # Trigger Celery task for TwelveLabs analysis
    from worker import analyze_videos_task
    task = analyze_videos_task.delay(event_id)

    return {
        "message": "Analysis started",
        "event_id": event_id,
        "video_count": len(videos.data),
        "task_id": task.id,
    }


@router.post("/{event_id}/generate")
async def generate_video(event_id: str, force: bool = False):
    """Generate the final video for an event.

    Args:
        event_id: Event ID
        force: If True, allow re-generation even if already completed
    """
    supabase = get_supabase()

    event = supabase.table("events").select("*").eq("id", event_id).execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    status = event.data[0]["status"]
    # Allow regeneration if force=True and status is analyzed or completed
    if status not in ("analyzed", "completed") and not force:
        raise HTTPException(
            status_code=400, detail="Event must be analyzed before generating video"
        )
    if status == "completed" and not force:
        raise HTTPException(
            status_code=400, detail="Event already generated. Use ?force=true to regenerate"
        )

    # Update status
    supabase.table("events").update({"status": "generating"}).eq(
        "id", event_id
    ).execute()

    # Trigger Celery task for video generation
    from worker import generate_video_task
    task = generate_video_task.delay(event_id)

    return {"message": "Video generation started", "event_id": event_id, "task_id": task.id}


@router.post("/{event_id}/sponsor")
async def set_sponsor(event_id: str, sponsor: SponsorUpdate):
    """Set sponsor for power plays."""
    supabase = get_supabase()

    result = (
        supabase.table("events")
        .update({"sponsor_name": sponsor.sponsor_name})
        .eq("id", event_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    return {"message": "Sponsor updated", "sponsor_name": sponsor.sponsor_name}


@router.get("/{event_id}/chapters")
async def get_chapters(event_id: str):
    """Get chapter markers for the event."""
    supabase = get_supabase()

    # Get timeline with chapters
    result = (
        supabase.table("timelines").select("chapters").eq("event_id", event_id).execute()
    )

    if not result.data:
        return {"chapters": []}

    return {"chapters": result.data[0].get("chapters", [])}


@router.post("/{event_id}/subtle-placements")
async def create_subtle_placements(event_id: str, request: SubtlePlacementRequest):
    """Generate subtle in-video product placements using Veo + chroma key.

    This creates product overlays that blend into the event footage rather than
    inserting separate ad clips. Products appear as floating/animated overlays
    at optimal moments detected from TwelveLabs analysis.

    The pipeline:
    1. Detect optimal placement times from video analysis
    2. Generate Veo product videos on green screen
    3. Chroma key remove the green background
    4. Composite onto event footage at detected positions

    Args:
        event_id: Event ID
        request: Placement configuration
    """
    supabase = get_supabase()

    # Get event
    event = supabase.table("events").select("*").eq("id", event_id).execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    event_data = event.data[0]

    if event_data["status"] not in ("analyzed", "completed"):
        raise HTTPException(
            status_code=400,
            detail="Event must be analyzed before adding placements"
        )

    # Get video analysis for placement detection
    videos = (
        supabase.table("videos")
        .select("analysis_data")
        .eq("event_id", event_id)
        .not_.is_("analysis_data", "null")
        .execute()
    )

    if not videos.data:
        raise HTTPException(
            status_code=400,
            detail="No analyzed videos found"
        )

    # Combine analysis from all videos
    combined_analysis = {
        "scenes": [],
        "moments": [],
    }
    for video in videos.data:
        analysis = video.get("analysis_data", {})
        combined_analysis["scenes"].extend(analysis.get("scenes", []))
        combined_analysis["moments"].extend(analysis.get("moments", []))

    # Get Shopify products if connected
    products = []
    if event_data.get("shopify_store_url"):
        from services.shopify_client import get_shopify_products
        try:
            products = await get_shopify_products(event_id)
        except Exception as e:
            print(f"Failed to fetch Shopify products: {e}")

    if not products:
        raise HTTPException(
            status_code=400,
            detail="No Shopify products available. Connect a store first."
        )

    # Filter to specific products if requested
    if request.product_ids:
        products = [p for p in products if p.get("id") in request.product_ids]

    # Detect optimal placement times (always returns at least one)
    from services.subtle_placement_service import detect_optimal_placement_times

    placement_times = detect_optimal_placement_times(
        video_analysis=combined_analysis,
        max_placements=request.max_placements,
        min_spacing_seconds=request.min_spacing_seconds,
        # video_duration_sec will be extracted from analysis or use default
    )

    # Override style if specified
    if request.style:
        for pt in placement_times:
            pt["style"] = request.style

    # Trigger async task for placement generation
    from worker import create_subtle_placements_task
    task = create_subtle_placements_task.delay(
        event_id=event_id,
        products=[{"id": p.get("id"), "title": p.get("title"), "description": p.get("description", "")} for p in products[:request.max_placements]],
        placement_times=placement_times,
        event_type=event_data["event_type"],
    )

    return {
        "message": "Subtle placement generation started",
        "event_id": event_id,
        "task_id": task.id,
        "placement_count": len(placement_times),
        "placements": placement_times,
    }
