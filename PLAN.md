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
Upload up to 12 videos → S3 → Audio sync (metadata + fingerprint) → TwelveLabs analysis 
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
- Upload up to 12 videos to S3
- User can provide context/instructions per video:
  - Angle description ("wide shot from bleachers", "closeup of stage")
  - Highlight preferences ("focus on #23", "zoom at 2:34 when goal happens")
  - Manual timestamp markers ("important moment at 1:45")
- Auto-detect angle type via TwelveLabs (first 5 sec): wide, closeup, crowd, stage
- Process uploads in parallel (all 12 videos uploaded simultaneously)

**2. Audio Sync (Hybrid: Metadata + Fingerprint)**

**Optimization for 12 videos:** Parallelize audio sync by comparing all videos against reference simultaneously. Metadata rough alignment is O(n), fingerprinting parallelizes well across workers.

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

**3. TwelveLabs Analysis + Chapter Generation (Parallelized for 12 Videos)**

All TwelveLabs work happens upfront: video analysis, scene classification, and chapter generation.

```python
import asyncio

client = TwelveLabs(api_key=KEY)
index = client.index.create(name=f"event_{id}", engines=[{"name": "marengo2.7", "options": ["visual", "audio"]}])

# Submit all videos for analysis in parallel
tasks = [client.task.create(index_id=index.id, url=video.s3_url) for video in videos]

# Wait for all to complete (non-blocking)
async def wait_for_all_analyses():
    return await asyncio.gather(*[task.wait_for_done() for task in tasks])

analyses = asyncio.run(wait_for_all_analyses())

# Returns per 2-3 sec: scene classification, objects, audio events, action intensity (1-10)
# Cache results aggressively to avoid re-analysis on timeline regeneration
```

**Chapter Generation (from TwelveLabs data)**

Auto-generate YouTube-compatible chapter timestamps from scene classification + transcription:

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
        return extract_key_phrase(segment["text"])

    if scenes:
        scene = find_scene_at(scenes, segment["start_ms"])
        if scene:
            return scene.classification

    return f"Segment {segment.get('index', 0) + 1}"
```

**4. User Instructions Integration**

```python
def process_user_instructions(video, user_context):
    """
    Parse user-provided instructions and convert to timeline hints.
    Examples:
    - "zoom at 2:34" → add zoom trigger at 154000ms
    - "focus on #23" → increase weight for shots with player #23
    - "this is the wide angle" → override auto-detected angle type
    """
    hints = {
        "manual_zooms": [],
        "focus_subjects": [],
        "angle_override": None,
        "priority_timestamps": []
    }
    
    # Parse timestamp mentions (2:34, 1:45, etc.)
    import re
    timestamps = re.findall(r'(\d+):(\d+)', user_context.instructions or "")
    for min, sec in timestamps:
        hints["priority_timestamps"].append(int(min) * 60000 + int(sec) * 1000)
    
    # Parse focus subjects (jersey numbers, names, objects)
    if "focus on" in user_context.instructions.lower():
        subject = re.search(r'focus on ([^,\.]+)', user_context.instructions, re.I)
        if subject:
            hints["focus_subjects"].append(subject.group(1).strip())
    
    # Manual angle type
    angle_keywords = {"wide": ["wide", "full court", "full field", "bleachers"],
                     "closeup": ["closeup", "close up", "tight", "zoomed"],
                     "crowd": ["crowd", "audience", "fans"],
                     "stage": ["stage", "podium", "platform"]}
    
    for angle, keywords in angle_keywords.items():
        if any(kw in user_context.instructions.lower() for kw in keywords):
            hints["angle_override"] = angle
            break
    
    return hints
