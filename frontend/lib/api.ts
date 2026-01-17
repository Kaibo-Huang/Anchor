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
  const token = await getAuthToken()

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || 'Request failed')
  }

  return response.json()
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

// Shopify API
export async function getShopifyAuthUrl(eventId: string, shop: string): Promise<{ auth_url: string }> {
  return apiRequest(`/api/events/${eventId}/shopify/auth-url?shop=${encodeURIComponent(shop)}`)
}

export interface ShopifyProduct {
  id: string
  title: string
  description: string
  price: string
  currency: string
  image_url: string | null
  checkout_url: string | null
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

// File upload helper
export async function uploadFileToS3(uploadUrl: string, file: File): Promise<void> {
  const response = await fetch(uploadUrl, {
    method: 'PUT',
    body: file,
    headers: {
      'Content-Type': file.type,
    },
  })

  if (!response.ok) {
    throw new Error('Failed to upload file')
  }
}

// Combined upload flow
export async function uploadVideo(
  eventId: string,
  file: File,
  angleType: string
): Promise<{ videoId: string }> {
  // Get presigned URL
  const { video_id, upload_url } = await getVideoUploadUrl(
    eventId,
    file.name,
    angleType,
    file.type
  )

  // Upload to S3
  await uploadFileToS3(upload_url, file)

  // Mark as uploaded
  await markVideoUploaded(eventId, video_id)

  return { videoId: video_id }
}

export async function uploadMusic(eventId: string, file: File): Promise<void> {
  // Get presigned URL
  const { upload_url } = await getMusicUploadUrl(eventId, file.name, file.type)

  // Upload to S3
  await uploadFileToS3(upload_url, file)
}
