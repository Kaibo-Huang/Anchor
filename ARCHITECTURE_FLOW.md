# ANCHOR PLATFORM - COMPLETE SYSTEM FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    USER BROWSER                                     │
│                         (Next.js Frontend - localhost:3000)                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ HTTP Requests
                                          ▼
                        ┌─────────────────────────────────────┐
                        │   app/page.tsx (Home)               │
                        │   - Create new event form           │
                        └─────────────┬───────────────────────┘
                                      │
                                      │ POST /api/events
                                      │ { name, event_type }
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          FASTAPI BACKEND (localhost:8000)                           │
│                                   main.py                                           │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                        ┌─────────────────────────────────────┐
                        │   routers/events.py                 │
                        │   POST /api/events                  │
                        │   - Validate event_type             │
                        └─────────────┬───────────────────────┘
                                      │
                                      │ INSERT
                                      ▼
                        ┌─────────────────────────────────────┐
                        │   Supabase PostgreSQL               │
                        │   ┌───────────────────────────────┐ │
                        │   │ events table                  │ │
                        │   │ - id (UUID)                   │ │
                        │   │ - name                        │ │
                        │   │ - event_type                  │ │
                        │   │ - status: "created"           │ │
                        │   │ - created_at                  │ │
                        │   └───────────────────────────────┘ │
                        └─────────────────────────────────────┘
                                      │
                                      │ Response: event_id
                                      ▼
                        ┌─────────────────────────────────────┐
                        │   app/events/[id]/page.tsx          │
                        │   (Event Detail Page)               │
                        │                                     │
                        │   Components mounted:               │
                        │   ├─ VideoUpload                    │
                        │   ├─ MusicUpload                    │
                        │   ├─ AnalysisProgress               │
                        │   ├─ ShopifyConnect                 │
                        │   ├─ PersonalReelGenerator          │
                        │   └─ VideoPlayer                    │
                        └─────────────┬───────────────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            │                         │                         │
            ▼                         ▼                         ▼
┌───────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ UPLOAD VIDEO FLOW     │  │ UPLOAD MUSIC FLOW    │  │ SHOPIFY CONNECT FLOW │
└───────────────────────┘  └──────────────────────┘  └──────────────────────┘

═══════════════════════════════════════════════════════════════════════════════════════
                            FLOW 1: VIDEO UPLOAD (MULTIPART)
═══════════════════════════════════════════════════════════════════════════════════════

User selects video file
(sports_game_angle1.mp4, 2.5GB)
            │
            ▼
┌─────────────────────────────────────┐
│ components/VideoUpload.tsx          │
│ - Detects file size > 100MB        │
│ - Initiates multipart upload       │
└─────────────┬───────────────────────┘
              │
              │ POST /api/events/{id}/videos/multipart/init
              │ { filename: "angle1.mp4", size: 2500000000, angle_type: "wide" }
              ▼
┌─────────────────────────────────────┐
│ routers/videos.py                   │
│ init_multipart_upload()             │
└─────────────┬───────────────────────┘
              │
              ├──► INSERT INTO videos (event_id, original_url, angle_type, status: "uploading")
              │    └──► Supabase: Returns video_id
              │
              └──► services/s3_client.py
                   └──► AWS S3: s3.create_multipart_upload()
                        └──► Returns: upload_id
              │
              │ Response: { video_id, upload_id }
              ▼
┌─────────────────────────────────────┐
│ components/VideoUpload.tsx          │
│ - Split file into 10MB chunks      │
│ - For each chunk (250 total):      │
└─────────────┬───────────────────────┘
              │
              │ POST /api/events/{id}/videos/{vid}/multipart/chunk-url
              │ { part_number: 1 }
              ▼
┌─────────────────────────────────────┐
│ routers/videos.py                   │
│ get_chunk_presigned_url()           │
└─────────────┬───────────────────────┘
              │
              └──► services/s3_client.py
                   └──► AWS S3: generate_presigned_url(method='PUT', part_number=1)
              │
              │ Response: { presigned_url }
              ▼
┌─────────────────────────────────────┐
│ Browser Direct Upload               │
│ PUT {presigned_url}                 │
│ Body: chunk data (10MB)             │
└─────────────┬───────────────────────┘
              │
              │ Direct to AWS S3 (bypass backend)
              ▼
┌─────────────────────────────────────┐
│ AWS S3                              │
│ - Stores chunk part                 │
│ - Returns ETag header               │
└─────────────┬───────────────────────┘
              │
              │ Response: ETag: "abc123..."
              ▼
      (Repeat for all 250 chunks in parallel - 4 concurrent)
              │
              │ All chunks uploaded
              ▼
┌─────────────────────────────────────┐
│ components/VideoUpload.tsx          │
│ POST /api/events/{id}/videos/{vid}/multipart/complete
│ { parts: [{part_number: 1, ETag: "abc"}, ...] }
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ routers/videos.py                   │
│ complete_multipart_upload()         │
└─────────────┬───────────────────────┘
              │
              └──► services/s3_client.py
                   └──► AWS S3: s3.complete_multipart_upload(parts=[...])
                        └──► Finalizes file: events/{event_id}/videos/{video_id}.mp4
              │
              └──► UPDATE videos SET status = 'uploaded', original_url = 's3://...'
              │
              │ Response: { success: true }
              ▼
      Video successfully uploaded to S3
      (Repeat for angle2.mp4, angle3.mp4, ...)

═══════════════════════════════════════════════════════════════════════════════════════
                            FLOW 2: MUSIC UPLOAD (OPTIONAL)
═══════════════════════════════════════════════════════════════════════════════════════

User selects music file
(team_anthem.mp3, 8MB)
            │
            ▼
┌─────────────────────────────────────┐
│ components/MusicUpload.tsx          │
│ - Get presigned URL for upload     │
└─────────────┬───────────────────────┘
              │
              │ POST /api/events/{id}/music/upload
              │ { filename: "team_anthem.mp3" }
              ▼
┌─────────────────────────────────────┐
│ routers/videos.py                   │
│ get_music_upload_url()              │
└─────────────┬───────────────────────┘
              │
              └──► services/s3_client.py
                   └──► AWS S3: generate_presigned_url(method='PUT')
              │
              │ Response: { presigned_url, music_url }
              ▼
