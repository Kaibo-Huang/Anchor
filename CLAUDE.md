# CLAUDE.md - Anchor Project Context

## Project Summary
AI-powered video production platform: multi-angle phone footage → broadcast-quality highlight reels with native ad integration.
**Hackathon Targets:** TwelveLabs + Shopify + Gemini/Veo. **Theme:** "Identity."

## Stack
```
Frontend:  Next.js 14+ (App Router), Tailwind, React Query, Video.js
Backend:   Python 3.11+, FastAPI, Celery + Redis
Database:  Supabase (PostgreSQL + Auth + Realtime)
Storage:   AWS S3 (presigned URLs)
Video:     FFmpeg (primary), MoviePy (animations), librosa (audio sync)
APIs:      TwelveLabs (Marengo 2.7, Pegasus 1.2), Shopify Storefront, Google Veo 3.1
Pkg Mgrs:  bun (frontend), uv (backend)
```

## Video Tools
| Tool | Purpose |
|------|---------|
| FFmpeg | Cut, concat, crop, zoom, overlay, transitions, audio mix (FAST) |
| MoviePy | Complex animations, smooth zoom easing (Python, slower) |
| TwelveLabs | UNDERSTAND video: scene detection, objects, actions, faces, audio |
| Google Veo | GENERATE new video from text/images (ads, NOT for editing footage) |
| librosa | Audio fingerprinting for multi-angle sync |

## FFmpeg Quick Reference
```bash
# Cut clip
ffmpeg -i input.mp4 -ss 5 -t 10 -c copy output.mp4
# Crop/zoom (2x center)
ffmpeg -i input.mp4 -vf "crop=iw/2:ih/2:iw/4:ih/4,scale=1920:1080" output.mp4
# Overlay banner (t=5-10s)
ffmpeg -i video.mp4 -i banner.png -filter_complex "overlay=10:H-200:enable='between(t,5,10)'" output.mp4
# Crossfade (0.5s)
ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex "xfade=transition=fade:duration=0.5:offset=4.5" output.mp4
# Ken Burns zoom
ffmpeg -i input.mp4 -vf "zoompan=z='min(zoom+0.001,1.5)':d=90:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" output.mp4
```

## MoviePy Animated Zoom
```python
clip = clip.resize(lambda t: 1 + 0.3 * min(t / 0.3, 1))  # 1x→1.3x over 0.3s
clip = clip.crop(x_center=960, y_center=540, width=1920, height=1080)
```

## Commands
```bash
cd frontend && bun install && bun dev          # Frontend
cd backend && uv sync && uv run uvicorn main:app --reload  # Backend
cd backend && uv run celery -A worker worker --loglevel=info  # Celery
docker run -d -p 6379:6379 redis:alpine        # Redis
```

## Architecture
```
Upload 2-4 videos → S3 → Audio sync → TwelveLabs analysis
  → Feature 1: Multi-angle switching (best angle per moment)
  → Feature 2: Auto-zoom on key moments
  → Feature 3: Shopify ads + Veo product videos + sponsor power plays
  → Feature 4: Personal highlight reels (stretch)
  → FFmpeg render → S3 output
```

---

## FEATURE 1: Multi-Angle Switching

**Goal:** Sync multiple camera angles, auto-select best view per moment.

### Audio Sync (Hybrid)
1. **Rough align:** Device metadata timestamps (within ~5s)
2. **Fine-tune:** librosa audio correlation via onset_strength + scipy.signal.correlate (<100ms accuracy)

### TwelveLabs Analysis
```python
client = TwelveLabs(api_key=KEY)
index = client.index.create(name=f"event_{id}", engines=[{"name": "marengo2.7", "options": ["visual", "audio"]}])
task = client.task.create(index_id=index.id, url=s3_url)
# Returns: scene classification, objects, audio events, action_intensity (1-10)
```

### Chunking Strategy
- **Speech present:** Use transcription sentence boundaries (natural breakpoints)
- **No speech:** Fixed 5-sec intervals, or audio event-based (whistle, beat drops)

