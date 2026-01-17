# CLAUDE.md - Anchor Project Context

## Project Summary
AI-powered video production platform that transforms multi-angle phone footage into broadcast-quality highlight reels with native ad integration. Targets TwelveLabs + Shopify + Gemini hackathon prizes. Theme: "Identity."

## Stack
```
Frontend:    Next.js 14+ (App Router), Tailwind, React Query, Video.js
Backend:     Python 3.11+, FastAPI, Celery + Redis
Database:    Supabase (PostgreSQL + Auth + Realtime)
Storage:     AWS S3 (presigned URLs)
Video:       FFmpeg, MoviePy, librosa
APIs:        TwelveLabs (Marengo 2.7, Pegasus 1.2), Shopify Storefront, Google Veo 3.1
Pkg Mgrs:    bun (frontend), uv (backend)
```

## Video Tools: What Does What
```
FFmpeg      → Cut, concat, crop, zoom, overlay, transitions, audio mix (FAST, primary tool)
MoviePy     → Complex animations, smooth zoom easing (Python, slower but easier)
TwelveLabs  → UNDERSTAND video (scene detection, objects, actions, faces, audio events)
Google Veo  → GENERATE new video content:
              ✅ Animated product videos from Shopify images (for ads)
              ✅ Stylized replays (stretch goal)
              ❌ NOT for editing/zooming real footage (that's FFmpeg/MoviePy)
librosa     → Audio analysis (sync videos via audio fingerprinting)
```

**Veo is NOT for editing.** It generates new video from text/images. All cutting, zooming, overlays use FFmpeg/MoviePy.

### FFmpeg Quick Reference
```bash
# Cut clip
ffmpeg -i input.mp4 -ss 5 -t 10 -c copy output.mp4

# Crop/zoom (2x center crop)
ffmpeg -i input.mp4 -vf "crop=iw/2:ih/2:iw/4:ih/4,scale=1920:1080" output.mp4

# Overlay banner (show at t=5-10s)
ffmpeg -i video.mp4 -i banner.png -filter_complex "overlay=10:H-200:enable='between(t,5,10)'" output.mp4

# Crossfade two clips (0.5s fade)
ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex "xfade=transition=fade:duration=0.5:offset=4.5" output.mp4

# Slow motion (0.5x)
ffmpeg -i input.mp4 -vf "setpts=2*PTS" output.mp4

# Concat multiple clips
ffmpeg -f concat -i filelist.txt -c copy output.mp4
```

### MoviePy (for animated zooms)
```python
from moviepy.editor import VideoFileClip

clip = VideoFileClip("input.mp4")

def zoom_in(t):
    zoom = 1 + 0.3 * min(t / 0.3, 1)  # 1x to 1.3x over 0.3s
    return zoom

# Apply with resize + crop per frame
clip = clip.resize(lambda t: zoom_in(t)).crop(x_center=960, y_center=540, width=1920, height=1080)
clip.write_videofile("output.mp4")
```

## Commands
```bash
# Frontend
cd frontend && bun install && bun dev

# Backend  
cd backend && uv sync && uv run uvicorn main:app --reload

# Celery worker
cd backend && uv run celery -A worker worker --loglevel=info

# Redis
docker run -d -p 6379:6379 redis:alpine

# Docker (Full Stack - Post-Hackathon)
# docker-compose up --build
```

## Architecture
```
Upload 2-4 videos → S3 → TwelveLabs analysis → Audio sync (metadata + fingerprint)
    ↓
Feature 1: Multi-angle switching (best angle per moment)
    ↓
Feature 2: Auto-zoom on key moments
    ↓
Feature 3: Shopify ad insertion (Veo generates product videos, sponsor power plays)
    ↓
Feature 4: Personal highlight reels (stretch)
    ↓
FFmpeg render → S3 → Output
```

---

## FEATURE 1: Multi-Angle Intelligent Switching

**What:** Takes multiple camera angles, picks best angle per moment automatically.

### Implementation

**1. Upload & Organize**
- Upload 3-4 videos to S3
- Auto-detect angle type via TwelveLabs (first 5 sec): wide, closeup, crowd, stage

