import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

// Types for database tables
export interface Event {
  id: string
  user_id: string | null
  name: string
  event_type: 'sports' | 'ceremony' | 'performance'
  status: 'created' | 'uploading' | 'analyzing' | 'analyzed' | 'generating' | 'completed' | 'failed'
  shopify_store_url: string | null
  sponsor_name: string | null
  master_video_url: string | null
  music_url: string | null
  music_metadata: MusicMetadata | null
  twelvelabs_index_id: string | null
  created_at: string
  updated_at: string
}

export interface Video {
  id: string
  event_id: string
  original_url: string
  angle_type: 'wide' | 'closeup' | 'crowd' | 'goal_angle' | 'stage' | 'other'
  sync_offset_ms: number
  analysis_data: Record<string, unknown> | null
  twelvelabs_video_id: string | null
  status: 'uploading' | 'uploaded' | 'analyzing' | 'analyzed' | 'failed'
  created_at: string
}

export interface Timeline {
  id: string
  event_id: string
  segments: TimelineSegment[]
  zooms: ZoomMoment[]
  ad_slots: AdSlot[]
  chapters: Chapter[]
  beat_synced: boolean
  created_at: string
}

export interface CustomReel {
  id: string
  event_id: string
  query: string
  vibe: 'high_energy' | 'emotional' | 'calm'
  output_url: string | null
  moments: ReelMoment[] | null
  duration_sec: number | null
  status: 'processing' | 'completed' | 'failed'
  created_at: string
}

// Supporting types
export interface MusicMetadata {
  tempo_bpm: number
  beat_times_ms: number[]
  intro_end_ms: number
  outro_start_ms: number
  duration_ms: number
  intensity_curve: number[]
}

export interface TimelineSegment {
  start_ms: number
  end_ms: number
  video_id: string
}

export interface ZoomMoment {
  start_ms: number
  duration_ms: number
  zoom_factor: number
}

export interface AdSlot {
  timestamp_ms: number
  score: number
  duration_ms: number
}

export interface Chapter {
  timestamp_ms: number
  title: string
  type: 'section' | 'highlight'
}

export interface ReelMoment {
  video_id: string
  start: number
  end: number
  confidence: number
  vibe_score: number
  final_score: number
}

// Auth helpers
export async function signInWithGoogle() {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: `${window.location.origin}/auth/callback`,
    },
  })
  return { data, error }
}

export async function signOut() {
  const { error } = await supabase.auth.signOut()
  return { error }
}

export async function getSession() {
  const { data: { session }, error } = await supabase.auth.getSession()
  return { session, error }
}

export async function getUser() {
  const { data: { user }, error } = await supabase.auth.getUser()
  return { user, error }
}
