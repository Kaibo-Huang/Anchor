"""Google Veo service for AI-generated product videos with strong prompting."""

import os
import re
import time
import tempfile
from typing import Literal

from google import genai
from google.genai import types

from config import get_settings


def get_veo_client():
    """Get Google GenAI client for Veo using Vertex AI."""
    settings = get_settings()
    # Use Vertex AI with OAuth2 credentials (not API key)
    # Requires GOOGLE_APPLICATION_CREDENTIALS env var to be set
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_region or "us-central1",
    )


# ============================================================================
# PROMPT ENGINEERING FOR BRAND ADS
# ============================================================================

# Style templates for different product categories
PRODUCT_STYLE_TEMPLATES = {
    "apparel": {
        "visual": "fabric texture visible, natural movement, professional fashion photography style",
        "lighting": "soft diffused lighting with subtle rim light",
        "motion": "gentle fabric movement, smooth reveal",
    },
    "electronics": {
        "visual": "sleek product design, premium materials, tech-forward aesthetic",
        "lighting": "dramatic lighting with reflections, dark background gradient",
        "motion": "smooth 360 rotation, interface animations",
    },
    "sports": {
        "visual": "dynamic action context, athlete in motion, energy and power",
        "lighting": "high contrast, dramatic shadows, stadium-style lighting",
        "motion": "fast cuts, slow-motion impact moments, kinetic energy",
    },
    "food": {
        "visual": "appetizing presentation, steam and texture, fresh ingredients visible",
        "lighting": "warm golden hour lighting, soft shadows",
        "motion": "smooth pour or reveal, macro detail shots",
    },
    "beauty": {
        "visual": "luxurious texture, product application, glowing skin",
        "lighting": "soft beauty lighting, no harsh shadows",
        "motion": "elegant slow motion, graceful application",
    },
    "default": {
        "visual": "clean product presentation, professional quality",
        "lighting": "balanced three-point lighting setup",
        "motion": "smooth camera movement, professional reveal",
    },
}

# Event context modifiers to match surrounding footage
EVENT_CONTEXT_MODIFIERS = {
    "sports": {
        "energy": "high energy, dynamic, competitive spirit",
        "colors": "vibrant team colors, stadium atmosphere",
        "audience": "fans cheering, crowd energy",
    },
    "ceremony": {
        "energy": "elegant, sophisticated, celebratory",
        "colors": "formal colors, gold accents, premium feel",
        "audience": "distinguished audience, formal attire",
    },
    "performance": {
        "energy": "artistic, expressive, creative",
        "colors": "stage lighting, dramatic color palette",
        "audience": "engaged audience, artistic appreciation",
    },
}

# Camera motion templates for seamless transitions
CAMERA_MOTION_TEMPLATES = {
    "fade": {
        "motion": "static shot with subtle depth movement",
        "transition_hint": "fade from black, fade to black",
    },
    "pan_left": {
        "motion": "smooth camera pan from right to left",
        "transition_hint": "continuous motion matching left pan",
    },
    "pan_right": {
        "motion": "smooth camera pan from left to right",
        "transition_hint": "continuous motion matching right pan",
    },
    "zoom_in": {
        "motion": "slow push in, focus pull to product",
        "transition_hint": "zoom continuation from wide to close",
    },
    "zoom_out": {
        "motion": "slow pull out revealing product in context",
        "transition_hint": "zoom continuation from close to wide",
    },
    "orbit": {
        "motion": "smooth orbital camera movement around product",
        "transition_hint": "continuous circular motion",
    },
}


def detect_product_category(product: dict) -> str:
    """Detect product category from title and description.

    Args:
        product: Product dict with title, description

    Returns:
        Category key matching PRODUCT_STYLE_TEMPLATES
    """
    text = f"{product.get('title', '')} {product.get('description', '')}".lower()

    category_keywords = {
        "apparel": ["shirt", "jersey", "pants", "jacket", "dress", "hoodie", "shorts", "wear", "clothing"],
        "electronics": ["phone", "laptop", "camera", "headphone", "speaker", "watch", "device", "tech"],
        "sports": ["ball", "racket", "bat", "glove", "cleats", "equipment", "gear", "fitness"],
        "food": ["snack", "drink", "food", "beverage", "coffee", "tea", "protein", "nutrition"],
        "beauty": ["skincare", "makeup", "cream", "serum", "beauty", "cosmetic", "lotion"],
    }

    for category, keywords in category_keywords.items():
        if any(kw in text for kw in keywords):
            return category

    return "default"


