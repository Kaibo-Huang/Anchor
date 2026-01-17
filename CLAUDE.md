CLAUDE.md - Anchor Project Context
Project Summary
AI-powered video production platform that transforms multi-angle phone footage into broadcast-quality highlight reels with native ad integration.
Hackathon Targets: TwelveLabs (Analysis) + Shopify (Commerce) + Gemini/Veo (Generative Video).
Core Theme: "Identity."
Tech Stack
code
Code
Frontend:    Next.js 14+ (App Router), Tailwind, React Query, Video.js
Backend:     Python 3.11+, FastAPI, Celery + Redis
Database:    Supabase (PostgreSQL + Auth + Realtime)
Storage:     AWS S3 (presigned URLs)
Video Ops:   FFmpeg (Primary processing), MoviePy (Animations), librosa (Audio sync)
AI APIs:     TwelveLabs (Marengo 2.7, Pegasus 1.2), Google Veo 3.1
Commerce:    Shopify Storefront API
Pkg Mgrs:    bun (frontend), uv (backend)
Video Tools: What Does What
FFmpeg: Cut, concat, crop, zoom, overlay, transitions, audio mix. (FAST, primary tool)
MoviePy: Complex animations, smooth zoom easing. (Slower, pythonic)
TwelveLabs: UNDERSTAND video (scene detection, objects, actions, faces, audio events).
Google Veo: GENERATE new video content (Ads, Transitions). NOT for editing real footage.
librosa: Audio analysis (sync videos via audio fingerprinting).
FFmpeg Quick Reference
code
Bash
# Cut clip
ffmpeg -i input.mp4 -ss 5 -t 10 -c copy output.mp4

# Crop/zoom (2x center crop)
ffmpeg -i input.mp4 -vf "crop=iw/2:ih/2:iw/4:ih/4,scale=1920:1080" output.mp4

# Overlay banner (show at t=5-10s)
ffmpeg -i video.mp4 -i banner.png -filter_complex "overlay=10:H-200:enable='between(t,5,10)'" output.mp4

# Crossfade two clips (0.5s fade)
ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex "xfade=transition=fade:duration=0.5:offset=4.5" output.mp4

# Zoom Pan (Ken Burns)
ffmpeg -i input.mp4 -vf "zoompan=z='min(zoom+0.001,1.5)':d=90:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" output.mp4
MoviePy (Animated Zooms)
code
Python
# Apply zoom per frame
clip = clip.resize(lambda t: 1 + 0.3 * min(t / 0.3, 1)) # 1x to 1.3x
clip = clip.crop(x_center=960, y_center=540, width=1920, height=1080)
Architecture Workflow
Upload: 12 videos → S3 → TwelveLabs Analysis → Audio Sync.
Feature 1: Multi-angle switching (Logic: Best angle per moment).
Feature 2: Auto-zoom on key moments (Logic: Action intensity + Object detection).
Feature 3: Native Ad Insertion (Logic: Veo generation + Shopify data).
Render: FFmpeg Assembly → S3 Output.
FEATURE 1: Multi-Angle Intelligent Switching
Goal: Sync 12 angles and automatically switch to the best view based on action.
1. Audio Sync (Hybrid: Metadata + Fingerprint)
Metadata is fast (O(n)) but inaccurate (~2s). Fingerprinting is slow but accurate (<100ms).
code
Python
import librosa
from scipy import signal
import numpy as np

def sync_videos(videos):
    # Step 1: Rough align via metadata creation_timestamp
    base_time = min(v.creation_timestamp for v in videos)
    rough_offsets = {v.id: int((v.creation_timestamp - base_time).total_seconds() * 1000) for v in videos}
    
    # Step 2: Fine-tune with audio correlation
    return audio_fingerprint_sync(videos, rough_offsets)

def audio_fingerprint_sync(videos, rough_offsets):
    ref_video = videos[0]
    ref_audio, sr = librosa.load(ref_video.path, sr=22050, mono=True)
    ref_onset = librosa.onset.onset_strength(y=ref_audio, sr=sr)
    
    offsets = {ref_video.id: 0}
    
    for v in videos[1:]:
        # Load and align
        audio, _ = librosa.load(v.path, sr=22050, mono=True)
        onset = librosa.onset.onset_strength(y=audio, sr=sr)
        
        corr = signal.correlate(ref_onset, onset, mode='full')
        lag = np.argmax(corr) - len(onset) + 1
        fine_offset_ms = int((lag / sr) * 1000)
        
        offsets[v.id] = rough_offsets[v.id] + fine_offset_ms
    return offsets