### Switching Profiles
```python
PROFILES = {
    "sports":    {"high_action": "closeup", "ball_near_goal": "goal_angle", "low_action": "crowd", "default": "wide"},
    "ceremony":  {"name_called": "stage_closeup", "walking": "wide", "applause": "crowd", "speech": "podium"},
    "performance": {"solo": "closeup", "full_band": "wide", "crowd_singing": "crowd"},
}
```

### Timeline Algorithm
- Score each angle every 2s using TwelveLabs data + profile rules
- Select highest-scoring angle with min 4s between switches
- Output: `[{"start_ms": 0, "video_id": "A"}, {"start_ms": 4000, "video_id": "B"}, ...]`

### Chapter Generation
Auto-generate YouTube-compatible timestamps from scene classification + transcription.

---

## FEATURE 2: Auto-Zoom

**Goal:** Ken Burns effect on key moments (goals, name calls, solos).

### Triggers
- action_intensity > 8, audio events ("cheer", "goal"), user timestamps
- Only zoom wide/medium shots (never closeups—resolution loss)
- Max 1 zoom per 10s

### Zoom Calculation
```python
zoom = 2.5 if importance >= 0.85 else 1.8  # Based on confidence
cx, cy = bbox center; crop to frame_size/zoom centered on (cx, cy)
# Ease-in 0.3s → hold 2-5s → ease-out 0.3s
```

---

## FEATURE 3: Brand Integration (Shopify + Veo)

**Goal:** Replace video segments with AI-generated Shopify product ads using seamless transitions (TV commercial break experience).

**Approach:** Native video replacement at natural transition points (PRIMARY)
**Fallback:** Simple overlay if time-constrained

### Ad Slot Detection (Multi-Factor Scoring)
- Score each timestamp 0-100 (action intensity 40pts, audio 25pts, transitions 20pts, visual complexity 15pts)
- Constraints: min 45s spacing, max 1 ad per 4 min, no ads in first/last 10s
- Penalties: nearby key moments (-70%), active speech (-50%), high crowd energy (-60%)
- Event rules: never interrupt scoring plays, name announcements, solos
- Result: 3-4 optimal placements

### Native Integration Pipeline
1. **Find transition points:** Scene boundaries, camera pans, angle switches
2. **Generate Veo video with motion matching:** Match pan direction or zoom for seamless blending
3. **Match visual style:** Color-grade Veo video to match event footage (brightness, saturation, color temp)
4. **Insert with FFmpeg xfade:** Cut event → crossfade (0.5s) → product video (3.5s) → crossfade → resume event
5. **Blend audio:** Crossfade event audio down/up around product video

```python
# Generate motion-matched Veo video
operation = client.models.generate_videos(
    model="veo-3.1-fast-preview",
    prompt=f"Product showcase, {product.name}, camera panning right" if transition == "pan" else "rotating",
    image=product.image_data,
    duration=3.5
)

# Insert with crossfade transition
ffmpeg -i before.mp4 -i product.mp4 -i after.mp4 \
  -filter_complex "[0][1]xfade=duration=0.5[v1];[v1][2]xfade=duration=0.5[v]" \
  output.mp4
```

### Sponsor Power Plays
Lower-third overlays for key moments: "{sponsor} GOAL CAM!", "{sponsor} Play of the Game"

### Sponsor Power Plays
```python
TEMPLATES = {
    "goal": "{sponsor} GOAL CAM!",
    "highlight": "{sponsor} Play of the Game",
    "replay": "{sponsor} Instant Replay",
    "timeout": "{sponsor} Timeout"
}
# Lower-third overlay, 4s duration, slide-in animation
```

### Smart Placement
- Detect objects (scoreboard, faces, ball) → create exclusion zones
- Test candidate positions (corners, gym walls) → select least overlap
- Adjust opacity/color to match scene lighting
- Track position across frames for camera movement

---

## FEATURE 4: On-Demand Highlight Reels (Stretch)

**Goal:** User requests custom highlight reel with natural language query.

**Examples:** "player 23", "guy in yellow pants", "the goalie", "person who scored first"