def build_product_ad_prompt(
    product: dict,
    event_type: str = "sports",
    transition_style: str = "fade",
    sponsor_name: str | None = None,
    preceding_scene: str | None = None,
) -> str:
    """Build a comprehensive prompt for product ad generation.

    Creates a detailed, high-quality prompt that produces native-feeling
    ad content that seamlessly integrates with event footage.

    Args:
        product: Product dict with title, description, price, image_url
        event_type: Type of event for context matching
        transition_style: Camera motion style to match transitions
        sponsor_name: Optional sponsor name to incorporate branding
        preceding_scene: Description of the scene before the ad (for context)

    Returns:
        Detailed prompt string for Veo generation
    """
    # Get style templates
    category = detect_product_category(product)
    style = PRODUCT_STYLE_TEMPLATES.get(category, PRODUCT_STYLE_TEMPLATES["default"])
    context = EVENT_CONTEXT_MODIFIERS.get(event_type, EVENT_CONTEXT_MODIFIERS["sports"])
    motion = CAMERA_MOTION_TEMPLATES.get(transition_style, CAMERA_MOTION_TEMPLATES["fade"])

    # Clean product description
    description = product.get("description", "")
    if description:
        description = re.sub(r'<[^>]+>', '', description)  # Remove HTML
        description = description[:150]  # Limit length

    # Build prompt - optimized for green screen compositing
    prompt = f"""Professional product commercial: {product['title']} on solid bright green (#00FF00) chroma key background.

PRODUCT PRESENTATION:
- {style["visual"]}
- {style["lighting"]}
- {motion["motion"]}

VISUAL STYLE:
- Energy: {context['energy']} atmosphere
- Color reflections on product: {context['colors']} tones
- {style["motion"]}

TECHNICAL REQUIREMENTS:
- Background: SOLID UNIFORM BRIGHT GREEN (#00FF00) - essential for chroma key
- No shadows cast on background - only on product
- Product centered, filling 50-70% of frame
- 4K ultra high definition, broadcast-ready quality
- {motion['transition_hint']}"""

    if description:
        prompt += f"\n\nProduct details: {description}"

    if sponsor_name:
        prompt += f"\n\nSubtle {sponsor_name} branding may appear on product"

    if preceding_scene:
        prompt += f"\n\nDesigned to follow: {preceding_scene}"

    prompt += "\n\nCRITICAL: The green background must be perfectly uniform for chroma key extraction - no gradients, no shadows on background."

    return prompt


def generate_product_video(
    product_name: str,
    product_description: str = "",
    style: Literal["showcase", "lifestyle", "action"] = "showcase",
    aspect_ratio: str = "16:9",
    duration: int = 4,
) -> str:
    """Generate an AI product video using Google Veo.

    Args:
        product_name: Name of the product
        product_description: Optional description for context
        style: Video style (showcase, lifestyle, action)
        aspect_ratio: Video aspect ratio (16:9, 9:16, 1:1)
        duration: Duration in seconds (4, 6, or 8)

    Returns:
        Path to generated video file
    """
    client = get_veo_client()

    # Build prompt based on style - optimized for green screen compositing
    style_prompts = {
        "showcase": f"Professional product commercial: {product_name} centered on solid bright green (#00FF00) chroma key background. Smooth rotating camera movement around product, professional studio lighting, 4K broadcast quality. Product fills 60% of frame, perfect for compositing.",
        "lifestyle": f"Product showcase: {product_name} on uniform bright green (#00FF00) background. Warm lighting with slight golden tones on product, subtle floating motion, cinematic quality. Clean chroma key background for compositing.",
        "action": f"Dynamic product commercial: {product_name} on pure bright green (#00FF00) chroma key background. Energetic entrance animation, product spinning or bouncing with energy, professional sports commercial lighting, 4K quality. Perfect green screen extraction.",
    }

    prompt = style_prompts.get(style, style_prompts["showcase"])
    if product_description:
        prompt += f" Product details: {product_description}."

    # Add universal green screen requirements
    prompt += " CRITICAL: Background must be solid uniform bright green (#00FF00) for chroma key - no shadows, no gradients on background."

    # Generate video
    operation = client.models.generate_videos(
        model="veo-3.1-generate-preview",
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
        ),
    )

    # Poll for completion
    max_wait = 300  # 5 minutes max
    wait_time = 0
    poll_interval = 10

    while not operation.done and wait_time < max_wait:
        time.sleep(poll_interval)
        wait_time += poll_interval
        operation = client.operations.get(operation)

    if not operation.done:
        raise TimeoutError("Video generation timed out")

    if not operation.response or not operation.response.generated_videos:
        raise ValueError("No video generated")

    # Get result
    generated_video = operation.response.generated_videos[0]

    # Save to temp file using SDK's save() method
    output_path = os.path.join(tempfile.gettempdir(), f"veo_{int(time.time())}.mp4")

    # Use the SDK's built-in save method
    generated_video.video.save(output_path)
    print(f"[Veo] Video saved to {output_path}")

    return output_path