2. User Instructions Integration
Parse natural language instructions to guide the editor.
code
Python
def process_user_instructions(video, user_context):
    hints = { "manual_zooms": [], "focus_subjects": [], "angle_override": None, "priority_timestamps": [] }
    
    # Timestamps "2:34"
    import re
    timestamps = re.findall(r'(\d+):(\d+)', user_context.instructions or "")
    for min, sec in timestamps:
        hints["priority_timestamps"].append(int(min) * 60000 + int(sec) * 1000)
    
    # Subjects "focus on #23"
    if "focus on" in user_context.instructions.lower():
        subject = re.search(r'focus on ([^,\.]+)', user_context.instructions, re.I)
        if subject: hints["focus_subjects"].append(subject.group(1).strip())
    
    return hints
3. Switching Logic & Profiles
Score angles every 2 seconds. Apply constraints (min cut duration 4s).
code
Python
PROFILES = {
    "sports":   {"high_action": "closeup", "ball_near_goal": "goal_angle", "default": "wide"},
    "ceremony": {"name_called": "stage_closeup", "walking": "wide", "speech": "podium"},
    "general":  {"default": "wide", "high_action": "closeup"}
}

def generate_timeline(videos, analyses, user_hints, event_type, duration_ms):
    timeline = []
    current_angle = None
    last_switch = -4000
    
    for ts in range(0, duration_ms, 2000):
        scores = {}
        for v in videos:
            # Score based on Profile + TwelveLabs data
            base_score = score_angle(analyses[v.id], ts, PROFILES[event_type])
            
            # Boost for User Hints
            if is_user_priority(ts, user_hints[v.id]): base_score *= 1.5
            if is_focus_subject_visible(analyses[v.id], ts): base_score *= 1.3
            
            scores[v.id] = base_score
        
        best = max(scores, key=scores.get)
        if best != current_angle and (ts - last_switch) >= 4000:
            timeline.append({"start_ms": ts, "video_id": best})
            current_angle = best
            last_switch = ts
            
    return timeline
FEATURE 2: Context-Aware Auto-Zoom
Goal: "Ken Burns" effect on static shots during high-action moments.
Triggers: action_intensity > 8, audio events ("cheer", "goal"), or user manual timestamp.
Constraint: Never zoom existing closeups (resolution loss).
code
Python
def calc_zoom(bbox, importance, frame_size):
    zoom = 2.5 if importance >= 0.85 else 1.8
    
    cx, cy = bbox["x"] + bbox["w"]/2, bbox["y"] + bbox["h"]/2
    crop_w, crop_h = frame_size[0]/zoom, frame_size[1]/zoom
    
    # Ensure crop stays within frame
    crop_x = max(0, min(cx - crop_w/2, frame_size[0] - crop_w))
    crop_y = max(0, min(cy - crop_h/2, frame_size[1] - crop_h))
    
    return {"zoom": zoom, "crop": (crop_x, crop_y, crop_w, crop_h), "duration": 3.5}
FEATURE 3: Native Brand Integration (Shopify + Veo)
Goal: Monetize videos by inserting product ads into low-intensity moments (timeouts, transitions).
3A. Generate Assets with Google Veo
Use Generative AI to create video from static product images.
code
Python
from google import genai

async def generate_product_video(product_image_url, product_name):
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    # Veo 3.1 for fast preview generation
    operation = client.models.generate_videos(
        model="veo-3.1-fast-preview",
        prompt=f"Product showcase, {product_name} rotating slowly, clean white background, studio lighting",
        image=await download_image(product_image_url),
    )
    
    # Poll until complete
    while not operation.done:
        await asyncio.sleep(3)
        operation = client.operations.get(operation)
    return operation.result.videos[0].uri
