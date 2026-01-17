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
| FFmpeg | Cut, concat, crop, zoom, overlay, transitions, audio mix (FAST - PRIMARY TOOL) |
| ffmpeg-python | Construct FFmpeg commands in Python, execute binary (NOT frame loops) |
| TwelveLabs | UNDERSTAND video: scene detection, objects, actions, faces, audio + embeddings |
| Google Veo | GENERATE new video from text/images (ads, NOT for editing footage) |
| librosa | Audio fingerprinting for multi-angle sync |

**CRITICAL: Use FFmpeg for 95% of video tasks. Never process frames in Python loops - it will timeout on 4K video.**

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
# Ken Burns zoom (smooth easing with zoompan)
ffmpeg -i input.mp4 -vf "zoompan=z='min(zoom+0.001,1.5)':d=90:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" output.mp4
# Advanced zoom with ease-in/ease-out
ffmpeg -i input.mp4 -vf "zoompan=z='if(lte(on,9),1+(0.5/9)*on,if(lte(on,60),1.5,1.5-(0.5/9)*(on-60)))':d=70:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" output.mp4
```

## ffmpeg-python Usage (Build Commands, Not Frame Processing)
```python
import ffmpeg

# CORRECT: Build and execute FFmpeg command
(
    ffmpeg
    .input('input.mp4')
    .filter('zoompan', z='min(zoom+0.001,1.5)', d=90, x='iw/2-(iw/zoom/2)', y='ih/2-(ih/zoom/2)')
    .output('output.mp4')
    .run()
)

# WRONG: Never do frame-by-frame processing in Python
# for frame in video:  # TIMEOUT on 4K video!
#     process_frame(frame)
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
Upload up to 12 videos → S3 → Audio sync → TwelveLabs analysis
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

### TwelveLabs Analysis (with Embeddings)
```python
client = TwelveLabs(api_key=KEY)

# Create index with embedding engine for style matching
index = client.index.create(
    name=f"event_{id}",
    engines=[
        {"name": "marengo2.7", "options": ["visual", "audio"]},
        {"name": "pegasus1.2", "options": ["visual"]}  # For embeddings
    ]
)

task = client.task.create(index_id=index.id, url=s3_url)
# Returns: scene classification, objects, audio events, action_intensity (1-10)

# USE EMBEDDINGS for style/vibe matching (not just keyword search)
# Example: Match "High Energy" segments
def find_high_energy_segments(index_id):
    """
    Use vector embeddings to find segments matching a vibe/identity.
    Better than keyword search for subjective qualities like "energy" or "emotion".
    """
    # Create embedding vector for "High Energy" reference
    high_energy_query = "fast movement, intense action, crowd cheering, high energy"

    # Use semantic search with embeddings
    search_results = client.search.query(
        index_id=index_id,
        query_text=high_energy_query,
        search_options=["visual", "audio"],
        operator="or"
    )

    # OR: Use embeddings endpoint directly for vector similarity
    embeddings = client.embed.task.create(
        engine_name="marengo2.7",
        video_url=s3_url
    )

    # Compare embeddings to "identity" vectors (High Energy, Calm, Emotional, etc.)
    # This maps the VIDEO IDENTITY to user preference
    return embeddings

# Use embeddings to match video style to user's desired "Identity" theme
def match_video_identity_to_preference(segment_embeddings, identity_preference):
    """
    Identity theme: Compare video segment embeddings to identity anchor vectors.
    Example: User selects "High Energy" → find segments with similar vector.
    """
    identity_anchors = {
        "high_energy": [0.8, 0.2, ...],  # Pre-computed or reference embedding
        "emotional": [0.3, 0.9, ...],
        "calm": [0.1, 0.1, ...]
    }

    anchor_vector = identity_anchors[identity_preference]

    # Compute cosine similarity between segment and anchor
    from scipy.spatial.distance import cosine
    scores = []
    for seg_embedding in segment_embeddings:
        similarity = 1 - cosine(seg_embedding, anchor_vector)
        scores.append(similarity)

    return scores  # Higher score = better identity match
```

