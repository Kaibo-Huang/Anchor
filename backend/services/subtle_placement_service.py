"""Subtle product placement service using Veo scene-matched overlays.

Creates AI-generated product overlays that are visually matched to the
event footage. Supports multiple approaches:

1. VERTEX_AI_INPAINT (Recommended): Uses Veo 2 video inpainting via Vertex AI
   to directly insert products into the video frame with a mask. Most seamless.

2. VEO_SCENE_MATCHING: Uses Gemini scene analysis + Veo image-conditioned
   generation to create matched overlays, then composites with alpha blending.

3. IMAGE_FALLBACK: Uses animated product images as overlays. Fastest but
   least integrated visually.

Pipeline for Vertex AI inpainting:
1. Extract video clip at placement timestamp
2. Create mask for placement region (corner, lower third, etc.)
3. Upload to GCS
4. Call Veo 2 inpainting API with mask + video + prompt
5. Replace segment in final video

Pipeline for Veo scene matching:
1. Extract frames at placement timestamp
2. Analyze scene with Gemini (lighting, colors, mood, action)
3. Generate Veo product video using reference frame + rich context
4. Composite onto event footage with alpha blending
"""

import os
import time
import tempfile
from typing import Literal

import ffmpeg

from config import get_settings

# Feature flags for different placement approaches
# Priority: VERTEX_AI_INPAINT > VEO_SCENE_MATCHING > IMAGE_FALLBACK
USE_VERTEX_AI_INPAINT = True  # Try Vertex AI Veo 2 inpainting first
USE_VEO_SCENE_MATCHING = True  # Fallback to Gemini+Veo if Vertex AI fails


# ============================================================================
# PLACEMENT STYLE CONFIGURATIONS
# ============================================================================

PLACEMENT_STYLES = {
    "floating": {
        "animation": "fade=t=in:st=0:d=0.5,fade=t=out:st=3.5:d=0.5",
        "position": "corner",
        "scale": 0.35,  # Increased from 0.20 for visibility
        "description": "Gentle floating/bobbing effect",
    },
    "showcase": {
        "animation": "fade=t=in:st=0:d=0.5,fade=t=out:st=3.5:d=0.5",
        "position": "corner",
        "scale": 0.40,  # Increased from 0.25
        "description": "Clean fade in/out",
    },
    "dynamic": {
        "animation": "fade=t=in:st=0:d=0.3,fade=t=out:st=3.7:d=0.3",
        "position": "lower_third",
        "scale": 0.30,  # Increased from 0.18
        "description": "Quick dynamic appearance",
    },
    "minimal": {
        "animation": "fade=t=in:st=0:d=0.8,fade=t=out:st=3.2:d=0.8",
        "position": "corner",
        "scale": 0.25,  # Increased from 0.15
        "description": "Subtle minimal presence",
    },
    "pulse": {
        "animation": "fade=t=in:st=0:d=0.5,fade=t=out:st=3.5:d=0.5",
        "position": "corner",
        "scale": 0.35,  # Increased from 0.22
        "description": "Pulsing attention effect",
    },
}

# Position coordinates for overlay placement (x, y as expressions for FFmpeg)
POSITION_COORDS = {
    "top_left": ("30", "30"),
    "top_right": ("W-w-30", "30"),
    "bottom_left": ("30", "H-h-120"),  # Above lower third
    "bottom_right": ("W-w-30", "H-h-120"),
    "corner": ("W-w-30", "30"),  # Default: top right
    "lower_third": ("(W-w)/2", "H-h-100"),  # Centered bottom
    "side": ("W-w-20", "(H-h)/2"),  # Right side centered
}


def download_product_image(product: dict, output_path: str) -> str:
    """Download product image from URL.

    Args:
        product: Product dict with image_url
        output_path: Where to save the image

    Returns:
        Path to downloaded image
    """
    import httpx

    image_url = product.get("image_url")
    if not image_url:
        raise ValueError(f"Product {product.get('title')} has no image_url")

    print(f"[SubtlePlacement] Downloading product image: {image_url[:80]}...")

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(image_url)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            f.write(response.content)

    print(f"[SubtlePlacement] Product image saved: {output_path}")
    return output_path


