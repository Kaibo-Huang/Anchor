from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from services.supabase_client import get_supabase

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

    return EventResponse(**result.data[0])


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
async def generate_video(event_id: str):
    """Generate the final video for an event."""
    supabase = get_supabase()

    event = supabase.table("events").select("*").eq("id", event_id).execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.data[0]["status"] != "analyzed":
        raise HTTPException(
            status_code=400, detail="Event must be analyzed before generating video"
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