**WHY EMBEDDINGS:** Maps the "Identity" of video style. If user selects "High Energy" vibe, compare vector embeddings of segments to a "High Energy" anchor, rather than just keyword searching for "running." More accurate for subjective qualities.

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

**CRITICAL: Use FFmpeg zoompan filter exclusively. Never process frames in Python - will timeout on 4K.**

### Triggers
- action_intensity > 8, audio events ("cheer", "goal"), user timestamps
- Only zoom wide/medium shots (never closeups—resolution loss)
- Max 1 zoom per 10s

### Zoom Implementation (FFmpeg Only)
```python
import ffmpeg
from config import VideoConfig

def apply_zoom_to_moment(input_path, output_path, zoom_start_sec, zoom_duration_sec, importance):
    """
    Apply Ken Burns zoom using FFmpeg zoompan filter.
    NEVER use Python frame loops - use FFmpeg binary for speed.
    """
    # Determine zoom factor
    zoom_factor = VideoConfig.ZOOM_FACTOR_HIGH if importance >= 0.85 else VideoConfig.ZOOM_FACTOR_MED

    # Calculate frame counts (assuming 30fps)
    fps = 30
    ease_in_frames = int(0.3 * fps)  # 0.3s ease-in
    hold_frames = int((zoom_duration_sec - 0.6) * fps)  # Hold time
    ease_out_frames = int(0.3 * fps)  # 0.3s ease-out
    total_frames = ease_in_frames + hold_frames + ease_out_frames

    # FFmpeg zoompan expression with ease-in, hold, ease-out
    # on=frame number, d=duration in frames
    zoom_expr = (
        f"if(lte(on,{ease_in_frames}),"
        f"1+({zoom_factor - 1}/{ease_in_frames})*on,"  # Ease in
        f"if(lte(on,{ease_in_frames + hold_frames}),"
        f"{zoom_factor},"  # Hold
        f"{zoom_factor}-({zoom_factor - 1}/{ease_out_frames})*(on-{ease_in_frames + hold_frames})))"  # Ease out
    )

    # Build FFmpeg command (NO PYTHON FRAME PROCESSING)
    (
        ffmpeg
        .input(input_path, ss=zoom_start_sec, t=zoom_duration_sec)
        .filter('zoompan',
                z=zoom_expr,
                d=total_frames,
                x='iw/2-(iw/zoom/2)',  # Center x
                y='ih/2-(ih/zoom/2)',  # Center y
                s='1920x1080')
        .output(output_path, vcodec='libx264', crf=18)
        .overwrite_output()
        .run()
    )

def generate_zoom_segments(timeline, analysis_data):
    """
    Identify moments for zoom based on TwelveLabs analysis.
    Use embeddings to find high-intensity moments matching desired vibe.
    """
    zoom_moments = []

    for segment in timeline:
        # Use TwelveLabs action_intensity
        if segment.get('action_intensity', 0) > VideoConfig.ZOOM_MIN_ACTION:
            # Check shot type (only zoom wide/medium shots)
            shot_type = segment.get('shot_type', 'unknown')
            if shot_type in ['wide', 'medium']:
                zoom_moments.append({
                    'start_sec': segment['start_sec'],
                    'duration_sec': min(segment['duration_sec'], 5),  # Max 5s zoom
                    'importance': segment['action_intensity'] / 10,  # Normalize to 0-1
                    'bbox_center': segment.get('primary_object_bbox', (0.5, 0.5))  # For targeted zoom
                })

    # Enforce spacing constraint (max 1 per 10s)
    spaced_moments = []
    last_zoom_time = -999
    for moment in sorted(zoom_moments, key=lambda m: m['importance'], reverse=True):
        if moment['start_sec'] - last_zoom_time >= VideoConfig.ZOOM_MIN_SPACING_SEC:
            spaced_moments.append(moment)
            last_zoom_time = moment['start_sec']

    return spaced_moments
```