def create_animated_product_overlay(
    product: dict,
    output_path: str,
    style: str = "floating",
    duration: float = 4.0,
    size: int = 300,
) -> str:
    """Create an animated product image overlay.

    Downloads the product image and creates an animated video overlay
    with the specified style (floating, pulse, fade, etc.)

    Args:
        product: Product dict with image_url, title
        output_path: Output video path
        style: Animation style from PLACEMENT_STYLES
        duration: Duration in seconds
        size: Output size in pixels (square)

    Returns:
        Path to animated overlay video (with transparency)
    """
    import subprocess

    style_config = PLACEMENT_STYLES.get(style, PLACEMENT_STYLES["floating"])

    # Download product image
    image_path = output_path.replace(".mov", "_img.png").replace(".mp4", "_img.png")
    download_product_image(product, image_path)

    print(f"[SubtlePlacement] Creating {style} animation for {product.get('title')}")

    # Create animated overlay from static image
    # Use zoompan for animation + fade for appearance
    # Output as MOV with ProRes 4444 for alpha support

    fps = 30
    total_frames = int(duration * fps)

    # SIMPLER approach that preserves alpha:
    # Don't use zoompan (it strips alpha). Instead, use a simple scale + fade
    # with a solid-color background that we can composite over the video.

    # For visibility, we'll create an overlay with a semi-transparent
    # dark background behind the product image

    filter_complex = (
        f"[0:v]scale={size}:-1:force_original_aspect_ratio=decrease,"
        f"pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:color=black@0.6,"  # Semi-transparent dark bg
        f"format=rgba,"
        f"fade=t=in:st=0:d=0.5:alpha=1,"
        f"fade=t=out:st={duration-0.5}:d=0.5:alpha=1"
    )

    # Use PNG codec for proper alpha support (more compatible than ProRes)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-filter_complex", filter_complex,
        "-t", str(duration),
        "-r", str(fps),
        "-c:v", "png",
        "-pix_fmt", "rgba",
        output_path
    ]

    print(f"[SubtlePlacement] Running FFmpeg animation...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[SubtlePlacement] FFmpeg error: {result.stderr}")
        # Fallback: try simpler approach with semi-transparent background
        cmd_simple = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", f"scale={size}:-1:force_original_aspect_ratio=decrease,pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:color=black@0.6,format=rgba",
            "-t", str(duration),
            "-r", str(fps),
            "-c:v", "png",
            "-pix_fmt", "rgba",
            output_path.replace(".mov", "_simple.mov")
        ]
        result = subprocess.run(cmd_simple, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg animation failed: {result.stderr}")
        output_path = output_path.replace(".mov", "_simple.mov")

    # Cleanup temp image
    try:
        os.remove(image_path)
    except OSError:
        pass

    print(f"[SubtlePlacement] Animated overlay created: {output_path}")
    return output_path


# ============================================================================
# VERTEX AI INPAINTING APPROACH (RECOMMENDED)
# ============================================================================

def style_to_position(style: str) -> str:
    """Convert style name to Vertex AI position.

    Args:
        style: Style name from PLACEMENT_STYLES

    Returns:
        Position name for Vertex AI mask
    """
    style_config = PLACEMENT_STYLES.get(style, PLACEMENT_STYLES["floating"])
    pos = style_config.get("position", "corner")

    # Map to Vertex AI positions
    pos_map = {
        "corner": "top_right",
        "lower_third": "lower_third",
        "side": "center_right",
        "top_left": "top_left",
        "top_right": "top_right",
        "bottom_left": "bottom_left",
        "bottom_right": "bottom_right",
    }
    return pos_map.get(pos, "top_right")


async def generate_inpainted_placement(
    event_video_path: str,
    product: dict,
    timestamp_sec: float,
    style: str = "floating",
    duration: float = 8.0,  # Veo 2 requires exactly 8 seconds
) -> str | None:
    """Generate a product placement using Vertex AI Veo 2 inpainting.

    This inserts the product DIRECTLY into the video frame using AI,
    creating the most seamless integration possible.

    Args:
        event_video_path: Path to event video
        product: Product dict with title, description
        timestamp_sec: Where to place the product (start time)
        style: Placement style (affects position)
        duration: How long the placement should last (must be 8s for Veo 2)

    Returns:
        Path to inpainted video clip, or None if inpainting failed
    """
    # Veo 2 requires exactly 8 seconds
    duration = 8.0
    
    try:
        from services.vertex_video_inpaint import inpaint_product_into_video

        position = style_to_position(style)

        print(f"[SubtlePlacement] Using Vertex AI inpainting for {product.get('title')}")
        print(f"[SubtlePlacement] Position: {position}, Duration: {duration}s")

        return inpaint_product_into_video(
            video_path=event_video_path,
            product=product,
            timestamp_sec=timestamp_sec,
            position=position,
            duration_sec=duration,
        )

    except ImportError as e:
        print(f"[SubtlePlacement] Vertex AI service not available: {e}")
        return None
    except RuntimeError as e:
        # GCS/GCP not configured
        print(f"[SubtlePlacement] Vertex AI configuration error: {e}")
        return None
    except Exception as e:
        print(f"[SubtlePlacement] Vertex AI inpainting failed: {e}")
        return None


# Legacy function for backwards compatibility
async def generate_greenscreen_product(
    product: dict,
    style: str = "floating",
    event_type: str = "sports",
    duration: int = 4,
    event_video_path: str = None,
    timestamp_sec: float = None,
) -> str:
    """Generate a product overlay using best available method.

    Priority:
    1. Vertex AI Veo 2 inpainting (if configured)
    2. Veo scene-matched generation with Gemini analysis
    3. Image-based animated overlay (fallback)

    Args:
        product: Product dict with title, image_url
        style: Placement style
        event_type: Event context
        duration: Video duration in seconds
        event_video_path: Optional path to event video for scene matching
        timestamp_sec: Optional timestamp for scene analysis

    Returns:
        Path to generated overlay video
    """
    # Priority 1: Try Vertex AI inpainting (most seamless)
    if USE_VERTEX_AI_INPAINT and event_video_path and timestamp_sec is not None:
        result = await generate_inpainted_placement(
            event_video_path=event_video_path,
            product=product,
            timestamp_sec=timestamp_sec,
            style=style,
            duration=8.0,  # Veo 2 requires exactly 8 seconds
        )
        if result:
            # Vertex AI returns an inpainted video CLIP, not an overlay
            # We need to signal this upstream so it can be spliced in
            print(f"[SubtlePlacement] ✓ Vertex AI inpainting successful")
            return result

    # Priority 2: Try Veo scene-matched generation
    if USE_VEO_SCENE_MATCHING and event_video_path and timestamp_sec is not None:
        try:
            from services.veo_service import generate_contextual_product_overlay

            print(f"[SubtlePlacement] Using Veo scene-matched generation for {product.get('title')}")
            print(f"[SubtlePlacement] Analyzing scene at {timestamp_sec}s from {event_video_path}")

            return generate_contextual_product_overlay(
                product=product,
                event_video_path=event_video_path,
                timestamp_sec=timestamp_sec,
                style=style,
                duration=duration,
            )

        except Exception as e:
            print(f"[SubtlePlacement] Veo scene matching failed: {e}")
            print("[SubtlePlacement] Falling back to image-based overlay")

    # Priority 3: Fallback to image-based animated overlay
    output_path = os.path.join(tempfile.gettempdir(), f"product_overlay_{int(time.time())}.mov")

    style_config = PLACEMENT_STYLES.get(style, PLACEMENT_STYLES["floating"])
    # Calculate size: scale * 1000 gives reasonable sizes for 1080p
    # e.g., 0.35 scale = 350px overlay
    size = int(1000 * style_config.get("scale", 0.35))

    print(f"[SubtlePlacement] Creating image overlay with size={size}px")

    return create_animated_product_overlay(
        product=product,
        output_path=output_path,
        style=style,
        duration=duration,
        size=max(250, min(500, size)),  # Clamp between 250-500px for visibility
    )


# Legacy function - no longer needed but kept for compatibility
def chromakey_and_scale(
    greenscreen_video: str,
    output_path: str,
    scale: float = 0.25,
    similarity: float = 0.3,
    blend: float = 0.1,
) -> str:
    """Scale video for overlay (chroma key no longer needed with image approach).

    Args:
        greenscreen_video: Path to overlay video
        output_path: Output path
        scale: Scale factor (unused - scaling done in creation)

    Returns:
        Path to processed video
    """
    # Just copy since we already have proper alpha from create_animated_product_overlay
    import shutil
    shutil.copy(greenscreen_video, output_path)
    print(f"[SubtlePlacement] Overlay ready: {output_path}")
    return output_path


def composite_product_overlay(
    event_video: str,
    product_overlay: str,
    output_path: str,
    start_time: float,
    duration: float = 4.0,
    position: str = "corner",
    fade_duration: float = 0.5,
) -> str:
    """Composite a chroma-keyed product video onto event footage.

    Args:
        event_video: Path to event footage
        product_overlay: Path to chroma-keyed product video (with alpha)
        output_path: Output video path
        start_time: When to show overlay (seconds)
        duration: How long to show overlay (seconds)
        position: Position key from POSITION_COORDS
        fade_duration: Fade in/out duration

    Returns:
        Path to composited video
    """
    print(f"[SubtlePlacement] Compositing overlay at {start_time}s for {duration}s, position={position}")

    x, y = POSITION_COORDS.get(position, POSITION_COORDS["corner"])
    end_time = start_time + duration

    # Use filter_complex for proper alpha handling
    # The overlay needs format=auto or format=rgb to handle alpha properly
    import subprocess

    # Build FFmpeg command manually for better control over alpha compositing
    filter_complex = (
        f"[1:v]setpts=PTS-STARTPTS,"
        f"fade=t=in:st=0:d={fade_duration}:alpha=1,"
        f"fade=t=out:st={duration - fade_duration}:d={fade_duration}:alpha=1[ovr];"
        f"[0:v][ovr]overlay={x}:{y}:enable='between(t,{start_time},{end_time})':format=auto[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", event_video,
        "-stream_loop", "-1", "-i", product_overlay,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-crf", "18",
        "-c:a", "copy",
        "-shortest",
        output_path
    ]

    print(f"[SubtlePlacement] Running FFmpeg: {' '.join(cmd[:8])}...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[SubtlePlacement] FFmpeg stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg overlay failed: {result.stderr}")

    print(f"[SubtlePlacement] Composited video saved: {output_path}")
    return output_path


def composite_multiple_placements(
    event_video: str,
    placements: list[dict],
    output_path: str,
) -> str:
    """Apply multiple product placements to event video.

    Args:
        event_video: Path to event footage
        placements: List of placement dicts with:
            - overlay_path: Path to chroma-keyed product video
            - start_time: When to show (seconds)
            - duration: How long to show (seconds)
            - position: Position key
            - fade_duration: Optional fade duration
        output_path: Output video path

    Returns:
        Path to final composited video
    """
    if not placements:
        # No placements, just copy
        import shutil
        shutil.copy(event_video, output_path)
        return output_path

    print(f"[SubtlePlacement] Applying {len(placements)} product placements")

    # Build FFmpeg command with filter_complex for proper alpha handling
    import subprocess

    # Build input arguments
    inputs = ["-i", event_video]
    for i, placement in enumerate(placements):
        inputs.extend(["-stream_loop", "-1", "-i", placement["overlay_path"]])

    # Build filter_complex string
    filter_parts = []
    current_label = "0:v"

    for i, placement in enumerate(placements):
        x, y = POSITION_COORDS.get(placement.get("position", "corner"), POSITION_COORDS["corner"])
        start_time = placement["start_time"]
        duration = placement.get("duration", 4.0)
        end_time = start_time + duration
        fade_dur = placement.get("fade_duration", 0.5)

        input_idx = i + 1  # 0 is the main video
        next_label = f"v{i}" if i < len(placements) - 1 else "outv"

        # Fade the overlay and composite
        filter_parts.append(
            f"[{input_idx}:v]setpts=PTS-STARTPTS,"
            f"fade=t=in:st=0:d={fade_dur}:alpha=1,"
            f"fade=t=out:st={duration - fade_dur}:d={fade_dur}:alpha=1[ovr{i}];"
            f"[{current_label}][ovr{i}]overlay={x}:{y}:"
            f"enable='between(t,{start_time},{end_time})':format=auto[{next_label}]"
        )
        current_label = next_label

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-crf", "18",
        "-c:a", "copy",
        "-shortest",
        output_path
    ]

    print(f"[SubtlePlacement] Running FFmpeg with {len(placements)} overlays...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[SubtlePlacement] FFmpeg stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg multi-overlay failed: {result.stderr}")

    print(f"[SubtlePlacement] Multi-placement compositing complete: {output_path}")
    return output_path


