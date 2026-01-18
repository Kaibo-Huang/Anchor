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

export async function analyzeEvent(eventId: string): Promise<{ message: string; event_id: string; video_count: number }> {
  return apiRequest(`/api/events/${eventId}/analyze`, {
    method: 'POST',
  })
}

export async function generateVideo(eventId: string): Promise<{ message: string; event_id: string }> {
  return apiRequest(`/api/events/${eventId}/generate`, {
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

// Combined upload flow with progress callback
export async function uploadVideo(
  eventId: string,
  file: File,
  angleType: string,
  onProgress?: (stage: 'preparing' | 'uploading' | 'finalizing', progress: number) => void
): Promise<{ videoId: string }> {
  console.log(`[Video Upload] ========== STARTING VIDEO UPLOAD ==========`)
  console.log(`[Video Upload] Event ID: ${eventId}`)
  console.log(`[Video Upload] File: ${file.name}`)
  console.log(`[Video Upload] Size: ${(file.size / (1024 * 1024)).toFixed(1)} MB`)
  console.log(`[Video Upload] Angle type: ${angleType}`)

  // Stage 1: Get presigned URL (5%)
  console.log(`[Video Upload] Stage 1: Getting presigned URL...`)
  onProgress?.('preparing', 5)
  const { video_id, upload_url } = await getVideoUploadUrl(
    eventId,
    file.name,
    angleType,
    file.type
  )
  console.log(`[Video Upload] Video ID assigned: ${video_id}`)
  console.log(`[Video Upload] Presigned URL obtained`)

  // Stage 2: Upload to S3 (5-95%)
  console.log(`[Video Upload] Stage 2: Uploading to S3...`)
  onProgress?.('uploading', 5)
  await uploadFileToS3(upload_url, file, (uploadProgress) => {
    // Map 0-100% upload progress to 5-95% overall progress
    const overallProgress = 5 + Math.round(uploadProgress * 0.9)
    onProgress?.('uploading', overallProgress)
  })
  console.log(`[Video Upload] S3 upload complete`)

  // Stage 3: Mark as uploaded (95-100%)
  console.log(`[Video Upload] Stage 3: Marking video as uploaded...`)
  onProgress?.('finalizing', 95)
  await markVideoUploaded(eventId, video_id)
  onProgress?.('finalizing', 100)
  console.log(`[Video Upload] Video marked as uploaded`)
  console.log(`[Video Upload] ========== VIDEO UPLOAD COMPLETE ==========`)

  return { videoId: video_id }
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