┌─────────────────────────────────────┐
│ Browser Direct Upload               │
│ PUT {presigned_url}                 │
│ Body: music file                    │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ AWS S3                              │
│ - Stores: events/{id}/music/track.mp3
└─────────────┬───────────────────────┘
              │
              │ Success
              ▼
┌─────────────────────────────────────┐
│ routers/videos.py                   │
│ POST /api/events/{id}/music/analyze │
└─────────────┬───────────────────────┘
              │
              │ Triggers Celery Task
              ▼
┌─────────────────────────────────────┐
│ worker_optimized.py                 │
│ @task analyze_music_task()          │
└─────────────┬───────────────────────┘
              │
              ├──► Download music from S3
              │
              ├──► services/music_sync.py
              │    └──► librosa.load("track.mp3")
              │         └──► librosa.beat.beat_track()
              │              └──► Returns: tempo, beat_frames
              │         └──► librosa.feature.rms()
              │              └──► Returns: intensity curve
              │
              └──► UPDATE events SET music_metadata = {
                       beats: [0, 500, 1000, ...],
                       tempo: 128,
                       intensity: [0.2, 0.5, 0.8, ...]
                   }
              │
              ▼
      Music analyzed and ready for beat-synced cuts

═══════════════════════════════════════════════════════════════════════════════════════
                         FLOW 3: SHOPIFY BRAND INTEGRATION
═══════════════════════════════════════════════════════════════════════════════════════

Brand clicks "Install App"
            │
            ▼
┌─────────────────────────────────────┐
│ app/brands/install/page.tsx         │
│ - Enter shop domain form            │
│ - shop: "nike.myshopify.com"        │
└─────────────┬───────────────────────┘
              │
              │ GET /api/shopify/install?shop=nike.myshopify.com
              ▼
┌─────────────────────────────────────┐
│ routers/shopify.py                  │
│ get_install_url()                   │
└─────────────┬───────────────────────┘
              │
              ├──► Generate random nonce (UUID)
              │
              ├──► services/redis_client.py
              │    └──► Redis SET oauth_nonce:{nonce} = "nike.myshopify.com" EX 600
              │
              └──► Build OAuth URL:
                   https://nike.myshopify.com/admin/oauth/authorize?
                     client_id={SHOPIFY_API_KEY}&
                     scope=read_products,read_product_listings&
                     redirect_uri={BASE_URL}/api/shopify/callback&
                     state={nonce}
              │
              │ Response: { auth_url }
              ▼
┌─────────────────────────────────────┐
│ Browser Redirect                    │
│ → Shopify OAuth consent page        │
└─────────────┬───────────────────────┘
              │
              │ Brand approves app install
              ▼
┌─────────────────────────────────────┐
│ Shopify Server                      │
│ - Generates code                    │
│ - Signs params with HMAC            │
│ - Redirects back                    │
└─────────────┬───────────────────────┘
              │
              │ GET /api/shopify/callback?
              │   code=abc123&
              │   shop=nike.myshopify.com&
              │   state={nonce}&
              │   hmac=xyz789
              ▼
┌─────────────────────────────────────┐
│ routers/shopify.py                  │
│ shopify_callback()                  │
└─────────────┬───────────────────────┘
              │
              ├──► Verify HMAC signature
              │    └──► hmac_sha256(params, SHOPIFY_API_SECRET)
              │         └──► Match with provided hmac ✓
              │
              ├──► services/redis_client.py
              │    └──► Redis GET oauth_nonce:{state}
              │         └──► Verify shop domain matches ✓
              │
              ├──► Exchange code for access_token
              │    POST https://nike.myshopify.com/admin/oauth/access_token
              │    { client_id, client_secret, code }
              │    └──► Response: { access_token, scope }
              │
              ├──► services/encryption.py
              │    └──► Fernet.encrypt(access_token)
              │         └──► Returns: encrypted_token
              │
              ├──► INSERT INTO shopify_stores (
              │        shop_domain: "nike.myshopify.com",
              │        access_token: {encrypted_token},
              │        scopes: "read_products,read_product_listings",
              │        status: "active"
              │    )
              │    └──► Supabase: Returns store_id
              │
              └──► Trigger Celery Task: sync_store_products_task
              │
              │ Redirect: /brands/connected?shop=nike.myshopify.com
              ▼
┌─────────────────────────────────────┐
│ worker_optimized.py                 │
│ @task sync_store_products_task()    │
└─────────────┬───────────────────────┘
              │
              ├──► SELECT access_token FROM shopify_stores WHERE id = {store_id}
              │    └──► services/encryption.py
              │         └──► Fernet.decrypt(encrypted_token)
              │              └──► Returns: access_token
              │
              ├──► services/shopify_sync.py
              │    └──► POST https://nike.myshopify.com/api/2024-01/graphql
              │         Headers: X-Shopify-Storefront-Access-Token: {access_token}
              │         Query: {
              │           products(first: 250) {
              │             edges {
              │               node {
              │                 id, title, description, images {
              │                   url
              │                 }, variants {
              │                   price
              │                 }
              │               }
              │             }
              │           }
              │         }
              │         └──► Response: { data: { products: [...] } }
              │
              ├──► For each product:
              │    └──► INSERT INTO shopify_products (
              │             store_id,
              │             shopify_product_id,
              │             title,
              │             description,
              │             price,
              │             image_url,
              │             raw_data
              │         ) ON CONFLICT (store_id, shopify_product_id) DO UPDATE
              │
              └──► UPDATE shopify_stores SET last_sync_at = NOW()
              │
              ▼
      Shopify products synced and cached in database

      Event organizer later:
              │
              │ GET /api/events/{event_id}/brands
              ▼
┌─────────────────────────────────────┐
│ routers/shopify.py                  │
│ get_event_brand_products()          │
└─────────────┬───────────────────────┘
              │
              └──► SELECT * FROM shopify_products
                   JOIN shopify_stores
                   WHERE status = 'active'
              │
              │ Response: [{ id, title, image_url, price }, ...]
              ▼