# ============================================================================
# HIGH-LEVEL API
# ============================================================================

async def create_subtle_placement(
    event_video: str,
    product: dict,
    start_time: float,
    output_path: str,
    style: str = "floating",
    position: str = "corner",
    duration: float = 4.0,
    event_type: str = "sports",
    use_scene_matching: bool = True,
    use_vertex_ai: bool = True,
) -> str:
    """Full pipeline: create product placement using best available method.

    This is the main entry point for adding a single subtle product placement.

    Methods (in priority order):
    1. Vertex AI Veo 2 inpainting - products directly in video
    2. Gemini scene analysis + Veo generation - matched overlays
    3. Image-based animated overlays - fastest fallback

    Args:
        event_video: Path to event footage
        product: Product dict with title, description
        start_time: When to show placement (seconds)
        output_path: Output video path
        style: Placement style (floating, showcase, dynamic, minimal, lifestyle)
        position: Where to place (corner, lower_third, side, top_left, etc.)
        duration: How long to show (seconds)
        event_type: Event context for style matching
        use_scene_matching: Use Gemini+Veo scene matching (default True)
        use_vertex_ai: Try Vertex AI inpainting first (default True)

    Returns:
        Path to video with product placement
    """
    print(f"[SubtlePlacement] Creating placement for {product.get('title')} at {start_time}s")
    print(f"[SubtlePlacement] Vertex AI: {use_vertex_ai}, Scene matching: {use_scene_matching}")

    # Method 1: Try Vertex AI inpainting (returns complete video segment)
    if use_vertex_ai and USE_VERTEX_AI_INPAINT:
        inpainted = await generate_inpainted_placement(
            event_video_path=event_video,
            product=product,
            timestamp_sec=start_time,
            style=style,
            duration=duration,
        )
        if inpainted:
            # Splice the inpainted segment into the video
            splice_inpainted_clips(
                event_video=event_video,
                inpainted_clips=[{
                    "inpainted_path": inpainted,
                    "start_time": start_time,
                    "duration": duration,
                }],
                output_path=output_path,
            )
            # Cleanup
            try:
                os.remove(inpainted)
            except OSError:
                pass
            return output_path

    # Method 2/3: Generate overlay (Veo scene-matched or image fallback)
    greenscreen_path = await generate_greenscreen_product(
        product=product,
        style=style,
        event_type=event_type,
        duration=int(duration) + 1,  # Slightly longer for safety
        event_video_path=event_video if use_scene_matching else None,
        timestamp_sec=start_time if use_scene_matching else None,
    )

    # Step 2: Chroma key and scale
    style_config = PLACEMENT_STYLES.get(style, PLACEMENT_STYLES["floating"])
    scale = style_config.get("scale", 0.25)

    keyed_path = os.path.join(tempfile.gettempdir(), f"keyed_{int(time.time())}.mov")
    chromakey_and_scale(greenscreen_path, keyed_path, scale=scale)

    # Step 3: Composite onto event footage
    composite_product_overlay(
        event_video=event_video,
        product_overlay=keyed_path,
        output_path=output_path,
        start_time=start_time,
        duration=duration,
        position=position,
    )

    # Cleanup temp files
    try:
        if greenscreen_path != keyed_path:
            os.remove(greenscreen_path)
        os.remove(keyed_path)
    except OSError:
        pass

    return output_path