**Performance Note:** FFmpeg zoompan processes 4K video in real-time. Python frame loops would take 100x longer.

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

## FEATURE 4: On-Demand Highlight Reels (CORE IDENTITY FEATURE)

**Goal:** Users create personalized highlight reels about THEMSELVES or specific people using natural language.

**Identity Theme Connection:** This is the STRONGEST identity feature - users search for "me," "my best moments," "when I scored" to find THEIR identity in the footage. It's literally about finding yourself.

**Examples:**
- "me" / "show me" / "my best moments"
- "player 23" / "number 23"
- "guy in yellow pants" / "person in red jersey"
- "the goalie" / "the person who scored first"
- "me celebrating" / "me scoring"
- "emotional moments with me"

### Flow
1. **User submits query + vibe preference + duration** via API/UI
2. **Calculate chunks needed** from requested duration (see below)
3. **TwelveLabs natural language search with embeddings** → fetch candidate moments
4. **Embedding-based ranking** by vibe (High Energy, Emotional, Calm) + confidence
5. **Select clips using actual durations** to fill requested time exactly
6. **Render with FFmpeg** → add title card, concatenate clips with crossfades, add user's music
7. **Return S3 URL** instantly (<10 seconds)

### Duration → Chunk Calculation
```python
from config import ReelConfig

def calculate_chunks_needed(requested_duration_sec: int) -> int:
    """
    Calculate how many highlight moments to fetch based on requested reel duration.
    Uses estimate for initial fetch, then actual durations for final selection.
    """
    effective_per_clip = ReelConfig.AVG_MOMENT_DURATION_SEC + ReelConfig.TRANSITION_DURATION_SEC
    base_chunks = int(requested_duration_sec / effective_per_clip)

    # Fetch extra to allow ranking/filtering
    return max(ReelConfig.MIN_MOMENTS, int(base_chunks * ReelConfig.FETCH_MULTIPLIER))

def select_clips_for_duration(ranked_clips: list, target_duration_sec: int) -> list:
    """
    Select clips using ACTUAL durations from TwelveLabs results.
    """
    selected = []
    total_duration = 0

    for clip in ranked_clips:
        actual_duration = clip.end - clip.start  # Real duration from search results
        if total_duration + actual_duration <= target_duration_sec:
            selected.append(clip)
            total_duration += actual_duration

    return selected, total_duration

# Examples (with default config):
# "30 second reel" → fetch ~14 candidates, select ~8 using actual durations
# "1 minute highlight" → fetch ~26 candidates, select ~15
# "15 second teaser" → fetch ~7 candidates, select ~4
```