┌─────────────────────────────────────┐
│ components/BrandStoreBrowser.tsx    │
│ - Display product grid              │
│ - Select products for ads           │
└─────────────┬───────────────────────┘
              │
              │ POST /api/events/{event_id}/brands
              │ { product_ids: ["prod_1", "prod_2", "prod_3"] }
              ▼
┌─────────────────────────────────────┐
│ routers/shopify.py                  │
│ add_event_brand_products()          │
└─────────────┬───────────────────────┘
              │
              └──► For each product_id:
                   INSERT INTO event_brand_products (
                       event_id,
                       store_id,
                       product_id,
                       display_order
                   )
              │
              ▼
      Products linked to event, ready for ad generation

═══════════════════════════════════════════════════════════════════════════════════════
                    FLOW 4: VIDEO ANALYSIS (TwelveLabs + AI)
═══════════════════════════════════════════════════════════════════════════════════════

All videos uploaded (3 angles)
User clicks "Analyze Videos"
            │
            ▼
┌─────────────────────────────────────┐
│ components/AnalysisProgress.tsx     │
│ POST /api/events/{id}/analyze       │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ routers/events.py                   │
│ analyze_event()                     │
└─────────────┬───────────────────────┘
              │
              ├──► UPDATE events SET status = 'analyzing'
              │
              └──► Celery: send_task("analyze_videos_task", args=[event_id])
                   └──► Redis: Enqueue task
              │
              │ Response: { status: "analyzing", task_id }
              ▼
┌─────────────────────────────────────┐
│ Redis Queue                         │
│ - Task: analyze_videos_task         │
│ - Args: [event_id]                  │
└─────────────┬───────────────────────┘
              │
              │ Celery worker picks up task
              ▼
┌─────────────────────────────────────┐
│ worker_optimized.py                 │
│ @task analyze_videos_task()         │
└─────────────┬───────────────────────┘
              │
              ├──► SELECT * FROM videos WHERE event_id = {id} AND status = 'uploaded'
              │    └──► Returns: [video_A, video_B, video_C]
              │
              ├──► PARALLEL DOWNLOAD (ThreadPoolExecutor, 4 workers)
              │    │
              │    ├──► Worker 1: Download video_A from S3
              │    │    └──► services/s3_client.py
              │    │         └──► s3.download_file("events/{id}/videos/A.mp4")
              │    │              └──► Local: /tmp/video_A.mp4 (4.2GB)
              │    │
              │    ├──► Worker 2: Download video_B from S3
              │    │    └──► Local: /tmp/video_B.mp4 (3.8GB)
              │    │
              │    └──► Worker 3: Download video_C from S3
              │         └──► Local: /tmp/video_C.mp4 (2.1GB)
              │
              ├──► Check file sizes (TwelveLabs limit: 4GB)
              │    │
              │    └──► video_A > 4GB → COMPRESS
              │         └──► services/video_compress.py
              │              └──► FFmpeg: ffmpeg -i video_A.mp4 -c:v libx264 -crf 23 \
              │                           -preset fast -c:a copy compressed_A.mp4
              │                   └──► New size: 3.1GB ✓
              │
              ├──► services/twelvelabs_service.py
              │    └──► create_index()
              │         └──► POST https://api.twelvelabs.io/v2/indexes
              │              Body: {
              │                  name: "event_{id}_index",
              │                  engines: [
              │                      { name: "marengo2.7", options: ["visual", "audio"] },
              │                      { name: "pegasus1.2", options: ["visual", "audio"] }
              │                  ]
              │              }
              │              └──► Response: { _id: "index_abc123" }
              │
              ├──► UPDATE events SET twelvelabs_index_id = "index_abc123"
              │
              ├──► PARALLEL INDEXING (submit all videos)
              │    │
              │    ├──► services/twelvelabs_service.py: index_video(video_A)
              │    │    └──► POST https://api.twelvelabs.io/v2/indexes/{index_id}/videos
              │    │         Body: video file (multipart)
              │    │         └──► Response: { _id: "video_task_A" }
              │    │
              │    ├──► index_video(video_B)
              │    │    └──► Response: { _id: "video_task_B" }
              │    │
              │    └──► index_video(video_C)
              │         └──► Response: { _id: "video_task_C" }
              │
              ├──► PARALLEL POLLING (wait for all completions - 2s interval)
              │    │
              │    ├──► Poll video_task_A status every 2s
              │    │    └──► GET /v2/indexes/{index_id}/videos/{task_A}
              │    │         └──► { status: "indexing" } ... "ready" ✓
              │    │              Returns: { _id: "video_id_A" }
              │    │
              │    ├──► Poll video_task_B → "ready" ✓
              │    │    └──► { _id: "video_id_B" }
              │    │
              │    └──► Poll video_task_C → "ready" ✓
              │         └──► { _id: "video_id_C" }
              │
              ├──► RETRIEVE ANALYSIS DATA (for each video)
              │    │
              │    └──► services/twelvelabs_service.py
              │         └──► GET /v2/indexes/{index_id}/videos/{video_id_A}
              │              └──► Response: {
              │                      metadata: {
              │                          duration: 1800,
              │                          width: 1920,
              │                          height: 1080
              │                      },
              │                      hls: { ... }
              │                  }
              │         └──► GET /v2/indexes/{index_id}/videos/{video_id_A}/classification
              │              └──► Response: {
              │                      data: [
              │                          {
              │                              start: 0,
              │                              end: 5.2,
              │                              classifications: [
              │                                  { class: "sports", score: 0.95 },
              │                                  { class: "outdoor", score: 0.88 }
              │                              ]
              │                          },
              │                          ...
              │                      ]
              │                  }
              │         └──► Aggregate analysis_data = {
              │                  scenes: [...],
              │                  objects: ["ball", "goal", "player"],
              │                  actions: ["running", "scoring", "celebrating"],
              │                  faces: [...],
              │                  audio_events: ["cheer", "whistle", "commentary"],
              │                  action_intensity: [3, 5, 8, 9, 7, 4, ...] (per 2s)
              │              }
              │
              ├──► GENERATE EMBEDDINGS (for vibe matching)
              │    │
              │    └──► services/twelvelabs_service.py
              │         └──► create_text_embedding("high energy action moments")
              │              └──► POST /v2/embeddings
              │                   └──► Response: { embedding: [0.23, -0.45, ...] (512-dim) }
              │         └──► create_text_embedding("emotional celebration moments")
              │         └──► create_text_embedding("calm steady moments")
              │
              ├──► UPDATE videos (for each video A, B, C)
              │    └──► UPDATE videos SET
              │             twelvelabs_video_id = "video_id_A",
              │             analysis_data = {scenes, objects, actions, ...},
              │             status = 'analyzed'
              │         WHERE id = video_A
              │
              ├──► UPDATE events SET status = 'analyzed'
              │
              └──► Celery task completes
              │
              ▼
