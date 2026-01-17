from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from services.s3_client import generate_presigned_upload_url
from services.supabase_client import get_supabase

router = APIRouter()


class UploadRequest(BaseModel):
    filename: str
    content_type: str = "video/mp4"
    angle_type: Literal["wide", "closeup", "crowd", "goal_angle", "stage", "other"] = (
        "other"
    )


class UploadResponse(BaseModel):
    video_id: str
    upload_url: str
    s3_key: str


class MusicUploadRequest(BaseModel):
    filename: str
    content_type: str = "audio/mpeg"


class MusicUploadResponse(BaseModel):
    upload_url: str
    s3_key: str


@router.post("/{event_id}/videos", response_model=UploadResponse)
async def get_video_upload_url(event_id: str, request: UploadRequest):
    """Get presigned S3 URL for video upload."""
    settings = get_settings()
    supabase = get_supabase()

    # Verify event exists
    event = supabase.table("events").select("id").eq("id", event_id).execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    # Generate video ID and S3 key
    video_id = str(uuid4())
    ext = request.filename.split(".")[-1] if "." in request.filename else "mp4"
    s3_key = f"events/{event_id}/videos/{video_id}.{ext}"

    # Generate presigned URL
    upload_url = generate_presigned_upload_url(
        bucket=settings.s3_bucket,
        key=s3_key,
        content_type=request.content_type,
        expires_in=3600,
    )

    # Create video record
    video_data = {
        "id": video_id,
        "event_id": event_id,
        "original_url": f"s3://{settings.s3_bucket}/{s3_key}",
        "angle_type": request.angle_type,
        "status": "uploading",
    }
    supabase.table("videos").insert(video_data).execute()

    return UploadResponse(video_id=video_id, upload_url=upload_url, s3_key=s3_key)


@router.post("/{event_id}/videos/{video_id}/uploaded")
async def mark_video_uploaded(event_id: str, video_id: str):
    """Mark video as uploaded (called after S3 upload completes)."""
    supabase = get_supabase()

    result = (
        supabase.table("videos")
        .update({"status": "uploaded"})
        .eq("id", video_id)
        .eq("event_id", event_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Video not found")

    return {"message": "Video marked as uploaded", "video_id": video_id}


@router.get("/{event_id}/videos")
async def list_videos(event_id: str):
    """List all videos for an event."""
    supabase = get_supabase()

    result = supabase.table("videos").select("*").eq("event_id", event_id).execute()

    return {"videos": result.data}


@router.post("/{event_id}/music/upload", response_model=MusicUploadResponse)
async def get_music_upload_url(event_id: str, request: MusicUploadRequest):
    """Get presigned S3 URL for music upload."""
    settings = get_settings()
    supabase = get_supabase()

    # Verify event exists
    event = supabase.table("events").select("id").eq("id", event_id).execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    # Generate S3 key
    ext = request.filename.split(".")[-1] if "." in request.filename else "mp3"
    s3_key = f"events/{event_id}/music/track.{ext}"

    # Generate presigned URL
    upload_url = generate_presigned_upload_url(
        bucket=settings.s3_bucket,
        key=s3_key,
        content_type=request.content_type,
        expires_in=3600,
    )

    # Update event with music URL
    music_url = f"s3://{settings.s3_bucket}/{s3_key}"
    supabase.table("events").update({"music_url": music_url}).eq(
        "id", event_id
    ).execute()

    return MusicUploadResponse(upload_url=upload_url, s3_key=s3_key)


@router.post("/{event_id}/music/analyze")
async def analyze_music(event_id: str):
    """Analyze uploaded music for beats and tempo."""
    supabase = get_supabase()

    event = supabase.table("events").select("music_url").eq("id", event_id).execute()
    if not event.data or not event.data[0].get("music_url"):
        raise HTTPException(status_code=400, detail="No music uploaded")

    # Trigger Celery task for music analysis
    from worker import analyze_music_task
    task = analyze_music_task.delay(event_id)

    return {"message": "Music analysis started", "event_id": event_id, "task_id": task.id}