**2. Audio Sync (Hybrid: Metadata + Fingerprint)**

iPhones and most devices record creation timestamps, but they can be 2+ seconds apart between devices. We use a two-step approach:

```python
import librosa
from scipy import signal
import numpy as np
from datetime import datetime

def sync_videos(videos):
    """
    Hybrid sync: metadata for rough alignment, audio fingerprint for fine-tuning.
    Gets alignment to <100ms accuracy.
    """
    # Step 1: Rough align via metadata (fast, gets within ~5 sec)
    base_time = min(v.creation_timestamp for v in videos)
    rough_offsets = {
        v.id: int((v.creation_timestamp - base_time).total_seconds() * 1000) 
        for v in videos
    }
    
    # Step 2: Fine-tune with audio correlation (accurate, <100ms)
    fine_offsets = audio_fingerprint_sync(videos, rough_offsets)
    
    return fine_offsets

def audio_fingerprint_sync(videos, rough_offsets):
    """Audio correlation for precise sync."""
    ref_video = videos[0]
    ref_audio, sr = librosa.load(ref_video.path, sr=22050, mono=True)
    ref_onset = librosa.onset.onset_strength(y=ref_audio, sr=sr)
    
    offsets = {ref_video.id: 0}
    
    for v in videos[1:]:
        audio, _ = librosa.load(v.path, sr=22050, mono=True)
        onset = librosa.onset.onset_strength(y=audio, sr=sr)
        
        # Use rough offset to narrow search window (±5 sec)
        rough_ms = rough_offsets[v.id]
        
        corr = signal.correlate(ref_onset, onset, mode='full')
        lag = np.argmax(corr) - len(onset) + 1
        fine_offset_ms = int((lag / sr) * 1000)
        
        # Combine rough + fine adjustment
        offsets[v.id] = rough_ms + fine_offset_ms
    
    return offsets
```

**3. TwelveLabs Analysis**
```python
client = TwelveLabs(api_key=KEY)
index = client.index.create(name=f"event_{id}", engines=[{"name": "marengo2.7", "options": ["visual", "audio"]}])
task = client.task.create(index_id=index.id, url=s3_url)
task.wait_for_done()

# Returns per 2-3 sec: scene classification, objects, audio events, action intensity (1-10)
```

**4. Analysis Chunking (Hybrid: Transcription + Fixed Intervals)**

```python
def get_chunk_boundaries(video_analysis):
    """
    Hybrid chunking: use transcription sentence boundaries when speech present,
    fall back to fixed 5-sec windows for non-speech content.
    """
    chunks = []
    
    if video_analysis.has_speech and video_analysis.transcription:
        # Use transcription sentence boundaries (natural breakpoints)
        for sentence in video_analysis.transcription.sentences:
            chunks.append({
                "start_ms": sentence.start_ms,
                "end_ms": sentence.end_ms,
                "type": "speech",
                "text": sentence.text
            })
        
        # Fill gaps between sentences with fixed intervals
        chunks = fill_gaps_with_fixed_chunks(chunks, interval_ms=5000)
    else:
        # No speech: fall back to fixed 5-sec windows
        chunks = create_fixed_chunks(video_analysis.duration_ms, interval_ms=5000)
    
    return chunks

def fill_gaps_with_fixed_chunks(speech_chunks, interval_ms=5000):
    """Fill gaps between speech segments with fixed-interval chunks."""
    all_chunks = []
    sorted_chunks = sorted(speech_chunks, key=lambda x: x["start_ms"])
    
    current_pos = 0
    for chunk in sorted_chunks:
        # Fill gap before this speech chunk
        while current_pos + interval_ms <= chunk["start_ms"]:
            all_chunks.append({
                "start_ms": current_pos,
                "end_ms": current_pos + interval_ms,
                "type": "fixed"
            })
            current_pos += interval_ms
        
        # Add speech chunk
        all_chunks.append(chunk)
        current_pos = chunk["end_ms"]
    
    return all_chunks

def create_fixed_chunks(duration_ms, interval_ms=5000):
    """Create fixed-interval chunks for non-speech content."""
    chunks = []
    for start in range(0, duration_ms, interval_ms):
        chunks.append({
            "start_ms": start,
            "end_ms": min(start + interval_ms, duration_ms),
            "type": "fixed"
        })
    return chunks
```

