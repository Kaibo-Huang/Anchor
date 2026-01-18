import { supabase } from './supabase'
import type { Event, Video, CustomReel, Chapter } from './supabase'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Helper to get auth token
async function getAuthToken(): Promise<string | null> {
  const { data: { session } } = await supabase.auth.getSession()
  return session?.access_token || null
}

// Helper for API requests
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const method = options.method || 'GET'
  console.log(`[API] ${method} ${endpoint}`)

  const token = await getAuthToken()
  console.log(`[API] Auth token: ${token ? 'present' : 'none'}`)

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  const startTime = performance.now()
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  })
  const duration = Math.round(performance.now() - startTime)

  console.log(`[API] Response: ${response.status} ${response.statusText} (${duration}ms)`)

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    console.error(`[API] ERROR: ${error.detail || 'Request failed'}`)
    throw new Error(error.detail || 'Request failed')
  }

  const data = await response.json()
  console.log(`[API] Success:`, data)
  return data
}

// Events API
export async function createEvent(data: { name: string; event_type: string }): Promise<Event> {
  return apiRequest('/api/events', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getEvent(eventId: string): Promise<Event> {
  return apiRequest(`/api/events/${eventId}`)
}

export async function listEvents(limit: number = 50, offset: number = 0): Promise<{ events: Event[] }> {
  return apiRequest(`/api/events?limit=${limit}&offset=${offset}`)
}

export async function analyzeEvent(eventId: string): Promise<{ message: string; event_id: string; video_count: number }> {
  return apiRequest(`/api/events/${eventId}/analyze`, {
    method: 'POST',
  })
}

export async function generateVideo(eventId: string, force: boolean = false): Promise<{ message: string; event_id: string }> {
  return apiRequest(`/api/events/${eventId}/generate?force=${force}`, {
    method: 'POST',
  })
}

export async function setSponsor(eventId: string, sponsorName: string): Promise<{ message: string }> {
  return apiRequest(`/api/events/${eventId}/sponsor`, {
    method: 'POST',
    body: JSON.stringify({ sponsor_name: sponsorName }),
  })
}

export async function getChapters(eventId: string): Promise<{ chapters: Chapter[] }> {
  return apiRequest(`/api/events/${eventId}/chapters`)
}

// Videos API
export interface UploadUrlResponse {
  video_id: string
  upload_url: string
  s3_key: string
}

export async function getVideoUploadUrl(
  eventId: string,
  filename: string,
  angleType: string,
  contentType: string = 'video/mp4'
): Promise<UploadUrlResponse> {
  return apiRequest(`/api/events/${eventId}/videos`, {
    method: 'POST',
    body: JSON.stringify({
      filename,
      content_type: contentType,
      angle_type: angleType,
    }),
  })
}

export async function markVideoUploaded(eventId: string, videoId: string): Promise<{ message: string }> {
  return apiRequest(`/api/events/${eventId}/videos/${videoId}/uploaded`, {
    method: 'POST',
  })
}

export async function listVideos(eventId: string): Promise<{ videos: Video[] }> {
  return apiRequest(`/api/events/${eventId}/videos`)
}

// Music API
export interface MusicUploadResponse {
  upload_url: string
  s3_key: string
}

export async function getMusicUploadUrl(
  eventId: string,
  filename: string,
  contentType: string = 'audio/mpeg'
): Promise<MusicUploadResponse> {
  return apiRequest(`/api/events/${eventId}/music/upload`, {
    method: 'POST',
    body: JSON.stringify({
      filename,
      content_type: contentType,
    }),
  })
}

export async function analyzeMusic(eventId: string): Promise<{ message: string }> {
  return apiRequest(`/api/events/${eventId}/music/analyze`, {
    method: 'POST',
  })
}

// Shopify Store API (Brand-level)
export interface ShopifyStore {
  id: string
  shop_domain: string
  shop_name: string | null
  status: string
  installed_at: string
  last_sync_at: string | null
  product_count: number
}

export interface ShopifyProduct {
  id: string
  title: string
  description: string | null
  price: number | string
  currency: string
  image_url: string | null
  checkout_url: string | null
  synced_at?: string
}

export interface BrandProduct {
  id: string
  display_order: number
  is_primary: boolean
  store: ShopifyStore
  product: ShopifyProduct
}

export async function getShopifyInstallUrl(shop: string): Promise<{ install_url: string; shop: string }> {
  return apiRequest(`/api/shopify/install?shop=${encodeURIComponent(shop)}`)
}

export async function listShopifyStores(
  status: string = 'active',
  limit: number = 50,
  offset: number = 0
): Promise<{ stores: ShopifyStore[] }> {
  return apiRequest(`/api/shopify/stores?status=${status}&limit=${limit}&offset=${offset}`)
}

export async function getShopifyStore(storeId: string): Promise<ShopifyStore> {
  return apiRequest(`/api/shopify/stores/${storeId}`)
}

export async function syncShopifyStore(storeId: string): Promise<{ message: string; task_id: string; store_id: string }> {
  return apiRequest(`/api/shopify/stores/${storeId}/sync`, { method: 'POST' })
}

export async function getShopifyStoreProducts(
  storeId: string,
  limit: number = 50,
  offset: number = 0
): Promise<{ products: ShopifyProduct[] }> {
  return apiRequest(`/api/shopify/stores/${storeId}/products?limit=${limit}&offset=${offset}`)
}

// Event-Brand Association API
export async function getEventBrands(eventId: string): Promise<{ brand_products: BrandProduct[] }> {
  return apiRequest(`/api/events/${eventId}/brands`)
}

export async function addEventBrands(
  eventId: string,
  storeId: string,
  productIds: string[],
  setPrimary: boolean = false
): Promise<{ message: string; associations: Array<{ id: string; product_id: string; is_primary: boolean }> }> {
  return apiRequest(`/api/events/${eventId}/brands`, {
    method: 'POST',
    body: JSON.stringify({
      store_id: storeId,
      product_ids: productIds,
      set_primary: setPrimary,
    }),
  })
}

export async function removeEventBrand(eventId: string, associationId: string): Promise<{ message: string }> {
  return apiRequest(`/api/events/${eventId}/brands/${associationId}`, {
    method: 'DELETE',
  })
}

// Legacy Shopify API (for backward compatibility)
export async function getShopifyAuthUrl(eventId: string, shop: string): Promise<{ auth_url: string }> {
  return apiRequest(`/api/events/${eventId}/shopify/auth-url?shop=${encodeURIComponent(shop)}`)
}

export async function getShopifyProducts(eventId: string): Promise<{ products: ShopifyProduct[] }> {
  return apiRequest(`/api/events/${eventId}/shopify/products`)
}

export async function disconnectShopify(eventId: string): Promise<{ message: string }> {
  return apiRequest(`/api/events/${eventId}/shopify`, {
    method: 'DELETE',
  })
}

// Reels API
export interface GenerateReelRequest {
  query: string
  vibe: 'high_energy' | 'emotional' | 'calm'
  duration?: number
  include_music?: boolean
}

export interface GenerateReelResponse {
  reel_id: string
  message: string
}

export async function generateReel(eventId: string, data: GenerateReelRequest): Promise<GenerateReelResponse> {
  return apiRequest(`/api/events/${eventId}/reels/generate`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function listReels(eventId: string): Promise<{ reels: CustomReel[] }> {
  return apiRequest(`/api/events/${eventId}/reels`)
}

export async function getReel(eventId: string, reelId: string): Promise<CustomReel> {
  return apiRequest(`/api/events/${eventId}/reels/${reelId}`)
}

// File upload helper with progress tracking
export async function uploadFileToS3(
  uploadUrl: string,
  file: File,
  onProgress?: (progress: number) => void
): Promise<void> {
  console.log(`[S3 Upload] Starting upload to S3`)
  console.log(`[S3 Upload] File: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)`)
  console.log(`[S3 Upload] Type: ${file.type}`)

  const startTime = performance.now()

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && onProgress) {
        const progress = Math.round((event.loaded / event.total) * 100)
        onProgress(progress)
        if (progress % 25 === 0) {
          console.log(`[S3 Upload] Progress: ${progress}%`)
        }
      }
    })

    xhr.addEventListener('load', () => {
      const duration = Math.round((performance.now() - startTime) / 1000)
      if (xhr.status >= 200 && xhr.status < 300) {
        console.log(`[S3 Upload] Upload complete (${duration}s)`)
        resolve()
      } else {
        console.error(`[S3 Upload] ERROR: Upload failed with status ${xhr.status}`)
        reject(new Error(`Upload failed with status ${xhr.status}`))
      }
    })

    xhr.addEventListener('error', () => {
      console.error(`[S3 Upload] ERROR: Network error`)
      reject(new Error('Upload failed - network error'))
    })

    xhr.addEventListener('abort', () => {
      console.warn(`[S3 Upload] Upload cancelled`)
      reject(new Error('Upload was cancelled'))
    })

    xhr.open('PUT', uploadUrl)
    xhr.setRequestHeader('Content-Type', file.type)
    xhr.send(file)
  })
}

