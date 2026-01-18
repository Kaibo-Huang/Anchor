# Anchor

**Elevator Pitch:** Turn any footage into your personal brand

## Inspiration

Branding builds identity. Whether you're a high school athlete creating a recruitment tape, a band promoting your concert, or a school showcasing your graduation, that perfect video tells your story.

But here's the problem: professional video editing is intimidating and expensive. Athletes have game footage but don't know how to stitch them together and promote their brand sponsors. Organizations want to promote their events but can't afford a videographer.

Meanwhile, professional sports broadcasts make multi-angle switching look seamless, but that requires expensive equipment and trained editors.

We asked ourselves: What if AI could do this automatically? What if anyone with phone footage could create broadcast-quality recaps? And what if those videos could actually generate revenue through seamless sponsorships?

That's why we built Anchor. We want to democratize professional video editing and help anyone amplify their identity through powerful visual storytelling.

## What it does

Anchor transforms multi-angle footage into broadcast-quality reels with integrated sponsorships—automatically, with your prompt.

Here's how it works:

1. **Upload Your Footage**: Capture your event from multiple angles. Upload videos to Anchor with different camera shots, and tell us what type of event it is.

2. **Add Your Personal Touch**: Upload your team anthem, graduation song, or favorite track. This is your identity—your music makes the reel uniquely yours.

3. **Tell Us What You Want**: Just describe your vision in plain English:
   - "Show me my best moments" - Anchor finds YOU across all the footage
   - "Create a high-energy highlight reel" - Get an intense, action-packed edit
   - "Track player #23, focus on scoring plays" - Follow a specific person, emphasize key moments
   - "Make me a 30-second teaser for Instagram" - Get the perfect length for social media

4. **Watch the Magic Happen**: Anchor's AI takes over:
   - Automatically syncs all your videos to the same timeline (no more "which angle had the best shot?")
   - Intelligently switches between angles like a professional broadcast director
   - Syncs scene changes to the beat drops of your music
   - Integrates sponsor ads that look like TV commercials, not annoying popups

## How we built it

The system processes footage through a six-stage pipeline:

1. **Upload & Sync**: Users upload videos directly to AWS S3 using presigned URLs. Videos are time-aligned using device metadata for rough sync, then refined with librosa audio fingerprinting.

2. **TwelveLabs Analysis**: TwelveLabs indexes each video using Marengo 3.0 for visual/audio analysis and Pegasus 1.2 for embedding generation. Users query with natural language and TwelveLabs semantic search returns timestamps to relevant clips.

3. **Intelligent Editing**: For every 2-second interval, the system scores each camera angle by combining embedding similarity to the user's desired vibe with event-specific rules. The highest-scoring angle is selected with minimum 4-second holds between switches. If music is uploaded, librosa detects beats and snaps cuts to the nearest beat drop.

4. **Async Processing**: Celery workers with Redis handle long-running jobs. Supabase Realtime broadcasts processing status via WebSocket so users see live progress.

5. **Video Assembly**: FFmpeg renders the final output by cutting clips using TwelveLabs timestamps, applying zoom on high-action moments, concatenating with crossfades, and mixing audio with intelligent ducking during speech.

6. **Native Sponsorships**: Google Veo generates product videos matching the footage's visual style. These are inserted at natural transition points using FFmpeg crossfades. Products are fetched from connected Shopify stores via OAuth.

## Challenges we ran into

* Parallelizing and batch processing video processing for TwelveLabs
* Compressing audio and optimizing upload speed to AWS S3 Bucket
* Making the editing/transitions not bad
* Configuring Celery workers and Redis for async video processing—managing worker memory limits for large FFmpeg jobs and preventing race conditions in real-time status updates

## Accomplishments that we're proud of

Building out such a cool idea

## What we learned

* TwelveLabs
* Batching + parallelizing processes at a large scale
* FFmpeg for video editing and putting videos together
* Audio syncing using librosa audio fingerprinting
## What's next for Anchor

* Better scalability so we can launch to the public
* Speeding up editing + video processing
## Did you implement a generative AI model or API in your hack this weekend?

**1. TwelveLabs APIs (Marengo 3.0 + Pegasus 1.2)**

- **Marengo 3.0**: Analyzes every frame for scene classification, object detection, action intensity (1-10 scale), and audio events (cheering, whistles, music)
- **Pegasus 1.2**: Generates 1024-dimensional embeddings that capture the emotional "vibe" of each segment

**Key Features Powered:**
- **Multi-angle switching**: Scores each camera angle every 2 seconds based on action intensity and scene context to select the best view
- **Natural language search**: Users query "show me my best moments" or "player 23 scoring" and TwelveLabs semantic search returns exact timestamps across all footage
- **Vibe matching**: Embedding similarity ranks moments as High Energy/Emotional/Calm, letting users find clips that match their desired identity

**2. Google Veo 3.1**

- **What it does**: Generates 3.5-second product videos from Shopify products, matching the footage's visual style (color grading, lighting, camera movement)
- **How it's used**: Creates native sponsor integrations at natural transition points (camera pans, scene fades) with seamless crossfades. The ad looks like an integrated TV commercials, not a popup ad