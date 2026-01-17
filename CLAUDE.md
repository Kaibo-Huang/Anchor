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
Generate navigation markers for major events (goals, halftime, awards) - min 1 minute spacing.
Returns JSON: `[{"timestamp_ms": 0, "title": "Start", "type": "section"}, ...]`

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

### Shopify OAuth Integration

**Goal:** Allow users to connect their Shopify store securely via OAuth, fetch products automatically.

#### Setup: Create Shopify App

1. **Create app in Shopify Partner Dashboard:**
   - App name: "Anchor Video Ads"
   - App URL: `https://anchor.app` (or localhost for dev)
   - Redirect URL: `https://anchor.app/api/auth/shopify/callback`

2. **Required Scopes:**
   ```
   read_products          # Fetch product data
   read_product_listings  # Get published products
   read_files             # Access product images
   ```

3. **Get credentials:**
   ```
   SHOPIFY_API_KEY=<from partner dashboard>
   SHOPIFY_API_SECRET=<from partner dashboard>
   ```

#### OAuth Flow Implementation

**Step 1: Install Button (Frontend)**
```tsx
// frontend/components/ShopifyConnect.tsx
export function ShopifyConnect({ eventId }: { eventId: string }) {
  const initiateOAuth = async () => {
    const { auth_url } = await api.getShopifyAuthUrl(eventId)
    window.location.href = auth_url
  }

  return (
    <Button onClick={initiateOAuth}>
      <ShoppingBag className="mr-2" />
      Connect Shopify Store
    </Button>
  )
}
```

**Step 2: Generate Auth URL (Backend)**
```python
# backend/routers/shopify.py
from fastapi import APIRouter, HTTPException
import hmac
import hashlib
from urllib.parse import urlencode

router = APIRouter()

@router.get("/api/events/{event_id}/shopify/auth-url")
async def get_shopify_auth_url(event_id: str, shop: str):
    """
    Generate Shopify OAuth URL.
    User provides their shop domain (e.g., 'my-store.myshopify.com')
    """
    # Validate shop domain
    if not shop.endswith('.myshopify.com'):
        raise HTTPException(400, "Invalid shop domain")

    # Generate nonce for security
    nonce = secrets.token_urlsafe(16)

    # Store nonce + event_id in session/cache
    await redis.setex(f"shopify_oauth:{nonce}", 600, event_id)

    # Build OAuth URL
    params = {
        "client_id": SHOPIFY_API_KEY,
        "scope": "read_products,read_product_listings,read_files",
        "redirect_uri": f"{BASE_URL}/api/auth/shopify/callback",
        "state": nonce,
        "grant_options[]": "per-user"
    }

    auth_url = f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"

    return {"auth_url": auth_url}
```

**Step 3: Handle OAuth Callback**
```python
# backend/routers/shopify.py
@router.get("/api/auth/shopify/callback")
async def shopify_oauth_callback(
    code: str,
    shop: str,
    state: str,
    hmac: str
):
    """
    Shopify redirects here after user approves.
    Exchange code for access token.
    """
    # Verify HMAC (security check)
    if not verify_shopify_hmac(request.query_params, SHOPIFY_API_SECRET):
        raise HTTPException(403, "Invalid HMAC signature")

    # Verify nonce
    event_id = await redis.get(f"shopify_oauth:{state}")
    if not event_id:
        raise HTTPException(400, "Invalid or expired state")

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": SHOPIFY_API_KEY,
                "client_secret": SHOPIFY_API_SECRET,
                "code": code
            }
        )

        if response.status_code != 200:
            raise HTTPException(500, "Failed to get access token")

        data = response.json()
        access_token = data["access_token"]

    # Store in database
    await update_event(event_id, {
        "shopify_store_url": f"https://{shop}",
        "shopify_access_token": encrypt(access_token),  # Encrypt token!
        "shopify_connected_at": datetime.utcnow()
    })

    # Redirect to success page
    return RedirectResponse(f"{FRONTEND_URL}/events/{event_id}?shopify=connected")


def verify_shopify_hmac(params: dict, secret: str) -> bool:
    """Verify Shopify HMAC signature for security."""
    provided_hmac = params.pop('hmac', None)
    if not provided_hmac:
        return False

    # Build sorted query string
    sorted_params = sorted(params.items())
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

    # Calculate HMAC
    computed_hmac = hmac.new(
        secret.encode(),
        query_string.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_hmac, provided_hmac)
```

