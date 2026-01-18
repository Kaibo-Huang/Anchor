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

  const statusColors: Record<string, string> = {
    created: 'bg-gray-100 text-gray-800',
    uploading: 'bg-blue-100 text-blue-800',
    analyzing: 'bg-yellow-100 text-yellow-800',
    analyzed: 'bg-green-100 text-green-800',
    generating: 'bg-purple-100 text-purple-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  }

  const eventTypeIcons: Record<string, string> = {
    sports: '🏆',
    ceremony: '🎓',
    performance: '🎸',
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-semibold text-red-600">Error loading events</h2>
        <p className="text-gray-600 mt-2">{(error as Error).message}</p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Events</h1>
          <p className="text-gray-500 mt-1">{events.length} event{events.length !== 1 ? 's' : ''}</p>
        </div>
        <Link
          href="/"
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          + New Event
        </Link>
      </div>

      {/* Events Grid */}
      {events.length === 0 ? (
        <div className="bg-white rounded-lg shadow-md p-12 text-center">
          <div className="text-6xl mb-4">📹</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">No events yet</h2>
          <p className="text-gray-600 mb-6">Create your first event to get started</p>
          <Link
            href="/"
            className="inline-block px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Create Event
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {events.map((event) => (
            <Link
              key={event.id}
              href={`/events/${event.id}`}
              className="bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow"
            >
              {/* Thumbnail / Preview */}
              <div className="h-40 bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                {event.status === 'completed' && event.master_video_url ? (
                  <video
                    src={event.master_video_url}
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
                  <span className="text-6xl">{eventTypeIcons[event.event_type] || '📹'}</span>
                )}
              </div>

              {/* Content */}
              <div className="p-4">
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold text-gray-900 truncate flex-1">{event.name}</h3>
                  <span className={`ml-2 px-2 py-1 rounded-full text-xs font-medium ${statusColors[event.status]}`}>
                    {event.status}
                  </span>
                </div>

                <div className="flex items-center text-sm text-gray-500">
                  <span className="mr-2">{eventTypeIcons[event.event_type]}</span>
                  <span className="capitalize">{event.event_type}</span>
                </div>

                {/* Progress indicator for active states */}
                {(event.status === 'analyzing' || event.status === 'generating') && (
                  <div className="mt-3">
                    <div className="h-1 bg-gray-200 rounded-full overflow-hidden">
                      <div className="h-full bg-indigo-600 rounded-full animate-pulse" style={{ width: '60%' }}></div>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      {event.status === 'analyzing' ? 'Analyzing videos...' : 'Generating final video...'}
                    </p>
                  </div>
                )}

                {/* Completed badge */}
                {event.status === 'completed' && (
                  <div className="mt-3 flex items-center text-green-600 text-sm">
                    <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    Video ready
                  </div>
                )}

                {/* Failed badge */}
                {event.status === 'failed' && (
                  <div className="mt-3 flex items-center text-red-600 text-sm">
                    <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                    Processing failed
                  </div>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
