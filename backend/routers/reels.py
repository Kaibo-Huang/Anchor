from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from services.supabase_client import get_supabase
from services.s3_client import generate_presigned_download_url, parse_s3_uri

router = APIRouter()


class ReelGenerateRequest(BaseModel):
    query: str  # e.g., "me", "player 23", "guy in yellow pants"
    vibe: Literal["high_energy", "emotional", "calm"] = "high_energy"
    duration: int = 30  # seconds
    include_music: bool = True


class ReelResponse(BaseModel):
    reel_id: str
    reel_url: str | None
    moments_count: int
    total_duration: float
    vibe: str
    status: str


@router.post("/{event_id}/reels/generate", response_model=ReelResponse)
async def generate_highlight_reel(event_id: str, request: ReelGenerateRequest):
    """
    Generate personalized highlight reel using natural language + embeddings.
    IDENTITY FEATURE: Find "me" in the video based on query.
    """
    supabase = get_supabase()

    # Get event
    event_result = supabase.table("events").select("*").eq("id", event_id).execute()
    if not event_result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    event = event_result.data[0]

    # Check if event has been analyzed
    if event["status"] not in ["analyzed", "completed"]:
        raise HTTPException(
            status_code=400,
            detail="Event must be analyzed before generating highlight reels",
        )

    # Create reel record
    reel_id = str(uuid4())
    reel_data = {
        "id": reel_id,
        "event_id": event_id,
        "query": request.query,
        "vibe": request.vibe,
        "duration_sec": request.duration,
        "status": "processing",
    }
    supabase.table("custom_reels").insert(reel_data).execute()

    # Trigger Celery task for reel generation
    from worker import generate_highlight_reel_task
    task = generate_highlight_reel_task.delay(event_id, reel_id, request.query, request.vibe, request.duration)

    return ReelResponse(
        reel_id=reel_id,
        reel_url=None,  # Will be populated when processing completes
        moments_count=0,
        total_duration=0,
        vibe=request.vibe,
        status="processing",
    )


@router.get("/{event_id}/reels")
async def list_reels(event_id: str):
    """List all generated reels for an event."""
    supabase = get_supabase()

    result = (
        supabase.table("custom_reels")
        .select("*")
        .eq("event_id", event_id)
        .order("created_at", desc=True)
        .execute()
    )

    # Convert S3 URIs to presigned URLs
    reels = result.data
    for reel in reels:
        if reel.get("output_url") and reel["output_url"].startswith("s3://"):
            try:
                bucket, key = parse_s3_uri(reel["output_url"])
                # Generate presigned URL valid for 24 hours
                reel["output_url"] = generate_presigned_download_url(bucket, key, expires_in=86400)
            except Exception as e:
                print(f"[Reels] Error generating presigned URL for reel {reel['id']}: {e}")

    return {"reels": reels}


@router.get("/{event_id}/reels/{reel_id}")
async def get_reel(event_id: str, reel_id: str):
    """Get a specific reel."""
    supabase = get_supabase()

    result = (
        supabase.table("custom_reels")
        .select("*")
        .eq("id", reel_id)
        .eq("event_id", event_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Reel not found")

    reel = result.data[0]

    # Convert S3 URI to presigned URL
    if reel.get("output_url") and reel["output_url"].startswith("s3://"):
        try:
            bucket, key = parse_s3_uri(reel["output_url"])
            # Generate presigned URL valid for 24 hours
            reel["output_url"] = generate_presigned_download_url(bucket, key, expires_in=86400)
        except Exception as e:
            print(f"[Reels] Error generating presigned URL for reel {reel['id']}: {e}")

    return reel
