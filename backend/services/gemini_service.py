"""Gemini Vision service for video analysis and product matching."""

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
    """Get Google GenAI client for Gemini."""
    settings = get_settings()
    return genai.Client(api_key=settings.google_api_key)


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
            contents=[types.Content(parts=[types.Part(text=prompt)])],
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