// Combined upload flow with progress callback (uses intelligent multipart for large files)
export async function uploadVideo(
  eventId: string,
  file: File,
  angleType: string,
  onProgress?: (stage: 'preparing' | 'uploading' | 'finalizing', progress: number) => void
): Promise<{ videoId: string }> {
  // Delegate to V2 implementation which handles both simple and multipart
  return uploadVideoV2(eventId, file, angleType, onProgress)
}

export async function uploadMusic(eventId: string, file: File): Promise<void> {
  console.log(`[Music Upload] ========== STARTING MUSIC UPLOAD ==========`)
  console.log(`[Music Upload] Event ID: ${eventId}`)
  console.log(`[Music Upload] File: ${file.name}`)
  console.log(`[Music Upload] Size: ${(file.size / (1024 * 1024)).toFixed(1)} MB`)

  // Get presigned URL
  console.log(`[Music Upload] Getting presigned URL...`)
  const { upload_url } = await getMusicUploadUrl(eventId, file.name, file.type)
  console.log(`[Music Upload] Presigned URL obtained`)

  // Upload to S3
  console.log(`[Music Upload] Uploading to S3...`)
  await uploadFileToS3(upload_url, file)
  console.log(`[Music Upload] ========== MUSIC UPLOAD COMPLETE ==========`)
}

