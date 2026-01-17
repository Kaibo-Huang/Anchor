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
Video:     FFmpeg (primary), librosa (audio sync)
APIs:      TwelveLabs (Marengo 2.7, Pegasus 1.2), Shopify Storefront, Google Veo 3.1
Pkg Mgrs:  bun (frontend), uv (backend)
```

## Video Tools
| Tool | Purpose |
|------|---------|
| FFmpeg | Cut, concat, crop, zoom, overlay, transitions, audio mix (FAST - PRIMARY) |
| ffmpeg-python | Build FFmpeg commands in Python (NOT frame loops - will timeout on 4K) |
| TwelveLabs | UNDERSTAND video: scene detection, objects, actions, faces, audio + embeddings |
| Google Veo | GENERATE new video from text/images (ads, NOT for editing footage) |
| librosa | Audio fingerprinting for multi-angle sync |

## FFmpeg Quick Reference
```bash
ffmpeg -i input.mp4 -ss 5 -t 10 -c copy output.mp4                    # Cut clip
ffmpeg -i input.mp4 -vf "crop=iw/2:ih/2:iw/4:ih/4,scale=1920:1080" out.mp4  # Crop/zoom
ffmpeg -i video.mp4 -i banner.png -filter_complex "overlay=10:H-200:enable='between(t,5,10)'" out.mp4  # Overlay
ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex "xfade=transition=fade:duration=0.5:offset=4.5" out.mp4  # Crossfade
ffmpeg -i input.mp4 -vf "zoompan=z='min(zoom+0.001,1.5)':d=90:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" out.mp4  # Ken Burns
```

## Commands
```bash
cd frontend && bun install && bun dev                                  # Frontend
cd backend && uv sync && uv run uvicorn main:app --reload             # Backend
cd backend && uv run celery -A worker worker --loglevel=info          # Celery
docker run -d -p 6379:6379 redis:alpine                               # Redis
```

## Architecture
```
Upload up to 12 videos → S3 → Audio sync → TwelveLabs analysis
  → Feature 1: Multi-angle switching (best angle per moment)
  → Feature 2: Auto-zoom on key moments
  → Feature 3: Shopify ads + Veo product videos + sponsor power plays
  → Feature 4: On-demand highlight reels (CORE IDENTITY)
  → Feature 5: Personal music integration
  → FFmpeg render → S3 output
