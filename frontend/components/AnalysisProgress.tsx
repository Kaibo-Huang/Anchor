'use client'

import { AnalysisProgress as AnalysisProgressType } from '@/lib/supabase'

interface AnalysisProgressProps {
  progress: AnalysisProgressType | null
  status: string
}

const STAGES = [
  { key: 'initializing', label: 'Initialize', icon: '1' },
  { key: 'downloading', label: 'Download', icon: '2' },
  { key: 'compressing', label: 'Compress', icon: '2' },  // Same step as download
  { key: 'indexing', label: 'Analyze', icon: '3' },
  { key: 'embeddings', label: 'Embeddings', icon: '4' },
  { key: 'saving', label: 'Save', icon: '5' },
  { key: 'complete', label: 'Done', icon: '✓' },
]

// Map stages to step numbers for progress calculation
const STAGE_TO_STEP: Record<string, number> = {
  'initializing': 0,
  'downloading': 1,
  'compressing': 1,
  'indexing': 2,
  'embeddings': 3,
  'saving': 4,
  'complete': 5,
}

const STAGE_LABELS: Record<string, string> = {
  'initializing': 'Initializing',
  'downloading': 'Downloading Videos',
  'compressing': 'Compressing Videos',
  'indexing': 'AI Analysis',
  'embeddings': 'Generating Embeddings',
  'saving': 'Saving Results',
  'complete': 'Complete',
}

export default function AnalysisProgress({ progress, status }: AnalysisProgressProps) {
  // If not analyzing, don't show detailed progress
  if (status !== 'analyzing') {
    return null
  }

  // If no progress data yet, show initializing state
  if (!progress) {
    return (
      <div className="mt-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="animate-spin h-4 w-4 border-2 border-yellow-500 border-t-transparent rounded-full"></div>
          <span className="text-sm text-gray-600">Starting analysis...</span>
        </div>
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <div className="h-full bg-yellow-500 rounded-full animate-pulse" style={{ width: '5%' }}></div>
        </div>
      </div>
    )
  }

  const currentStep = STAGE_TO_STEP[progress.stage] ?? 0
  const totalSteps = 5

  // Calculate overall progress: step progress + intra-step progress
  const stepWeight = 1 / totalSteps
  const overallProgress = (currentStep * stepWeight) + (progress.stage_progress * stepWeight)
  const progressPercent = Math.min(100, Math.round(overallProgress * 100))

  const stageLabel = STAGE_LABELS[progress.stage] || progress.stage

  return (
    <div className="mt-4 space-y-3">
      {/* Stage indicator pills */}
      <div className="flex gap-1 justify-between">
        {['Download', 'Analyze', 'Embed', 'Save'].map((label, idx) => {
          const stepNum = idx + 1
          const isActive = currentStep === stepNum
          const isComplete = currentStep > stepNum || progress.stage === 'complete'

          return (
            <div
              key={label}
              className={`flex-1 text-center py-1 px-2 rounded text-xs font-medium transition-colors ${
                isComplete
                  ? 'bg-green-100 text-green-700'
                  : isActive
                  ? 'bg-yellow-100 text-yellow-700'
                  : 'bg-gray-100 text-gray-500'
              }`}
            >
              {isComplete ? '✓' : ''} {label}
            </div>
          )
        })}
      </div>

      {/* Progress bar */}
      <div className="relative">
        <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ease-out ${
              progress.stage === 'complete' ? 'bg-green-500' : 'bg-yellow-500'
            }`}
            style={{ width: `${progressPercent}%` }}
          ></div>
        </div>
        <span className="absolute right-0 top-4 text-xs text-gray-500">{progressPercent}%</span>
      </div>

      {/* Current status message */}
      <div className="flex items-center gap-2">
        {progress.stage !== 'complete' && (
          <div className="animate-spin h-4 w-4 border-2 border-yellow-500 border-t-transparent rounded-full"></div>
        )}
        {progress.stage === 'complete' && (
          <div className="h-4 w-4 bg-green-500 rounded-full flex items-center justify-center text-white text-xs">✓</div>
        )}
        <span className="text-sm text-gray-600">{progress.message}</span>
      </div>

      {/* Video count */}
      {progress.total_videos > 0 && progress.stage !== 'complete' && (
        <div className="text-xs text-gray-400">
          Processing {progress.current_video} of {progress.total_videos} videos
        </div>
      )}
    </div>
  )
}