// Multipart Upload Types and Functions

export interface MultipartUploadInitRequest {
  filename: string
  content_type: string
  file_size: number
  angle_type: string
}

export interface MultipartUploadInitResponse {
  video_id: string
  upload_id: string
  s3_key: string
  chunk_size: number
  total_chunks: number
  use_multipart: boolean
  upload_url: string | null
}

export interface ChunkUrlResponse {
  chunk_number: number
  upload_url: string
}

export interface CompletedPart {
  PartNumber: number
  ETag: string
}

export async function initMultipartUpload(
  eventId: string,
  filename: string,
  fileSize: number,
  angleType: string,
  contentType: string = 'video/mp4'
): Promise<MultipartUploadInitResponse> {
  return apiRequest(`/api/events/${eventId}/videos/multipart/init`, {
    method: 'POST',
    body: JSON.stringify({
      filename,
      content_type: contentType,
      file_size: fileSize,
      angle_type: angleType,
    }),
  })
}

export async function getChunkUploadUrl(
  eventId: string,
  videoId: string,
  uploadId: string,
  chunkNumber: number
): Promise<ChunkUrlResponse> {
  return apiRequest(`/api/events/${eventId}/videos/${videoId}/multipart/chunk-url`, {
    method: 'POST',
    body: JSON.stringify({
      upload_id: uploadId,
      chunk_number: chunkNumber,
    }),
  })
}

export async function completeMultipartUpload(
  eventId: string,
  videoId: string,
  uploadId: string,
  parts: CompletedPart[]
): Promise<{ message: string }> {
  return apiRequest(`/api/events/${eventId}/videos/${videoId}/multipart/complete`, {
    method: 'POST',
    body: JSON.stringify({
      upload_id: uploadId,
      parts,
    }),
  })
}

export async function abortMultipartUpload(
  eventId: string,
  videoId: string,
  uploadId: string
): Promise<{ message: string }> {
  return apiRequest(`/api/events/${eventId}/videos/${videoId}/multipart/abort`, {
    method: 'POST',
    body: JSON.stringify({
      upload_id: uploadId,
    }),
  })
}

// Helper to upload a single chunk with retry logic
async function uploadChunkWithRetry(
  uploadUrl: string,
  chunk: Blob,
  chunkNumber: number,
  maxRetries: number = 3,
  onProgress?: (loaded: number, total: number) => void
): Promise<string> {
  let lastError: Error | null = null

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      console.log(`[Chunk ${chunkNumber}] Attempt ${attempt}/${maxRetries}`)

      const etag = await new Promise<string>((resolve, reject) => {
        const xhr = new XMLHttpRequest()

        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable && onProgress) {
            onProgress(event.loaded, event.total)
          }
        })

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            const etag = xhr.getResponseHeader('ETag')
            if (etag) {
              console.log(`[Chunk ${chunkNumber}] Upload complete, ETag: ${etag}`)
              resolve(etag)
            } else {
              reject(new Error('No ETag returned'))
            }
          } else {
            reject(new Error(`Upload failed with status ${xhr.status}`))
          }
        })

        xhr.addEventListener('error', () => {
          reject(new Error('Network error'))
        })

        xhr.addEventListener('timeout', () => {
          reject(new Error('Upload timeout'))
        })

        xhr.timeout = 30000 // 30 second timeout
        xhr.open('PUT', uploadUrl)
        xhr.send(chunk)
      })

      return etag
    } catch (error) {
      lastError = error as Error
      console.error(`[Chunk ${chunkNumber}] Upload failed (attempt ${attempt}):`, error)

      if (attempt < maxRetries) {
        // Exponential backoff: 1s, 2s, 4s
        const delay = Math.pow(2, attempt - 1) * 1000
        console.log(`[Chunk ${chunkNumber}] Retrying in ${delay}ms...`)
        await new Promise(resolve => setTimeout(resolve, delay))
      }
    }
  }

  throw lastError || new Error('Upload failed after retries')
}