3B. Sponsor Power Plays (Templates)
Overlay templates for sponsored events.
Goal: "{Sponsor} GOAL CAM!"
Replay: "Instant Replay by {Sponsor}"
Timeout: "{Sponsor} Break"
3C. Smart Contextual Placement
Use TwelveLabs object detection to place banners on "safe" surfaces (walls, floors) rather than covering faces.
code
Python
def find_safe_placement(frame_analysis):
    # Avoid faces, scoreboard, ball
    exclusion_zones = [obj.bbox for obj in frame_analysis.objects if obj.type in ["face", "scoreboard", "ball"]]
    
    candidates = ["top_right", "bottom_left", "wall_area_1"]
    # Select candidate with least overlap with exclusion_zones
    return best_candidate
3D. Monetization Model
Affiliate: Generate links ?ref={event_id}.
Split: Creator (70%) / Anchor (30%).
Tiers: Free (Watermark), Creator (
19
)
,
P
r
o
(
19),Pro(
99).
FEATURE 4: Personalized Highlight Reels (Stretch)
Identify: TwelveLabs Face Clustering.
Filter: Select clips where Person_ID is visible && Focus is sharp.
Assemble: Concat clips + Personalized Title Card.
File Structure
code
Code
anchor/
├── frontend/
│   ├── app/ (Next.js App Router)
│   │   ├── events/[id]/page.tsx
│   │   └── page.tsx
│   ├── components/
│   ├── lib/ (supabase.ts, api.ts)
│   └── package.json
├── backend/
│   ├── main.py
│   ├── worker.py (Celery)
│   ├── routers/ (events.py, videos.py, shopify.py)
│   ├── services/
│   │   ├── twelvelabs.py
│   │   ├── veo.py
│   │   ├── audio_sync.py
│   │   ├── timeline.py
│   │   ├── zoom.py
│   │   └── render.py (FFmpeg wrapper)
│   └── pyproject.toml
├── CLAUDE.md
└── docker-compose.yml
Database Schema (Supabase)
code
SQL
events (
  id uuid PK, user_id uuid, name text, status text,
  shopify_store_url text, sponsor_name text, master_video_url text
)
videos (
  id uuid PK, event_id uuid, original_url text, s3_key text,
  angle_type text, sync_offset_ms int,
  user_instructions text, -- "Wide shot, focus on #23"
  analysis_data jsonb,    -- TwelveLabs output cache
  status text
)
timelines (
  id uuid PK, event_id uuid,
  segments jsonb, -- [{"start": 0, "vid": "A"}, ...]
  zooms jsonb,    -- [{"start": 5000, "rect": [...]}]
  ad_slots jsonb, -- [{"start": 15000, "product_id": "123"}]
  chapters jsonb  -- YouTube timestamps
)
personal_reels (
  id uuid PK, event_id uuid, person_name text, output_url text
)
API Endpoints
code
Code
POST   /api/events                      Create event
POST   /api/events/:id/videos           Get presigned S3 URL
PATCH  /api/events/:id/videos/:video_id Update metadata (instructions)
POST   /api/events/:id/analyze          Start TwelveLabs analysis (Parallel)
POST   /api/events/:id/generate         Generate final video
POST   /api/events/:id/shopify          Connect Shopify store
GET    /api/events/:id/chapters         Get generated timestamps
Development Commands
code
Bash
# Frontend
cd frontend && bun install && bun dev

# Backend  
cd backend && uv sync && uv run uvicorn main:app --reload

# Celery Worker
cd backend && uv run celery -A worker worker --loglevel=info

# Redis (Required for Celery)
docker run -d -p 6379:6379 redis:alpine
Docker Deployment (Roadmap)
code
Yaml
services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [backend]
  
  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [redis]
    volumes: ["./temp:/app/temp"]
  
  celery:
    build: ./backend
    command: celery -A worker worker
    depends_on: [redis, backend]
    volumes: ["./temp:/app/temp"]
  
  redis:
    image: redis:alpine
Build Priority (Hackathon)
Setup: Repos, Supabase, S3.
Core: Feature 1 (Sync + Switching).
Visuals: Feature 2 (Auto-Zoom).
Prize Differentiator: Feature 3 (Veo Ads + Shopify).
Polish: UI + Feature 4 (Personal Reels).