**Use cases:**
- **Broadcasts/ceremonies**: Transcription-based is great (announcer calls names, speeches)
- **Sports action/concerts**: Fixed intervals or audio event-based (whistle, beat drops)

**5. Switching Rules (Event Profiles)**
```python
PROFILES = {
    "sports": {
        "high_action": "closeup",      # fast break → closeup
        "ball_near_goal": "goal_angle", # shot → basket/goal cam
        "low_action": "crowd",          # timeout → crowd
        "default": "wide"
    },
    "ceremony": {
        "name_called": "stage_closeup",
        "walking": "wide",
        "applause": "crowd",
        "speech": "podium"
    },
    "performance": {
        "solo": "closeup",
        "full_band": "wide",
        "crowd_singing": "crowd"
    },
    "general": {
        "default": "wide",
        "high_action": "closeup"
    }
}
```

**6. Angle Selection Algorithm**
```python
def generate_timeline(videos, analyses, event_type, duration_ms):
    profile = PROFILES.get(event_type, PROFILES["general"])
    timeline = []
    current_angle = None
    last_switch = -4000  # min 4 sec between switches
    
    for ts in range(0, duration_ms, 2000):  # every 2 sec
        scores = {}
        for v in videos:
            local_ts = ts - v.sync_offset
            if 0 <= local_ts <= v.duration:
                scores[v.id] = score_angle(analyses[v.id], local_ts, profile)
        
        best = max(scores, key=scores.get) if scores else current_angle
        if best != current_angle and (ts - last_switch) >= 4000:
            timeline.append({"start_ms": ts, "video_id": best})
            current_angle = best
            last_switch = ts
    
    return timeline
```

**7. FFmpeg Assembly**
```bash
# Cut clips per timeline segment
ffmpeg -i input.mp4 -ss START -t DURATION -c copy clip.mp4

# Concat with crossfade (0.5 sec)
ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex "xfade=transition=fade:duration=0.5" output.mp4
```

**8. Chapter Generation**

Use YouTube Chapter Highlight Generator approach to auto-generate chapter timestamps:
- Analyze video content to identify key segments
- Create timestamps for better video navigation
- Output in YouTube-compatible chapter format

```python
def generate_chapters(video_analysis, timeline):
    """
    Generate YouTube-compatible chapter timestamps.
    Based on YouTube Chapter Highlight Generator approach.
    """
    chapters = []
    
    for segment in timeline:
        # Use TwelveLabs scene classification + transcription
        chapter_title = determine_chapter_title(
            segment, 
            video_analysis.scenes,
            video_analysis.transcription
        )
        
        timestamp = ms_to_timestamp(segment["start_ms"])
        chapters.append(f"{timestamp} {chapter_title}")
    
    return "\n".join(chapters)

def ms_to_timestamp(ms):
    """Convert milliseconds to YouTube timestamp format (MM:SS or HH:MM:SS)."""
    seconds = ms // 1000
    minutes = seconds // 60
    hours = minutes // 60
    
    if hours > 0:
        return f"{hours}:{minutes % 60:02d}:{seconds % 60:02d}"
    return f"{minutes}:{seconds % 60:02d}"

def determine_chapter_title(segment, scenes, transcription):
    """Determine chapter title from scene context and speech."""
    # Priority: explicit speech mention > scene classification > generic
    if segment.get("text"):
        # Extract key phrase from transcription
        return extract_key_phrase(segment["text"])
    
    if scenes:
        scene = find_scene_at(scenes, segment["start_ms"])
        if scene:
            return scene.classification
    
    return f"Segment {segment.get('index', 0) + 1}"
```

---

## FEATURE 2: Context-Aware Auto-Zoom

**What:** Automatically zooms on important moments (goals, name calls, solos) using TwelveLabs bounding boxes.

### Implementation