### Implementation with Embeddings
```python
from scipy.spatial.distance import cosine
import ffmpeg

# API endpoint
@router.post("/api/events/{event_id}/reels/generate")
async def generate_personal_highlight_reel(
    event_id: str,
    query: str,  # e.g., "me", "player 23", "guy in yellow pants"
    vibe: str = "high_energy",  # "high_energy", "emotional", "calm"
    duration: int = 30,
    include_music: bool = True
):
    """
    Generate personalized highlight reel using natural language + embeddings.
    IDENTITY FEATURE: Find "me" in the video based on query.
    """
    event = await get_event(event_id)

    # 1. TwelveLabs natural language search
    search_results = client.search.query(
        index_id=event.twelvelabs_index_id,
        query_text=query,
        search_options=["visual", "conversation"],
        operator="or",
        page_limit=20  # Get top 20 candidate moments
    )

    # 2. Get embeddings for candidate moments
    candidate_embeddings = []
    for result in search_results.data:
        embedding = await get_segment_embedding(
            event.twelvelabs_index_id,
            result.video_id,
            result.start,
            result.end
        )
        candidate_embeddings.append({
            "video_id": result.video_id,
            "start": result.start,
            "end": result.end,
            "confidence": result.confidence,
            "embedding": embedding
        })

    # 3. Rank by embedding similarity to desired vibe
    identity_anchors = {
        "high_energy": get_identity_vector("high_energy"),
        "emotional": get_identity_vector("emotional"),
        "calm": get_identity_vector("calm")
    }

    vibe_vector = identity_anchors[vibe]

    scored_moments = []
    for moment in candidate_embeddings:
        # Combine text search confidence + embedding similarity
        text_score = moment["confidence"]
        vibe_score = 1 - cosine(moment["embedding"], vibe_vector)

        # Weighted combination: 60% vibe match, 40% text match
        final_score = 0.6 * vibe_score + 0.4 * text_score

        scored_moments.append({
            **moment,
            "final_score": final_score,
            "vibe_score": vibe_score
        })

    # 4. Select top moments to fill duration
    top_moments = sorted(scored_moments, key=lambda m: m["final_score"], reverse=True)

    selected_clips = []
    total_duration = 0
    for moment in top_moments:
        clip_duration = moment["end"] - moment["start"]
        if total_duration + clip_duration <= duration:
            selected_clips.append(moment)
            total_duration += clip_duration
        if total_duration >= duration:
            break

    # 5. Build FFmpeg concat filter
    reel_id = generate_reel_id()
    output_path = f"/tmp/reel_{reel_id}.mp4"

    # Download clips from S3
    clip_paths = []
    for i, clip in enumerate(selected_clips):
        clip_path = f"/tmp/clip_{i}.mp4"
        await download_clip_segment(
            event.videos[clip["video_id"]].url,
            clip["start"],
            clip["end"],
            clip_path
        )
        clip_paths.append(clip_path)

    # 6. Render with crossfades and music
    await render_highlight_reel(
        clip_paths,
        output_path,
        title=f"{query.title()} - Highlight Reel",
        music_path=event.music_url if include_music else None,
        vibe=vibe
    )

    # 7. Upload to S3
    reel_url = await upload_to_s3(output_path, f"reels/{reel_id}.mp4")

    # 8. Save to database
    await create_custom_reel(
        event_id=event_id,
        query=query,
        vibe=vibe,
        output_url=reel_url,
        moments=selected_clips,
        duration_sec=total_duration
    )

    return {
        "reel_url": reel_url,
        "moments_count": len(selected_clips),
        "total_duration": total_duration,
        "vibe": vibe,
        "processing_time_ms": "< 10000"  # Instant results
    }


async def render_highlight_reel(
    clip_paths: list[str],
    output_path: str,
    title: str,
    music_path: str | None,
    vibe: str
):
    """
    Render highlight reel with crossfades and optional music.
    Uses FFmpeg exclusively for speed.
    """
    # Create title card (2 seconds)
    title_card_path = await generate_title_card(title, vibe)

    # Build concat with crossfades
    inputs = [ffmpeg.input(title_card_path)]
    inputs.extend([ffmpeg.input(path) for path in clip_paths])

    # Apply crossfade transitions (0.5s each)
    video = inputs[0]
    for i in range(1, len(inputs)):
        video = ffmpeg.filter([video, inputs[i]], 'xfade', transition='fade', duration=0.5)

    # Add music if provided
    if music_path:
        music = ffmpeg.input(music_path)
        audio = ffmpeg.filter([music, video], 'amix', inputs=2, duration='shortest')
        output = ffmpeg.output(video, audio, output_path, vcodec='libx264', acodec='aac')
    else:
        output = ffmpeg.output(video, output_path, vcodec='libx264', acodec='aac')

    ffmpeg.run(output, overwrite_output=True)


async def generate_title_card(title: str, vibe: str):
    """Generate title card with vibe-based styling."""
    vibe_styles = {
        "high_energy": {"bg_color": "#FF5722", "font_color": "white", "animation": "zoom"},
        "emotional": {"bg_color": "#3F51B5", "font_color": "white", "animation": "fade"},
        "calm": {"bg_color": "#4CAF50", "font_color": "white", "animation": "slide"}
    }

    style = vibe_styles[vibe]

    # Use FFmpeg to generate title card
    output_path = f"/tmp/title_{hash(title)}.mp4"
    (
        ffmpeg
        .input('color=c={}:s=1920x1080:d=2'.format(style["bg_color"]), f='lavfi')
        .drawtext(
            text=title,
            fontsize=72,
            fontcolor=style["font_color"],
            x='(w-text_w)/2',
            y='(h-text_h)/2'
        )
        .output(output_path, vcodec='libx264', pix_fmt='yuv420p')
        .overwrite_output()
        .run()
    )

    return output_path
```