```

**5. Analysis Chunking (Hybrid: Transcription + Fixed Intervals)**

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

**7. Angle Selection Algorithm (with User Hints)**
```python
def generate_timeline(videos, analyses, user_hints, event_type, duration_ms):
    """
    Select best angle per moment, incorporating user instructions.
    Optimized for 12 videos: scores cached per timestamp, progressive preview available.
    """
    profile = PROFILES.get(event_type, PROFILES["general"])
    timeline = []
    current_angle = None
    last_switch = -4000  # min 4 sec between switches
    
    for ts in range(0, duration_ms, 2000):  # every 2 sec
        scores = {}
        for v in videos:
            local_ts = ts - v.sync_offset
            if 0 <= local_ts <= v.duration:
                base_score = score_angle(analyses[v.id], local_ts, profile)
                
                # Boost score if user marked this timestamp as important
                hints = user_hints.get(v.id, {})
                if any(abs(ts - priority_ts) < 5000 for priority_ts in hints.get("priority_timestamps", [])):
                    base_score *= 1.5  # 50% boost for user-highlighted moments
                
                # Boost if user's focus subject is visible
                if hints.get("focus_subjects"):
                    for subject in hints["focus_subjects"]:
                        if subject_visible(analyses[v.id], local_ts, subject):
                            base_score *= 1.3
                
                scores[v.id] = base_score
        
        best = max(scores, key=scores.get) if scores else current_angle
        if best != current_angle and (ts - last_switch) >= 4000:
            timeline.append({"start_ms": ts, "video_id": best})
            current_angle = best
            last_switch = ts
    
    return timeline

def subject_visible(analysis, timestamp_ms, subject_query):
    """Check if subject (person, object, jersey number) is visible at timestamp."""
    # Check TwelveLabs text recognition and object detection
    # e.g., jersey number "23" or person name from OCR/face recognition
    return False  # Placeholder implementation
```

**8. FFmpeg Assembly**
```bash
# Cut clips per timeline segment
ffmpeg -i input.mp4 -ss START -t DURATION -c copy clip.mp4

# Concat with crossfade (0.5 sec)
ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex "xfade=transition=fade:duration=0.5" output.mp4
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

**What:** Replace video segments with AI-generated Shopify product ads at natural transition points (TV commercial break experience).

**Approach:** Native Content Integration (seamless video replacement with crossfade transitions)

**Fallback:** If time-constrained, use simple overlay approach (see section 3D)

---

### Implementation: Native Video Replacement

**1. Find Ad Slots (Enhanced Multi-Factor Scoring)**

Use intelligent scoring instead of simple threshold to prevent ad fatigue:

```python
def calculate_ad_suitability_score(ts_analysis, context):
    """Score 0-100: higher = better placement. Only 70+ considered."""
    score = 0

    # Factor 1: Action Intensity (40 pts max)
    if ts_analysis.action_intensity <= 2:
        score += 40
    elif ts_analysis.action_intensity <= 3:
        score += 25
    elif ts_analysis.action_intensity <= 4:
        score += 10

    # Factor 2: Audio Context (25 pts max)
    IDEAL_AUDIO = {"timeout": 25, "halftime": 25, "pause": 25,
                   "transition": 20, "break": 25, "whistle": 15}
    audio_score = max([IDEAL_AUDIO.get(e, 0) for e in ts_analysis.audio_events], default=0)
    score += audio_score

    # Factor 3: Scene Transition (20 pts max)
    if ts_analysis.is_scene_boundary:
        score += 20
    elif ts_analysis.is_camera_switch:
        score += 15

    # Factor 4: Visual Complexity (15 pts max - lower is better)
    if ts_analysis.visual_complexity < 0.3:
        score += 15
    elif ts_analysis.visual_complexity < 0.5:
        score += 10

    # PENALTIES

    # Hard block if ad within 45 seconds
    time_since_last_ad = ts_analysis.timestamp_ms - context.last_ad_timestamp
    if time_since_last_ad < 45000:
        return 0

    # Penalty for nearby key moments (goals, scores)
    if any(abs(ts_analysis.timestamp_ms - km.timestamp) < 8000
           for km in context.key_moments):
        score *= 0.3

    # Penalty for active speech (engaging content)
    if ts_analysis.has_active_speech:
        score *= 0.5

    # Penalty for high crowd energy
    if ts_analysis.crowd_energy > 0.7:
        score *= 0.4

    return score

def select_optimal_ad_slots(timeline_analysis, event_type, duration_ms):
    """Select best N ad slots with constraints."""
    # Dynamic max ads: 1 per 4 minutes (max 8 total)
    max_ads = min(int(duration_ms / 240000), 8)
    if duration_ms < 120000:  # <2 min
        max_ads = 1

    # Score all candidates
    context = {"last_ad_timestamp": -999999,
               "key_moments": [m for m in timeline_analysis
                              if m.action_intensity >= 8 or
                              m.scene_classification in ["goal", "score", "name_called"]]}

    candidates = []
    for ts in timeline_analysis:
        score = calculate_ad_suitability_score(ts, context)

        # Event-specific adjustments
        if event_type == "sports":
            if ts.scene_classification in ["scoring_play", "fast_break"]:
                score = 0  # Hard block
            elif ts.scene_classification in ["timeout", "halftime"]:
                score *= 1.5

        if score >= 70:
            candidates.append({"timestamp_ms": ts.timestamp_ms,
                             "score": score, "duration_ms": 4000})

    # Greedy selection with spacing
    candidates.sort(key=lambda x: x["score"], reverse=True)
    selected = []

    for c in candidates:
        # Check 45s spacing + not in first/last 10s
        if (c["timestamp_ms"] > 10000 and
            c["timestamp_ms"] < duration_ms - 10000 and
            all(abs(c["timestamp_ms"] - s["timestamp_ms"]) >= 45000 for s in selected)):

            selected.append(c)
            if len(selected) >= max_ads:
                break

    return sorted(selected, key=lambda x: x["timestamp_ms"])
```