**1. Detect Zoom-Worthy Moments**
```python
ZOOM_TRIGGERS = {
    "sports": ["goal", "shot", "score", "celebration"],
    "ceremony": ["name_called", "handshake", "diploma"],
    "performance": ["solo", "climax", "crowd_reaction"],
}

# TwelveLabs returns: timestamp, confidence, bounding_box {x, y, w, h}
```

**2. Calculate Zoom**
```python
def calc_zoom(bbox, importance, frame_size):
    zoom = 2.5 if importance >= 0.85 else 1.8 if importance >= 0.6 else 1.5
    
    cx, cy = bbox["x"] + bbox["w"]/2, bbox["y"] + bbox["h"]/2
    crop_w, crop_h = frame_size[0]/zoom, frame_size[1]/zoom
    crop_x = max(0, min(cx - crop_w/2, frame_size[0] - crop_w))
    crop_y = max(0, min(cy - crop_h/2, frame_size[1] - crop_h))
    
    return {"zoom": zoom, "crop": (crop_x, crop_y, crop_w, crop_h), "duration": 3.5}
```

**3. Smooth Zoom (Ken Burns)**
- Ease-in: 0.3s gradual zoom
- Hold: 2-5s at zoom level (adjusted based on moment importance)
- Ease-out: 0.3s back to normal
- Only zoom wide/medium shots, never closeups
- Max 1 zoom per 10 sec

**4. FFmpeg Zoom**
```bash
ffmpeg -i input.mp4 -vf "zoompan=z='min(zoom+0.001,1.5)':d=90:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" output.mp4
```

---

## FEATURE 3: Native Brand Integration (Shopify + Veo)

**What:** Insert Shopify product ads into low-action moments. Use Google Veo to generate animated product videos from static images.

### 3A: Dynamic Banner Overlays (MVP)

**1. Find Ad Slots**
```python
# TwelveLabs: action_intensity < 3, audio = "break/whistle/pause"
ad_slots = [ts for ts in analysis if ts.action_intensity < 3 and ts.audio in ["timeout", "pause", "transition"]]
```

**2. Fetch Shopify Products**
```python
import httpx

async def get_products(store_url, access_token):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{store_url}/admin/api/2024-01/products.json",
            headers={"X-Shopify-Access-Token": access_token}
        )
        return [{
            "id": p["id"],
            "title": p["title"],
            "price": p["variants"][0]["price"],
            "image": p["images"][0]["src"],
            "checkout_url": f"{store_url}/cart/{p['variants'][0]['id']}:1"
        } for p in r.json()["products"]]
```

**3. Generate Product Video with Veo** ⭐ (Differentiator)
```python
from google import genai

async def generate_product_video(product_image_url, product_name):
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    # Download product image
    image_data = await download_image(product_image_url)
    
    # Generate 3-sec animated product video
    operation = client.models.generate_videos(
        model="veo-3.1-fast-preview",  # Fast + cheaper
        prompt=f"Product showcase, {product_name} rotating slowly, clean white background, studio lighting, commercial quality",
        image=image_data,
    )
    
    while not operation.done:
        await asyncio.sleep(3)
        operation = client.operations.get(operation)
    
    return operation.result.videos[0].uri
```

**4. Sponsor Power Plays** ⭐ (New Feature)

Branded moment highlights sponsored by local businesses:

```python
SPONSOR_POWER_PLAYS = {
    "sports": {
        "goal": "{sponsor} GOAL CAM!",
        "highlight": "{sponsor} Play of the Game",
        "replay": "{sponsor} Instant Replay",
        "timeout": "{sponsor} Timeout"
    },
    "ceremony": {
        "graduate_walk": "{sponsor} Spotlight Moment",
        "applause": "{sponsor} Standing Ovation"
    }
}

def create_sponsor_overlay(moment_type, sponsor_name, event_type="sports"):
    """
    Create sponsored moment overlay.
    Example: "John's Bakery GOAL CAM!" or "John's Bakery Play of the Game"
    """
    templates = SPONSOR_POWER_PLAYS.get(event_type, SPONSOR_POWER_PLAYS["sports"])
    template = templates.get(moment_type, "{sponsor} Highlight")
    
    return {
        "text": template.format(sponsor=sponsor_name),
        "style": "broadcast_lower_third",
        "duration_ms": 4000,
        "animation": "slide_in_left"
    }
```