┌─────────────────────────────────────┐
│ Frontend (polling every 3s)         │
│ GET /api/events/{id}                │
│ - Detects status: "analyzed"        │
│ - Shows "Generate Video" button     │
└─────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════════════
                    FLOW 5: VIDEO GENERATION (Multi-Angle + Ads)
═══════════════════════════════════════════════════════════════════════════════════════

User clicks "Generate Video"
            │
            ▼
┌─────────────────────────────────────┐
│ app/events/[id]/page.tsx            │
│ POST /api/events/{id}/generate      │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ routers/events.py                   │
│ generate_event_video()              │
└─────────────┬───────────────────────┘
              │
              ├──► UPDATE events SET status = 'generating'
              │
              └──► Celery: send_task("generate_video_task", args=[event_id])
                   └──► Redis: Enqueue task
              │
              ▼
┌─────────────────────────────────────┐
│ worker_optimized.py                 │
│ @task generate_video_task()         │
└─────────────┬───────────────────────┘
              │
              ├──► Fetch from Supabase:
              │    ├─ event (name, event_type, music_url, music_metadata)
              │    ├─ videos[] (3 videos with analysis_data)
              │    └─ event_brand_products[] (Shopify products for ads)
              │
              ├─────────────────────────────────────────────────────────────┐
              │                  STEP 1: AUDIO SYNC                         │
              └─────────────────────────────────────────────────────────────┘
              │
              ├──► services/audio_sync.py
              │    └──► sync_videos(videos)
              │         │
              │         ├──► For each video:
              │         │    └──► librosa.load("video.mp4") → extract audio waveform
              │         │         └──► librosa.onset.onset_detect() → audio fingerprint
              │         │
              │         ├──► Reference: video_A (offset = 0ms)
              │         │
              │         ├──► scipy.signal.correlate(audio_A, audio_B)
              │         │    └──► Find peak correlation → offset = +2300ms
              │         │         └──► UPDATE videos SET sync_offset_ms = 2300 WHERE id = B
              │         │
              │         └──► scipy.signal.correlate(audio_A, audio_C)
              │              └──► Find peak correlation → offset = +800ms
              │                   └──► UPDATE videos SET sync_offset_ms = 800 WHERE id = C
              │
              ├─────────────────────────────────────────────────────────────┐
              │              STEP 2: TIMELINE GENERATION                    │
              └─────────────────────────────────────────────────────────────┘
              │
              ├──► services/timeline.py
              │    └──► generate_timeline(event, videos)
              │         │
              │         ├──► Get SWITCHING_PROFILES["sports"] from config.py:
              │         │    {
              │         │        high_action: "closeup",
              │         │        ball_near_goal: "goal_angle",
              │         │        low_action: "crowd",
              │         │        default: "wide"
              │         │    }
              │         │
              │         ├──► For t = 0 to video_duration (step = 2000ms):
              │         │    │
              │         │    ├──► Score each angle at timestamp t:
              │         │    │    │
              │         │    │    ├──► video_A (wide):
              │         │    │    │    ├─ action_intensity = 8 → +50 (high_action)
              │         │    │    │    ├─ scene_type = "kickoff" → +20
              │         │    │    │    └─ Total score_A = 70
              │         │    │    │
              │         │    │    ├──► video_B (closeup):
              │         │    │    │    ├─ action_intensity = 8 → +80 (profile: high_action → closeup)
              │         │    │    │    ├─ face_visible → +15
              │         │    │    │    └─ Total score_B = 95
              │         │    │    │
              │         │    │    └──► video_C (crowd):
              │         │    │         ├─ action_intensity = 8 → +30 (crowd secondary)
              │         │    │         └─ Total score_C = 30
              │         │    │
              │         │    ├──► Apply HYSTERESIS (30% threshold):
              │         │    │    └─ Current: video_A (score 70)
              │         │    │         New best: video_B (score 95)
              │         │    │         Improvement: 95/70 = 1.36 → 36% > 30% threshold
              │         │    │         → SWITCH to video_B ✓
              │         │    │
              │         │    ├──► Enforce MIN_SEGMENT_DURATION (4000ms for sports):
              │         │    │    └─ Only switch if current segment ≥ 4s
              │         │    │
              │         │    └──► Add to timeline:
              │         │         segments.push({
              │         │             start_ms: 0,
              │         │             end_ms: 4000,
              │         │             video_id: "A"
              │         │         })
              │         │         segments.push({
              │         │             start_ms: 4000,
              │         │             end_ms: 8000,
              │         │             video_id: "B"
              │         │         })
              │         │
              │         ├──► IDENTIFY ZOOM MOMENTS:
              │         │    │
              │         │    └──► For each segment:
              │         │         ├─ If action_intensity ≥ 8 (from TwelveLabs)
              │         │         ├─ AND angle_type in ["wide", "medium"]
              │         │         ├─ AND no zoom in last 10s (ZOOM_MIN_SPACING_SEC)
              │         │         └─ Add zoom:
              │         │             zooms.push({
              │         │                 start_ms: 24000,
              │         │                 duration_ms: 3000,
              │         │                 zoom_factor: 1.5 (ZOOM_FACTOR_HIGH = 2.5 if very intense)
              │         │             })
              │         │
              │         ├──► FIND AD SLOTS (multi-factor scoring):
              │         │    │
              │         │    └──► For each 2s window t:
              │         │         ├─ Initialize: ad_score = 0
              │         │         │
              │         │         ├─ ACTION SCORE (40pts weight):
              │         │         │  └─ If action_intensity ≤ 3 → +40
              │         │         │     Else if intensity ≤ 5 → +20
              │         │         │
              │         │         ├─ AUDIO SCORE (25pts weight):
              │         │         │  └─ If audio_event in ["timeout", "break"] → +25
              │         │         │     Else if "applause" → +15
              │         │         │
              │         │         ├─ SCENE SCORE (20pts weight):
              │         │         │  └─ If scene_type = "transition" → +20
              │         │         │
              │         │         ├─ VISUAL COMPLEXITY (15pts weight):
              │         │         │  └─ If low_complexity → +15
              │         │         │
              │         │         ├─ APPLY PENALTIES:
              │         │         │  ├─ Near key moment (goal, score) → score × 0.3
              │         │         │  ├─ Speech detected → score × 0.5
              │         │         │  └─ High crowd energy → score × 0.4
              │         │         │
              │         │         ├─ CONSTRAINTS:
              │         │         │  ├─ If ad_score ≥ 70 (AD_SCORE_THRESHOLD)
              │         │         │  ├─ AND distance from last ad ≥ 45s (AD_MIN_SPACING_MS)
              │         │         │  ├─ AND count in last 4min < 1 (AD_MAX_PER_4MIN)
              │         │         │  ├─ AND not in first/last 10s
              │         │         │  └─ Add ad slot:
              │         │         │      ad_slots.push({
              │         │         │          timestamp_ms: 45000,
              │         │         │          duration_ms: 4000,
              │         │         │          score: 85
              │         │         │      })
              │         │
              │         ├──► GENERATE CHAPTERS (navigation markers):
              │         │    │
              │         │    └──► Detect major events:
              │         │         ├─ t=0 → { timestamp_ms: 0, title: "Kickoff", type: "start" }
              │         │         ├─ action_spike + audio "cheer" → { timestamp_ms: 120000, title: "First Goal", type: "highlight" }
              │         │         └─ Min spacing: 60s between chapters
              │         │
              │         ├──► BEAT-SYNC (if music uploaded):
              │         │    │
              │         │    └──► services/music_sync.py
              │         │         └──► align_cuts_to_beats(segments, music_metadata)
              │         │              ├─ For each segment boundary:
              │         │              │  ├─ Find nearest beat within ±200ms tolerance
              │         │              │  └─ Adjust segment.start_ms to beat_time
              │         │              └─ Returns: adjusted segments
              │         │
              │         └──► INSERT INTO timelines (
              │                  event_id,
              │                  segments: [...], (150 segments total)
              │                  zooms: [...], (12 zoom moments)
              │                  ad_slots: [...], (3 ad slots)
              │                  chapters: [...], (8 chapter markers)
              │                  beat_synced: true
              │              )
              │
              ├─────────────────────────────────────────────────────────────┐
              │           STEP 3: AD GENERATION (Google Veo)                │
              └─────────────────────────────────────────────────────────────┘
              │
              ├──► If event_brand_products.length > 0:
              │    │
              │    └──► services/veo_service.py
              │         └──► generate_ads_for_slots(ad_slots, products, event_context)
              │              │
              │              ├──► For ad_slot #1 (timestamp: 45000ms):
              │              │    │
              │              │    ├──► Select product #1: "Nike Soccer Cleats" (cycle through)
              │              │    │
              │              │    ├──► Get preceding scene context (for continuity):
              │              │    │    └─ Scene at t=43s: outdoor, daylight, grass field
              │              │    │         Camera motion: panning right
              │              │    │
              │              │    ├──► build_product_ad_prompt():
              │              │    │    └──► Prompt: """
              │              │    │         Professional product showcase for Nike Soccer Cleats.
              │              │    │
              │              │    │         STYLE: Sports, athletic, dynamic
              │              │    │         SETTING: Outdoor grass field, daylight, natural lighting
              │              │    │         COLORS: Match surrounding environment - green grass, blue sky
              │              │    │         CAMERA: Smooth pan right motion
              │              │    │         DURATION: 4 seconds
              │              │    │         MOOD: Energetic, professional, seamless
              │              │    │
              │              │    │         Show product prominently with clean composition.
              │              │    │         Maintain visual continuity with sports event.
              │              │    │         """
              │              │    │
              │              │    ├──► Google Veo API:
              │              │    │    └──► client.models.generate_videos(
              │              │    │             model="veo-3.1-fast-preview",
              │              │    │             prompt=prompt,
              │              │    │             image=product_image_data,
              │              │    │             duration=4.0,
              │              │    │             aspect_ratio="16:9"
              │              │    │         )
              │              │    │         └──► Returns: operation_id
              │              │    │
              │              │    ├──► Poll operation status (every 5s):
              │              │    │    └──► operation.result() → video_bytes
              │              │    │
              │              │    ├──► Save: /tmp/veo_ad_45000.mp4
              │              │    │
              │              │    └──► color_grade_to_match(veo_ad, reference_frame)
              │              │         └──► FFmpeg color correction:
              │              │              ffmpeg -i veo_ad.mp4 -i reference_frame.jpg \
              │              │                -filter_complex "colorlevels, eq=..." \
              │              │                veo_ad_graded_45000.mp4
              │              │
              │              ├──► For ad_slot #2 (timestamp: 180000ms):
              │              │    └──► Select product #2: "Gatorade Sports Drink"
              │              │         (repeat process with different prompt)
              │              │
              │              └──► Returns: [
              │                       "/tmp/veo_ad_45000.mp4",
              │                       "/tmp/veo_ad_180000.mp4"
              │                   ]
              │
              ├─────────────────────────────────────────────────────────────┐
              │        STEP 4: SEGMENT EXTRACTION (FFmpeg Parallel)         │
              └─────────────────────────────────────────────────────────────┘
              │
              ├──► ThreadPoolExecutor (4 workers):
              │    │
              │    ├──► Worker 1: Extract segment_0
              │    │    └──► FFmpeg:
              │    │         ffmpeg -ss 0 -t 4.0 -i video_A.mp4 -c copy segment_0.mp4
              │    │         └──► Output: /tmp/segment_0.mp4
              │    │
              │    ├──► Worker 2: Extract segment_1 (WITH ZOOM)
              │    │    └──► FFmpeg zoompan (Ken Burns):
              │    │         ffmpeg -ss 4.0 -t 4.0 -i video_B.mp4 \
              │    │           -vf "zoompan=z='if(lte(on,9),1+(0.5/9)*on,1.5)':d=90:
              │    │                x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" \
              │    │           segment_1.mp4
              │    │         └─ Ease-in 0.3s → zoom to 1.5x → hold 2s → ease-out
              │    │         └──► Output: /tmp/segment_1.mp4
              │    │
              │    ├──► Worker 3: Extract segment_2
              │    │    └──► FFmpeg: -ss 8.0 -t 6.0 -i video_A.mp4 ...
              │    │
              │    └──► (Continue for all 150 segments in parallel batches)
              │
              ├─────────────────────────────────────────────────────────────┐
              │     STEP 5: COMPOSITION & AUDIO MIX (FFmpeg Single Pass)    │
              └─────────────────────────────────────────────────────────────┘
              │
              ├──► services/render.py
              │    └──► render_video(timeline, segments, ads, music_metadata)
              │         │
              │         ├──► Build FFmpeg filter_complex command:
              │         │    │
              │         │    ├─ VIDEO COMPOSITION:
              │         │    │  │
              │         │    │  ├─ Concat segments with xfade (0.3s crossfade):
              │         │    │  │  [0:v][1:v]xfade=transition=fade:duration=0.3:offset=3.7[v01];
              │         │    │  │  [v01][2:v]xfade=transition=fade:duration=0.3:offset=7.7[v02];
              │         │    │  │  ... (repeat for 150 segments)
              │         │    │  │
              │         │    │  ├─ Insert ads with transitions (0.5s):
              │         │    │  │  # At t=45s, insert ad
              │         │    │  │  [v_pre_ad][ad1:v]xfade=transition=fade:duration=0.5:offset=44.5[v_ad1_in];
              │         │    │  │  [v_ad1_in][v_post_ad]xfade=transition=fade:duration=0.5:offset=48.5[v_ad1_out];
              │         │    │  │
              │         │    │  └─ Add sponsor overlays (drawtext):
              │         │    │     drawtext=text='⚡ NIKE GOAL CAM':fontsize=36:
              │         │    │       x=10:y=H-200:fontcolor=white:
              │         │    │       box=1:boxcolor=black@0.5:
              │         │    │       enable='between(t,45,49)'[v_overlay]
              │         │    │
              │         │    └─ AUDIO MIXING:
              │         │       │
              │         │       ├─ Extract event audio from all segments:
              │         │       │  [0:a][1:a][2:a]...[150:a]concat=n=150:v=0:a=1[event_audio]
              │         │       │
              │         │       ├─ Load personal music:
              │         │       │  [music_input:a]
              │         │       │
              │         │       ├─ Apply ducking during speech (intensity curve from metadata):
              │         │       │  [music_input:a]volume='if(between(t,10,20),0.2,
              │         │       │                          if(between(t,30,45),0.2,
              │         │       │                          1.0))'[music_ducked]
              │         │       │
              │         │       ├─ Apply boosting during high-action (intensity ≥ 8):
              │         │       │  [music_ducked]volume='if(gte(intensity,8),1.2,0.5)'[music_boosted]
              │         │       │
              │         │       ├─ Fade in/out:
              │         │       │  [music_boosted]afade=t=in:d=2,afade=t=out:d=3[music_faded]
              │         │       │
              │         │       ├─ Mute event audio during ads:
              │         │       │  [event_audio]volume='if(between(t,45,49),0,
              │         │       │                      if(between(t,180,184),0,
              │         │       │                      1.0))'[event_audio_muted]
              │         │       │
              │         │       └─ Mix event + music:
              │         │          [event_audio_muted][music_faded]amix=inputs=2:weights=1 0.5[audio_out]
              │         │
              │         ├──► Execute FFmpeg (single command, ~5min processing):
              │         │    └──► ffmpeg \
              │         │           -i segment_0.mp4 -i segment_1.mp4 ... -i segment_150.mp4 \
              │         │           -i veo_ad_45000.mp4 -i veo_ad_180000.mp4 \
              │         │           -i music.mp3 \
              │         │           -filter_complex "{huge_filter_complex_string}" \
              │         │           -c:v h264_videotoolbox -b:v 8M \
              │         │           -c:a aac -b:a 192k \
              │         │           -s 1920x1080 \
              │         │           master.mp4
              │         │         └──► Output: /tmp/master.mp4 (850MB, 5min video)
              │         │
              │         └──► services/s3_client.py
              │              └──► Upload master.mp4 → S3
              │                   └──► s3.upload_file("/tmp/master.mp4",
              │                            "outputs/{event_id}/master.mp4")
              │
              ├──► Generate presigned GET URL (1 hour expiry):
              │    └──► master_url = s3.generate_presigned_url('get_object', ...)
              │
              ├──► UPDATE events SET
              │        master_video_url = master_url,
              │        status = 'completed'
              │
              ├──► Cleanup temp files:
              │    └──► os.remove(segment_*.mp4, veo_ad_*.mp4, /tmp/master.mp4)
              │
              └──► Celery task completes
              │
              ▼