**Step 4: Fetch Products**
```python
# backend/services/shopify.py
import httpx

class ShopifyService:
    def __init__(self, shop_url: str, access_token: str):
        self.shop_url = shop_url
        self.access_token = access_token
        self.api_version = "2024-01"

    async def get_products(self, limit: int = 10) -> list[dict]:
        """Fetch products from Shopify store."""
        url = f"{self.shop_url}/admin/api/{self.api_version}/products.json"

        headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=headers,
                params={"limit": limit, "status": "active"}
            )

            if response.status_code != 200:
                raise HTTPException(500, f"Shopify API error: {response.text}")

            products = response.json()["products"]

            # Transform to our format
            return [
                {
                    "id": str(p["id"]),
                    "title": p["title"],
                    "description": p["body_html"],
                    "price": p["variants"][0]["price"],
                    "currency": p["variants"][0].get("currency_code", "USD"),
                    "image_url": p["images"][0]["src"] if p["images"] else None,
                    "checkout_url": f"{self.shop_url}/cart/{p['variants'][0]['id']}:1"
                }
                for p in products
            ]

# API endpoint
@router.get("/api/events/{event_id}/shopify/products")
async def get_shopify_products(event_id: str):
    """Fetch products from connected Shopify store."""
    event = await get_event(event_id)

    if not event.shopify_access_token:
        raise HTTPException(400, "Shopify store not connected")

    access_token = decrypt(event.shopify_access_token)

    shopify = ShopifyService(event.shopify_store_url, access_token)
    products = await shopify.get_products(limit=10)

    return {"products": products}
```

#### Security Considerations

**Token Encryption:**
```python
# backend/services/encryption.py
from cryptography.fernet import Fernet
import base64

# Generate key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
cipher = Fernet(ENCRYPTION_KEY.encode())

def encrypt(plaintext: str) -> str:
    """Encrypt sensitive data like access tokens."""
    return cipher.encrypt(plaintext.encode()).decode()

def decrypt(ciphertext: str) -> str:
    """Decrypt sensitive data."""
    return cipher.decrypt(ciphertext.encode()).decode()
```

**Database Schema Update:**
```sql
ALTER TABLE events ADD COLUMN shopify_store_url TEXT;
ALTER TABLE events ADD COLUMN shopify_access_token TEXT;  -- Encrypted
ALTER TABLE events ADD COLUMN shopify_connected_at TIMESTAMPTZ;
```

#### Frontend UI Flow

```tsx
// frontend/app/events/[id]/page.tsx
export default function EventPage({ params }: { params: { id: string } }) {
  const { data: event } = useQuery(['event', params.id], () => api.getEvent(params.id))
  const [shopDomain, setShopDomain] = useState('')

  const handleConnect = async () => {
    const { auth_url } = await api.getShopifyAuthUrl(params.id, shopDomain)
    window.location.href = auth_url
  }

  return (
    <div>
      {!event.shopify_store_url ? (
        <Card>
          <CardHeader>
            <CardTitle>Connect Shopify Store</CardTitle>
            <CardDescription>
              Connect your store to automatically insert product ads
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Input
                placeholder="your-store.myshopify.com"
                value={shopDomain}
                onChange={(e) => setShopDomain(e.target.value)}
              />
              <Button onClick={handleConnect}>
                Connect
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              Shopify Connected
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-gray-600">{event.shopify_store_url}</p>
            <Button variant="outline" size="sm" onClick={handleDisconnect}>
              Disconnect
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
```

#### Alternative: Shopify App Embed (Post-Hackathon)

For production, create embedded Shopify app:

1. **App Embed in Shopify Admin:**
   - Users install from Shopify App Store
   - Embedded UI inside Shopify admin
   - Auto-sync products on update

2. **Webhooks for Real-Time Updates:**
   ```python
   # Listen for product updates
   @router.post("/api/webhooks/shopify/products/update")
   async def shopify_product_webhook(request: Request):
       # Verify webhook signature
       hmac_header = request.headers.get('X-Shopify-Hmac-SHA256')
       if not verify_webhook_hmac(await request.body(), hmac_header):
           raise HTTPException(403, "Invalid webhook signature")

       product_data = await request.json()
       # Update cached product data
       await update_product_cache(product_data)
       return {"status": "received"}
   ```

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
events (id, user_id, name, event_type, status, shopify_store_url, sponsor_name, master_video_url, music_url, music_metadata JSONB)
videos (id, event_id, original_url, angle_type, sync_offset_ms, analysis_data JSONB, status)
timelines (id, event_id, segments JSONB, zooms JSONB, ad_slots JSONB, chapters JSONB, beat_synced BOOLEAN)
custom_reels (id, event_id, query TEXT, output_url, moments JSONB, duration_sec INT, created_at)