**5. Banner Templates**
- Bottom-third (sports style)
- Side panel (unobtrusive)
- Picture-in-picture
- Fade in 0.5s → display 3-4s → fade out 0.5s

**6. FFmpeg Overlay**
```bash
ffmpeg -i main.mp4 -i banner.png -filter_complex "overlay=x=100:y=H-200:enable='between(t,45,49)'" output.mp4
```

### 3B: Smart Contextual Placement

**What:** Intelligently place ads in the 3D scene without covering important content (like pro sports broadcasts).

**1. Detect Scene Objects**
```python
# TwelveLabs object detection
objects = client.search.query(index_id, "objects", ["visual"])
# Returns: scoreboard, basket, stage, podium, goal, net, etc. with bounding boxes
```

**2. Calculate Safe Placement Zones**
```python
def find_safe_placement(frame_analysis, banner_size):
    # Get important objects (scoreboard, action zone, faces)
    important_objects = [obj for obj in frame_analysis.objects
                        if obj.type in ["scoreboard", "basket", "goal", "face", "ball"]]

    # Create exclusion zones (expand bboxes by 15%)
    exclusion_zones = [expand_bbox(obj.bbox, 1.15) for obj in important_objects]

    # Test candidate positions (corners, thirds, gym wall areas)
    candidates = [
        {"pos": (50, 50), "type": "top_left"},
        {"pos": (frame_width - banner_width - 50, 50), "type": "top_right"},
        {"pos": (50, frame_height - banner_height - 50), "type": "bottom_left"},
        {"pos": (frame_width - banner_width - 50, frame_height - banner_height - 50), "type": "bottom_right"},
        {"pos": (frame_width / 2 - banner_width / 2, frame_height - banner_height - 100), "type": "bottom_center"},
        # Gym wall placements (if wall detected)
        *detect_wall_positions(frame_analysis)
    ]

    # Score each position (prefer unobstructed, natural surfaces)
    scores = []
    for candidate in candidates:
        overlap = calculate_overlap(candidate["pos"], banner_size, exclusion_zones)
        naturalness = 1.0 if candidate["type"].startswith("wall_") else 0.7
        scores.append((candidate, (1 - overlap) * naturalness))

    return max(scores, key=lambda x: x[1])[0]
```

**3. Environmental Integration (Pro-Style)**
```python
def integrate_into_scene(banner, frame_analysis, placement):
    # Adjust color/opacity to match scene lighting
    scene_brightness = calculate_avg_brightness(frame_analysis.frame)
    scene_color_temp = calculate_color_temperature(frame_analysis.frame)

    # Dim banner in dark scenes, brighten in bright scenes
    opacity = 0.85 if scene_brightness > 0.6 else 0.95

    # Color correction to match scene
    banner = adjust_color_temperature(banner, scene_color_temp)

    # If placing on gym wall/surface, add perspective warp
    if placement["type"].startswith("wall_"):
        banner = apply_perspective_warp(banner, placement["surface_normal"])
        # Add subtle shadow/lighting to match wall
        banner = apply_lighting(banner, frame_analysis.light_direction)

    return {"banner": banner, "opacity": opacity, "blend_mode": "multiply"}
```

**4. Depth-Aware Placement**
```python
def apply_depth_layering(frame, banner, placement, depth_map):
    # Use TwelveLabs depth estimation or simple heuristics
    # Place banner "behind" foreground objects for realism

    if placement["type"] == "wall_gym":
        # Extract foreground (players)
        foreground_mask = depth_map < 0.4  # Close objects

        # Composite: background → banner → foreground
        composite = place_banner_on_wall(frame, banner, placement)
        composite = blend_foreground(composite, frame, foreground_mask)

        return composite
    else:
        # Standard overlay
        return overlay_banner(frame, banner, placement, opacity=0.85)
```