┌─────────────────────────────────────┐
│ Frontend (polling)                  │
│ GET /api/events/{id}                │
│ - Detects status: "completed"       │
│ - Displays master_video_url         │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ components/VideoPlayer.tsx          │
│ - Plays master video from S3        │
│ - Shows chapter markers             │
│ - Download option                   │
└─────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════════════
            FLOW 6: CUSTOM HIGHLIGHT REEL (IDENTITY FEATURE - "Find Me")
═══════════════════════════════════════════════════════════════════════════════════════

User enters query: "me"
Selects vibe: "high_energy"
Duration: 30 seconds
            │
            ▼
┌─────────────────────────────────────┐
│ components/PersonalReelGenerator.tsx│
│ POST /api/events/{id}/reels/generate│
│ { query: "me", vibe: "high_energy", duration: 30 }
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ routers/reels.py                    │
│ generate_custom_reel()              │
└─────────────┬───────────────────────┘
              │
              ├──► INSERT INTO custom_reels (
              │        event_id,
              │        query,
              │        vibe,
              │        duration_sec,
              │        status: 'processing'
              │    )
              │    └──► Returns: reel_id
              │
              └──► Celery: send_task("generate_highlight_reel_task",
                       args=[event_id, reel_id, "me", "high_energy", 30])
              │
              ▼
