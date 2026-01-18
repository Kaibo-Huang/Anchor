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
import ProcessingLogs from '@/components/ProcessingLogs'
import Link from 'next/link'

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
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-[#4078F2] border-t-transparent rounded-full animate-spin"></div>
          <p className="text-[#A1A1A1] text-lg">Loading your event...</p>
        </div>
      </div>
    )
  }

  if (!event) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <h2 className="text-2xl font-semibold text-[#383A42]">Event not found</h2>
        <Link href="/" className="text-[#4078F2] hover:underline">Return home</Link>
      </div>
    )
  }

  const videos = videosData?.videos || []
  const reels = reelsData?.reels || []
  const uploadedVideos = videos.filter(v => v.status !== 'uploading')

  const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
    created: { bg: 'bg-[#F4F4F4]', text: 'text-[#383A42]', label: 'Ready' },
    uploading: { bg: 'bg-[#4078F2]/10', text: 'text-[#4078F2]', label: 'Uploading' },
    analyzing: { bg: 'bg-[#4078F2]/10', text: 'text-[#4078F2]', label: 'Analyzing' },
    analyzed: { bg: 'bg-[#50A14F]/10', text: 'text-[#50A14F]', label: 'Analyzed' },
    generating: { bg: 'bg-[#4078F2]/10', text: 'text-[#4078F2]', label: 'Generating' },
    completed: { bg: 'bg-[#50A14F]/10', text: 'text-[#50A14F]', label: 'Complete' },
    failed: { bg: 'bg-[#CA1243]/10', text: 'text-[#CA1243]', label: 'Failed' },
  }

  const status = statusConfig[event.status] || statusConfig.created

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-4xl font-bold text-white tracking-tight">{event.name}</h1>
          <p className="text-[#A1A1A1] mt-2 text-lg capitalize">{event.event_type} Event</p>
        </div>
        <span className={`px-4 py-2 rounded-full text-sm font-semibold ${status.bg} ${status.text}`}>
          {status.label}
        </span>
      </div>

      {shopifyConnected && (
        <div className="bg-[#50A14F]/10 border border-[#50A14F]/20 rounded-2xl p-4">
          <p className="text-[#50A14F] font-medium">Shopify store connected successfully!</p>
        </div>
      )}

      {/* Main Video Player (when completed) */}
      {event.status === 'completed' && event.master_video_url && (
        <div className="bg-white rounded-3xl border border-[#E5E5E5] p-8">
          <h2 className="text-2xl font-bold text-[#383A42] mb-6">Final Video</h2>
          <div className="rounded-2xl overflow-hidden">
            <VideoPlayer url={event.master_video_url} />
          </div>
        </div>
      )}

      {/* Progress Steps */}
      <div className="bg-white rounded-3xl border border-[#E5E5E5] p-8">
        <h2 className="text-2xl font-bold text-[#383A42] mb-8">Production Pipeline</h2>
        <div className="space-y-6">
          {/* Step 1: Upload */}
          <div className="flex items-start gap-5">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold shrink-0 ${
              uploadedVideos.length > 0 ? 'bg-[#50A14F] text-white' : 'bg-[#E5E5E5] text-[#6B6B6B]'
            }`}>
              {uploadedVideos.length > 0 ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                </svg>
              ) : '1'}
            </div>
            <div className="flex-1 pt-1">
              <h3 className="font-semibold text-[#383A42] text-lg">Upload Videos</h3>
              <p className="text-[#A1A1A1] mt-1">
                {uploadedVideos.length} video{uploadedVideos.length !== 1 ? 's' : ''} uploaded
              </p>
            </div>
          </div>

          {/* Step 2: Analyze */}
          <div className="flex items-start gap-5">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold shrink-0 transition-all ${
              event.status === 'analyzed' || event.status === 'generating' || event.status === 'completed'
                ? 'bg-[#50A14F] text-white'
                : event.status === 'analyzing'
                ? 'bg-[#4078F2] text-white animate-pulse'
                : 'bg-[#E5E5E5] text-[#6B6B6B]'
            }`}>
              {event.status === 'analyzed' || event.status === 'generating' || event.status === 'completed' ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                </svg>
              ) : '2'}
            </div>
            <div className="flex-1 pt-1">
              <h3 className="font-semibold text-[#383A42] text-lg">AI Analysis</h3>
              <p className="text-[#A1A1A1] mt-1">
                {event.status === 'analyzing' ? 'Analyzing with TwelveLabs...' : 'Scene detection, objects, actions'}
              </p>
              <AnalysisProgress progress={event.analysis_progress} status={event.status} />
            </div>
          </div>

          {/* Step 3: Generate */}
          <div className="flex items-start gap-5">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold shrink-0 transition-all ${
              event.status === 'completed'
                ? 'bg-[#50A14F] text-white'
                : event.status === 'generating'
                ? 'bg-[#4078F2] text-white animate-pulse'
                : 'bg-[#E5E5E5] text-[#6B6B6B]'
            }`}>
              {event.status === 'completed' ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                </svg>
              ) : '3'}
            </div>
            <div className="flex-1 pt-1">
              <h3 className="font-semibold text-[#383A42] text-lg">Generate Video</h3>
              <p className="text-[#A1A1A1] mt-1">
                {event.status === 'generating' ? 'Rendering final video...' : 'Multi-angle switching, zooms, music'}
              </p>
              <GenerationProgress progress={event.generation_progress} status={event.status} />
            </div>
          </div>
        </div>

        {/* Processing Logs */}
        {(event.status === 'analyzing' || event.status === 'analyzed' || event.status === 'generating' || event.status === 'completed' || event.status === 'failed') && (
          <div className="mt-8">
            <ProcessingLogs
              analysisProgress={event.analysis_progress}
              generationProgress={event.generation_progress}
              eventStatus={event.status}
            />
          </div>
        )}

        {/* Action Buttons */}
        <div className="mt-8 flex gap-4">
          {event.status === 'created' && uploadedVideos.length > 0 && (
            <button
              onClick={() => analyzeMutation.mutate()}
              disabled={analyzeMutation.isPending}
              className="px-6 py-3 bg-[#4078F2] text-white rounded-xl font-semibold hover:bg-[#2d5bd9] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {analyzeMutation.isPending ? 'Starting...' : 'Start Analysis'}
            </button>
          )}

          {event.status === 'analyzed' && (
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
              className="px-6 py-3 bg-[#4078F2] text-white rounded-xl font-semibold hover:bg-[#2d5bd9] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {generateMutation.isPending ? 'Starting...' : 'Generate Final Video'}
            </button>
          )}

          {event.status === 'completed' && (
            <button
              onClick={() => regenerateMutation.mutate()}
              disabled={regenerateMutation.isPending}
              className="px-6 py-3 bg-white text-[#4078F2] border-2 border-[#4078F2] rounded-xl font-semibold hover:bg-[#4078F2]/5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {regenerateMutation.isPending ? 'Re-rendering...' : 'Re-render Video'}
            </button>
          )}

          {event.status === 'failed' && uploadedVideos.length > 0 && (
            <button
              onClick={() => analyzeMutation.mutate()}
              disabled={analyzeMutation.isPending}
              className="px-6 py-3 bg-[#CA1243] text-white rounded-xl font-semibold hover:bg-[#a80f37] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {analyzeMutation.isPending ? 'Retrying...' : 'Retry Analysis'}
            </button>
          )}
        </div>
      </div>

      {/* Video Upload Section */}
      {(event.status === 'created' || event.status === 'uploading') && (
        <div className="bg-white rounded-3xl border border-[#E5E5E5] p-8">
          <h2 className="text-2xl font-bold text-[#383A42] mb-6">Upload Videos</h2>
          <VideoUpload eventId={eventId} existingVideos={videos} />
        </div>
      )}

      {/* Music Upload */}
      {event.status !== 'completed' && (
        <div className="bg-white rounded-3xl border border-[#E5E5E5] p-8">
          <h2 className="text-2xl font-bold text-[#383A42] mb-6">Personal Music</h2>
          <p className="text-[#A1A1A1] mb-4">Add your own soundtrack to make it personal</p>
          <MusicUpload eventId={eventId} currentMusicUrl={event.music_url} />
        </div>
      )}

      {/* Personal Highlight Reels */}
      {(event.status === 'analyzed' || event.status === 'completed') && (
        <div className="bg-white rounded-3xl border border-[#E5E5E5] p-8">
          <h2 className="text-2xl font-bold text-[#383A42] mb-6">Create Your Highlight Reel</h2>
          <p className="text-[#A1A1A1] mb-4">Find yourself in the footage with natural language search</p>
          <PersonalReelGenerator eventId={eventId} reels={reels} />
        </div>
      )}

      {/* Shopify Integration */}
      <div className="bg-white rounded-3xl border border-[#E5E5E5] p-8">
        <h2 className="text-2xl font-bold text-[#383A42] mb-6">Shopify Integration</h2>
        <p className="text-[#A1A1A1] mb-4">Connect your store for native product ads</p>
        <ShopifyConnect eventId={eventId} connectedUrl={event.shopify_store_url} />
      </div>
    </div>
  )
}