async def create_multiple_placements(
    event_video: str,
    products: list[dict],
    placement_times: list[dict],
    output_path: str,
    event_type: str = "sports",
    use_scene_matching: bool = True,
    use_vertex_ai: bool = True,
) -> str:
    """Create multiple subtle product placements in one video.

    Uses best available method:
    1. Vertex AI Veo 2 inpainting - products directly embedded in video
    2. Gemini scene analysis + Veo - matched overlays composited
    3. Image-based overlays - fastest fallback

    Args:
        event_video: Path to event footage
        products: List of products to feature
        placement_times: List of dicts with start_time, duration, position, style
        output_path: Output video path
        event_type: Event context
        use_scene_matching: Whether to use Veo scene matching (default True)
        use_vertex_ai: Whether to try Vertex AI inpainting first (default True)

    Returns:
        Path to video with all placements
    """
    if not products or not placement_times:
        import shutil
        shutil.copy(event_video, output_path)
        return output_path

    print(f"[SubtlePlacement] Creating {len(placement_times)} placements")
    print(f"[SubtlePlacement] Vertex AI: {use_vertex_ai}, Scene matching: {use_scene_matching}")

    # Track inpainted clips and overlay placements separately
    inpainted_clips = []
    overlay_placements = []

    for i, pt in enumerate(placement_times):
        product = products[i % len(products)]
        style = pt.get("style", "floating")
        start_time = pt["start_time"]
        duration = pt.get("duration", 4.0)

        print(f"[SubtlePlacement] --- Generating placement {i+1}/{len(placement_times)} ---")
        print(f"[SubtlePlacement] Product: {product.get('title')}, Time: {start_time}s, Style: {style}")

        # Try Vertex AI inpainting first
        if use_vertex_ai and USE_VERTEX_AI_INPAINT:
            inpainted = await generate_inpainted_placement(
                event_video_path=event_video,
                product=product,
                timestamp_sec=start_time,
                style=style,
                duration=duration,
            )
            if inpainted:
                inpainted_clips.append({
                    "inpainted_path": inpainted,
                    "start_time": start_time,
                    "duration": duration,
                })
                continue  # Skip to next placement

        # Fallback: Generate overlay with scene context (if enabled)
        greenscreen_path = await generate_greenscreen_product(
            product=product,
            style=style,
            event_type=event_type,
            event_video_path=event_video if use_scene_matching else None,
            timestamp_sec=start_time if use_scene_matching else None,
        )

        style_config = PLACEMENT_STYLES.get(style, PLACEMENT_STYLES["floating"])
        keyed_path = os.path.join(tempfile.gettempdir(), f"keyed_{i}_{int(time.time())}.mov")
        chromakey_and_scale(greenscreen_path, keyed_path, scale=style_config.get("scale", 0.25))

        overlay_placements.append({
            "overlay_path": keyed_path,
            "start_time": start_time,
            "duration": duration,
            "position": pt.get("position", style_config.get("position", "corner")),
            "fade_duration": pt.get("fade_duration", 0.5),
        })

        # Cleanup green screen
        try:
            if greenscreen_path != keyed_path:
                os.remove(greenscreen_path)
        except OSError:
            pass

    # Process based on what we generated
    temp_output = output_path

    # If we have inpainted clips, splice them first
    if inpainted_clips:
        if overlay_placements:
            # We have both - splice inpainted first, then composite overlays
            temp_output = os.path.join(tempfile.gettempdir(), f"spliced_{int(time.time())}.mp4")
        splice_inpainted_clips(event_video, inpainted_clips, temp_output)

        # Cleanup inpainted clips
        for clip in inpainted_clips:
            try:
                os.remove(clip["inpainted_path"])
            except OSError:
                pass

    # If we have overlay placements, composite them
    if overlay_placements:
        input_video = temp_output if inpainted_clips else event_video
        composite_multiple_placements(input_video, overlay_placements, output_path)

        # Cleanup temp spliced video if we used it
        if inpainted_clips and temp_output != output_path:
            try:
                os.remove(temp_output)
            except OSError:
                pass

        # Cleanup keyed files
        for p in overlay_placements:
            try:
                os.remove(p["overlay_path"])
            except OSError:
                pass
    elif not inpainted_clips:
        # No placements at all, just copy
        import shutil
        shutil.copy(event_video, output_path)

    return output_path


