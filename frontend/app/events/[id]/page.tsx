'use client'

import { useParams, useSearchParams } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getEvent, analyzeEvent, generateVideo, listVideos, listReels } from '@/lib/api'
import VideoUpload from '@/components/VideoUpload'
import MusicUpload from '@/components/MusicUpload'
import ShopifyConnect from '@/components/ShopifyConnect'
import PersonalReelGenerator from '@/components/PersonalReelGenerator'
import VideoPlayer from '@/components/VideoPlayer'
import AnalysisProgress from '@/components/AnalysisProgress'
import GenerationProgress from '@/components/GenerationProgress'

export default function EventPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const eventId = params.id as string
  const queryClient = useQueryClient()

  const shopifyConnected = searchParams.get('shopify') === 'connected'

  const { data: event, isLoading: eventLoading } = useQuery({
    queryKey: ['event', eventId],
    queryFn: () => getEvent(eventId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'analyzing' || status === 'generating') {
        return 3000 // Poll every 3s while processing
      }
      return false
    },
  })

  const { data: videosData } = useQuery({
    queryKey: ['videos', eventId],
    queryFn: () => listVideos(eventId),
  })

  const { data: reelsData } = useQuery({
    queryKey: ['reels', eventId],
    queryFn: () => listReels(eventId),
    enabled: event?.status === 'analyzed' || event?.status === 'completed',
  })

  const analyzeMutation = useMutation({
    mutationFn: () => analyzeEvent(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] })
    },
  })

  const generateMutation = useMutation({
    mutationFn: () => generateVideo(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] })
    },
  })

  const regenerateMutation = useMutation({
    mutationFn: () => generateVideo(eventId, true), // force=true
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] })
    },
  })

  if (eventLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    )
  }

  if (!event) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-semibold text-gray-900">Event not found</h2>
      </div>
    )
  }

  const videos = videosData?.videos || []
  const reels = reelsData?.reels || []
  const uploadedVideos = videos.filter(v => v.status !== 'uploading')

  const statusColors: Record<string, string> = {
    created: 'bg-gray-100 text-gray-800',
    uploading: 'bg-blue-100 text-blue-800',
    analyzing: 'bg-yellow-100 text-yellow-800',
    analyzed: 'bg-green-100 text-green-800',
    generating: 'bg-purple-100 text-purple-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">{event.name}</h1>
          <p className="text-gray-500 mt-1 capitalize">{event.event_type} Event</p>
        </div>
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusColors[event.status]}`}>
          {event.status.charAt(0).toUpperCase() + event.status.slice(1)}
        </span>
      </div>

      {shopifyConnected && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-green-800">Shopify store connected successfully!</p>
        </div>
      )}

      {/* Main Video Player (when completed) */}
      {event.status === 'completed' && event.master_video_url && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold mb-4">Final Video</h2>
          <VideoPlayer url={event.master_video_url} />
        </div>
      )}

      {/* Progress Steps */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-semibold mb-6">Production Pipeline</h2>
        <div className="space-y-4">
          {/* Step 1: Upload */}
          <div className="flex items-start gap-4">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white ${
              uploadedVideos.length > 0 ? 'bg-green-500' : 'bg-gray-300'
            }`}>
              {uploadedVideos.length > 0 ? '✓' : '1'}
            </div>
            <div className="flex-1">
              <h3 className="font-medium">Upload Videos</h3>
              <p className="text-sm text-gray-500">
                {uploadedVideos.length} video{uploadedVideos.length !== 1 ? 's' : ''} uploaded
              </p>
            </div>
          </div>

          {/* Step 2: Analyze */}
          <div className="flex items-start gap-4">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white ${
              event.status === 'analyzed' || event.status === 'generating' || event.status === 'completed'
                ? 'bg-green-500'
                : event.status === 'analyzing'
                ? 'bg-yellow-500 animate-pulse'
                : 'bg-gray-300'
            }`}>
              {event.status === 'analyzed' || event.status === 'generating' || event.status === 'completed' ? '✓' : '2'}
            </div>
            <div className="flex-1">
              <h3 className="font-medium">AI Analysis</h3>
              <p className="text-sm text-gray-500">
                {event.status === 'analyzing' ? 'Analyzing with TwelveLabs...' : 'Scene detection, objects, actions'}
              </p>
              {/* Detailed Progress Bar */}
              <AnalysisProgress progress={event.analysis_progress} status={event.status} />
            </div>
          </div>

          {/* Step 3: Generate */}
          <div className="flex items-start gap-4">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white ${
              event.status === 'completed'
                ? 'bg-green-500'
                : event.status === 'generating'
                ? 'bg-purple-500 animate-pulse'
                : 'bg-gray-300'
            }`}>
              {event.status === 'completed' ? '✓' : '3'}
            </div>
            <div className="flex-1">
              <h3 className="font-medium">Generate Video</h3>
              <p className="text-sm text-gray-500">
                {event.status === 'generating' ? 'Rendering final video...' : 'Multi-angle switching, zooms, music'}
              </p>
              {/* Detailed Progress Bar for Generation */}
              <GenerationProgress progress={event.generation_progress} status={event.status} />
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="mt-6 flex gap-4">
          {event.status === 'created' && uploadedVideos.length > 0 && (
            <button
              onClick={() => analyzeMutation.mutate()}
              disabled={analyzeMutation.isPending}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {analyzeMutation.isPending ? 'Starting...' : 'Start Analysis'}
            </button>
          )}

          {event.status === 'analyzed' && (
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
            >
              {generateMutation.isPending ? 'Starting...' : 'Generate Final Video'}
            </button>
          )}

          {event.status === 'completed' && (
            <button
              onClick={() => regenerateMutation.mutate()}
              disabled={regenerateMutation.isPending}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
            >
              {regenerateMutation.isPending ? 'Re-rendering...' : 'Re-render Video'}
            </button>
          )}

          {event.status === 'failed' && uploadedVideos.length > 0 && (
            <button
              onClick={() => analyzeMutation.mutate()}
              disabled={analyzeMutation.isPending}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              {analyzeMutation.isPending ? 'Retrying...' : 'Retry Analysis'}
            </button>
          )}
        </div>
      </div>

      {/* Video Upload Section */}
      {(event.status === 'created' || event.status === 'uploading') && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold mb-4">Upload Videos</h2>
          <VideoUpload eventId={eventId} existingVideos={videos} />
        </div>
      )}

      {/* Music Upload */}
      {event.status !== 'completed' && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold mb-4">Personal Music (Optional)</h2>
          <MusicUpload eventId={eventId} currentMusicUrl={event.music_url} />
        </div>
      )}

      {/* Shopify Integration */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-semibold mb-4">Shopify Integration</h2>
        <ShopifyConnect eventId={eventId} connectedUrl={event.shopify_store_url} />
      </div>

      {/* Personal Highlight Reels */}
      {(event.status === 'analyzed' || event.status === 'completed') && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold mb-4">Create Your Highlight Reel</h2>
          <PersonalReelGenerator eventId={eventId} reels={reels} />
        </div>
      )}
    </div>
  )
}