**5. Dynamic Tracking**
```python
# Track placement across frames (account for camera movement)
def track_banner_position(frames, initial_placement):
    positions = [initial_placement]

    for i in range(1, len(frames)):
        # Optical flow or feature matching
        motion = estimate_camera_motion(frames[i-1], frames[i])

        # Adjust banner position to "stick" to surface
        if initial_placement["type"].startswith("wall_"):
            positions.append(apply_motion_to_surface(positions[-1], motion))
        else:
            # Fixed screen position for overlays
            positions.append(positions[-1])

    return positions
```

**6. FFmpeg Complex Overlay**
```bash
# Basic smart placement
ffmpeg -i main.mp4 -i banner.png -filter_complex "overlay=x='W-w-50':y='H-h-100':enable='between(t,10,14)'" output.mp4

# Perspective warp (for wall placement)
ffmpeg -i main.mp4 -i banner.png -filter_complex "perspective=x0=0:y0=0:x1=W:y1=20:x2=0:y2=H:x3=W:y3=H-20[warped]; [0][warped]overlay=x=100:y=200" output.mp4
```

### 3C: Native Content Integration (Advanced)

**1. Find Natural Cut Points**
- Camera pans (insert mid-pan)
- Scene transitions (fade to black)
- Wide→closeup switches

**2. Match Visual Style**
- Analyze color grading, lighting, camera movement
- Apply matching filters to Veo-generated ad

**3. Seamless Insertion**
```
Event footage → ball out of bounds → camera pans →
MID-PAN: transition to Veo product video (matching pan motion) →
2.5 sec product showcase →
Pan completes → back to game footage
```

**4. Audio Blending**
- Crossfade event audio down (0.3s)
- Veo generates native audio OR add subtle music
- Crossfade event audio back (0.3s)

**5. Contextual Matching**
```python
CONTEXT_ADS = {
    "player_drinking": "sports_drink",
    "crowd_dancing": "tickets",
    "graduation": "alumni_merch",
}
```

---

## MONETIZATION MODEL

### Revenue Streams

**1. Shopify Affiliate Links**
```python
def generate_affiliate_link(product, store_url, affiliate_id):
    # Shopify Affiliate program integration
    base_url = product["checkout_url"]
    affiliate_params = f"?ref={affiliate_id}&utm_source=anchor&utm_medium=video"

    return {
        "url": f"{base_url}{affiliate_params}",
        "commission_rate": 0.10,  # 10% default
        "tracking_id": generate_tracking_id()
    }
```

**2. Sponsorship Model**
- **Sponsored Events**: Brand pays flat fee → use affiliate links for tracking
- **Organic Events**: Traditional CPM/CPC advertising → Google AdSense fallback

**3. Pricing Tiers**
```python
PRICING = {
    "free": {
        "price": 0,
        "features": ["Multi-angle switching", "Watermarked output", "Max 60s"],
        "ads": "banner_overlays"
    },
    "creator": {
        "price": 19,  # per event
        "features": ["HD no watermark", "Auto-zoom", "Smart ad placement", "Max 5 min"],
        "ads": "native_integration",
        "revenue_share": 0.70  # Creator gets 70% of affiliate revenue
    },
    "pro": {
        "price": 99,  # per event
        "features": ["4K", "Personal reels", "Custom branding", "Unlimited length"],
        "ads": "optional",
        "revenue_share": 0.85
    },
    "enterprise": {
        "price": "custom",
        "features": ["API access", "White-label", "Dedicated support"],
        "ads": "bring_your_own_sponsors"
    }
}
```

**4. Affiliate Revenue Split**
```
Sponsored event:
  Brand → $500 flat fee → Anchor
  Affiliate sales → 10% commission → Anchor (70%) + Event creator (30%)

Organic event (Creator tier):
  Affiliate sales → 10% commission → Anchor (30%) + Event creator (70%)

Example: $1000 in product sales via video
  → $100 commission
  → Creator gets $70, Anchor gets $30
```

**5. Analytics Dashboard**
```python
class MonetizationStats:
    total_views: int
    unique_viewers: int
    ad_impressions: int
    ad_clicks: int
    affiliate_conversions: int
    affiliate_revenue: float
    creator_payout: float

    ctr: float  # click-through rate
    conversion_rate: float
    avg_order_value: float
```