### Flow
1. **User submits query** via API/UI
2. **TwelveLabs natural language search** → finds matching moments
3. **Filter and rank** moments by importance/confidence
4. **Build 30s timeline** from top moments
5. **Render with FFmpeg** → add title card, concatenate clips with crossfades
6. **Return S3 URL** instantly

```python
# API call
POST /api/events/:id/reels/generate
Body: { "query": "player 23", "duration": 30 }

# Returns
{ "reel_url": "https://s3.../reel.mp4", "moments_count": 8 }
```

**Benefits:** On-demand (no batch processing), handles any natural language query, instant results using existing TwelveLabs index.

---

## Database Schema
```sql
events (id, user_id, name, event_type, status, shopify_store_url, sponsor_name, master_video_url)
videos (id, event_id, original_url, angle_type, sync_offset_ms, analysis_data JSONB, status)
timelines (id, event_id, segments JSONB, zooms JSONB, ad_slots JSONB, chapters JSONB)
custom_reels (id, event_id, query TEXT, output_url, moments JSONB, duration_sec INT, created_at)
```

## API Endpoints
```
POST /api/events                     Create event
POST /api/events/:id/videos          Get presigned S3 URL
POST /api/events/:id/analyze         Start TwelveLabs analysis
POST /api/events/:id/generate        Generate final video
POST /api/events/:id/shopify         Connect Shopify store
POST /api/events/:id/sponsor         Set sponsor power plays
GET  /api/events/:id/chapters        Get YouTube timestamps
POST /api/events/:id/reels/generate  Generate custom highlight reel from query
```

## Configuration Management

**Use config files for tunable thresholds** instead of hardcoding values.

Create `backend/config.py` with:
```python
class VideoConfig:
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
    MIN_ANGLE_DURATION_MS = 4000

SWITCHING_PROFILES = {
    "sports": {"ad_block_scenes": ["scoring_play"], "ad_boost_scenes": ["timeout"]},
    "ceremony": {"ad_block_scenes": ["name_announcement"], "ad_boost_scenes": ["pause"]}
}
```

**Benefits:** Easy tuning during demo without code changes, event-specific customization.

## Environment Variables
```
TWELVELABS_API_KEY, GOOGLE_API_KEY, SUPABASE_URL, SUPABASE_KEY
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET
REDIS_URL=redis://localhost:6379, SHOPIFY_API_VERSION=2024-01
NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL
```

## Dependencies
**Backend:** fastapi, uvicorn, celery[redis], twelvelabs, google-genai, ffmpeg-python, moviepy, librosa, scipy, supabase, boto3, httpx
**Frontend:** next 14.x, react 18.x, @tanstack/react-query, @supabase/supabase-js, video.js

## File Structure
```
anchor/
├── frontend/app/, components/, lib/ (supabase.ts, api.ts)
├── backend/main.py, worker.py, routers/, services/
│   └── services: twelvelabs, veo, audio_sync, timeline, zoom, overlay, chapters, sponsor, render
└── CLAUDE.md
```

## Processing Pipeline
1. Sync audio (metadata rough → fingerprint fine)
2. TwelveLabs analysis (parallel)
3. Generate angle-switching timeline
4. Identify zoom moments
5. Find ad slots (multi-factor scoring) + identify transition points
6. Generate Veo product videos (motion-matched) + color-grade to match footage
7. Insert product videos with seamless transitions (native replacement)
8. Add sponsor power plays (overlays)
9. Generate chapters
10. FFmpeg render → S3

## Docker (Post-Hackathon)
Services: frontend (Next.js), backend (FastAPI), celery (workers), redis, postgres
One-command: `docker-compose up --build`

---

## Build Priority
```
Hours 0-4:   Setup (repos, Supabase, S3, API keys)
Hours 4-12:  Feature 1 (multi-angle switching)
Hours 12-20: Feature 2 (auto-zoom)
Hours 20-28: Feature 3 (Native ad integration: Veo + seamless transitions)
Hours 28-36: Polish, demo, pitch
Fallback:    Simple overlay if native integration too complex
Stretch:     Feature 4 (personal reels)
```

**Target Prizes:** TwelveLabs (full API), Shopify (shoppable video), Gemini (Veo generation), Top 3 Overall