-- music_metadata JSONB example:
-- {
--   "tempo_bpm": 128.5,
--   "beat_times_ms": [0, 468, 937, ...],
--   "intro_end_ms": 2500,
--   "outro_start_ms": 175000,
--   "duration_ms": 180000,
--   "intensity_curve": [0.2, 0.3, 0.8, ...]
-- }
```

## API Endpoints
```
POST /api/events                     Create event
POST /api/events/:id/videos          Get presigned S3 URL
POST /api/events/:id/music/upload    Get presigned S3 URL for music upload
POST /api/events/:id/music/analyze   Analyze uploaded music (beats, tempo, intensity)
POST /api/events/:id/analyze         Start TwelveLabs analysis
POST /api/events/:id/generate        Generate final video (with music mix)
POST /api/events/:id/shopify         Connect Shopify store
POST /api/events/:id/sponsor         Set sponsor power plays
GET  /api/events/:id/chapters        Get chapter markers (JSON for player navigation)
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

    # Music Integration
    MUSIC_BEAT_SYNC_TOLERANCE_MS = 200  # How close to snap to beat
    MUSIC_FADE_IN_SEC = 2
    MUSIC_FADE_OUT_SEC = 3
    MUSIC_DUCK_SPEECH_VOLUME = 0.2  # 20% during speech
    MUSIC_BOOST_ACTION_VOLUME = 1.2  # 120% during highlights

SWITCHING_PROFILES = {
    "sports": {"ad_block_scenes": ["scoring_play"], "ad_boost_scenes": ["timeout"]},
    "ceremony": {"ad_block_scenes": ["name_announcement"], "ad_boost_scenes": ["pause"]}
}

MUSIC_MIX_PROFILES = {
    "sports": {"music_volume": 0.5, "event_volume": 0.8, "duck_speech": True},
    "ceremony": {"music_volume": 0.3, "event_volume": 1.0, "duck_speech": True},
    "performance": {"music_volume": 0.2, "event_volume": 1.0, "duck_speech": False}
}
```

**Benefits:** Easy tuning during demo without code changes, event-specific customization.

## Environment Variables
```
TWELVELABS_API_KEY, GOOGLE_API_KEY, SUPABASE_URL, SUPABASE_KEY
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET
REDIS_URL=redis://localhost:6379
SHOPIFY_API_KEY, SHOPIFY_API_SECRET, SHOPIFY_API_VERSION=2024-01
ENCRYPTION_KEY  # For encrypting Shopify access tokens (Fernet key)
BASE_URL=https://anchor.app  # Or http://localhost:8000 for dev
NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL, NEXT_PUBLIC_BASE_URL
```

## Dependencies
**Backend:** fastapi, uvicorn, celery[redis], twelvelabs, google-genai, ffmpeg-python, moviepy, librosa, scipy, supabase, boto3, httpx, cryptography
**Frontend:** next 14.x, react 18.x, @tanstack/react-query, @supabase/supabase-js, video.js

## File Structure
```
anchor/
├── frontend/app/, components/, lib/ (supabase.ts, api.ts)
├── backend/main.py, worker.py, routers/, services/
│   └── services: twelvelabs, veo, audio_sync, music_sync, timeline, zoom, overlay, chapters, sponsor, render
└── CLAUDE.md
```

## FEATURE 5: Personal Music Integration (Identity)

**Goal:** User uploads personal music that represents their identity - team anthem, graduation song, favorite track.

**Theme Connection:** Music is core to personal/team identity. This makes every highlight reel truly unique and meaningful.

### Upload & Storage
```python
# User uploads music file (MP3, WAV, M4A)
POST /api/events/:id/music/upload
# Returns presigned S3 URL for direct upload
# Store: events.music_url, events.music_metadata JSONB
```

### Beat Detection & Analysis
```python
import librosa
import numpy as np