**6. Integration with Shopify**
```python
async def setup_sponsorship(event_id: str, shopify_store_url: str):
    # Verify store ownership
    store = await verify_shopify_store(shopify_store_url)

    # Create affiliate program
    affiliate = await create_affiliate_program(store)

    # Auto-select products for ads
    products = await get_products(shopify_store_url)
    featured = select_featured_products(products, max=5)

    # Generate tracking pixels
    tracking = create_conversion_tracking(event_id, affiliate.id)

    return {
        "affiliate_id": affiliate.id,
        "products": featured,
        "tracking_code": tracking.code
    }
```

**7. Traditional Ad Fallback**
```python
# If no Shopify sponsor, use Google AdSense
async def get_fallback_ads(event_context):
    if event_context.type == "sports":
        categories = ["sporting_goods", "tickets", "apparel"]
    elif event_context.type == "ceremony":
        categories = ["education", "professional_services", "gifts"]

    # Programmatic ad insertion
    return await adsense_client.get_video_ads(categories, duration=5)
```

---

## FEATURE 4: Personalized Highlight Reels (Stretch)

**What:** Generate individual videos for each person (e.g., each graduate gets their own reel).

### Implementation

**1. Person Identification**
```python
# TwelveLabs face detection + clustering
faces = client.search.query(index_id, "faces", ["visual"])
clusters = cluster_faces(faces)  # Group same person

# Match to roster if provided
roster = [{"name": "John Smith", "ref_image": "john.jpg"}, ...]
for cluster in clusters:
    cluster.identity = match_to_roster(cluster.representative, roster)
```

**2. Extract Moments**
- Find all timestamps where person appears
- Filter: face visible, in focus, meaningful (not background)
- Rank by importance

**3. Build Personal Timeline**
```python
def create_personal_reel(person_id, appearances, target_duration=30):
    moments = sorted(appearances, key=lambda x: x.importance, reverse=True)
    timeline = []
    total = 0
    
    for m in moments:
        if total + m.duration <= target_duration:
            timeline.append(m)
            total += m.duration
    
    return sorted(timeline, key=lambda x: x.timestamp)
```

**4. Personalization**
- Title card: "John Smith - Class of 2025"
- Lower-third name during key moments
- Background music (optional)

**5. Batch Generation**
```python
async def generate_all_reels(event_id, persons):
    tasks = [generate_reel(event_id, p) for p in persons]
    results = await asyncio.gather(*tasks)
    
    for person, url in zip(persons, results):
        await send_email(person.email, url)
```

**6. Monetization**
- Free: 20s watermarked
- $10: Full 45s HD no watermark

---

## Database Schema (Supabase)
```sql
events (id, user_id, name, event_type, status, shopify_store_url, sponsor_name, master_video_url, created_at)
videos (id, event_id, original_url, angle_type, sync_offset_ms, analysis_data JSONB, status)
timelines (id, event_id, segments JSONB, zooms JSONB, ad_slots JSONB, chapters JSONB)
personal_reels (id, event_id, person_name, person_email, moments JSONB, output_url, status)
```

## API Endpoints
```
POST   /api/events                 Create event
GET    /api/events/:id             Get event
POST   /api/events/:id/videos      Get presigned S3 URL
POST   /api/events/:id/analyze     Start TwelveLabs analysis
POST   /api/events/:id/generate    Generate final video
GET    /api/events/:id/status      Processing status
POST   /api/events/:id/shopify     Connect Shopify store
POST   /api/events/:id/sponsor     Set sponsor for power plays
GET    /api/events/:id/chapters    Get generated chapter timestamps
POST   /api/events/:id/reels       Generate personal reels (stretch)
```

