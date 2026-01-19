"""Gemini Vision service for video analysis and product matching."""

import base64
import os
import subprocess
import tempfile
from typing import Literal

from google import genai
from google.genai import types

from config import get_settings


AngleType = Literal["wide", "closeup", "crowd", "goal_angle", "stage", "other"]

VALID_ANGLES = ["wide", "closeup", "crowd", "goal_angle", "stage", "other"]

ANGLE_CLASSIFICATION_PROMPT = """Analyze this video frame and classify the camera shot type.

Options:
- wide: Wide shot showing the full scene, sports field, stage, venue, or large area
- closeup: Close-up shot focused on a person's face, hands, or specific small detail
- crowd: Shot primarily showing the audience, spectators, or a group of people watching
- goal_angle: Shot positioned near a goal, net, basket, or specific target/scoring area
- stage: Shot of a stage, podium, performance area, or presentation space
- other: None of the above clearly apply

Analyze the visual composition and respond with ONLY ONE WORD from the options above.
Do not include any explanation or punctuation."""


def get_gemini_client() -> genai.Client:
    """Get Google GenAI client for Gemini using Vertex AI."""
    settings = get_settings()
    # Use Vertex AI with OAuth2 credentials (not API key)
    # Requires GOOGLE_APPLICATION_CREDENTIALS env var to be set
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_region or "us-central1",
    )


def classify_video_angle(frame_base64: str) -> AngleType:
    """Use Gemini Vision to classify camera angle from a video frame.

    Args:
        frame_base64: Base64-encoded JPEG image of the video frame

    Returns:
        Classified angle type (one of: wide, closeup, crowd, goal_angle, stage, other)
    """
    client = get_gemini_client()

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(text=ANGLE_CLASSIFICATION_PROMPT),
                    types.Part(
                        inline_data=types.Blob(
                            mime_type="image/jpeg",
                            data=frame_base64,
                        )
                    ),
                ]
            )
        ],
    )

    result = response.text.strip().lower().replace("_", "")

    # Normalize common variations
    if result in ("wideshot", "wide_shot"):
        result = "wide"
    elif result in ("closeup", "close-up", "close_up"):
        result = "closeup"
    elif result in ("goalangle", "goal_angle", "goal"):
        result = "goal_angle"

    return result if result in VALID_ANGLES else "other"


PRODUCT_MATCH_PROMPT = """You are helping select the most appropriate product advertisement for a video.

Event Type: {event_type}
Video Themes/Content: {video_themes}

Available Products:
{products_list}

Select the product that would be MOST relevant and natural to advertise during this type of video content.
Consider:
1. Does the product relate to the event type (sports equipment for sports, formal wear for ceremonies, etc.)?
2. Would the audience of this event type be interested in this product?
3. Does the product match the energy/tone of the video content?

Respond with ONLY the product ID number (e.g., "1" or "3"). No explanation."""


def match_product_to_video(
    products: list[dict],
    event_type: str,
    video_themes: list[str] | None = None,
) -> dict | None:
    """Use Gemini to select the best-fitting product for a video.

    Args:
        products: List of product dicts with id, title, description, price, image_url
        event_type: Type of event (sports, ceremony, performance, etc.)
        video_themes: Optional list of themes/topics detected in the video

    Returns:
        The selected product dict, or None if no products available
    """
    if not products:
        return None

    if len(products) == 1:
        return products[0]

    client = get_gemini_client()

    # Build products list for prompt
    products_list = "\n".join([
        f"{i + 1}. {p['title']} - {p.get('description', 'No description')[:100]}... (${p.get('price', '0.00')})"
        for i, p in enumerate(products)
    ])

    themes_str = ", ".join(video_themes) if video_themes else "general content"

    prompt = PRODUCT_MATCH_PROMPT.format(
        event_type=event_type,
        video_themes=themes_str,
        products_list=products_list,
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        )

        result = response.text.strip()
        # Extract number from response
        product_index = int("".join(c for c in result if c.isdigit())) - 1

        if 0 <= product_index < len(products):
            return products[product_index]
    except (ValueError, IndexError):
        pass

    # Fallback to first product if parsing fails
    return products[0]


# ============================================================================
# FRAME EXTRACTION
# ============================================================================

def extract_frames_at_timestamp(
    video_path: str,
    timestamp_sec: float,
    num_frames: int = 3,
    spread_sec: float = 0.5,
) -> list[str]:
    """Extract frames from video at and around a specific timestamp.

    Args:
        video_path: Path to video file
        timestamp_sec: Center timestamp to extract frames from
        num_frames: Number of frames to extract (spread around timestamp)
        spread_sec: How many seconds to spread frames across

    Returns:
        List of paths to extracted frame images (JPEG)
    """
    frame_paths = []

    # Calculate timestamps for each frame
    if num_frames == 1:
        timestamps = [timestamp_sec]
    else:
        start = max(0, timestamp_sec - spread_sec / 2)
        step = spread_sec / (num_frames - 1)
        timestamps = [start + i * step for i in range(num_frames)]

    for i, ts in enumerate(timestamps):
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"frame_{int(timestamp_sec)}_{i}.jpg"
        )

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(ts),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",  # High quality JPEG
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and os.path.exists(output_path):
            frame_paths.append(output_path)

    return frame_paths