def analyze_music_track(audio_path):
    """Extract beat timings and intensity for sync with video."""
    y, sr = librosa.load(audio_path, sr=22050, mono=True)

    # Detect beats
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times_ms = librosa.frames_to_time(beat_frames, sr=sr) * 1000

    # Analyze intensity per segment (for dynamic volume)
    rms = librosa.feature.rms(y=y)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    # Find intro/outro (low energy sections at start/end)
    intro_end_ms = find_intro_end(rms, sr) * 1000
    outro_start_ms = find_outro_start(rms, sr) * 1000

    return {
        "tempo_bpm": float(tempo),
        "beat_times_ms": beat_times_ms.tolist(),
        "intro_end_ms": intro_end_ms,
        "outro_start_ms": outro_start_ms,
        "duration_ms": int(len(y) / sr * 1000),
        "intensity_curve": rms.tolist()  # For ducking
    }
```

### Beat-Synced Cuts
```python
def align_cuts_to_beats(timeline_segments, beat_times_ms, tolerance_ms=200):
    """Snap angle switches and transitions to nearest beat."""
    synced_segments = []

    for segment in timeline_segments:
        # Find nearest beat within tolerance
        nearest_beat = min(beat_times_ms,
                          key=lambda b: abs(b - segment['start_ms']))

        if abs(nearest_beat - segment['start_ms']) <= tolerance_ms:
            # Snap to beat for professional feel
            segment['start_ms'] = nearest_beat
            segment['beat_synced'] = True

        synced_segments.append(segment)

    return synced_segments
```

### Audio Ducking (Speech Priority)
```python
def create_ducking_filter(music_metadata, speech_segments, action_intensity_timeline):
    """
    Lower music during speech, boost during high action.
    Creates FFmpeg volume filter string.
    """
    filters = []

    # Duck to 20% volume during speech
    for seg in speech_segments:
        filters.append(
            f"volume=0.2:enable='between(t,{seg['start_sec']},{seg['end_sec']})'"
        )

    # Boost to 120% during high action (goals, key moments)
    for moment in action_intensity_timeline:
        if moment['intensity'] >= 8:
            filters.append(
                f"volume=1.2:enable='between(t,{moment['start_sec']},{moment['end_sec']})'"
            )

    # Fade out during ad slots (product videos have their own audio)
    for ad in ad_slots:
        pre_fade = ad['timestamp_ms'] / 1000 - 0.5
        post_fade = (ad['timestamp_ms'] + ad['duration_ms']) / 1000 + 0.5
        filters.append(
            f"volume=0:enable='between(t,{pre_fade},{post_fade})'"
        )

    return ",".join(filters)
```

### Music Timing Options
```python
# Option 1: Loop music to match video length
def loop_music_to_video_duration(music_path, video_duration_ms, music_metadata):
    """Loop music seamlessly to fill entire video."""
    music_duration = music_metadata['duration_ms']

    if music_duration >= video_duration_ms:
        # Trim music to video length, use outro
        return trim_music_with_outro(music_path, video_duration_ms, music_metadata)
    else:
        # Loop music, crossfade loops at beat boundaries
        return loop_music_at_beats(music_path, video_duration_ms, music_metadata)

# Option 2: Start at first action, end naturally
def align_music_to_key_moments(music_metadata, video_timeline):
    """Start music at first high-action moment, let it play through."""
    first_action = next((m for m in video_timeline if m['intensity'] >= 7), None)

    if first_action:
        music_start_ms = first_action['timestamp_ms'] - music_metadata['intro_end_ms']
    else:
        music_start_ms = 0

    return {"music_start_offset_ms": max(0, music_start_ms)}
```

### FFmpeg Audio Mixing
```bash
# Basic mix: music + event audio with ducking
ffmpeg -i video.mp4 -i music.mp3 \
  -filter_complex \
    "[1:a]volume=0.6,afade=t=in:d=2:st=0,afade=t=out:d=3:st=57[music]; \
     [0:a]volume=1.0[event]; \
     [music][event]amix=inputs=2:duration=first:weights='0.4 1.0'[audio]" \
  -map 0:v -map "[audio]" output.mp4

# With ducking for speech
ffmpeg -i video.mp4 -i music.mp3 \
  -filter_complex \
    "[1:a]volume=0.6,volume=0.2:enable='between(t,10,15)',afade=t=in:d=2[music]; \
     [0:a]volume=1.0[event]; \
     [music][event]amix=inputs=2:duration=first[audio]" \
  -map 0:v -map "[audio]" output.mp4