### Frontend UI - Identity-Focused
```tsx
// frontend/components/PersonalReelGenerator.tsx
export function PersonalReelGenerator({ eventId }: { eventId: string }) {
  const [query, setQuery] = useState("")
  const [vibe, setVibe] = useState<"high_energy" | "emotional" | "calm">("high_energy")
  const { mutate: generateReel, isLoading } = useMutation(api.generateReel)

  const examples = [
    { query: "me", vibe: "high_energy", label: "My Best Moments" },
    { query: "me celebrating", vibe: "emotional", label: "My Celebrations" },
    { query: "me scoring", vibe: "high_energy", label: "My Goals" },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create Your Highlight Reel</CardTitle>
        <CardDescription>
          Find yourself in the video with natural language - "me", "my best moments", "when I scored"
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Natural Language Input */}
          <div>
            <Label>What do you want to see?</Label>
            <Input
              placeholder='Try: "me", "my best moments", "player 23"'
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          {/* Vibe Selection */}
          <div>
            <Label>Vibe / Identity</Label>
            <RadioGroup value={vibe} onValueChange={setVibe}>
              <div className="flex gap-4">
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="high_energy" id="high_energy" />
                  <Label htmlFor="high_energy">High Energy ⚡</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="emotional" id="emotional" />
                  <Label htmlFor="emotional">Emotional 💙</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="calm" id="calm" />
                  <Label htmlFor="calm">Calm 🌊</Label>
                </div>
              </div>
            </RadioGroup>
          </div>

          {/* Quick Examples */}
          <div>
            <Label>Quick Examples</Label>
            <div className="flex gap-2 flex-wrap">
              {examples.map((ex) => (
                <Button
                  key={ex.query}
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setQuery(ex.query)
                    setVibe(ex.vibe as any)
                  }}
                >
                  {ex.label}
                </Button>
              ))}
            </div>
          </div>

          <Button
            onClick={() => generateReel({ eventId, query, vibe })}
            disabled={!query || isLoading}
            className="w-full"
          >
            {isLoading ? "Generating..." : "Generate My Reel"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
```

### API Endpoints
```
POST /api/events/:id/reels/generate
Body: {
  "query": "me",
  "vibe": "high_energy",
  "duration": 30,
  "include_music": true
}

Returns: {
  "reel_url": "https://s3.../reel.mp4",
  "moments_count": 8,
  "total_duration": 28.5,
  "vibe": "high_energy",
  "processing_time_ms": 8234
}

GET /api/events/:id/reels
Returns: List of previously generated reels
```

### Benefits
- **STRONGEST Identity Feature:** Users literally search for "me" to find themselves
- **Instant Results:** <10s generation using existing TwelveLabs index
- **On-Demand:** No batch processing, no waiting
- **Embedding-Powered:** Matches vibe preference (High Energy, Emotional, Calm)
- **Demo Impact:** Live queries during presentation show real-time personalization
- **Natural Language:** "me celebrating," "my best moments" - intuitive for users
- **Music Integration:** Automatically adds user's personal music track