```

---

## FEATURE 1: Multi-Angle Switching

**Goal:** Sync multiple camera angles, auto-select best view per moment.

**Audio Sync (Hybrid):**
1. Rough align via device metadata timestamps (within ~5s)
2. Fine-tune via librosa audio correlation + scipy.signal.correlate (<100ms accuracy)

**TwelveLabs Analysis:**
- Create index with `marengo2.7` (visual+audio) + `pegasus1.2` (embeddings)
- Returns: scene classification, objects, audio events, action_intensity (1-10)
- Use embeddings for vibe matching (High Energy, Emotional, Calm) - better than keywords

**Switching Profiles:**
```python
PROFILES = {
    "sports":    {"high_action": "closeup", "ball_near_goal": "goal_angle", "low_action": "crowd", "default": "wide"},
    "ceremony":  {"name_called": "stage_closeup", "walking": "wide", "applause": "crowd", "speech": "podium"},
    "performance": {"solo": "closeup", "full_band": "wide", "crowd_singing": "crowd"},
}
```

**Timeline Algorithm:** Score each angle every 2s, select highest with min 4s between switches.
Output: `[{"start_ms": 0, "video_id": "A"}, {"start_ms": 4000, "video_id": "B"}, ...]`

**Chapter Generation:** Navigation markers for major events (goals, halftime, awards) - min 1 min spacing.

---

## FEATURE 2: Auto-Zoom

**Goal:** Ken Burns effect on key moments (goals, name calls, solos).

**Triggers:** action_intensity > 8, audio events ("cheer", "goal"), user timestamps
**Constraints:** Only wide/medium shots (never closeups), max 1 zoom per 10s

**FFmpeg zoompan** (use exclusively - Python frame loops timeout on 4K):
```bash
ffmpeg -i input.mp4 -vf "zoompan=z='if(lte(on,9),1+(0.5/9)*on,if(lte(on,60),1.5,1.5-(0.5/9)*(on-60)))':d=70:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" out.mp4
```
Ease-in 0.3s → hold 2-5s → ease-out 0.3s

---

## FEATURE 3: Brand Integration (Shopify + Veo)

**Goal:** Native video replacement with AI-generated Shopify product ads at natural transitions (TV commercial break feel).

**Shopify OAuth Flow:**
1. User enters shop domain → generate OAuth URL with nonce
2. Shopify redirects to callback → verify HMAC, exchange code for access token
3. Encrypt token (Fernet), store in DB → fetch products via Storefront API
4. Scopes: `read_products, read_product_listings, read_files`

**Ad Slot Detection (Multi-Factor Scoring 0-100):**
- Action intensity (40pts), audio context (25pts), scene transition (20pts), visual complexity (15pts)
- Constraints: min 45s spacing, max 1 ad per 4 min, no ads in first/last 10s
- Penalties: nearby key moments (-70%), active speech (-50%), high crowd energy (-60%)
- Result: 3-4 optimal placements

**Native Integration Pipeline:**
1. Find transition points (scene boundaries, camera pans, angle switches)
2. Generate Veo video with motion matching (pan direction, zoom style)
3. Color-grade to match event footage
4. Insert with FFmpeg xfade: event → crossfade (0.5s) → product (3.5s) → crossfade → resume

```python
operation = client.models.generate_videos(
    model="veo-3.1-fast-preview",
    prompt=f"Product showcase, {product.name}, camera panning right",
    image=product.image_data, duration=3.5
)
```

**Sponsor Power Plays:** Lower-third overlays: "{sponsor} GOAL CAM!", "{sponsor} Play of the Game"

---

## FEATURE 4: On-Demand Highlight Reels (CORE IDENTITY)

**Goal:** Users create personalized highlight reels using natural language - find YOURSELF in the footage.

**Query Examples:** "me", "my best moments", "player 23", "guy in yellow pants", "me scoring"

**Flow:**
1. User submits query + vibe (High Energy/Emotional/Calm)
2. TwelveLabs natural language search → candidate moments
3. Embedding-based ranking by vibe similarity + confidence
4. Build 30s timeline from top moments
5. FFmpeg render with crossfades + user's music
6. Return S3 URL instantly (<10s)

**API:**
```
POST /api/events/:id/reels/generate
Body: { "query": "me", "vibe": "high_energy", "duration": 30 }
Returns: { "reel_url": "https://s3.../reel.mp4", "moments_count": 8 }
```

**Why Core Identity:** Users literally search for "me" to find themselves in multi-angle footage. Instant results, embedding-powered vibe matching.

---

## FEATURE 5: Personal Music Integration

**Goal:** User uploads personal music (team anthem, graduation song) - makes every reel unique.

**Beat Detection (librosa):**
```python
tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
beat_times_ms = librosa.frames_to_time(beat_frames, sr=sr) * 1000
```

**Beat-Synced Cuts:** Snap angle switches to nearest beat (±200ms tolerance)

**Audio Ducking:** Lower music to 20% during speech, boost to 120% during highlights, fade out during ads

**FFmpeg Mix:**
```bash
ffmpeg -i video.mp4 -i music.mp3 -filter_complex \
  "[1:a]volume=0.5,afade=t=in:d=2,afade=t=out:d=3[music];[0:a]volume=1.0[event];[music][event]amix=inputs=2[audio]" \
  -map 0:v -map "[audio]" output.mp4
