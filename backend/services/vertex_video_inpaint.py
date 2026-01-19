"""Vertex AI Veo 2 video inpainting service for subtle product placement.

Uses Veo 2's video inpainting capability to insert products directly into
existing video footage with a mask, creating seamless product placements
that appear as native overlays.
"""

import base64
import json
import os
import subprocess
import tempfile
import time
from typing import Literal

import httpx
from PIL import Image, ImageDraw

from config import get_settings


# ============================================================================
# VERTEX AI CLIENT SETUP
# ============================================================================

VERTEX_AI_ENDPOINT = "https://us-central1-aiplatform.googleapis.com/v1"
VEO_MODEL = "veo-2.0-generate-preview"


def get_gcp_access_token() -> str:
    """Get GCP access token using gcloud CLI or service account.

    Returns:
        Access token string for API authentication
    """
    # Try gcloud CLI first (for local development)
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: Use google-auth library with default credentials
    try:
        import google.auth
        import google.auth.transport.requests

        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token
    except Exception as e:
        raise RuntimeError(
            f"Could not obtain GCP access token. Ensure gcloud is configured "
            f"or GOOGLE_APPLICATION_CREDENTIALS is set: {e}"
        )


def get_gcp_project_id() -> str:
    """Get GCP project ID from environment or gcloud config.

    Returns:
        GCP project ID string
    """
    # First try settings (loaded from .env via pydantic)
    settings = get_settings()
    if settings.gcp_project_id:
        return settings.gcp_project_id

    # Check environment variable
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project_id:
        return project_id

    # Try gcloud config
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Try google-auth default credentials
    try:
        import google.auth
        _, project = google.auth.default()
        if project:
            return project
    except Exception:
        pass

    raise RuntimeError(
        "Could not determine GCP project ID. Set GCP_PROJECT_ID in .env "
        "or configure gcloud with: gcloud config set project YOUR_PROJECT_ID"
    )


# ============================================================================
# MASK GENERATION
# ============================================================================

PlacementPosition = Literal[
    "top_left", "top_right", "bottom_left", "bottom_right",
    "lower_third", "upper_third", "center_right", "center_left"
]