### Why This is Core to Identity Theme
1. **Personal Discovery:** Finding YOURSELF in multi-angle footage
2. **Self-Expression:** Choose vibe that matches YOUR identity
3. **Instant Gratification:** See YOUR moments instantly
4. **Shareable:** Download and share YOUR highlight reel on social media

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

class ReelConfig:
    # Duration → Chunk Calculation
    AVG_MOMENT_DURATION_SEC = 3.5    # Estimate for initial fetch count
    TRANSITION_DURATION_SEC = 0.5    # Crossfade time between clips
    FETCH_MULTIPLIER = 1.75          # Fetch extra for ranking quality
    MIN_MOMENTS = 3                  # Minimum clips in any reel
    DEFAULT_DURATION_SEC = 30        # Default reel length if not specified

    # Vibe Ranking Weights
    VIBE_WEIGHT = 0.6                # Weight for embedding similarity
    TEXT_MATCH_WEIGHT = 0.4          # Weight for TwelveLabs text confidence

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
**Backend:** fastapi, uvicorn, celery[redis], twelvelabs, google-genai, ffmpeg-python (command builder ONLY), librosa, scipy, supabase, boto3, httpx, cryptography, numpy
**Frontend:** next 14.x, react 18.x, @tanstack/react-query, @supabase/supabase-js, video.js

**Note:** MoviePy removed - use FFmpeg exclusively for performance. ffmpeg-python only used to build commands, not process frames.

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

## Processing Pipeline (Identity-First)

### Core Pipeline (Master Video)
1. Sync audio (metadata rough → fingerprint fine)
2. **TwelveLabs analysis with embeddings** (Marengo 2.7 + Pegasus 1.2) → enables all features
3. **Analyze user's music track** (beats, intensity, intro/outro) - optional
4. Generate angle-switching timeline with embedding-based scoring
5. **Align cuts to music beats** (optional, configurable)
6. Identify zoom moments using embeddings + action intensity
7. Find ad slots (multi-factor scoring) + identify transition points
8. Generate Veo product videos (motion-matched) + color-grade to match footage
9. Insert product videos with seamless transitions (native replacement)
10. Add sponsor power plays (overlays)
11. Generate chapters
12. **Mix personal music with event audio** (ducking, beat-sync, fades)
13. FFmpeg render → S3

### On-Demand Pipeline (Personal Highlight Reels - FAST)
1. **User submits query** ("me", "my best moments", "player 23") + vibe preference
2. **TwelveLabs search** → candidate moments from existing index
3. **Embedding ranking** → score moments by vibe similarity (High Energy, Emotional, Calm)
4. **Select top clips** → fill requested duration (default 30s)
5. **FFmpeg render** → concat with crossfades, add title card, mix music
6. **S3 upload** → instant URL (<10s total)

**Key Difference:** On-demand reels use EXISTING TwelveLabs index → no re-analysis → instant results. This is why Feature 4 is high priority - it's fast to implement and has huge demo impact.

## Docker (Post-Hackathon)
Services: frontend (Next.js), backend (FastAPI), celery (workers), redis, postgres
One-command: `docker-compose up --build`

---

## Degraded Mode / Fallback Strategies

**Goal:** Ensure every feature has graceful fallback when dependencies fail - critical for hackathon time constraints and demo reliability.

### Feature 1: Multi-Angle Switching
- **Primary:** librosa audio fingerprinting (<100ms sync accuracy)
- **Degraded Mode 1:** Metadata-only alignment with 5s accuracy + warning to user
- **Degraded Mode 2:** Manual offset adjustment UI (user drags timeline to sync)
- **Fallback:** Use first uploaded video as master, no switching
- **User Notification:** "Audio sync accuracy reduced - using device timestamps"

### Feature 2: Auto-Zoom
- **Primary:** FFmpeg zoompan with ease-in/ease-out
- **Degraded Mode:** Static crop (no smooth zoom) on high-action moments
- **Fallback:** Skip zoom entirely, log moments for manual review
- **User Notification:** None (feature is optional enhancement)

