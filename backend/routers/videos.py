from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from services.s3_client import (
    abort_multipart_upload,
    complete_multipart_upload,
    create_multipart_upload,
    generate_presigned_chunk_url,
    generate_presigned_upload_url,
    parse_s3_uri,
)
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


# Multipart Upload Models


class MultipartUploadInitRequest(BaseModel):
    filename: str
    content_type: str = "video/mp4"
    file_size: int
    angle_type: Literal["wide", "closeup", "crowd", "goal_angle", "stage", "other"] = (
        "other"
    )


class MultipartUploadInitResponse(BaseModel):
    video_id: str
    upload_id: str
    s3_key: str
    chunk_size: int
    total_chunks: int
    use_multipart: bool
    upload_url: str | None  # For simple uploads


class ChunkUrlRequest(BaseModel):
    upload_id: str
    chunk_number: int


class ChunkUrlResponse(BaseModel):
    chunk_number: int
    upload_url: str


class CompleteMultipartRequest(BaseModel):
    upload_id: str
    parts: list[dict]  # [{"PartNumber": 1, "ETag": "..."}, ...]


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


# Multipart Upload Endpoints


@router.post(
    "/{event_id}/videos/multipart/init", response_model=MultipartUploadInitResponse
)
async def init_multipart_upload(
    event_id: str, request: MultipartUploadInitRequest
):
    """Initialize a video upload (either simple or multipart based on file size)."""
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

    # Determine upload strategy
    use_multipart = request.file_size >= settings.s3_multipart_threshold

    if use_multipart:
        # Initiate multipart upload
        upload_id = create_multipart_upload(
            bucket=settings.s3_bucket,
            key=s3_key,
            content_type=request.content_type,
        )

        # Calculate chunk info
        chunk_size = settings.s3_multipart_chunk_size
        total_chunks = (request.file_size + chunk_size - 1) // chunk_size

        response = MultipartUploadInitResponse(
            video_id=video_id,
            upload_id=upload_id,
            s3_key=s3_key,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            use_multipart=True,
            upload_url=None,
        )
    else:
        # Use simple presigned URL upload
        upload_url = generate_presigned_upload_url(
            bucket=settings.s3_bucket,
            key=s3_key,
            content_type=request.content_type,
            expires_in=3600,
        )

        response = MultipartUploadInitResponse(
            video_id=video_id,
            upload_id="",
            s3_key=s3_key,
            chunk_size=0,
            total_chunks=1,
            use_multipart=False,
            upload_url=upload_url,
        )

    # Create video record with upload metadata
    video_data = {
        "id": video_id,
        "event_id": event_id,
        "original_url": f"s3://{settings.s3_bucket}/{s3_key}",
        "angle_type": request.angle_type,
        "status": "uploading",
    }
    supabase.table("videos").insert(video_data).execute()

    return response


@router.post(
    "/{event_id}/videos/{video_id}/multipart/chunk-url",
    response_model=ChunkUrlResponse,
)
async def get_chunk_upload_url(
    event_id: str, video_id: str, request: ChunkUrlRequest
):
    """Get presigned URL for uploading a specific chunk."""
    settings = get_settings()
    supabase = get_supabase()

    # Verify video exists
    video = (
        supabase.table("videos")
        .select("original_url")
        .eq("id", video_id)
        .eq("event_id", event_id)
        .execute()
    )
    if not video.data:
        raise HTTPException(status_code=404, detail="Video not found")

    # Extract S3 key from original_url
    original_url = video.data[0]["original_url"]
    _, s3_key = parse_s3_uri(original_url)

    # Generate presigned URL for this chunk
    upload_url = generate_presigned_chunk_url(
        bucket=settings.s3_bucket,
        key=s3_key,
        upload_id=request.upload_id,
        part_number=request.chunk_number,
        expires_in=3600,
    )

    return ChunkUrlResponse(chunk_number=request.chunk_number, upload_url=upload_url)


@router.post("/{event_id}/videos/{video_id}/multipart/complete")
async def complete_multipart(
    event_id: str, video_id: str, request: CompleteMultipartRequest
):
    """Complete multipart upload and mark video as uploaded."""
    settings = get_settings()
    supabase = get_supabase()

    # Verify video exists
    video = (
        supabase.table("videos")
        .select("original_url")
        .eq("id", video_id)
        .eq("event_id", event_id)
        .execute()
    )
    if not video.data:
        raise HTTPException(status_code=404, detail="Video not found")

    # Extract S3 key
    original_url = video.data[0]["original_url"]
    _, s3_key = parse_s3_uri(original_url)

    # Complete multipart upload
    complete_multipart_upload(
        bucket=settings.s3_bucket,
        key=s3_key,
        upload_id=request.upload_id,
        parts=request.parts,
    )

    # Mark video as uploaded
    supabase.table("videos").update({"status": "uploaded"}).eq("id", video_id).execute()

    return {"message": "Multipart upload completed", "video_id": video_id}


@router.post("/{event_id}/videos/{video_id}/multipart/abort")
async def abort_multipart(event_id: str, video_id: str, upload_id: str):
    """Abort multipart upload and clean up."""
    settings = get_settings()
    supabase = get_supabase()

    # Verify video exists
    video = (
        supabase.table("videos")
        .select("original_url")
        .eq("id", video_id)
        .eq("event_id", event_id)
        .execute()
    )
    if not video.data:
        raise HTTPException(status_code=404, detail="Video not found")

    # Extract S3 key
    original_url = video.data[0]["original_url"]
    _, s3_key = parse_s3_uri(original_url)

    # Abort multipart upload
    abort_multipart_upload(
        bucket=settings.s3_bucket,
        key=s3_key,
        upload_id=upload_id,
    )

    # Mark video as failed
    supabase.table("videos").update({"status": "failed"}).eq("id", video_id).execute()

    return {"message": "Multipart upload aborted", "video_id": video_id}


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