**Result:** 3-4 carefully selected ads instead of 20-30 intrusive placements.

---

**2. Find Natural Transition Points**
```python
def find_transition_opportunities(timeline_analysis, ad_slots):
    """Find moments where we can cleanly cut to product video."""
    opportunities = []

    for slot in ad_slots:
        ts = slot["timestamp_ms"]
        analysis = get_analysis_at_timestamp(timeline_analysis, ts)

        # Priority 1: Scene boundaries (fade to black, cuts)
        if analysis.is_scene_boundary:
            opportunities.append({
                "timestamp_ms": ts,
                "type": "scene_cut",
                "transition": "crossfade",
                "duration": 500,  # 0.5s transition
                "confidence": 0.95
            })

        # Priority 2: Camera pans/movements
        elif analysis.camera_movement in ["pan_left", "pan_right", "zoom_out"]:
            opportunities.append({
                "timestamp_ms": ts,
                "type": "camera_pan",
                "transition": "continue_motion",  # Match pan direction
                "duration": 800,
                "confidence": 0.85
            })

        # Priority 3: Angle switches (already cutting between cameras)
        elif analysis.is_angle_switch:
            opportunities.append({
                "timestamp_ms": ts,
                "type": "angle_switch",
                "transition": "cut",  # Hard cut already happening
                "duration": 0,
                "confidence": 0.90
            })

    return opportunities
```

**3. Fetch Shopify Products**
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

**4. Generate Product Video with Veo (Motion-Matched)** ⭐ (Differentiator)
```python
from google import genai

async def generate_product_video_with_motion(product, transition_type):
    """Generate Veo video that matches the transition style for seamless integration."""
    client = genai.Client(api_key=GOOGLE_API_KEY)

    # Download product image
    image_data = await download_image(product.image_url)

    # Base prompt
    base_prompt = f"Product showcase, {product.name}, studio lighting, commercial quality"

    # Add motion matching for seamless transition
    if transition_type == "camera_pan":
        prompt = f"{base_prompt}, camera slowly panning right, smooth motion"
    elif transition_type == "zoom_out":
        prompt = f"{base_prompt}, camera pulling back reveal shot"
    elif transition_type == "scene_cut":
        prompt = f"{base_prompt}, static shot, clean fade in"
    else:
        prompt = f"{base_prompt}, product rotating slowly"

    # Generate 3.5-second video
    operation = client.models.generate_videos(
        model="veo-3.1-fast-preview",
        prompt=prompt,
        image=image_data,
        duration=3.5,
    )

    while not operation.done:
        await asyncio.sleep(3)
        operation = client.operations.get(operation)

    return operation.result.videos[0].uri
```

