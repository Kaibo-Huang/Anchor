'use client'

import { GenerationProgress as GenerationProgressType } from '@/lib/supabase'

interface GenerationProgressProps {
  progress: GenerationProgressType | null
  status: string
}

// Map stages to step numbers for progress calculation
const STAGE_TO_STEP: Record<string, number> = {
  'initializing': 0,
  'downloading': 1,
  'syncing': 2,
  'timeline': 3,
  'music': 4,
  'ads': 5,
  'rendering': 6,
  'uploading': 7,
  'complete': 8,
}

// User-friendly stage labels
const STAGE_LABELS: Record<string, string> = {
  'initializing': 'Setup',
  'downloading': 'Download',
  'syncing': 'Sync Audio',
  'timeline': 'Timeline',
  'music': 'Music',
  'ads': 'AI Ads',
  'rendering': 'Render',
  'uploading': 'Upload',
  'complete': 'Done',
}

export default function GenerationProgress({ progress, status }: GenerationProgressProps) {
  // If not generating, don't show detailed progress
  if (status !== 'generating') {
    return null
  }

  // If no progress data yet, show initializing state
  if (!progress) {
    return (
      <div className="mt-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full"></div>
          <span className="text-sm text-gray-600">Starting video generation...</span>
        </div>
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{ width: '5%' }}></div>
        </div>
      </div>
    )
  }

  const currentStep = STAGE_TO_STEP[progress.stage] ?? 0
  const totalSteps = 9  // 0-8

  // Calculate overall progress: step progress + intra-step progress
  const stepWeight = 1 / totalSteps
  const overallProgress = (currentStep * stepWeight) + (progress.stage_progress * stepWeight)
  const progressPercent = Math.min(100, Math.max(0, Math.round(overallProgress * 100)))

  // Determine which stages to show based on current progress
  const visibleStages = ['initializing', 'downloading', 'syncing', 'timeline', 'rendering', 'uploading']

  // Add optional stages if we've reached them
  if (currentStep >= STAGE_TO_STEP['music']) {
    visibleStages.splice(4, 0, 'music')
  }
  if (currentStep >= STAGE_TO_STEP['ads']) {
    visibleStages.splice(5, 0, 'ads')
  }

  return (
    <div className="mt-4 space-y-3">
      {/* Stage indicator pills */}
      <div className="flex gap-1 justify-between flex-wrap">
        {visibleStages.map((stage) => {
          const stepNum = STAGE_TO_STEP[stage]
          const isActive = currentStep === stepNum
          const isComplete = currentStep > stepNum || progress.stage === 'complete'

          return (
            <div
              key={stage}
              className={`flex-1 min-w-[80px] text-center py-1 px-2 rounded text-xs font-medium transition-colors ${
                isComplete
                  ? 'bg-green-100 text-green-700'
                  : isActive
                  ? 'bg-blue-100 text-blue-700 animate-pulse'
                  : 'bg-gray-100 text-gray-500'
              }`}
            >
              {isComplete ? '✓' : ''} {STAGE_LABELS[stage] || stage}
            </div>
          )
        })}
      </div>

      {/* Progress bar */}
      <div className="relative">
        <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ease-out ${
              progress.stage === 'complete' ? 'bg-green-500' : 'bg-blue-500'
            }`}
            style={{ width: `${progressPercent}%` }}
          ></div>
        </div>
        <span className="absolute right-0 top-4 text-xs text-gray-500">{progressPercent}%</span>
      </div>

      {/* Current status message */}
      <div className="flex items-start gap-2">
        {progress.stage !== 'complete' && (
          <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full flex-shrink-0 mt-0.5"></div>
        )}
        {progress.stage === 'complete' && (
          <div className="h-4 w-4 bg-green-500 rounded-full flex items-center justify-center text-white text-xs flex-shrink-0 mt-0.5">✓</div>
        )}
        <div className="flex-1">
          <span className="text-sm text-gray-600">{progress.message}</span>
          {progress.stage === 'syncing' && (
            <p className="text-xs text-gray-400 mt-1">Using audio fingerprinting to perfectly align all camera angles...</p>
          )}
          {progress.stage === 'timeline' && (
            <p className="text-xs text-gray-400 mt-1">AI selecting the best camera angle for each moment...</p>
          )}
          {progress.stage === 'ads' && (
            <p className="text-xs text-gray-400 mt-1">Creating native product videos with Google Veo 3.1...</p>
          )}
          {progress.stage === 'rendering' && (
            <p className="text-xs text-gray-400 mt-1">Applying transitions, zooms, music, and effects with FFmpeg...</p>
          )}
          {progress.stage === 'uploading' && (
            <p className="text-xs text-gray-400 mt-1">Saving to cloud storage...</p>
          )}
        </div>
      </div>

      {/* Estimated time remaining (optional) */}
      {progress.stage !== 'complete' && currentStep > 1 && (
        <div className="text-xs text-gray-400 text-center">
          {currentStep < 6 ? 'Processing your footage...' : 'Almost done...'}
        </div>
      )}
    </div>
  )
}
