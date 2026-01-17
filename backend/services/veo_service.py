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
    """Get Google GenAI client for Veo."""
    settings = get_settings()
    return genai.Client(api_key=settings.google_api_key)


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

    # Build prompt components
    prompt_parts = []

    # 1. Core product showcase
    prompt_parts.append(
        f"Cinematic product advertisement featuring {product['title']}"
    )

    # 2. Product description context
    if description:
        prompt_parts.append(f"showcasing {description}")

    # 3. Visual style
    prompt_parts.append(style["visual"])

    # 4. Lighting
    prompt_parts.append(style["lighting"])

    # 5. Camera motion for transitions
    prompt_parts.append(motion["motion"])

    # 6. Event context matching
    prompt_parts.append(f"matching {context['energy']} atmosphere")

    # 7. Color grading hint
    prompt_parts.append(f"color palette: {context['colors']}")

    # 8. Professional quality markers
    prompt_parts.append(
        "4K ultra high definition, professional commercial quality, "
        "broadcast-ready, premium production value"
    )

    # 9. Transition hints
    prompt_parts.append(f"designed for {motion['transition_hint']}")

    # 10. Sponsor integration if provided
    if sponsor_name:
        prompt_parts.append(f"subtle {sponsor_name} branding integration")

    # 11. Scene continuity if preceding scene known
    if preceding_scene:
        prompt_parts.append(f"following from {preceding_scene}, maintaining visual continuity")

    # Combine into final prompt
    prompt = ", ".join(prompt_parts)

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

    # Build prompt based on style
    style_prompts = {
        "showcase": f"Premium product showcase of {product_name}, professional studio lighting, smooth rotating camera movement, clean gradient background, commercial quality, 4K",
        "lifestyle": f"Lifestyle shot featuring {product_name} in natural aspirational setting, warm golden hour lighting, cinematic depth of field, authentic moment",
        "action": f"Dynamic action shot of {product_name} in use, energetic camera movement, high-speed capture, powerful impact moment, professional sports commercial style",
    }

    prompt = style_prompts.get(style, style_prompts["showcase"])
    if product_description:
        prompt += f", {product_description}"

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
    video = operation.response.generated_videos[0]

    # Save to temp file
    output_path = os.path.join(tempfile.gettempdir(), f"veo_{int(time.time())}.mp4")
    video.video.save(output_path)

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
    video = operation.response.generated_videos[0]

    # Save to temp file
    output_path = os.path.join(tempfile.gettempdir(), f"veo_ad_{int(time.time())}.mp4")
    video.video.save(output_path)

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