**5. Match Visual Style (Color Grading)**
```python
def match_visual_style(veo_video_path, event_footage_sample):
    """Apply color grading to Veo video to match event footage for seamless integration."""

    # Analyze event footage color profile
    avg_brightness = analyze_brightness(event_footage_sample)
    color_temp = analyze_color_temperature(event_footage_sample)
    saturation = analyze_saturation(event_footage_sample)

    # Apply matching LUT to Veo video
    subprocess.run([
        "ffmpeg", "-i", veo_video_path,
        "-vf", f"eq=brightness={avg_brightness}:saturation={saturation},colortemperature={color_temp}",
        "matched_veo.mp4"
    ])

    return "matched_veo.mp4"
```

**6. Insert Product Video with Seamless Transitions**
```python
def insert_product_video(event_clip, product_video, insert_point_ms, transition):
    """
    Cut event footage, insert product video, rejoin with transitions.
    Timeline: [Event Part 1] → [Transition] → [Product] → [Transition] → [Event Part 2]
    """

    before_clip = f"before_{insert_point_ms}.mp4"
    after_clip = f"after_{insert_point_ms}.mp4"
    product_duration = 3500  # 3.5 seconds

    # Cut event footage into before/after segments
    cut_before = insert_point_ms - transition["duration"]
    subprocess.run([
        "ffmpeg", "-i", event_clip,
        "-ss", "0", "-to", f"{cut_before}ms",
        "-c", "copy", before_clip
    ])

    cut_after = insert_point_ms + product_duration + transition["duration"]
    subprocess.run([
        "ffmpeg", "-i", event_clip,
        "-ss", f"{cut_after}ms",
        "-c", "copy", after_clip
    ])

    # Create transition based on type
    if transition["type"] == "crossfade":
        subprocess.run([
            "ffmpeg",
            "-i", before_clip,
            "-i", product_video,
            "-i", after_clip,
            "-filter_complex",
            f"[0][1]xfade=transition=fade:duration={transition['duration']/1000}:offset={get_duration(before_clip)-0.5}[v1];"
            f"[v1][2]xfade=transition=fade:duration={transition['duration']/1000}:offset={get_duration(before_clip)+3.5-0.5}[v]",
            "-map", "[v]",
            "output_with_ad.mp4"
        ])
    elif transition["type"] == "cut":
        # Hard cut (no transition) - simplest
        with open("concat_list.txt", "w") as f:
            f.write(f"file '{before_clip}'\nfile '{product_video}'\nfile '{after_clip}'\n")
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", "concat_list.txt", "-c", "copy", "output_with_ad.mp4"
        ])

    return "output_with_ad.mp4"
```

**7. Complete Integration Pipeline**
```python
async def integrate_product_ads_natively(event_video, timeline_analysis, shopify_products):
    """Full pipeline for native ad integration (TV commercial break style)."""

    # 1. Find optimal ad slots
    ad_slots = select_optimal_ad_slots(timeline_analysis, event_type, duration_ms)

    # 2. Find best transition opportunities
    opportunities = find_transition_opportunities(timeline_analysis, ad_slots)

    # 3. Generate Veo videos with matching motion
    product_videos = []
    for opp in opportunities[:3]:  # Top 3 slots
        product = random.choice(shopify_products)
        veo_video = await generate_product_video_with_motion(product, opp["type"])

        # Match visual style to event footage
        sample = extract_sample(event_video, opp["timestamp_ms"])
        styled_video = match_visual_style(veo_video, sample)

        product_videos.append({
            "video": styled_video,
            "insert_point": opp["timestamp_ms"],
            "transition": opp
        })

    # 4. Insert all product videos sequentially
    current_video = event_video
    for pv in sorted(product_videos, key=lambda x: x["insert_point"]):
        current_video = insert_product_video(
            current_video,
            pv["video"],
            pv["insert_point"],
            pv["transition"]
        )

    return current_video
```