┌─────────────────────────────────────┐
│ worker_optimized.py                 │
│ @task generate_highlight_reel_task()│
└─────────────┬───────────────────────┘
              │
              ├──► SELECT twelvelabs_index_id FROM events
              │
              ├──► services/twelvelabs_service.py
              │    └──► search_videos(index_id, query="me")
              │         └──► POST https://api.twelvelabs.io/v2/search
              │              Body: {
              │                  query: "me",
              │                  index_id: "index_abc123",
              │                  options: ["visual", "audio"],
              │                  search_type: "semantic"
              │              }
              │              └──► Response: {
              │                      data: [
              │                          {
              │                              video_id: "video_id_A",
              │                              start: 45.2,
              │                              end: 52.8,
              │                              confidence: 0.89,
              │                              clip_text: "person in frame, active motion"
              │                          },
              │                          {
              │                              video_id: "video_id_B",
              │                              start: 120.5,
              │                              end: 128.0,
              │                              confidence: 0.92,
              │                              clip_text: "person celebrating, high energy"
              │                          },
              │                          ... (20 total moments)
              │                      ]
              │                  }
              │
              ├──► GET EMBEDDINGS for each moment:
              │    │
              │    └──► services/twelvelabs_service.py
              │         └──► For each moment:
              │              ├─ Extract video clip embedding (from Pegasus 1.2)
              │              └─ Returns: moment_embedding (512-dim vector)
              │
              ├──► GET VIBE EMBEDDINGS:
              │    │
              │    └──► create_text_embedding("high energy action moments")
              │         └──► Returns: vibe_embedding (512-dim vector)
              │
              ├──► RANK MOMENTS by similarity:
              │    │
              │    └──► For each moment:
              │         ├─ cosine_similarity(moment_embedding, vibe_embedding)
              │         │  └─ Moment 1: similarity = 0.76
              │         │  └─ Moment 2: similarity = 0.91 ★
              │         │  └─ Moment 3: similarity = 0.68
              │         │  ...
              │         │
              │         ├─ Sort by similarity score (descending)
              │         │
              │         └─ Select top moments within duration budget (30s):
              │             selected_moments = [
              │                 { video_id: B, start: 120.5, end: 128.0, score: 0.91 }, (7.5s)
              │                 { video_id: A, start: 45.2, end: 52.8, score: 0.89 }, (7.6s)
              │                 { video_id: C, start: 200.0, end: 207.0, score: 0.85 }, (7.0s)
              │                 { video_id: B, start: 310.2, end: 318.0, score: 0.82 } (7.8s)
              │             ]
              │             Total: 29.9s ≤ 30s ✓
              │
              ├──► EXTRACT MOMENTS (FFmpeg):
              │    │
              │    └──► For each selected_moment:
              │         └──► ffmpeg -ss 120.5 -t 7.5 -i video_B.mp4 -c copy moment_0.mp4
              │              ffmpeg -ss 45.2 -t 7.6 -i video_A.mp4 -c copy moment_1.mp4
              │              ffmpeg -ss 200.0 -t 7.0 -i video_C.mp4 -c copy moment_2.mp4
              │              ffmpeg -ss 310.2 -t 7.8 -i video_B.mp4 -c copy moment_3.mp4
              │
              ├──► COMPOSE REEL (FFmpeg):
              │    │
              │    └──► ffmpeg \
              │           -i moment_0.mp4 -i moment_1.mp4 -i moment_2.mp4 -i moment_3.mp4 \
              │           -i music.mp3 \
              │           -filter_complex "
              │               [0:v][1:v]xfade=transition=fade:duration=0.3:offset=7.2[v01];
              │               [v01][2:v]xfade=transition=fade:duration=0.3:offset=14.8[v02];
              │               [v02][3:v]xfade=transition=fade:duration=0.3:offset=21.8[v_out];
              │
              │               [0:a][1:a][2:a][3:a]concat=n=4:v=0:a=1[event_audio];
              │               [music:a]volume=0.6[music_lowered];
              │               [event_audio][music_lowered]amix=inputs=2[a_out]
              │           " \
              │           -map "[v_out]" -map "[a_out]" \
              │           -c:v libx264 -c:a aac \
              │           reel.mp4
              │         └──► Output: /tmp/reel_{reel_id}.mp4 (45MB, 30s)
              │
              ├──► UPLOAD REEL to S3:
              │    └──► s3.upload_file("/tmp/reel.mp4", "outputs/{reel_id}/reel.mp4")
              │         └──► reel_url = s3.generate_presigned_url(...)
              │
              ├──► UPDATE custom_reels SET
              │        output_url = reel_url,
              │        moments = selected_moments,
              │        status = 'completed'
              │
              └──► Celery task completes (<10s total)
              │
              ▼