# ============================================================================
# INPAINTED CLIP SPLICING
# ============================================================================

def splice_inpainted_clips(
    event_video: str,
    inpainted_clips: list[dict],
    output_path: str,
) -> str:
    """Splice inpainted video clips into the main event video.

    When using Vertex AI inpainting, we get back complete video segments
    with the product already integrated. This function replaces the
    corresponding segments in the original video.

    Args:
        event_video: Path to original event video
        inpainted_clips: List of dicts with:
            - inpainted_path: Path to inpainted clip
            - start_time: Where in original video (seconds)
            - duration: Length of clip (seconds)
        output_path: Output video path

    Returns:
        Path to final video with spliced clips
    """
    if not inpainted_clips:
        import shutil
        shutil.copy(event_video, output_path)
        return output_path

    import subprocess

    print(f"[SubtlePlacement] Splicing {len(inpainted_clips)} inpainted clips")

    # Sort clips by start time
    clips = sorted(inpainted_clips, key=lambda x: x["start_time"])

    # Build FFmpeg concat demuxer file
    concat_list_path = os.path.join(tempfile.gettempdir(), f"concat_{int(time.time())}.txt")
    segment_paths = []

    current_time = 0.0

    with open(concat_list_path, "w") as f:
        for i, clip in enumerate(clips):
            start = clip["start_time"]
            duration = clip["duration"]

            # If there's a gap before this clip, extract from original
            if start > current_time:
                gap_path = os.path.join(
                    tempfile.gettempdir(),
                    f"gap_{i}_{int(time.time())}.mp4"
                )
                # Extract segment from original
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(current_time),
                    "-i", event_video,
                    "-t", str(start - current_time),
                    "-c:v", "libx264", "-crf", "18",
                    "-c:a", "aac",
                    gap_path
                ]
                subprocess.run(cmd, capture_output=True)
                segment_paths.append(gap_path)
                f.write(f"file '{gap_path}'\n")

            # Add the inpainted clip
            # Need to re-encode to ensure compatibility
            compat_path = os.path.join(
                tempfile.gettempdir(),
                f"inpaint_compat_{i}_{int(time.time())}.mp4"
            )

            # Extract matching audio from original and combine with inpainted video
            cmd = [
                "ffmpeg", "-y",
                "-i", clip["inpainted_path"],
                "-ss", str(start),
                "-t", str(duration),
                "-i", event_video,
                "-map", "0:v",  # Video from inpainted
                "-map", "1:a?",  # Audio from original
                "-c:v", "libx264", "-crf", "18",
                "-c:a", "aac",
                "-shortest",
                compat_path
            ]
            subprocess.run(cmd, capture_output=True)
            segment_paths.append(compat_path)
            f.write(f"file '{compat_path}'\n")

            current_time = start + duration

        # Add remaining part of original video
        # Get original duration
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            event_video
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        total_duration = float(result.stdout.strip())

        if current_time < total_duration:
            end_path = os.path.join(
                tempfile.gettempdir(),
                f"end_{int(time.time())}.mp4"
            )
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(current_time),
                "-i", event_video,
                "-c:v", "libx264", "-crf", "18",
                "-c:a", "aac",
                end_path
            ]
            subprocess.run(cmd, capture_output=True)
            segment_paths.append(end_path)
            f.write(f"file '{end_path}'\n")

    # Concatenate all segments
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[SubtlePlacement] Concat failed: {result.stderr}")
        # Try with re-encoding
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c:v", "libx264", "-crf", "18",
            "-c:a", "aac",
            output_path
        ]
        subprocess.run(cmd, capture_output=True)

    # Cleanup temp files
    for path in segment_paths:
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        os.remove(concat_list_path)
    except OSError:
        pass

    print(f"[SubtlePlacement] Spliced video saved: {output_path}")
    return output_path