def generate_native_ad(
    product: dict,
    event_type: str = "sports",
    transition_style: Literal["fade", "pan_left", "pan_right", "zoom_in", "zoom_out", "orbit"] = "fade",
    sponsor_name: str | None = None,
    preceding_scene: str | None = None,
    duration: int = 4,
) -> str:
    """Generate a native ad video that seamlessly integrates with event footage.

    This is the main function for generating brand ads with strong prompting
    that matches the surrounding event context.

    Args:
        product: Product dict with title, description, price, image_url
        event_type: Type of event (sports, ceremony, performance)
        transition_style: Camera motion to match surrounding footage
        sponsor_name: Optional sponsor name for branding
        preceding_scene: Description of scene before ad for continuity
        duration: Duration in seconds (4, 6, or 8)

    Returns:
        Path to generated video file
    """
    client = get_veo_client()

    # Build comprehensive prompt
    prompt = build_product_ad_prompt(
        product=product,
        event_type=event_type,
        transition_style=transition_style,
        sponsor_name=sponsor_name,
        preceding_scene=preceding_scene,
    )

    print(f"[Veo] Generating ad for {product['title']}")
    print(f"[Veo] Prompt: {prompt[:200]}...")

    # Generate video
    operation = client.models.generate_videos(
        model="veo-3.1-generate-preview",
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio="16:9",
        ),
    )

    # Poll for completion with progress updates
    max_wait = 300
    wait_time = 0
    poll_interval = 10

    while not operation.done and wait_time < max_wait:
        time.sleep(poll_interval)
        wait_time += poll_interval
        operation = client.operations.get(operation)
        print(f"[Veo] Waiting for generation... ({wait_time}s)")

    if not operation.done:
        raise TimeoutError(f"Video generation timed out after {max_wait}s")

    if not operation.response or not operation.response.generated_videos:
        raise ValueError("No video generated by Veo")

    # Get result
    generated_video = operation.response.generated_videos[0]

    # Save to temp file using SDK's save() method
    output_path = os.path.join(tempfile.gettempdir(), f"veo_ad_{int(time.time())}.mp4")

    # Use the SDK's built-in save method
    generated_video.video.save(output_path)
    print(f"[Veo] Generated ad saved to {output_path}")

    return output_path


def generate_ads_for_slots(
    products: list[dict],
    ad_slots: list[dict],
    event_type: str = "sports",
    sponsor_name: str | None = None,
    video_analysis: dict | None = None,
) -> list[dict]:
    """Generate Veo ads for all ad slots using available products.

    Distributes products across ad slots and generates native ads
    with appropriate context for each slot.

    Args:
        products: List of Shopify products
        ad_slots: List of ad slots from timeline with timestamp_ms
        event_type: Event type for context matching
        sponsor_name: Optional sponsor name
        video_analysis: Optional TwelveLabs analysis for scene context

    Returns:
        List of dicts with slot info and generated video path
    """
    if not products or not ad_slots:
        return []

    generated_ads = []

    # Cycle through products for each slot
    for i, slot in enumerate(ad_slots):
        product = products[i % len(products)]

        # Determine transition style based on slot position
        # First and last slots use fades, middle slots use dynamic transitions
        if i == 0:
            transition_style = "fade"
        elif i == len(ad_slots) - 1:
            transition_style = "fade"
        else:
            # Alternate between dynamic transitions
            transitions = ["pan_right", "zoom_in", "orbit"]
            transition_style = transitions[i % len(transitions)]

        # Get preceding scene context from analysis if available
        preceding_scene = None
        if video_analysis:
            # Find scene before this ad slot
            slot_time = slot["timestamp_ms"] / 1000
            for scene in video_analysis.get("scenes", []):
                if scene.get("end_time", 0) <= slot_time < scene.get("end_time", 0) + 2:
                    preceding_scene = scene.get("description", "")
                    break

        try:
            ad_path = generate_native_ad(
                product=product,
                event_type=event_type,
                transition_style=transition_style,
                sponsor_name=sponsor_name,
                preceding_scene=preceding_scene,
                duration=4,
            )

            generated_ads.append({
                "slot_index": i,
                "timestamp_ms": slot["timestamp_ms"],
                "duration_ms": slot.get("duration_ms", 4000),
                "product_id": product.get("id"),
                "product_title": product.get("title"),
                "video_path": ad_path,
                "transition_style": transition_style,
            })

        except Exception as e:
            print(f"[Veo] Failed to generate ad for slot {i}: {e}")
            continue

    return generated_ads