**Result:** Product ads feel like TV commercial breaks - seamless transitions that viewers expect and accept.

---

**8. Sponsor Power Plays** ⭐ (Bonus Feature)

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

---

### 3D: Fallback Options (If Time-Constrained)

If native integration (above) is too complex for hackathon timeline, use these simpler overlay approaches:

#### Option 1: Simple Banner Overlays
- Veo product video plays as overlay in corner
- FFmpeg overlay filter with fade in/out
- Fastest implementation (2-3 hours)
- Less immersive but functional

```bash
ffmpeg -i event.mp4 -i product_veo.mp4 \
  -filter_complex "overlay=x=W-w-50:y=H-h-50:enable='between(t,45,49)'" \
  output.mp4
```

#### Option 2: Smart Contextual Placement

**What:** Same overlay, but intelligently positioned to avoid covering important content.

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

---

## FEATURE 4: On-Demand Highlight Reels (Stretch)

**What:** User requests custom highlight reel with natural language: "generate highlight reel for player 23" or "make a reel of the guy in yellow pants"

**Approach:** Natural language → TwelveLabs search → extract moments → generate reel on demand

### Implementation

**1. Natural Language Query Processing**
```python
async def generate_custom_reel(event_id: str, user_query: str):
    """
    Examples:
    - "player 23" → search for jersey number
    - "guy in yellow pants" → search for clothing color
    - "the goalie" → search for position/role
    - "person who scored the first goal" → search for action + temporal
    """

    # Use TwelveLabs natural language search
    client = TwelveLabs(api_key=TWELVELABS_API_KEY)
    index_id = get_event_index_id(event_id)

    # Search for moments matching the query
    search_results = client.search.query(
        index_id=index_id,
        query_text=user_query,
        search_options=["visual", "conversation"],
        threshold="high"
    )

    return search_results
```

**2. Extract and Rank Moments**
```python
def filter_moments(search_results, min_confidence=0.6):
    """Extract clips where the person/object appears clearly."""
    moments = []

    for result in search_results:
        # Filter for quality: person in focus, well-lit, not just background
        if result.confidence >= min_confidence:
            moments.append({
                "video_id": result.video_id,
                "start_ms": result.start,
                "end_ms": result.end,
                "confidence": result.confidence,
                "description": result.metadata.get("description", ""),
                "importance": calculate_moment_importance(result)
            })

    # Rank by importance (key moments > background appearances)
    return sorted(moments, key=lambda x: x["importance"], reverse=True)
```

**3. Build Highlight Reel Timeline**
```python
def create_reel_timeline(moments, target_duration_sec=30):
    """Select best moments that fit within target duration."""
    timeline = []
    total_duration = 0

    for moment in moments:
        clip_duration = (moment["end_ms"] - moment["start_ms"]) / 1000

        # Trim long clips to 5 seconds max
        if clip_duration > 5:
            moment["end_ms"] = moment["start_ms"] + 5000
            clip_duration = 5

        if total_duration + clip_duration <= target_duration_sec:
            timeline.append(moment)
            total_duration += clip_duration

        if total_duration >= target_duration_sec:
            break

    # Sort chronologically for coherent narrative
    return sorted(timeline, key=lambda x: x["start_ms"])
```

**4. Render Custom Reel**
```python
async def render_custom_reel(event_id: str, timeline: list, user_query: str):
    """Generate video from selected moments."""
    clips = []

    # Extract clips
    for moment in timeline:
        video_path = get_video_path(event_id, moment["video_id"])
        clip_path = f"clip_{moment['start_ms']}.mp4"

        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-ss", f"{moment['start_ms']/1000}",
            "-to", f"{moment['end_ms']/1000}",
            "-c:v", "libx264", "-preset", "fast",
            clip_path
        ])
        clips.append(clip_path)

    # Add title card with query
    title_card = create_title_card(f"Highlight Reel: {user_query}")
    clips.insert(0, title_card)

    # Concatenate with crossfade transitions
    output = concat_with_transitions(clips, transition="fade", duration=0.3)

    # Upload to S3
    s3_url = upload_to_s3(output, f"reels/{event_id}/{uuid.uuid4()}.mp4")

    return s3_url
```