def load_frame_as_base64(frame_path: str) -> str:
    """Load a frame image as base64 string.

    Args:
        frame_path: Path to JPEG frame

    Returns:
        Base64-encoded image data
    """
    with open(frame_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ============================================================================
# SCENE ANALYSIS FOR VEO CONTEXT
# ============================================================================

SCENE_ANALYSIS_PROMPT = """Analyze these video frames in EXTREME DETAIL to help generate a product overlay video that seamlessly blends into this scene.

Provide a comprehensive analysis covering:

1. **VISUAL ENVIRONMENT**:
   - Location/setting (indoor/outdoor, venue type, specific features)
   - Background elements (walls, sky, crowds, equipment, scenery)
   - Depth and spatial arrangement (foreground, midground, background layers)

2. **LIGHTING CONDITIONS**:
   - Primary light source direction and type (natural, artificial, mixed)
   - Color temperature (warm/cool, specific tints like arena blue, sunset orange)
   - Contrast level and shadow characteristics
   - Any dramatic lighting effects (spotlights, lens flares, backlighting)

3. **COLOR PALETTE**:
   - Dominant colors in the scene (be VERY specific: "deep navy blue", not just "blue")
   - Secondary accent colors
   - Team/brand colors if visible
   - Overall color mood (vibrant, muted, saturated, desaturated)

4. **ACTION & ENERGY**:
   - What's happening in the scene (specific actions, movements)
   - Energy level (calm, moderate, intense, explosive)
   - Speed of motion (static, slow, moderate, fast-paced)
   - Key subjects and their positions

5. **MOOD & ATMOSPHERE**:
   - Emotional tone (celebratory, tense, peaceful, exciting)
   - Visual style (cinematic, documentary, broadcast sports, casual)
   - Production quality indicators

6. **CAMERA CHARACTERISTICS**:
   - Approximate shot type (wide, medium, close-up)
   - Camera angle (eye level, low angle, high angle, dutch)
   - Any camera motion evident (static, pan, zoom, tracking)
   - Depth of field (shallow/deep focus)

7. **OPTIMAL OVERLAY PLACEMENT**:
   - Suggested screen position for product (corner, side, lower third)
   - Visual "quiet zones" where overlay won't obstruct action
   - Timing considerations based on motion

Respond with a detailed JSON object. Be EXTREMELY SPECIFIC with colors, lighting, and mood - this will be used to generate AI video that must match perfectly."""


def analyze_scene_for_veo_context(
    video_path: str,
    timestamp_sec: float,
    num_frames: int = 3,
) -> dict:
    """Analyze video frames to generate rich context for Veo generation.

    Extracts frames at the specified timestamp and uses Gemini to analyze
    the scene in extreme detail for seamless product overlay generation.

    Args:
        video_path: Path to video file
        timestamp_sec: Timestamp to analyze
        num_frames: Number of frames to analyze (more = better context)

    Returns:
        Dict with detailed scene analysis including:
        - environment, lighting, colors, action, mood, camera, placement_recommendation
    """
    print(f"[Gemini] Analyzing scene at {timestamp_sec}s for Veo context...")

    # Extract frames
    frame_paths = extract_frames_at_timestamp(
        video_path, timestamp_sec, num_frames=num_frames, spread_sec=1.0
    )

    if not frame_paths:
        print("[Gemini] No frames extracted, returning default context")
        return _default_scene_context()

    client = get_gemini_client()

    # Build content with multiple frames
    content_parts = [types.Part(text=SCENE_ANALYSIS_PROMPT)]

    for frame_path in frame_paths:
        frame_b64 = load_frame_as_base64(frame_path)
        content_parts.append(
            types.Part(
                inline_data=types.Blob(
                    mime_type="image/jpeg",
                    data=frame_b64,
                )
            )
        )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(role="user", parts=content_parts)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        import json
        result = json.loads(response.text)
        print(f"[Gemini] Scene analysis complete: {list(result.keys())}")

        # Cleanup frames
        for fp in frame_paths:
            try:
                os.remove(fp)
            except OSError:
                pass

        return result

    except Exception as e:
        print(f"[Gemini] Scene analysis failed: {e}")
        # Cleanup frames
        for fp in frame_paths:
            try:
                os.remove(fp)
            except OSError:
                pass
        return _default_scene_context()


def _default_scene_context() -> dict:
    """Return default scene context when analysis fails."""
    return {
        "environment": {
            "setting": "indoor venue",
            "background": "crowd and arena elements",
        },
        "lighting": {
            "type": "artificial arena lighting",
            "color_temperature": "neutral white",
            "contrast": "moderate",
        },
        "colors": {
            "dominant": ["gray", "blue"],
            "accents": ["white", "red"],
            "mood": "vibrant",
        },
        "action": {
            "description": "sports event",
            "energy_level": "moderate",
            "motion_speed": "moderate",
        },
        "mood": {
            "tone": "exciting",
            "style": "broadcast sports",
        },
        "camera": {
            "shot_type": "medium",
            "angle": "eye level",
            "motion": "static",
        },
        "placement_recommendation": {
            "position": "top_right",
            "reason": "clear viewing area",
        },
    }


def build_veo_prompt_from_scene_analysis(
    scene_analysis: dict,
    product: dict,
    style: str = "floating",
) -> str:
    """Build a rich Veo prompt using detailed scene analysis.

    Creates a prompt that will generate product video matching the
    analyzed scene's lighting, colors, mood, and energy.

    Args:
        scene_analysis: Dict from analyze_scene_for_veo_context
        product: Product dict with title, description
        style: Placement style (floating, showcase, dynamic, etc.)

    Returns:
        Detailed Veo prompt string
    """
    env = scene_analysis.get("environment", {})
    lighting = scene_analysis.get("lighting", {})
    colors = scene_analysis.get("colors", {})
    action = scene_analysis.get("action", {})
    mood = scene_analysis.get("mood", {})
    camera = scene_analysis.get("camera", {})

    # Build color description
    dominant_colors = colors.get("dominant", ["blue", "gray"])
    if isinstance(dominant_colors, list):
        color_str = ", ".join(dominant_colors[:3])
    else:
        color_str = str(dominant_colors)

    accent_colors = colors.get("accents", [])
    if isinstance(accent_colors, list) and accent_colors:
        accent_str = ", ".join(accent_colors[:2])
    else:
        accent_str = "white highlights"

    # Build lighting description
    light_type = lighting.get("type", "studio lighting")
    light_temp = lighting.get("color_temperature", "neutral")

    # Build motion/energy description
    energy = action.get("energy_level", "moderate")
    motion = action.get("motion_speed", "moderate")

    # Style-specific motion
    style_motions = {
        "floating": "gentle floating motion, subtle bob up and down",
        "showcase": "smooth slow rotation, elegant reveal",
        "dynamic": "energetic entrance, quick attention-grabbing motion",
        "minimal": "subtle fade in, nearly static with gentle pulse",
        "pulse": "rhythmic pulsing glow, attention-grabbing beat",
    }

    product_motion = style_motions.get(style, style_motions["floating"])

    # Get environment details for context
    setting = env.get("setting", "sports venue")
    atmosphere = env.get("atmosphere", "energetic")

    # Construct the mega-prompt - optimized for Veo 3.1 text-only generation
    # Focus on generating a clean green-screen product video that composites well
    prompt = f"""Cinematic product commercial video: {product.get('title', 'Product')} on solid bright green chroma key background.

ABSOLUTE REQUIREMENTS:
- Background: Solid pure bright green (#00FF00) covering ENTIRE frame - no gradients, no shadows on background
- The green must be uniform, bright, and perfect for chroma key extraction

PRODUCT STYLING:
- {product.get('title')} shown with {product_motion}
- Lighting: {light_type} with {light_temp} color temperature
- Product reflects subtle {color_str} color tones to match destination footage
- {accent_str} highlights on product edges

MOTION AND ENERGY:
- {energy} energy level, {motion} motion speed
- Product enters smoothly, performs {product_motion}
- Professional broadcast commercial quality animation

MOOD: {mood.get('tone', 'exciting')}, {mood.get('style', 'professional')} - designed to fit {setting} {atmosphere} environment

Camera: Static or very subtle movement, product fills 60-70% of frame, centered.

Create a 4-second product showcase video with {product.get('title')} performing {product_motion} on a perfectly uniform bright green background, broadcast-quality commercial style that will composite seamlessly into live event footage."""

    return prompt


def get_reference_frame_for_veo(
    video_path: str,
    timestamp_sec: float,
) -> tuple[str, str]:
    """Get a reference frame for Veo image-to-video generation.

    Extracts a single high-quality frame that can be passed to Veo
    as a reference for style matching.

    Args:
        video_path: Path to video file
        timestamp_sec: Timestamp to extract frame from

    Returns:
        Tuple of (frame_path, base64_data)
    """
    frame_paths = extract_frames_at_timestamp(
        video_path, timestamp_sec, num_frames=1
    )

    if not frame_paths:
        return None, None

    frame_path = frame_paths[0]
    frame_b64 = load_frame_as_base64(frame_path)

    return frame_path, frame_b64