## Environment Variables
```
TWELVELABS_API_KEY=
GOOGLE_API_KEY=          # For Veo
SUPABASE_URL=
SUPABASE_KEY=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET=
REDIS_URL=redis://localhost:6379
SHOPIFY_API_VERSION=2024-01

NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Key Dependencies

### Backend (pyproject.toml)
```toml
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "celery[redis]>=5.3.0",
    "twelvelabs>=0.2.0",
    "google-genai>=0.5.0",      # Veo
    "ffmpeg-python>=0.2.0",
    "moviepy>=1.0.3",
    "librosa>=0.10.0",
    "scipy>=1.12.0",
    "numpy>=1.26.0",
    "supabase>=2.3.0",
    "boto3>=1.34.0",
    "httpx>=0.26.0",
    "pydantic>=2.5.0",
]
```

### Frontend (package.json)
```json
{
  "dependencies": {
    "next": "14.x",
    "react": "18.x",
    "@tanstack/react-query": "^5.0.0",
    "@supabase/supabase-js": "^2.39.0",
    "video.js": "^8.0.0"
  }
}
```

## Processing Pipeline
```python
@celery.task
def process_event(event_id: str):
    # 1. Sync audio across videos (metadata rough → fingerprint fine-tune)
    # 2. Analyze each with TwelveLabs (parallel)
    # 3. Chunk analysis (hybrid: transcription + fixed intervals)
    # 4. Generate angle-switching timeline (Feature 1)
    # 5. Identify zoom moments (Feature 2)
    # 6. Find ad slots + fetch Shopify products
    # 7. Generate product videos with Veo (Feature 3)
    # 8. Add sponsor power plays if configured
    # 9. Generate chapter timestamps
    # 10. Render with FFmpeg
    # 11. Upload to S3, update status
```

## File Structure
```
anchor/
├── frontend/
│   ├── app/
│   │   ├── page.tsx
│   │   └── events/[id]/page.tsx
│   ├── components/
│   ├── lib/ (supabase.ts, api.ts)
│   └── package.json
├── backend/
│   ├── main.py
│   ├── worker.py
│   ├── routers/ (events.py, videos.py, shopify.py)
│   ├── services/
│   │   ├── twelvelabs.py
│   │   ├── veo.py
│   │   ├── audio_sync.py       # Hybrid: metadata + fingerprint
│   │   ├── chunking.py         # Hybrid: transcription + fixed intervals
│   │   ├── timeline.py
│   │   ├── zoom.py
│   │   ├── overlay.py
│   │   ├── chapters.py         # YouTube chapter generation
│   │   ├── sponsor.py          # Sponsor power plays
│   │   └── render.py
│   └── pyproject.toml
├── CLAUDE.md
└── README.md
```

## Docker Deployment (Post-Hackathon Goal)

**Goal:** Fully containerize the application for easy deployment and scaling.

### Docker Compose Structure
```yaml
services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [backend]
  
  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [redis, postgres]
    volumes: ["./temp:/app/temp"]  # For video processing
  
  celery:
    build: ./backend
    command: celery -A worker worker --loglevel=info
    depends_on: [redis, backend]
    volumes: ["./temp:/app/temp"]
  
  redis:
    image: redis:alpine
    ports: ["6379:6379"]
  
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: anchor
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes: ["postgres_data:/var/lib/postgresql/data"]
```

### Benefits
- One-command deployment: `docker-compose up`
- Consistent environments (dev/staging/prod)
- Easy scaling (multiple Celery workers)
- Simplified CI/CD pipeline
- FFmpeg pre-installed in containers

### Implementation Priority
- **Hackathon:** Development mode (local installs)
- **Post-Hackathon:** Dockerize for production deployment
- **Production:** Add nginx reverse proxy, health checks, auto-restart policies

---

## Build Priority (Hackathon)
```
Hours 0-4:   Setup (repos, Supabase, S3, API keys)
Hours 4-12:  Feature 1 (multi-angle switching) ← Core
Hours 12-20: Feature 2 (auto-zoom) ← Visual impact
Hours 20-28: Feature 3A (Shopify + Veo ads + sponsor power plays) ← Prize differentiator
Hours 28-36: Polish, demo prep, pitch practice

Stretch:     Feature 3B (native ads), Feature 4 (personal reels), Veo stylized replays
Post-Launch: Full Docker containerization for production deployment
```

## Target Prizes
- **TwelveLabs**: Full API suite (scene, objects, audio, faces)
- **Shopify**: Novel shoppable video ad format + sponsor power plays
- **Gemini/Google**: Using Veo for AI-generated product videos (+ optional stylized replays)
- **Top 3 Overall**: Technical depth + clear business model