def create_placement_mask(
    width: int,
    height: int,
    position: PlacementPosition,
    mask_width_ratio: float = 0.25,
    mask_height_ratio: float = 0.20,
    padding_ratio: float = 0.03,
) -> Image.Image:
    """Create a mask image for product placement region.

    White area = where the product will be inserted
    Black area = preserved original video

    Args:
        width: Video frame width
        height: Video frame height
        position: Where to place the product
        mask_width_ratio: Width of mask as ratio of frame width
        mask_height_ratio: Height of mask as ratio of frame height
        padding_ratio: Padding from edges as ratio

    Returns:
        PIL Image with white mask on black background
    """
    # Create black background
    mask = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(mask)

    # Calculate mask dimensions
    mask_w = int(width * mask_width_ratio)
    mask_h = int(height * mask_height_ratio)
    padding_x = int(width * padding_ratio)
    padding_y = int(height * padding_ratio)

    # Calculate position coordinates
    position_coords = {
        "top_left": (padding_x, padding_y),
        "top_right": (width - mask_w - padding_x, padding_y),
        "bottom_left": (padding_x, height - mask_h - padding_y),
        "bottom_right": (width - mask_w - padding_x, height - mask_h - padding_y),
        "lower_third": (padding_x, height - int(height * 0.33)),
        "upper_third": (padding_x, int(height * 0.05)),
        "center_right": (width - mask_w - padding_x, (height - mask_h) // 2),
        "center_left": (padding_x, (height - mask_h) // 2),
    }

    x, y = position_coords.get(position, position_coords["top_right"])

    # Adjust mask size for special positions
    if position in ("lower_third", "upper_third"):
        mask_w = width - 2 * padding_x
        mask_h = int(height * 0.15)

    # Draw white rectangle (the insertion area)
    draw.rectangle([x, y, x + mask_w, y + mask_h], fill=(255, 255, 255))

    return mask


def save_mask_as_png(mask: Image.Image, output_path: str) -> str:
    """Save mask image as PNG file.

    Args:
        mask: PIL Image mask
        output_path: Where to save

    Returns:
        Path to saved mask file
    """
    mask.save(output_path, "PNG")
    return output_path


# ============================================================================
# VIDEO CLIP EXTRACTION
# ============================================================================

def extract_video_clip(
    video_path: str,
    start_sec: float,
    duration_sec: float = 8.0,  # Veo 2 requires exactly 8 seconds
    output_path: str | None = None,
) -> str:
    """Extract a short clip from video for inpainting.

    Args:
        video_path: Source video path
        start_sec: Start time in seconds
        duration_sec: Clip duration (must be 8s for Veo 2)
        output_path: Optional output path

    Returns:
        Path to extracted clip
    """
    if output_path is None:
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"clip_{int(start_sec)}_{int(time.time())}.mp4"
        )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", video_path,
        "-t", str(duration_sec),
        "-r", "24",  # Veo 2 requires 24 FPS for inpainting
        "-vf", "scale=1280:720",  # Veo 2 requires 720p resolution
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-an",  # No audio for inpainting
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg clip extraction failed: {result.stderr}")

    return output_path


def get_video_dimensions(video_path: str) -> tuple[int, int]:
    """Get video width and height.

    Args:
        video_path: Path to video file

    Returns:
        Tuple of (width, height)
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        video_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return stream["width"], stream["height"]


# ============================================================================
# GCS UPLOAD (for Vertex AI)
# ============================================================================

def upload_to_gcs(
    local_path: str,
    bucket: str,
    blob_name: str,
) -> str:
    """Upload file to Google Cloud Storage.

    Args:
        local_path: Local file path
        bucket: GCS bucket name
        blob_name: Object name in bucket

    Returns:
        GCS URI (gs://bucket/blob_name)
    """
    from google.cloud import storage

    client = storage.Client()
    bucket_obj = client.bucket(bucket)
    blob = bucket_obj.blob(blob_name)

    blob.upload_from_filename(local_path)

    return f"gs://{bucket}/{blob_name}"


def get_gcs_bucket() -> str:
    """Get GCS bucket for Vertex AI operations.

    Returns:
        Bucket name
    """
    # First try settings (loaded from .env via pydantic)
    settings = get_settings()
    if settings.gcs_bucket:
        return settings.gcs_bucket

    # Fallback to environment variable directly
    bucket = os.environ.get("GCS_BUCKET")
    if bucket:
        return bucket

    raise RuntimeError(
        "GCS_BUCKET not configured. "
        "Set GCS_BUCKET in .env or environment for video inpainting."
    )


# ============================================================================
# VERTEX AI VIDEO INPAINTING
# ============================================================================

def inpaint_product_into_video(
    video_path: str,
    product: dict,
    timestamp_sec: float,
    position: PlacementPosition = "top_right",
    duration_sec: float = 8.0,  # Veo 2 requires exactly 8 seconds
    output_bucket: str | None = None,
) -> str:
    """Insert a product into video using Vertex AI Veo 2 inpainting.

    This is the main function that:
    1. Extracts a clip from the video at the specified timestamp
    2. Creates a mask for the placement region
    3. Uploads both to GCS
    4. Calls Veo 2 inpainting API
    5. Downloads and returns the result

    Args:
        video_path: Path to source event video
        product: Product dict with title, description, image_url
        timestamp_sec: Where in the video to insert (start of placement)
        position: Where on screen to place the product
        duration_sec: How long the placement should last
        output_bucket: Optional GCS bucket for output (uses default if not specified)

    Returns:
        Path to the inpainted video clip (local file)
    """
    print(f"[Vertex AI] Starting video inpainting for {product.get('title')}")
    print(f"[Vertex AI] Position: {position}, Duration: {duration_sec}s")

    # Get GCS bucket
    bucket = output_bucket or get_gcs_bucket()
    project_id = get_gcp_project_id()

    # Step 1: Extract video clip
    print(f"[Vertex AI] Extracting clip at {timestamp_sec}s...")
    clip_path = extract_video_clip(
        video_path=video_path,
        start_sec=timestamp_sec,
        duration_sec=duration_sec,
    )

    # Step 2: Get video dimensions and create mask
    # Note: We always scale to 720p for Veo 2 inpainting
    width, height = 1280, 720
    print(f"[Vertex AI] Using fixed 720p dimensions: {width}x{height}")

    mask = create_placement_mask(
        width=width,
        height=height,
        position=position,
    )
    mask_path = os.path.join(tempfile.gettempdir(), f"mask_{int(time.time())}.png")
    save_mask_as_png(mask, mask_path)

    # Step 3: Upload to GCS
    timestamp_id = int(time.time())
    print(f"[Vertex AI] Uploading to GCS bucket: {bucket}...")

    video_gcs_uri = upload_to_gcs(
        local_path=clip_path,
        bucket=bucket,
        blob_name=f"veo-inpaint/input/video_{timestamp_id}.mp4",
    )

    mask_gcs_uri = upload_to_gcs(
        local_path=mask_path,
        bucket=bucket,
        blob_name=f"veo-inpaint/input/mask_{timestamp_id}.png",
    )

    output_gcs_uri = f"gs://{bucket}/veo-inpaint/output/{timestamp_id}/"

    print(f"[Vertex AI] Video URI: {video_gcs_uri}")
    print(f"[Vertex AI] Mask URI: {mask_gcs_uri}")

    # Step 4: Build the inpainting prompt
    prompt = build_inpainting_prompt(product, position)
    print(f"[Vertex AI] Prompt: {prompt[:150]}...")

    # Step 5: Call Vertex AI Veo 2 inpainting API
    access_token = get_gcp_access_token()

    request_body = {
        "instances": [
            {
                "prompt": prompt,
                "mask": {
                    "gcsUri": mask_gcs_uri,
                    "mimeType": "image/png",
                    "maskMode": "insert",
                },
                "video": {
                    "gcsUri": video_gcs_uri,
                    "mimeType": "video/mp4",
                },
            }
        ],
        "parameters": {
            "storageUri": output_gcs_uri,
            "sampleCount": 1,
        },
    }

    endpoint_url = (
        f"{VERTEX_AI_ENDPOINT}/projects/{project_id}/locations/us-central1/"
        f"publishers/google/models/{VEO_MODEL}:predictLongRunning"
    )

    print(f"[Vertex AI] Calling inpainting API...")

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            endpoint_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
        operation = response.json()

    print(f"[Vertex AI] Initial operation response: {operation}")
    operation_name = operation.get("name")
    print(f"[Vertex AI] Operation started: {operation_name}")

    # Check for immediate error
    if operation.get("error"):
        error = operation.get("error")
        raise RuntimeError(f"Veo inpainting request failed: {error.get('message', error)}")

    # Step 6: Poll for completion
    result = poll_operation_until_done(
        project_id=project_id,
        operation_name=operation_name,
        max_wait_sec=300,
    )

    # Step 7: Download result from GCS
    print(f"[Vertex AI] Full result: {result}")
    response_data = result.get("response", {})
    print(f"[Vertex AI] Response data: {response_data}")

    # Check for errors in the response
    if result.get("error"):
        error = result.get("error")
        raise RuntimeError(f"Veo inpainting error: {error.get('message', error)}")

    output_videos = response_data.get("videos", [])
    if not output_videos:
        # Try alternative response structures
        generated_videos = response_data.get("generatedVideos", [])
        if generated_videos:
            output_videos = generated_videos
        else:
            print(f"[Vertex AI] No videos found in response. Keys: {response_data.keys()}")
            raise RuntimeError("No output video generated by Veo inpainting")

    output_gcs_path = output_videos[0].get("gcsUri")
    print(f"[Vertex AI] Output video: {output_gcs_path}")

    # Download from GCS
    local_output = os.path.join(
        tempfile.gettempdir(),
        f"inpainted_{timestamp_id}.mp4"
    )
    download_from_gcs(output_gcs_path, local_output)

    # Cleanup temp files
    for path in [clip_path, mask_path]:
        try:
            os.remove(path)
        except OSError:
            pass

    print(f"[Vertex AI] Inpainting complete: {local_output}")
    return local_output


def build_inpainting_prompt(product: dict, position: PlacementPosition) -> str:
    """Build an effective prompt for product inpainting.

    The prompt tells Veo what to insert in the masked (white) region.

    Args:
        product: Product dict with title, description
        position: Placement position for context

    Returns:
        Prompt string
    """
    title = product.get("title", "Product")
    description = product.get("description", "")

    # Clean description
    if description:
        import re
        description = re.sub(r'<[^>]+>', '', description)[:100]

    # Position-specific styling
    position_styles = {
        "top_right": "floating product display, clean presentation",
        "top_left": "floating product display, clean presentation",
        "bottom_right": "product showcase badge, broadcast overlay style",
        "bottom_left": "product showcase badge, broadcast overlay style",
        "lower_third": "lower third product banner, TV broadcast style, professional",
        "upper_third": "header product banner, clean modern design",
        "center_right": "side panel product display, elegant floating",
        "center_left": "side panel product display, elegant floating",
    }

    style = position_styles.get(position, "floating product display")

    prompt = (
        f"Insert a {title} product advertisement. "
        f"{style}. "
        f"The product should appear as a professional broadcast overlay, "
        f"semi-transparent background, modern advertising style, "
        f"high quality product visualization, "
        f"subtle animation, premium commercial quality. "
    )

    if description:
        prompt += f"Product: {description}. "

    prompt += (
        "The product should blend naturally with the video, "
        "matching the lighting and color temperature of the scene. "
        "Professional sports broadcast sponsorship style."
    )

    return prompt


def poll_operation_until_done(
    project_id: str,
    operation_name: str,
    max_wait_sec: int = 300,
    poll_interval_sec: int = 10,
) -> dict:
    """Poll a long-running operation until completion.

    Args:
        project_id: GCP project ID
        operation_name: Full operation name from initial request
        max_wait_sec: Maximum time to wait
        poll_interval_sec: Time between polls

    Returns:
        Final operation response dict
    """
    # Extract model ID from operation name
    # Format: projects/PROJECT/locations/REGION/publishers/google/models/MODEL/operations/OP_ID
    parts = operation_name.split("/")
    model_id = parts[7] if len(parts) > 7 else VEO_MODEL

    fetch_url = (
        f"{VERTEX_AI_ENDPOINT}/projects/{project_id}/locations/us-central1/"
        f"publishers/google/models/{model_id}:fetchPredictOperation"
    )

    waited = 0
    while waited < max_wait_sec:
        access_token = get_gcp_access_token()

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                fetch_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"operationName": operation_name},
            )
            response.raise_for_status()
            result = response.json()

        if result.get("done"):
            print(f"[Vertex AI] Operation completed after {waited}s")
            # Log full result for debugging
            if result.get("error"):
                print(f"[Vertex AI] Operation error: {result.get('error')}")
            if result.get("response"):
                print(f"[Vertex AI] Response keys: {result.get('response', {}).keys()}")
            return result

        print(f"[Vertex AI] Waiting for inpainting... ({waited}s)")
        time.sleep(poll_interval_sec)
        waited += poll_interval_sec

    raise TimeoutError(f"Veo inpainting timed out after {max_wait_sec}s")


def download_from_gcs(gcs_uri: str, local_path: str) -> str:
    """Download file from GCS to local path.

    Args:
        gcs_uri: GCS URI (gs://bucket/path)
        local_path: Local destination path

    Returns:
        Local path
    """
    from google.cloud import storage

    # Parse GCS URI
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")

    path = gcs_uri[5:]  # Remove "gs://"
    bucket_name, blob_name = path.split("/", 1)

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.download_to_filename(local_path)

    return local_path


# ============================================================================
# HIGH-LEVEL INTEGRATION
# ============================================================================

def create_inpainted_placement(
    event_video_path: str,
    product: dict,
    placement: dict,
    event_type: str = "sports",
) -> str:
    """Create a single inpainted product placement.

    High-level function that handles the full workflow for one placement.

    Args:
        event_video_path: Path to the event video
        product: Product dict
        placement: Placement dict with timestamp_ms, position, duration_ms
        event_type: Event type for styling

    Returns:
        Path to inpainted video clip
    """
    timestamp_sec = placement.get("timestamp_ms", 0) / 1000
    duration_sec = placement.get("duration_ms", 8000) / 1000  # Veo 2 requires 8s
    # Force 8 seconds for Veo 2 inpainting
    duration_sec = 8.0
    position = placement.get("position", "top_right")

    # Ensure position is valid
    valid_positions = [
        "top_left", "top_right", "bottom_left", "bottom_right",
        "lower_third", "upper_third", "center_right", "center_left"
    ]
    if position not in valid_positions:
        position = "top_right"

    return inpaint_product_into_video(
        video_path=event_video_path,
        product=product,
        timestamp_sec=timestamp_sec,
        position=position,
        duration_sec=duration_sec,
    )


def create_all_inpainted_placements(
    event_video_path: str,
    products: list[dict],
    placements: list[dict],
    event_type: str = "sports",
) -> list[dict]:
    """Create all inpainted product placements for an event.

    Args:
        event_video_path: Path to the event video
        products: List of available products
        placements: List of placement dicts with timestamp_ms, position
        event_type: Event type for styling

    Returns:
        List of dicts with placement info and inpainted video paths
    """
    if not products or not placements:
        return []

    results = []

    for i, placement in enumerate(placements):
        # Cycle through products
        product = products[i % len(products)]

        try:
            inpainted_path = create_inpainted_placement(
                event_video_path=event_video_path,
                product=product,
                placement=placement,
                event_type=event_type,
            )

            results.append({
                "placement_index": i,
                "timestamp_ms": placement.get("timestamp_ms"),
                "duration_ms": placement.get("duration_ms", 4000),
                "position": placement.get("position", "top_right"),
                "product_id": product.get("id"),
                "product_title": product.get("title"),
                "inpainted_video_path": inpainted_path,
            })

        except Exception as e:
            print(f"[Vertex AI] Failed to create placement {i}: {e}")
            continue

    return results