```

---

## Database Schema
```sql
events (id, user_id, name, event_type, status, shopify_store_url, sponsor_name, master_video_url, music_url, music_metadata JSONB)
videos (id, event_id, original_url, angle_type, sync_offset_ms, analysis_data JSONB, status)
timelines (id, event_id, segments JSONB, zooms JSONB, ad_slots JSONB, chapters JSONB, beat_synced BOOLEAN)
custom_reels (id, event_id, query TEXT, output_url, moments JSONB, duration_sec INT, created_at)
```

## API Endpoints
```
POST /api/events                      Create event
POST /api/events/:id/videos           Get presigned S3 URL for video upload
POST /api/events/:id/music/upload     Get presigned S3 URL for music upload
POST /api/events/:id/analyze          Start TwelveLabs analysis
POST /api/events/:id/generate         Generate final video
GET  /api/events/:id/shopify/auth-url Get Shopify OAuth URL
GET  /api/auth/shopify/callback       Handle OAuth callback
GET  /api/events/:id/shopify/products Fetch connected store products
POST /api/events/:id/sponsor          Set sponsor power plays
GET  /api/events/:id/chapters         Get chapter markers (JSON)
POST /api/events/:id/reels/generate   Generate custom highlight reel
```

## Environment Variables
```
TWELVELABS_API_KEY, GOOGLE_API_KEY, SUPABASE_URL, SUPABASE_KEY
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET
REDIS_URL=redis://localhost:6379
SHOPIFY_API_KEY, SHOPIFY_API_SECRET, SHOPIFY_API_VERSION=2024-01
ENCRYPTION_KEY  # Fernet key for token encryption
BASE_URL, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL
```

## Dependencies
**Backend:** fastapi, uvicorn, celery[redis], twelvelabs, google-genai, ffmpeg-python, librosa, scipy, supabase, boto3, httpx, cryptography
**Frontend:** next 14.x, react 18.x, @tanstack/react-query, @supabase/supabase-js, video.js

## File Structure
```
anchor/
├── frontend/
│   ├── app/ (page.tsx, events/[id]/page.tsx)
│   ├── components/ (ShopifyConnect, PersonalReelGenerator, MusicUpload)
│   └── lib/ (supabase.ts, api.ts)
├── backend/
│   ├── main.py, worker.py, config.py
│   ├── routers/ (events.py, videos.py, shopify.py, reels.py)
│   └── services/ (twelvelabs, veo, audio_sync, music_sync, timeline, zoom, overlay, render)
└── CLAUDE.md, PLAN.md
```

## Processing Pipeline
1. Sync audio (metadata rough → fingerprint fine)
2. TwelveLabs analysis with embeddings (parallel for all videos)
3. Analyze user's music (beats, intensity) - optional
4. Generate angle-switching timeline
5. Align cuts to beats (optional)
6. Identify zoom moments
7. Find ad slots + generate Veo product videos
8. Insert with seamless transitions + add sponsor overlays
9. Generate chapters
10. Mix personal music with ducking
11. FFmpeg render → S3

---

## Build Priority (IDENTITY-FIRST)
```
Hours 0-4:   Setup (repos, Supabase, S3, API keys)
Hours 4-12:  Feature 1 (multi-angle switching)
Hours 12-18: Feature 4 (On-Demand Highlight Reels - CORE IDENTITY)
Hours 18-24: Feature 5 (personal music integration)
Hours 24-28: Feature 2 (auto-zoom)
Hours 28-34: Feature 3 (Native ad integration: Veo + transitions)
Hours 34-36: Polish, demo, pitch
Fallback:    Simple overlay if native integration too complex
```

**Target Prizes:** TwelveLabs (embeddings + search), Shopify (shoppable video), Gemini (Veo), Top 3

**Theme "Identity":**
- Feature 4: Find YOURSELF in footage ("me", "my best moments")
- Feature 5: Express identity through personal music
- Embeddings: Match video vibe to user's desired identity (High Energy, Emotional, Calm)