**5. API Endpoint**
```python
@router.post("/api/events/{event_id}/reels/generate")
async def generate_custom_highlight_reel(
    event_id: str,
    request: CustomReelRequest  # { "query": "player 23", "duration": 30 }
):
    # Search for matching moments
    search_results = await generate_custom_reel(event_id, request.query)

    # Filter and rank
    moments = filter_moments(search_results)

    if not moments:
        raise HTTPException(404, "No moments found matching query")

    # Build timeline
    timeline = create_reel_timeline(moments, request.duration or 30)

    # Render video
    video_url = await render_custom_reel(event_id, timeline, request.query)

    return {"reel_url": video_url, "moments_count": len(timeline)}
```

**6. Example Usage**
```bash
# User requests in UI or API
POST /api/events/abc123/reels/generate
{
  "query": "player 23",
  "duration": 30
}

# Returns
{
  "reel_url": "https://s3.../reels/abc123/xyz.mp4",
  "moments_count": 8
}
```

### Supported Query Types

| Query Example | TwelveLabs Search Strategy |
|---------------|----------------------------|
| "player 23" | Visual search for jersey number |
| "guy in yellow pants" | Visual search for clothing color |
| "the goalie" | Visual + conversation search for role |
| "person who scored first" | Visual search for action + temporal filter |
| "tallest player" | Visual search for person attributes |
| "John Smith" | Conversation search (if name mentioned) + face search (if roster provided) |

### Benefits Over Batch Generation
- **On-demand:** Only generate when user requests (saves processing time)
- **Flexible:** Handles any natural language query without pre-defined roster
- **Instant:** Uses TwelveLabs search (already indexed) instead of re-processing
- **Scalable:** No need to generate hundreds of reels upfront

---

## Database Schema (Supabase)
```sql
events (id, user_id, name, event_type, status, shopify_store_url, sponsor_name, master_video_url, created_at)
videos (id, event_id, original_url, angle_type, sync_offset_ms, user_instructions TEXT, user_context JSONB, analysis_data JSONB, status)
timelines (id, event_id, segments JSONB, zooms JSONB, ad_slots JSONB, chapters JSONB)
custom_reels (id, event_id, query TEXT, output_url, moments JSONB, duration_sec INT, created_at)

-- user_context JSONB example:
-- {
--   "angle_description": "wide shot from bleachers",
--   "highlight_preferences": ["focus on #23", "zoom at 2:34"],
--   "manual_markers": [{"timestamp_ms": 154000, "note": "goal"}]
-- }

-- custom_reels.moments JSONB example:
-- [
--   {"video_id": "abc", "start_ms": 5000, "end_ms": 8000, "confidence": 0.92},
--   {"video_id": "def", "start_ms": 15000, "end_ms": 19000, "confidence": 0.88}
-- ]
```

## API Endpoints
```
POST   /api/events                      Create event
GET    /api/events/:id                  Get event
POST   /api/events/:id/videos           Get presigned S3 URL
PATCH  /api/events/:id/videos/:video_id Update video metadata (instructions, context)
POST   /api/events/:id/analyze          Start TwelveLabs analysis (parallel for all videos)
POST   /api/events/:id/generate         Generate final video
GET    /api/events/:id/status           Processing status
POST   /api/events/:id/shopify          Connect Shopify store
POST   /api/events/:id/sponsor          Set sponsor for power plays
GET    /api/events/:id/chapters         Get generated chapter timestamps
POST   /api/events/:id/reels/generate   Generate custom highlight reel from natural language query (stretch)

# Example: Update video with user instructions
PATCH /api/events/123/videos/456
{
  "instructions": "Wide angle from bleachers. Focus on #23. Zoom at 2:34 when goal happens.",
  "angle_description": "wide"
}

# Example: Generate custom highlight reel
POST /api/events/123/reels/generate
{
  "query": "player 23",
  "duration": 30
}
# Returns: { "reel_url": "https://s3.../reel.mp4", "moments_count": 8 }
```