def color_grade_to_match(
    ad_video_path: str,
    reference_video_path: str,
    output_path: str,
) -> str:
    """Color grade an ad video to match reference event footage.

    Extracts color characteristics from reference and applies to ad
    for seamless visual integration.

    Args:
        ad_video_path: Path to Veo-generated ad
        reference_video_path: Path to event footage for color reference
        output_path: Output path for graded video

    Returns:
        Path to color-graded video
    """
    import ffmpeg

    # Extract color stats from reference (simplified approach)
    # In production, could use more sophisticated color matching

    try:
        # Apply subtle color adjustment to match event footage
        # This adjusts brightness, contrast, and saturation to blend better
        (
            ffmpeg
            .input(ad_video_path)
            .filter("eq", brightness=0.02, contrast=1.05, saturation=1.05)
            .filter("colorbalance", rs=0.05, gs=0, bs=-0.05)  # Slight warm shift
            .output(output_path, vcodec="libx264", acodec="copy", crf=18)
            .overwrite_output()
            .run(quiet=True)
        )

        return output_path

    except Exception as e:
        print(f"[Veo] Color grading failed: {e}, using original")
        # Fall back to copying original
        import shutil
        shutil.copy(ad_video_path, output_path)
        return output_path


# Legacy function for backwards compatibility
def generate_ad_video(
    product: dict,
    transition_style: Literal["fade", "pan", "zoom"] = "fade",
    sponsor_name: str = None,
) -> str:
    """Generate an ad video for a Shopify product (legacy interface).

    Args:
        product: Product dict with title, description, image_url
        transition_style: Style to match surrounding footage
        sponsor_name: Optional sponsor name to include

    Returns:
        Path to generated video file
    """
    # Map legacy transition styles to new ones
    style_map = {
        "fade": "fade",
        "pan": "pan_right",
        "zoom": "zoom_in",
    }

    return generate_native_ad(
        product=product,
        event_type="sports",
        transition_style=style_map.get(transition_style, "fade"),
        sponsor_name=sponsor_name,
    )


def color_grade_video(
    video_path: str,
    reference_path: str,
    output_path: str,
) -> None:
    """Color grade a video to match reference footage (legacy interface)."""
    color_grade_to_match(video_path, reference_path, output_path)


# ============================================================================
# IMAGE-CONDITIONED VEO GENERATION (for scene-matched overlays)
# ============================================================================