┌─────────────────────────────────────┐
│ Frontend (polling)                  │
│ GET /api/events/{id}/reels/{reel_id}│
│ - Detects status: "completed"       │
│ - Shows reel_url instantly          │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ components/VideoPlayer.tsx          │
│ - Plays 30s highlight reel          │
│ - "Download" and "Share" buttons    │
└─────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════════════
                          TECHNOLOGY INTERACTION MAP
═══════════════════════════════════════════════════════════════════════════════════════

┌────────────┐       ┌────────────┐       ┌────────────┐       ┌────────────┐
│  Next.js   │◄─────►│  FastAPI   │◄─────►│  Supabase  │       │    AWS S3  │
│  Frontend  │ HTTP  │  Backend   │  SQL  │ PostgreSQL │       │   Storage  │
│            │       │            │       │            │       │            │
│ React Query│       │ Routers:   │       │ Tables:    │       │ Presigned  │
│ TanStack   │       │ - events   │       │ - events   │       │ URLs       │
│            │       │ - videos   │       │ - videos   │       │            │
│ Components:│       │ - reels    │       │ - timelines│       │ Multipart  │
│ - VideoUp  │       │ - shopify  │       │ - reels    │       │ Upload     │
│ - MusicUp  │       │            │       │ - shopify_*│       │            │
│ - Shopify  │       │ Services:  │       │            │       │ Buckets:   │
│ - Reel Gen │       │ - s3       │◄──────┼────────────┼──────►│ - videos/  │
│ - Analysis │       │ - supabase │       │            │       │ - music/   │
│ - Player   │       │ - redis    │       │            │       │ - outputs/ │
└────────────┘       │ - twelve   │       └────────────┘       └────────────┘
                     │ - veo      │
                     │ - audio    │
                     │ - timeline │       ┌────────────┐       ┌────────────┐
                     │ - render   │       │   Redis    │       │   Celery   │
                     │ - shopify  │◄─────►│   Queue    │◄─────►│   Worker   │
                     └────────────┘       │            │       │            │
                           │              │ Port: 6379 │       │ Tasks:     │
                           │              │            │       │ - analyze  │
                           │              │ Purpose:   │       │ - generate │
                           ▼              │ - Celery   │       │ - sync     │
                     ┌────────────┐       │   broker   │       │ - music    │
                     │  Ngrok     │       │ - OAuth    │       │ - reel     │
                     │  Tunnel    │       │   nonces   │       │            │
                     │            │       │ - Cache    │       │ Parallel:  │
                     │ Dev webhook│       └────────────┘       │ Thread     │
                     │ for Shopify│                            │ Pool       │
                     └────────────┘                            └──────┬─────┘
                                                                      │
                           ┌──────────────────────────────────────────┘
                           │
        ┌──────────────────┼─���────────────────┬─────────────────┐
        │                  │                  │                 │
        ▼                  ▼                  ▼                 ▼