## Configuration Management

**Use config files for tunable thresholds** - Avoid hardcoding values that may need adjustment during testing/demos.

### Config File Structure
```python
# backend/config.py
class VideoConfig:
    # Feature 1: Multi-Angle Switching
    ANGLE_SWITCH_MIN_DURATION_MS = 4000  # Min time before switching angles
    ANGLE_SCORE_SAMPLE_INTERVAL_MS = 2000  # How often to evaluate angles

    # Feature 2: Auto-Zoom
    ZOOM_MIN_ACTION_INTENSITY = 8  # Trigger zoom on high action
    ZOOM_MIN_SPACING_SEC = 10  # Min time between zooms
    ZOOM_WIDE_SHOT_MAX_INTENSITY = 1.5  # Only zoom wide/medium shots
    ZOOM_FACTOR_HIGH = 2.5  # For importance >= 0.85
    ZOOM_FACTOR_MEDIUM = 1.8  # For importance < 0.85
    ZOOM_EASE_IN_SEC = 0.3
    ZOOM_HOLD_MIN_SEC = 2
    ZOOM_HOLD_MAX_SEC = 5
    ZOOM_EASE_OUT_SEC = 0.3

    # Feature 3: Ad Slot Detection (Multi-Factor Scoring)
    AD_SCORE_THRESHOLD = 70  # Min score to consider slot
    AD_MIN_SPACING_MS = 45000  # 45s between ads
    AD_MAX_PER_4MIN = 1  # Max ad density
    AD_MAX_TOTAL = 8  # Hard cap
    AD_EXCLUDE_START_MS = 10000  # No ads in first 10s
    AD_EXCLUDE_END_MS = 10000  # No ads in last 10s

    # Ad Scoring Weights
    AD_WEIGHT_ACTION_INTENSITY = 40
    AD_WEIGHT_AUDIO_CONTEXT = 25
    AD_WEIGHT_SCENE_TRANSITION = 20
    AD_WEIGHT_VISUAL_COMPLEXITY = 15

    # Ad Scoring Penalties
    AD_PENALTY_KEY_MOMENT = 0.3  # 70% reduction near goals/scores
    AD_PENALTY_ACTIVE_SPEECH = 0.5  # 50% reduction during speech
    AD_PENALTY_CROWD_ENERGY = 0.4  # 60% reduction high energy

    # Feature 3: Veo Video Generation
    VEO_PRODUCT_VIDEO_DURATION_SEC = 3.5
    VEO_TRANSITION_CROSSFADE_MS = 500
    VEO_TRANSITION_CONTINUE_MOTION_MS = 800

    # Chapter Generation
    CHAPTER_MIN_SCENE_DURATION_SEC = 8

    # Audio Sync
    AUDIO_SYNC_FINE_TUNE_TOLERANCE_MS = 100
```

### Event-Specific Profiles
```python
# backend/config.py
SWITCHING_PROFILES = {
    "sports": {
        "high_action": "closeup",
        "ball_near_goal": "goal_angle",
        "low_action": "crowd",
        "default": "wide",
        # Event-specific ad rules
        "ad_block_scenes": ["scoring_play", "fast_break"],
        "ad_boost_scenes": ["timeout", "halftime"],
        "ad_boost_multiplier": 1.5
    },
    "ceremony": {
        "name_called": "stage_closeup",
        "walking": "wide",
        "applause": "crowd",
        "speech": "podium",
        "ad_block_scenes": ["name_announcement", "award_presentation"],
        "ad_boost_scenes": ["pause", "transition"],
        "ad_boost_multiplier": 1.3
    },
    "performance": {
        "solo": "closeup",
        "full_band": "wide",
        "crowd_singing": "crowd",
        "ad_block_scenes": ["solo", "chorus"],
        "ad_boost_scenes": ["break", "intermission"],
        "ad_boost_multiplier": 1.4
    }
}

IDEAL_AUDIO_SCORES = {
    "timeout": 25,
    "halftime": 25,
    "pause": 25,
    "transition": 20,
    "break": 25,
    "whistle": 15,
    "applause": 10,
    "cheer": 5
}
```