### Feature 3: Brand Integration
- **Primary:** Native video replacement with Veo-generated product ads + seamless transitions
- **Degraded Mode 1:** Static product images with Ken Burns effect instead of Veo video
- **Degraded Mode 2:** Simple overlay with product card (title, price, image)
- **Degraded Mode 3:** Lower-third banner with sponsor name only
- **Fallback:** Skip ad integration, return master video without ads
- **User Notification:** "Product video generation unavailable - using static overlay"

**Veo Failure Handling:**
```python
try:
    product_video = await generate_veo_video(product, transition_style)
except VeoAPIError as e:
    logger.warning(f"Veo generation failed: {e}, falling back to static overlay")
    product_video = create_static_product_card(product)  # FFmpeg with product image
except VeoTimeoutError:
    logger.warning("Veo timeout, skipping this ad slot")
    continue  # Move to next ad slot
```

### Feature 4: On-Demand Highlight Reels
- **Primary:** TwelveLabs natural language search + embedding-based vibe ranking
- **Degraded Mode 1:** Keyword matching only (no embeddings) with lower quality
- **Degraded Mode 2:** Manual timestamp selection UI
- **Fallback:** Return full video with chapters, user navigates manually
- **User Notification:** "Smart search unavailable - showing all matching clips"

**TwelveLabs Failure Handling:**
```python
try:
    search_results = await twelvelabs_search(query)
    if search_results.data:
        ranked_moments = rank_by_embedding_similarity(search_results, vibe)
    else:
        raise ValueError("No search results")
except (TwelveLabsAPIError, ValueError) as e:
    logger.warning(f"TwelveLabs search failed: {e}, falling back to keyword match")
    # Simple text matching in video filenames or user-provided descriptions
    ranked_moments = keyword_fallback_search(query, video_metadata)
    user_notification = "Using basic search - results may be less accurate"
```

### Feature 5: Personal Music Integration
- **Primary:** Beat-synced cuts + audio ducking + intensity-based volume
- **Degraded Mode 1:** Music loop with simple fade-in/out (no beat sync)
- **Degraded Mode 2:** Fixed 50/50 mix (no ducking)
- **Fallback:** Event audio only, no music
- **User Notification:** "Music analysis failed - using simple audio mix"

**librosa Failure Handling:**
```python
try:
    music_metadata = analyze_music_track(music_path)
    timeline = align_cuts_to_beats(timeline, music_metadata['beat_times_ms'])
except LibrosaError as e:
    logger.warning(f"Beat detection failed: {e}, using simple loop")
    music_metadata = {"duration_ms": get_audio_duration(music_path), "beat_times_ms": []}
    # No beat sync, just loop music to video length
```

### Cross-Cutting Concerns

**S3 Upload Failures:**
```python
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2

async def upload_with_retry(file_path, s3_key):
    for attempt in range(MAX_RETRIES):
        try:
            return await s3_client.upload_file(file_path, s3_key)
        except S3Error as e:
            if attempt == MAX_RETRIES - 1:
                raise HTTPException(500, f"Upload failed after {MAX_RETRIES} attempts")
            await asyncio.sleep(RETRY_DELAY_SEC * (attempt + 1))
```

**FFmpeg Rendering Failures:**
```python
try:
    ffmpeg_output = run_ffmpeg_command(cmd)
except FFmpegError as e:
    logger.error(f"FFmpeg failed: {e.stderr}")
    if "Conversion failed" in e.stderr:
        # Try with lower quality settings
        cmd_fallback = cmd.with_crf(28).with_preset('fast')
        ffmpeg_output = run_ffmpeg_command(cmd_fallback)
    else:
        raise HTTPException(500, "Video rendering failed - check input files")
```

