'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { generateReel, getReel } from '@/lib/api'
import type { CustomReel } from '@/lib/supabase'
import VideoPlayer from './VideoPlayer'

interface PersonalReelGeneratorProps {
  eventId: string
  reels: CustomReel[]
}

const VIBE_OPTIONS = [
  { value: 'high_energy', label: 'High Energy', icon: '⚡', description: 'Fast action, celebrations, exciting moments' },
  { value: 'emotional', label: 'Emotional', icon: '💙', description: 'Heartfelt moments, reactions, meaningful scenes' },
  { value: 'calm', label: 'Calm', icon: '🌊', description: 'Peaceful, relaxed, gentle moments' },
] as const

const QUICK_EXAMPLES = [
  { query: 'me', label: 'My Best Moments' },
  { query: 'me celebrating', label: 'My Celebrations' },
  { query: 'me scoring', label: 'My Goals' },
  { query: 'highlights', label: 'Top Highlights' },
]

export default function PersonalReelGenerator({ eventId, reels }: PersonalReelGeneratorProps) {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [vibe, setVibe] = useState<'high_energy' | 'emotional' | 'calm'>('high_energy')
  const [duration, setDuration] = useState(30)

  const generateMutation = useMutation({
    mutationFn: () => generateReel(eventId, { query, vibe, duration }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reels', eventId] })
      setQuery('')
    },
  })

  const completedReels = reels.filter(r => r.status === 'completed')
  const processingReels = reels.filter(r => r.status === 'processing')

  return (
    <div className="space-y-6">
      <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
        <h3 className="font-medium text-indigo-900 mb-2">Find Yourself in the Footage</h3>
        <p className="text-sm text-indigo-700">
          Use natural language to search for moments - &quot;me&quot;, &quot;player 23&quot;, &quot;person in red jersey&quot;
        </p>
      </div>

      {/* Search Input */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          What do you want to see?
        </label>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder='Try: "me", "my best moments", "player 23"'
          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        />
      </div>

      {/* Quick Examples */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Quick Examples
        </label>
        <div className="flex flex-wrap gap-2">
          {QUICK_EXAMPLES.map((example) => (
            <button
              key={example.query}
              onClick={() => setQuery(example.query)}
              className="px-3 py-1 text-sm border border-gray-300 rounded-full hover:border-indigo-500 hover:text-indigo-600 transition-colors"
            >
              {example.label}
            </button>
          ))}
        </div>
      </div>

      {/* Vibe Selection */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Vibe / Identity
        </label>
        <div className="grid grid-cols-3 gap-3">
          {VIBE_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => setVibe(option.value)}
              className={`p-4 border-2 rounded-lg text-left transition-colors ${
                vibe === option.value
                  ? 'border-indigo-500 bg-indigo-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="text-xl mb-1">{option.icon}</div>
              <div className="font-medium text-sm">{option.label}</div>
              <div className="text-xs text-gray-500 mt-1">{option.description}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Duration */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Duration: {duration} seconds
        </label>
        <input
          type="range"
          min="15"
          max="60"
          step="5"
          value={duration}
          onChange={(e) => setDuration(parseInt(e.target.value))}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-gray-500">
          <span>15s</span>
          <span>60s</span>
        </div>
      </div>

      {/* Generate Button */}
      <button
        onClick={() => generateMutation.mutate()}
        disabled={!query || generateMutation.isPending}
        className="w-full py-3 px-4 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {generateMutation.isPending ? 'Generating...' : 'Generate My Reel'}
      </button>

      {generateMutation.isError && (
        <p className="text-red-600 text-sm">
          Error: {generateMutation.error.message}
        </p>
      )}

      {/* Processing Reels */}
      {processingReels.length > 0 && (
        <div>
          <h3 className="font-medium mb-3">Processing ({processingReels.length})</h3>
          <div className="space-y-2">
            {processingReels.map((reel) => (
              <div key={reel.id} className="flex items-center justify-between p-3 bg-yellow-50 rounded-lg">
                <div>
                  <p className="font-medium text-sm">&quot;{reel.query}&quot;</p>
                  <p className="text-xs text-gray-500">{reel.vibe} - {reel.duration_sec}s</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-yellow-600"></div>
                  <span className="text-sm text-yellow-600">Processing...</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Completed Reels */}
      {completedReels.length > 0 && (
        <div>
          <h3 className="font-medium mb-3">Your Reels ({completedReels.length})</h3>
          <div className="space-y-4">
            {completedReels.map((reel) => (
              <div key={reel.id} className="border rounded-lg overflow-hidden">
                <div className="p-3 bg-gray-50 border-b">
                  <p className="font-medium">&quot;{reel.query}&quot;</p>
                  <p className="text-xs text-gray-500">
                    {reel.vibe} - {reel.duration_sec}s - {reel.moments?.length || 0} moments
                  </p>
                </div>
                {reel.output_url && (
                  <div className="p-3">
                    <VideoPlayer url={reel.output_url} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