### Usage in Code
```python
from config import VideoConfig, SWITCHING_PROFILES

def select_optimal_ad_slots(timeline_analysis, event_type, duration_ms):
    max_ads = min(int(duration_ms / 240000), VideoConfig.AD_MAX_TOTAL)

    for ts in timeline_analysis:
        score = calculate_ad_suitability_score(ts, context)

        # Apply event-specific rules from config
        profile = SWITCHING_PROFILES.get(event_type, {})
        if ts.scene_classification in profile.get("ad_block_scenes", []):
            score = 0
        elif ts.scene_classification in profile.get("ad_boost_scenes", []):
            score *= profile.get("ad_boost_multiplier", 1.0)

        if score >= VideoConfig.AD_SCORE_THRESHOLD:
            candidates.append(...)
```

**Benefits:**
- Easy tuning during hackathon testing without code changes
- Can override via environment variables for quick testing
- Event organizers could customize thresholds per event type
- Demo flexibility (adjust ad frequency on the fly)

---

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
    #    - Parallelized: all 11 videos compared to reference simultaneously
    # 2. Parse user instructions for each video
    #    - Extract manual zooms, focus subjects, priority timestamps
    # 3. Analyze all videos with TwelveLabs (parallel submission)
    #    - All 12 videos analyzed concurrently
    #    - Cache results to avoid re-analysis
    # 4. Chunk analysis (hybrid: transcription + fixed intervals)
    # 5. Generate angle-switching timeline (Feature 1)
    #    - Incorporate user hints (boosted scores for marked moments)
    #    - Progressive processing: first 4 videos for quick preview
    # 6. Identify zoom moments (Feature 2)
    #    - Include user-specified zoom timestamps
    # 7. Find ad slots (multi-factor scoring)
    #    - 3-4 optimal placements with 45s spacing
    # 8. Find transition opportunities at ad slots
    #    - Scene boundaries, camera pans, angle switches
    # 9. Fetch Shopify products
    # 10. Generate Veo product videos (Feature 3) with motion matching
    #    - Match camera pan direction or zoom style
    # 11. Color-grade Veo videos to match event footage
    # 12. Insert product videos with seamless transitions (native replacement)
    #    - Cut event footage, crossfade to product, crossfade back
    # 13. Add sponsor power plays if configured (overlays)
    # 14. Generate chapter timestamps
    # 15. Render with FFmpeg
    # 16. Upload to S3, update status
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
Hours 4-12:  Feature 1 (multi-angle switching) ← Core functionality
Hours 12-20: Feature 2 (auto-zoom) ← Visual impact
Hours 20-28: Feature 3 (Native ad integration: Shopify + Veo) ← Prize differentiator
             - Multi-factor ad slot detection
             - Veo product video generation with motion matching
             - Seamless video insertion with transitions
             - Sponsor power plays
Hours 28-36: Polish, demo prep, pitch practice

Fallback:    If Feature 3 native integration too complex, use simple overlay (30 min implementation)
Stretch:     Feature 4 (personal reels), Veo stylized replays
Post-Launch: Full Docker containerization for production deployment
```

## Target Prizes
- **TwelveLabs**: Full API suite (scene, objects, audio, faces)
- **Shopify**: Novel shoppable video ad format + sponsor power plays
- **Gemini/Google**: Using Veo for AI-generated product videos (+ optional stylized replays)
- **Top 3 Overall**: Technical depth + clear business model