┌────────────┐     ┌────────────┐     ┌────────────┐    ┌────────────┐
│TwelveLabs  │     │Google Veo  │     │  Shopify   │    │   FFmpeg   │
│    API     │     │    API     │     │    API     │    │            │
│            │     │            │     │            │    │ Operations:│
│ Models:    │     │ Model:     │     │ Storefront │    │ - Extract  │
│ - Marengo  │     │ veo-3.1-   │     │ GraphQL    │    │ - Concat   │
│   2.7      │     │ fast       │     │            │    │ - xfade    │
│ - Pegasus  │     │            │     │ OAuth 2.0  │    │ - zoompan  │
│   1.2      │     │ Generate:  │     │            │    │ - overlay  │
│            │     │ - Product  │     │ Products:  │    │ - audio    │
│ Features:  │     │   ads      │     │ - title    │    │   mix      │
│ - Scene    │     │ - Color    │     │ - image    │    │ - duck     │
│ - Object   │     │   grade    │     │ - price    │    │ - encode   │
│ - Action   │     │ - Motion   │     │ - checkout │    │            │
│ - Face     │     │   sync     │     │            │    │ Hardware:  │
│ - Audio    │     │            │     │ HMAC auth  │    │ - h264_    │
│ - Embed    │     │ 4s videos  │     │ verify     │    │   video    │
│ - Search   │     │ 16:9       │     │            │    │   toolbox  │
└────────────┘     └────────────┘     └────────────┘    └──────┬─────┘
                                                                │
                           ┌────────────────────────────────────┘
                           │
                           ▼
                     ┌────────────┐       ┌────────────┐
                     │  librosa   │       │   scipy    │
                     │            │       │            │
                     │ Audio:     │       │ Signal:    │
                     │ - Beat     │◄─────►│ - Correlate│
                     │   detect   │       │ - Offset   │
                     │ - Onset    │       │   find     │
                     │ - Finger   │       │            │
                     │   print    │       │ Multi-angle│
                     │ - Tempo    │       │ sync       │
                     │ - RMS      │       │            │
                     │            │       │ <100ms     │
                     │ Music sync │       │ accuracy   │
                     └────────────┘       └────────────┘

═══════════════════════════════════════════════════════════════════════════════════════
                              DATA FLOW SUMMARY
═══════════════════════════════════════════════════════════════════════════════════════

USER UPLOADS
    │
    ├──► Videos (multipart) ──► S3 ──► Supabase (videos.original_url)
    ├──► Music (presigned) ──► S3 ──► Supabase (events.music_url)
    └──► Shopify OAuth ──► Redis (nonce) ──► Supabase (shopify_stores)
                                                    │
                                                    └──► Celery: sync products
                                                             │
                                                             └──► Shopify API
                                                                      │
                                                                      └──► Supabase (shopify_products)

ANALYSIS TRIGGER
    │
    └──► Celery Worker
             │
             ├──► S3: Download videos
             ├──► FFmpeg: Compress if needed
             ├──► TwelveLabs: Index videos
             │        │
             │        └──► Returns: scenes, objects, actions, embeddings
             │
             └──► Supabase: Store analysis_data

GENERATION TRIGGER
    │
    └──► Celery Worker
             │
             ├──► librosa + scipy: Audio sync
             ├──► Timeline Service: Generate segments, zooms, ad_slots, chapters
             ├──► Google Veo: Generate product ads
             ├──► FFmpeg: Extract segments (parallel)
             ├──► FFmpeg: Compose with xfade + audio mix (single pass)
             ├──► S3: Upload master video
             └──► Supabase: Update master_video_url, status='completed'

REEL GENERATION
    │
    └──► Celery Worker
             │
             ├──► TwelveLabs: Search "me" query
             ├──► Embeddings: Rank by vibe similarity
             ├──► FFmpeg: Extract top moments
             ├──► FFmpeg: Compose reel with music
             ├──► S3: Upload reel
             └──► Supabase: Update reel.output_url, status='completed'

═══════════════════════════════════════════════════════════════════════════════════════
```

This complete flow diagram shows every interaction, API call, service dependency, and data transformation in your Anchor platform from upload to final video generation!