def generate_scene_matched_product_video(
    product: dict,
    reference_frame_path: str,
    scene_context: dict,
    style: str = "floating",
    duration: int = 4,
) -> str:
    """Generate a product video using a reference frame for scene matching.

    Uses Veo's image-to-video capability to generate product content that
    matches the visual style of the reference frame from the event footage.

    Args:
        product: Product dict with title, description, image_url
        reference_frame_path: Path to frame extracted from event video
        scene_context: Detailed scene analysis from Gemini
        style: Placement style (floating, showcase, dynamic, etc.)
        duration: Duration in seconds

    Returns:
        Path to generated video file
    """
    from services.gemini_service import build_veo_prompt_from_scene_analysis

    client = get_veo_client()

    # Build the rich prompt from scene analysis
    prompt = build_veo_prompt_from_scene_analysis(
        scene_analysis=scene_context,
        product=product,
        style=style,
    )

    print(f"[Veo] Generating scene-matched video for {product.get('title')}")
    print(f"[Veo] Using reference frame: {reference_frame_path}")
    print(f"[Veo] Prompt preview: {prompt[:300]}...")

    try:
        # Load reference frame using the SDK's from_file method (requires keyword arg)
        reference_image = types.Image.from_file(location=reference_frame_path)

        # Try image-to-video generation (Veo 3.1 supports this)
        # Note: enhance_prompt is not supported for image-conditioned generation
        operation = client.models.generate_videos(
            model="veo-3.1-generate-preview",
            prompt=prompt,
            image=reference_image,
            config=types.GenerateVideosConfig(
                aspect_ratio="16:9",
            ),
        )
        print("[Veo] Using image-conditioned generation with reference frame")

    except Exception as e:
        print(f"[Veo] Image-conditioned generation not available: {e}")
        print("[Veo] Falling back to text-only generation with enhanced prompt")

        # Enhance prompt for text-only generation - emphasize green screen quality
        enhanced_prompt = f"""{prompt}

CRITICAL FOR TEXT-ONLY GENERATION:
- The background MUST be solid, uniform, bright green (#00FF00) - this is essential
- No background variations, shadows, or gradients - pure flat green
- Product should be the ONLY non-green element in the frame
- Ensure perfect chroma key extraction will be possible
- Professional TV commercial quality, 4K sharp"""

        # Fallback to text-only with enhanced prompt
        operation = client.models.generate_videos(
            model="veo-3.1-generate-preview",
            prompt=enhanced_prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio="16:9",
            ),
        )
        print(f"[Veo] Enhanced prompt length: {len(enhanced_prompt)} chars")

    # Poll for completion
    max_wait = 300
    wait_time = 0
    poll_interval = 10

    while not operation.done and wait_time < max_wait:
        time.sleep(poll_interval)
        wait_time += poll_interval
        operation = client.operations.get(operation)
        print(f"[Veo] Waiting for scene-matched generation... ({wait_time}s)")

    if not operation.done:
        raise TimeoutError(f"Video generation timed out after {max_wait}s")

    if not operation.response or not operation.response.generated_videos:
        raise ValueError("No video generated by Veo")

    # Get result
    generated_video = operation.response.generated_videos[0]

    # Save to temp file using SDK's save() method
    output_path = os.path.join(
        tempfile.gettempdir(),
        f"veo_scene_matched_{int(time.time())}.mp4"
    )

    # Use the SDK's built-in save method
    generated_video.video.save(output_path)
    print(f"[Veo] Scene-matched video saved: {output_path}")
    return output_path


def generate_contextual_product_overlay(
    product: dict,
    event_video_path: str,
    timestamp_sec: float,
    style: str = "floating",
    duration: int = 4,
) -> str:
    """Full pipeline: analyze scene, get reference frame, generate matched video.

    This is the HIGH-LEVEL function that combines:
    1. Frame extraction from event video
    2. Gemini scene analysis for rich context
    3. Veo generation with reference frame + context

    Args:
        product: Product dict with title, description, image_url
        event_video_path: Path to event video file
        timestamp_sec: Where to extract reference frame (placement time)
        style: Placement style
        duration: Duration in seconds

    Returns:
        Path to generated product overlay video
    """
    from services.gemini_service import (
        analyze_scene_for_veo_context,
        get_reference_frame_for_veo,
    )

    print(f"[Veo] Generating contextual overlay for {product.get('title')} at {timestamp_sec}s")

    # Step 1: Analyze scene with Gemini (using multiple frames)
    scene_context = analyze_scene_for_veo_context(
        video_path=event_video_path,
        timestamp_sec=timestamp_sec,
        num_frames=3,  # More frames = better analysis
    )

    # Step 2: Get single reference frame for Veo
    frame_path, _ = get_reference_frame_for_veo(
        video_path=event_video_path,
        timestamp_sec=timestamp_sec,
    )

    if not frame_path:
        print("[Veo] Could not extract reference frame, using standard generation")
        return generate_native_ad(
            product=product,
            event_type="sports",
            transition_style="fade",
            duration=duration,
        )

    try:
        # Step 3: Generate scene-matched video
        result = generate_scene_matched_product_video(
            product=product,
            reference_frame_path=frame_path,
            scene_context=scene_context,
            style=style,
            duration=duration,
        )

        return result

    finally:
        # Cleanup reference frame
        try:
            os.remove(frame_path)
        except OSError:
            pass