def detect_optimal_placement_times(
    video_analysis: dict,
    max_placements: int = 3,
    min_spacing_seconds: float = 60.0,
    video_duration_sec: float = None,
) -> list[dict]:
    """Detect optimal times for subtle product placements based on TwelveLabs analysis.

    Looks for moments where product placement won't distract from action:
    - Low action intensity periods
    - Scene transitions
    - Replays/slow motion
    - Post-score celebrations

    IMPORTANT: Always returns at least one placement, even if no optimal times
    are found from analysis. Falls back to fixed intervals if needed.

    Args:
        video_analysis: TwelveLabs analysis data
        max_placements: Maximum number of placements
        min_spacing_seconds: Minimum time between placements
        video_duration_sec: Total video duration (for fallback placement calculation)

    Returns:
        List of placement time dicts with start_time, duration, position, style
    """
    placements = []

    # Extract scenes/moments from analysis
    scenes = video_analysis.get("scenes", [])
    moments = video_analysis.get("moments", [])

    # Try to get video duration from analysis if not provided
    if video_duration_sec is None:
        video_duration_sec = video_analysis.get("duration", 0)
        if not video_duration_sec and scenes:
            # Estimate from last scene
            video_duration_sec = max(
                scene.get("end_time", scene.get("start_time", 0) + 10)
                for scene in scenes
            )
        if not video_duration_sec:
            # Default to 2 minutes if we can't determine
            video_duration_sec = 120.0

    # Find low-intensity periods
    candidates = []

    for scene in scenes:
        intensity = scene.get("action_intensity", 5)
        if intensity < 4:  # Low action
            candidates.append({
                "start_time": scene.get("start_time", 0),
                "score": 10 - intensity,  # Higher score for lower intensity
                "reason": "low_action",
            })

    # Find post-highlight moments (after goals, scores, etc.)
    for moment in moments:
        if moment.get("type") in ["goal", "score", "highlight", "celebration"]:
            # Place product 3-5 seconds after the highlight
            candidates.append({
                "start_time": moment.get("end_time", moment.get("time", 0)) + 3,
                "score": 8,
                "reason": "post_highlight",
            })

    # Find scene transitions
    for i, scene in enumerate(scenes[:-1]):
        transition_time = scene.get("end_time", 0)
        candidates.append({
            "start_time": transition_time,
            "score": 6,
            "reason": "scene_transition",
        })

    # Sort by score and filter by spacing
    candidates.sort(key=lambda x: x["score"], reverse=True)

    last_time = -min_spacing_seconds
    for candidate in candidates:
        if len(placements) >= max_placements:
            break

        if candidate["start_time"] - last_time >= min_spacing_seconds:
            # Determine style based on reason
            if candidate["reason"] == "post_highlight":
                style = "dynamic"
                position = "corner"
            elif candidate["reason"] == "scene_transition":
                style = "showcase"
                position = "lower_third"
            else:
                style = "floating"
                position = "corner"

            placements.append({
                "start_time": candidate["start_time"],
                "duration": 4.0,
                "position": position,
                "style": style,
            })
            last_time = candidate["start_time"]

    # ALWAYS ensure at least one placement - fallback to fixed intervals
    if not placements:
        print(f"[SubtlePlacement] No optimal times found from analysis, using fallback placements")

        # Calculate placement times based on video duration
        # Place first ad at ~20% into video, then every min_spacing_seconds
        first_placement_time = max(10.0, video_duration_sec * 0.2)  # At least 10s in, or 20% mark

        # Ensure we don't place too close to the end (leave at least 10s buffer)
        max_start_time = video_duration_sec - 10.0

        styles = ["floating", "showcase", "dynamic"]
        positions = ["corner", "lower_third", "corner"]

        current_time = first_placement_time
        placement_idx = 0

        while current_time < max_start_time and len(placements) < max_placements:
            placements.append({
                "start_time": current_time,
                "duration": 4.0,
                "position": positions[placement_idx % len(positions)],
                "style": styles[placement_idx % len(styles)],
            })
            current_time += min_spacing_seconds
            placement_idx += 1

        # If video is very short, still add at least one placement at 20% mark
        if not placements and video_duration_sec > 15:
            placements.append({
                "start_time": max(5.0, video_duration_sec * 0.2),
                "duration": 4.0,
                "position": "corner",
                "style": "floating",
            })

    # Sort by time
    placements.sort(key=lambda x: x["start_time"])

    print(f"[SubtlePlacement] Detected {len(placements)} placement times (video: {video_duration_sec:.1f}s)")
    for i, p in enumerate(placements):
        print(f"[SubtlePlacement]   #{i+1}: {p['start_time']:.1f}s - {p['style']} at {p['position']}")

    return placements
