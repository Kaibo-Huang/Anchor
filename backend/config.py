import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Keys
    twelvelabs_api_key: str = ""
    google_api_key: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket: str = ""

    # S3 Upload Optimization
    s3_use_acceleration: bool = True
    s3_multipart_threshold: int = 100 * 1024 * 1024  # 100MB threshold
    s3_multipart_chunk_size: int = 10 * 1024 * 1024  # 10MB chunks
    s3_multipart_max_concurrency: int = 4  # Max parallel chunk uploads

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Shopify
    shopify_api_key: str = ""
    shopify_api_secret: str = ""
    shopify_api_version: str = "2024-01"

    # Encryption
    encryption_key: str = ""

    # URLs
    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


class VideoConfig:
    """Tunable thresholds for video processing."""

    # Ad Detection
    AD_SCORE_THRESHOLD = 70
    AD_MIN_SPACING_MS = 45000
    AD_MAX_PER_4MIN = 1
    AD_WEIGHT_ACTION = 40
    AD_WEIGHT_AUDIO = 25
    AD_PENALTY_KEY_MOMENT = 0.3
    AD_PENALTY_SPEECH = 0.5

    # Zoom
    ZOOM_MIN_ACTION = 8
    ZOOM_MIN_SPACING_SEC = 10
    ZOOM_FACTOR_HIGH = 2.5
    ZOOM_FACTOR_MED = 1.8

    # Angle Switching
    MIN_ANGLE_DURATION_MS = 2000

    # Timeline Duration Limits
    MAX_TOTAL_DURATION_MS = 300000      # 5 minutes max output
    MIN_SEGMENT_DURATION_MS = 8000      # Minimum 8 seconds (default fallback)
    MAX_SEGMENT_DURATION_MS = 20000     # Maximum 20 seconds

    # Quality Thresholds
    MIN_SEGMENT_QUALITY_SCORE = 30      # Minimum score to include segment
    HIGH_QUALITY_THRESHOLD = 60         # Score that allows extended segments

    # Softer Rotation (replaces rigid +50/-15)
    ROTATION_BONUS_BASE = 20            # Reduced from 50
    ROTATION_PENALTY = 10               # Reduced from 15

    # Music Integration
    MUSIC_BEAT_SYNC_TOLERANCE_MS = 200
    MUSIC_FADE_IN_SEC = 2
    MUSIC_FADE_OUT_SEC = 3
    MUSIC_DUCK_SPEECH_VOLUME = 0.2
    MUSIC_BOOST_ACTION_VOLUME = 1.2


SWITCHING_PROFILES = {
    "sports": {
        "high_action": "closeup",
        "ball_near_goal": "goal_angle",
        "low_action": "crowd",
        "default": "wide",
        "ad_block_scenes": ["scoring_play"],
        "ad_boost_scenes": ["timeout"],
    },
    "ceremony": {
        "name_called": "stage_closeup",
        "walking": "wide",
        "applause": "crowd",
        "speech": "podium",
        "ad_block_scenes": ["name_announcement"],
        "ad_boost_scenes": ["pause"],
    },
    "performance": {
        "solo": "closeup",
        "full_band": "wide",
        "crowd_singing": "crowd",
        "ad_block_scenes": ["solo"],
        "ad_boost_scenes": ["break"],
    },
}

MUSIC_MIX_PROFILES = {
    "sports": {"music_volume": 0.5, "event_volume": 0.8, "duck_speech": True},
    "ceremony": {"music_volume": 0.3, "event_volume": 1.0, "duck_speech": True},
    "performance": {"music_volume": 0.2, "event_volume": 1.0, "duck_speech": False},
}

# Minimum segment duration by event type (in milliseconds)
# CRITICAL: Longer durations prevent "MTV effect" motion sickness
# Professional broadcast holds shots 7-15 seconds for low-intensity content
MIN_SEGMENT_DURATION_BY_EVENT = {
    "sports": 4000,       # 4s - fast-paced but not frantic
    "ceremony": 10000,    # 10s - speeches/walks need stability
    "performance": 6000,  # 6s - music-driven, moderate pacing
    "speech": 10000,      # 10s - lectures/talks require calm pacing
    "lecture": 12000,     # 12s - educational content needs longest holds
}

# Hysteresis threshold to prevent jittery switching
# Only switch angles if new angle scores > current * (1 + threshold)
HYSTERESIS_THRESHOLD = 0.30  # 30% better required to switch

# Speaker prioritization multipliers (for speech/ceremony events)
SPEAKER_SCORE_MULTIPLIERS = {
    "closeup": 2.0,       # 2x boost when speaker detected on closeup
    "medium": 1.5,        # 1.5x boost for medium shots with speaker
    "podium": 2.0,        # 2x boost for podium angle during speech
    "stage_closeup": 2.0, # 2x boost for stage closeup
}
