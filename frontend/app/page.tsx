'use client'

import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import { createEvent } from '@/lib/api'

export default function Home() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [eventType, setEventType] = useState<'sports' | 'ceremony' | 'performance'>('sports')

  const createEventMutation = useMutation({
    mutationFn: () => createEvent({ name, event_type: eventType }),
    onSuccess: (event) => {
      router.push(`/events/${event.id}`)
    },
  })

  return (
    <div className="max-w-2xl mx-auto">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          Create Broadcast-Quality Highlights
        </h1>
        <p className="text-lg text-gray-600">
          Upload multi-angle footage, let AI find the best moments, and generate
          professional highlight reels with your personal music.
        </p>
      </div>

      <div className="bg-white rounded-lg shadow-md p-8">
        <h2 className="text-2xl font-semibold mb-6">Create New Event</h2>

        <div className="space-y-6">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
              Event Name
            </label>
            <input
              type="text"
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Championship Game, Graduation 2024"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Event Type
            </label>
            <div className="grid grid-cols-3 gap-4">
              {[
                { value: 'sports', label: 'Sports', icon: '🏆' },
                { value: 'ceremony', label: 'Ceremony', icon: '🎓' },
                { value: 'performance', label: 'Performance', icon: '🎸' },
              ].map((type) => (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => setEventType(type.value as typeof eventType)}
                  className={`p-4 border-2 rounded-lg text-center transition-colors ${
                    eventType === type.value
                      ? 'border-indigo-500 bg-indigo-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="text-2xl mb-1">{type.icon}</div>
                  <div className="font-medium">{type.label}</div>
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={() => createEventMutation.mutate()}
            disabled={!name || createEventMutation.isPending}
            className="w-full py-3 px-4 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {createEventMutation.isPending ? 'Creating...' : 'Create Event'}
          </button>

          {createEventMutation.isError && (
            <p className="text-red-600 text-sm">
              Error: {createEventMutation.error.message}
            </p>
          )}
        </div>
      </div>

      <div className="mt-12 grid grid-cols-3 gap-8 text-center">
        <div>
          <div className="text-3xl mb-2">📹</div>
          <h3 className="font-semibold mb-1">Multi-Angle</h3>
          <p className="text-sm text-gray-600">Upload up to 12 camera angles</p>
        </div>
        <div>
          <div className="text-3xl mb-2">🤖</div>
          <h3 className="font-semibold mb-1">AI-Powered</h3>
          <p className="text-sm text-gray-600">Smart angle switching & highlights</p>
        </div>
        <div>
          <div className="text-3xl mb-2">🎵</div>
          <h3 className="font-semibold mb-1">Your Music</h3>
          <p className="text-sm text-gray-600">Beat-synced with your soundtrack</p>
        </div>
      </div>
    </div>
  )
}
