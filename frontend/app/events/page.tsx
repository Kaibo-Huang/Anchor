'use client'

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { listEvents } from '@/lib/api'

export default function EventsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['events'],
    queryFn: () => listEvents(),
    refetchInterval: 10000, // Refresh every 10s
  })

  const events = data?.events || []

  const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
    created: { bg: 'bg-[#F4F4F4]', text: 'text-[#383A42]', label: 'Ready' },
    uploading: { bg: 'bg-[#4078F2]/10', text: 'text-[#4078F2]', label: 'Uploading' },
    analyzing: { bg: 'bg-[#4078F2]/10', text: 'text-[#4078F2]', label: 'Analyzing' },
    analyzed: { bg: 'bg-[#50A14F]/10', text: 'text-[#50A14F]', label: 'Analyzed' },
    generating: { bg: 'bg-[#4078F2]/10', text: 'text-[#4078F2]', label: 'Generating' },
    completed: { bg: 'bg-[#50A14F]/10', text: 'text-[#50A14F]', label: 'Complete' },
    failed: { bg: 'bg-[#CA1243]/10', text: 'text-[#CA1243]', label: 'Failed' },
  }

  const eventTypeIcons: Record<string, string> = {
    sports: '🏆',
    ceremony: '🎓',
    performance: '🎸',
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-[#4078F2] border-t-transparent rounded-full animate-spin"></div>
          <p className="text-[#A1A1A1] text-lg">Loading your events...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <h2 className="text-2xl font-semibold text-[#CA1243]">Error loading events</h2>
        <p className="text-[#A1A1A1] mt-2">{(error as Error).message}</p>
        <Link href="/" className="text-[#4078F2] hover:underline">Return home</Link>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-white tracking-tight">Your Events</h1>
          <p className="text-[#A1A1A1] mt-2 text-lg">{events.length} event{events.length !== 1 ? 's' : ''}</p>
        </div>
        <Link
          href="/"
          className="px-6 py-3 bg-[#4078F2] text-white rounded-xl font-semibold hover:bg-[#2d5bd9] transition-colors"
        >
          + New Event
        </Link>
      </div>

      {/* Events Grid */}
      {events.length === 0 ? (
        <div className="bg-white rounded-3xl border border-[#E5E5E5] p-12 text-center">
          <div className="text-6xl mb-6">📹</div>
          <h2 className="text-2xl font-bold text-[#383A42] mb-3">No events yet</h2>
          <p className="text-[#A1A1A1] mb-8 text-lg">Create your first event to get started with Anchor</p>
          <Link
            href="/"
            className="inline-block px-6 py-3 bg-[#4078F2] text-white rounded-xl font-semibold hover:bg-[#2d5bd9] transition-colors"
          >
            Create Event
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {events.map((event) => {
            const status = statusConfig[event.status] || statusConfig.created
            return (
              <Link
                key={event.id}
                href={`/events/${event.id}`}
                className="bg-white rounded-2xl border border-[#E5E5E5] overflow-hidden hover:shadow-xl hover:border-[#4078F2]/30 transition-all group"
              >
                {/* Thumbnail / Preview */}
                <div className="h-48 bg-gradient-to-br from-[#4078F2] to-[#2d5bd9] flex items-center justify-center relative overflow-hidden">
                  {(event.master_video_url || (event as any).thumbnail_url) ? (
                    <video
                      src={event.master_video_url || (event as any).thumbnail_url}
                      className="w-full h-full object-cover"
                      muted
                      playsInline
                      onMouseOver={(e) => (e.target as HTMLVideoElement).play()}
                      onMouseOut={(e) => {
                        const video = e.target as HTMLVideoElement
                        video.pause()
                        video.currentTime = 0
                      }}
                    />
                  ) : (
                    <span className="text-6xl filter drop-shadow-lg">{eventTypeIcons[event.event_type] || '📹'}</span>
                  )}

                  {/* Status badge overlay */}
                  <div className="absolute top-3 right-3">
                    <span className={`px-3 py-1.5 rounded-full text-xs font-semibold ${status.bg} ${status.text} backdrop-blur-sm`}>
                      {status.label}
                    </span>
                  </div>
                </div>

                {/* Content */}
                <div className="p-5">
                  <h3 className="font-bold text-[#383A42] text-lg mb-2 truncate group-hover:text-[#4078F2] transition-colors">
                    {event.name}
                  </h3>

                  <div className="flex items-center text-sm text-[#A1A1A1] mb-3">
                    <span className="mr-2">{eventTypeIcons[event.event_type]}</span>
                    <span className="capitalize">{event.event_type}</span>
                  </div>

                  {/* Progress indicator for active states */}
                  {(event.status === 'analyzing' || event.status === 'generating') && (
                    <div className="mt-3">
                      <div className="h-1.5 bg-[#E5E5E5] rounded-full overflow-hidden">
                        <div className="h-full bg-[#4078F2] rounded-full animate-pulse" style={{ width: '60%' }}></div>
                      </div>
                      <p className="text-xs text-[#A1A1A1] mt-2">
                        {event.status === 'analyzing' ? 'Analyzing videos...' : 'Generating final video...'}
                      </p>
                    </div>
                  )}

                  {/* Completed badge */}
                  {event.status === 'completed' && (
                    <div className="mt-3 flex items-center text-[#50A14F] text-sm font-medium">
                      <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                      Video ready to view
                    </div>
                  )}

                  {/* Failed badge */}
                  {event.status === 'failed' && (
                    <div className="mt-3 flex items-center text-[#CA1243] text-sm font-medium">
                      <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Processing failed
                    </div>
                  )}
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