```

### Smart Mixing Strategy
```python
def create_audio_mix_strategy(event_type, has_commentary, has_crowd_noise):
    """Determine optimal music/event audio balance."""

    if event_type == "ceremony" and has_commentary:
        # Prioritize speech (names being called)
        return {
            "music_base_volume": 0.3,
            "event_volume": 1.0,
            "duck_during_speech": True,
            "fade_in_duration_sec": 3,
            "fade_out_duration_sec": 4
        }

    elif event_type == "sports" and has_crowd_noise:
        # Balance music with crowd energy
        return {
            "music_base_volume": 0.5,
            "event_volume": 0.8,
            "duck_during_speech": True,
            "boost_on_action": True,  # Boost music during highlights
            "fade_in_duration_sec": 2,
            "fade_out_duration_sec": 3
        }

    elif event_type == "performance":
        # Music secondary to live performance
        return {
            "music_base_volume": 0.2,
            "event_volume": 1.0,
            "duck_during_speech": False,  # Performance audio is primary
            "fade_in_duration_sec": 4,
            "fade_out_duration_sec": 5
        }

    else:
        # Default balanced mix
        return {
            "music_base_volume": 0.4,
            "event_volume": 1.0,
            "duck_during_speech": True,
            "fade_in_duration_sec": 2,
            "fade_out_duration_sec": 3
        }
```

### Complete Integration
```python
async def integrate_personal_music(event_id, video_path, music_url):
    """Full pipeline for music integration."""

    # 1. Download and analyze music
    music_path = download_from_s3(music_url)
    music_metadata = analyze_music_track(music_path)

    # 2. Get video analysis (speech segments, action moments)
    timeline = get_timeline_analysis(event_id)
    speech_segments = extract_speech_segments(timeline)

    # 3. Align cuts to beats (if enabled)
    if user_preferences.beat_sync_enabled:
        timeline['segments'] = align_cuts_to_beats(
            timeline['segments'],
            music_metadata['beat_times_ms']
        )

    # 4. Create ducking filter
    ducking_filter = create_ducking_filter(
        music_metadata,
        speech_segments,
        timeline['action_intensity']
    )

    # 5. Determine mix strategy
    mix_strategy = create_audio_mix_strategy(
        event.event_type,
        has_commentary=len(speech_segments) > 0,
        has_crowd_noise=has_crowd_audio(timeline)
    )

    # 6. Render with FFmpeg
    output = render_with_music(
        video_path,
        music_path,
        music_metadata,
        mix_strategy,
        ducking_filter
    )

    return output
```

## Processing Pipeline
1. Sync audio (metadata rough → fingerprint fine)
2. TwelveLabs analysis (parallel)
3. **Analyze user's music track** (beats, intensity, intro/outro)
4. Generate angle-switching timeline
5. **Align cuts to music beats** (optional, configurable)
6. Identify zoom moments
7. Find ad slots (multi-factor scoring) + identify transition points
8. Generate Veo product videos (motion-matched) + color-grade to match footage
9. Insert product videos with seamless transitions (native replacement)
10. Add sponsor power plays (overlays)
11. Generate chapters
12. **Mix personal music with event audio** (ducking, beat-sync, fades)
13. FFmpeg render → S3

## Docker (Post-Hackathon)
Services: frontend (Next.js), backend (FastAPI), celery (workers), redis, postgres
One-command: `docker-compose up --build`

---

## Build Priority
```
Hours 0-4:   Setup (repos, Supabase, S3, API keys)
Hours 4-12:  Feature 1 (multi-angle switching)
Hours 12-20: Feature 2 (auto-zoom)
Hours 20-26: Feature 5 (personal music integration - IDENTITY THEME)
Hours 26-32: Feature 3 (Native ad integration: Veo + seamless transitions)
Hours 32-36: Polish, demo, pitch
Fallback:    Simple overlay if native integration too complex
Stretch:     Feature 4 (personal reels), Veo stylized replays
```

**Target Prizes:** TwelveLabs (full API), Shopify (shoppable video), Gemini (Veo generation), Top 3 Overall

**Theme Connection:** Music upload directly addresses "Identity" - users express their personal/team identity through their choice of soundtrack.