// Replace uploadVideo with intelligent multipart version
export async function uploadVideoV2(
  eventId: string,
  file: File,
  angleType: string,
  onProgress?: (stage: 'preparing' | 'uploading' | 'finalizing', progress: number) => void
): Promise<{ videoId: string }> {
  console.log(`[Video Upload V2] Starting upload for ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)`)

  // Stage 1: Initialize upload (0-5%)
  onProgress?.('preparing', 0)
  const initResponse = await initMultipartUpload(
    eventId,
    file.name,
    file.size,
    angleType,
    file.type
  )

  console.log(`[Video Upload V2] Upload strategy: ${initResponse.use_multipart ? 'multipart' : 'simple'}`)
  onProgress?.('preparing', 5)

  if (!initResponse.use_multipart) {
    // Simple upload for small files
    console.log(`[Video Upload V2] Using simple upload`)
    await uploadFileToS3(initResponse.upload_url!, file, (uploadProgress) => {
      const overallProgress = 5 + Math.round(uploadProgress * 0.9)
      onProgress?.('uploading', overallProgress)
    })

    onProgress?.('finalizing', 95)
    await markVideoUploaded(eventId, initResponse.video_id)
    onProgress?.('finalizing', 100)

    return { videoId: initResponse.video_id }
  }

  // Multipart upload for large files
  console.log(`[Video Upload V2] Using multipart upload: ${initResponse.total_chunks} chunks`)

  const { video_id, upload_id, chunk_size, total_chunks } = initResponse
  const completedParts: CompletedPart[] = []

  try {
    // Stage 2: Upload chunks (5-95%)
    onProgress?.('uploading', 5)

    // Track progress across all chunks
    const chunkProgress = new Array(total_chunks).fill(0)

    const updateOverallProgress = () => {
      const totalProgress = chunkProgress.reduce((sum, p) => sum + p, 0) / total_chunks
      const overallProgress = 5 + Math.round(totalProgress * 0.9)
      onProgress?.('uploading', overallProgress)
    }

    // Upload chunks with concurrency control
    const maxConcurrency = 4
    const uploadChunk = async (chunkNumber: number) => {
      // Calculate chunk boundaries
      const start = (chunkNumber - 1) * chunk_size
      const end = Math.min(start + chunk_size, file.size)
      const chunk = file.slice(start, end)

      console.log(`[Chunk ${chunkNumber}/${total_chunks}] Size: ${(chunk.size / (1024 * 1024)).toFixed(1)} MB`)

      // Get presigned URL for this chunk
      const { upload_url } = await getChunkUploadUrl(eventId, video_id, upload_id, chunkNumber)

      // Upload chunk with retry
      const etag = await uploadChunkWithRetry(
        upload_url,
        chunk,
        chunkNumber,
        3,
        (loaded, total) => {
          chunkProgress[chunkNumber - 1] = (loaded / total) * 100
          updateOverallProgress()
        }
      )

      completedParts.push({
        PartNumber: chunkNumber,
        ETag: etag,
      })

      chunkProgress[chunkNumber - 1] = 100
      updateOverallProgress()
    }

    // Upload chunks in batches with concurrency control
    for (let i = 0; i < total_chunks; i += maxConcurrency) {
      const batch = []
      for (let j = i; j < Math.min(i + maxConcurrency, total_chunks); j++) {
        batch.push(uploadChunk(j + 1))
      }
      await Promise.all(batch)
    }

    // Sort parts by part number (S3 requires this)
    completedParts.sort((a, b) => a.PartNumber - b.PartNumber)

    // Stage 3: Complete multipart upload (95-100%)
    onProgress?.('finalizing', 95)
    console.log(`[Video Upload V2] Completing multipart upload with ${completedParts.length} parts`)

    await completeMultipartUpload(eventId, video_id, upload_id, completedParts)
    onProgress?.('finalizing', 100)

    console.log(`[Video Upload V2] Upload complete`)
    return { videoId: video_id }

  } catch (error) {
    console.error(`[Video Upload V2] Upload failed, aborting multipart upload:`, error)

    // Abort multipart upload on error
    try {
      await abortMultipartUpload(eventId, video_id, upload_id)
    } catch (abortError) {
      console.error(`[Video Upload V2] Failed to abort multipart upload:`, abortError)
    }

    throw error
  }
}