**TwelveLabs Index Creation Timeout:**
```python
# Don't block user - process async and notify when ready
task = client.task.create(index_id=index.id, url=s3_url)

# Poll with timeout
max_wait_sec = 300  # 5 minutes
start = time.time()
while time.time() - start < max_wait_sec:
    status = client.task.get(task.id)
    if status.status == "ready":
        break
    await asyncio.sleep(5)
else:
    logger.warning(f"TwelveLabs indexing timeout for {s3_url}")
    # Mark video as "analysis_pending", allow user to proceed with basic features
    await update_video(video_id, {"status": "analysis_pending"})
    return {"status": "processing", "message": "Analysis taking longer than expected"}
```

### User Experience During Degradation

**Status Updates:**
```python
# Real-time status via Supabase Realtime
await supabase.table('events').update({
    "id": event_id,
    "processing_status": "rendering",
    "current_step": "Mixing audio (beat sync unavailable)",
    "warnings": ["Using simple audio mix - beat detection failed"]
}).execute()
```

**Frontend Handling:**
```tsx
// Show warnings but don't block
{event.warnings?.map(warning => (
  <Alert variant="warning" key={warning}>
    <AlertTriangle className="h-4 w-4" />
    <AlertDescription>{warning}</AlertDescription>
  </Alert>
))}
```

### Testing Degraded Modes

**Mock API Failures in Development:**
```python
# backend/config.py
class FeatureFlags:
    FORCE_AUDIO_SYNC_FAIL = os.getenv("FORCE_AUDIO_SYNC_FAIL") == "true"
    FORCE_VEO_FAIL = os.getenv("FORCE_VEO_FAIL") == "true"
    FORCE_TWELVELABS_FAIL = os.getenv("FORCE_TWELVELABS_FAIL") == "true"

# Use in services
if FeatureFlags.FORCE_VEO_FAIL:
    raise VeoAPIError("Simulated failure for testing")
```

**Demo Script Includes Fallback Demo:**
- Show primary flow working
- Trigger degraded mode (disconnect API key)
- Show graceful fallback + user notification
- Re-enable and show recovery

---

## Build Priority (IDENTITY-FIRST)
```
Hours 0-4:   Setup (repos, Supabase, S3, API keys, TwelveLabs embeddings)
Hours 4-12:  Feature 1 (multi-angle switching with embedding-based scoring + degraded mode)
Hours 12-18: Feature 4 (On-Demand Highlight Reels - CORE IDENTITY FEATURE + keyword fallback)
Hours 18-24: Feature 5 (personal music integration - IDENTITY THEME + simple mix fallback)
Hours 24-28: Feature 2 (auto-zoom with FFmpeg + static crop fallback)
Hours 28-34: Feature 3 (Native ad integration: Veo + seamless transitions + overlay fallback)
Hours 34-36: Polish, demo, pitch
Fallback:    Simple overlay if native integration too complex
Stretch:     Veo stylized replays, advanced color grading
```

**Target Prizes:** TwelveLabs (embeddings + search), Shopify (shoppable video), Gemini (Veo generation), Top 3 Overall

**Theme Connection - "Identity":**
1. **Feature 4 (Personal Highlight Reels):** Users create highlight reels about THEMSELVES using natural language - "show me my best moments," "when I scored," "me celebrating." This is the STRONGEST identity feature - it's literally about finding yourself in the video.
2. **Feature 5 (Personal Music):** Users express their personal/team identity through their choice of soundtrack.
3. **Embeddings Throughout:** Match video segments to user's desired vibe/identity (High Energy, Emotional, Calm).

**Why Feature 4 is Prioritized:**
- **Strongest Identity Connection:** Natural language search for "me," "player 23," "guy in yellow pants" - finding YOUR identity in footage
- **Fast Implementation:** Uses existing TwelveLabs index, no rendering pipeline complexity
- **Instant Results:** On-demand generation, no batch processing delays
- **Demo Impact:** Live queries during presentation - "show me when I scored" → instant 30s reel
- **Embedding Showcase:** Perfect use case for TwelveLabs embeddings + semantic search
