'use client'

import { useEffect, useRef, useState } from 'react'
import { AnalysisProgress, GenerationProgress } from '@/lib/supabase'

interface LogEntry {
  id: string
  timestamp: Date
  type: 'analysis' | 'generation' | 'info'
  stage: string
  message: string
  status: 'pending' | 'in_progress' | 'completed' | 'error'
}

interface ProcessingLogsProps {
  analysisProgress: AnalysisProgress | null
  generationProgress: GenerationProgress | null
  eventStatus: string
}

// Analysis stages in order
const ANALYSIS_STAGES = [
  { key: 'initializing', label: 'Initializing', description: 'Setting up AI analysis environment' },
  { key: 'downloading', label: 'Downloading', description: 'Fetching videos from storage' },
  { key: 'compressing', label: 'Compressing', description: 'Optimizing video files for analysis' },
  { key: 'indexing', label: 'Indexing', description: 'Processing with TwelveLabs AI' },
  { key: 'embeddings', label: 'Embeddings', description: 'Creating semantic embeddings' },
  { key: 'saving', label: 'Saving', description: 'Storing analysis results' },
  { key: 'complete', label: 'Complete', description: 'Analysis finished' },
]

// Generation stages in order
const GENERATION_STAGES = [
  { key: 'initializing', label: 'Initializing', description: 'Setting up video generation' },
  { key: 'downloading', label: 'Downloading', description: 'Fetching source videos' },
  { key: 'syncing', label: 'Audio Sync', description: 'Aligning camera angles via audio' },
  { key: 'timeline', label: 'Timeline', description: 'Building multi-angle switching timeline' },
  { key: 'music', label: 'Music', description: 'Processing and syncing music' },
  { key: 'ads', label: 'AI Ads', description: 'Generating product videos with Veo' },
  { key: 'rendering', label: 'Rendering', description: 'Applying effects with FFmpeg' },
  { key: 'uploading', label: 'Uploading', description: 'Saving to cloud storage' },
  { key: 'complete', label: 'Complete', description: 'Video generation finished' },
]

export default function ProcessingLogs({
  analysisProgress,
  generationProgress,
  eventStatus
}: ProcessingLogsProps) {
  const logsEndRef = useRef<HTMLDivElement>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [autoScroll, setAutoScroll] = useState(true)

  // Build logs based on progress
  useEffect(() => {
    const newLogs: LogEntry[] = []
    const now = new Date()

    // Determine if we're analyzing or generating
    const isAnalyzing = eventStatus === 'analyzing' ||
      (eventStatus === 'analyzed' && !generationProgress) ||
      (eventStatus === 'generating' && analysisProgress?.stage === 'complete')

    const isGenerating = eventStatus === 'generating' || eventStatus === 'completed'

    // Add analysis logs
    if (analysisProgress || isAnalyzing || eventStatus === 'analyzed' || eventStatus === 'completed') {
      const currentStageIndex = analysisProgress
        ? ANALYSIS_STAGES.findIndex(s => s.key === analysisProgress.stage)
        : eventStatus === 'analyzed' || eventStatus === 'generating' || eventStatus === 'completed'
          ? ANALYSIS_STAGES.length - 1 // complete
          : -1

      ANALYSIS_STAGES.forEach((stage, index) => {
        let status: LogEntry['status'] = 'pending'
        let message = stage.description

        if (index < currentStageIndex) {
          status = 'completed'
          message = `${stage.description} - Done`
        } else if (index === currentStageIndex) {
          if (analysisProgress?.stage === 'complete' || eventStatus === 'analyzed' || eventStatus === 'generating' || eventStatus === 'completed') {
            status = 'completed'
            message = stage.key === 'complete' ? 'Analysis completed successfully!' : `${stage.description} - Done`
          } else {
            status = 'in_progress'
            message = analysisProgress?.message || stage.description
          }
        }

        // Only add logs for stages that have started
        if (status !== 'pending') {
          newLogs.push({
            id: `analysis-${stage.key}`,
            timestamp: now,
            type: 'analysis',
            stage: stage.label,
            message,
            status,
          })
        }
      })
    }

    // Add generation logs
    if (generationProgress || isGenerating) {
      const currentStageIndex = generationProgress
        ? GENERATION_STAGES.findIndex(s => s.key === generationProgress.stage)
        : eventStatus === 'completed'
          ? GENERATION_STAGES.length - 1
          : -1

      GENERATION_STAGES.forEach((stage, index) => {
        let status: LogEntry['status'] = 'pending'
        let message = stage.description

        if (index < currentStageIndex) {
          status = 'completed'
          message = `${stage.description} - Done`
        } else if (index === currentStageIndex) {
          if (generationProgress?.stage === 'complete' || eventStatus === 'completed') {
            status = 'completed'
            message = stage.key === 'complete' ? 'Video generation completed successfully!' : `${stage.description} - Done`
          } else {
            status = 'in_progress'
            message = generationProgress?.message || stage.description
          }
        }

        // Only add logs for stages that have started
        if (status !== 'pending') {
          newLogs.push({
            id: `generation-${stage.key}`,
            timestamp: now,
            type: 'generation',
            stage: stage.label,
            message,
            status,
          })
        }
      })
    }

    setLogs(newLogs)
  }, [analysisProgress, generationProgress, eventStatus])

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
    setAutoScroll(isAtBottom)
  }

  // Don't show if no processing has happened
  if (eventStatus === 'created' || eventStatus === 'uploading') {
    return null
  }

  if (logs.length === 0) {
    return null
  }

  return (
    <div className="bg-[#1E1E1E] rounded-2xl border border-[#333] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-[#252525] border-b border-[#333]">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-[#FF5F56]"></div>
            <div className="w-3 h-3 rounded-full bg-[#FFBD2E]"></div>
            <div className="w-3 h-3 rounded-full bg-[#27CA40]"></div>
          </div>
          <span className="text-[#A1A1A1] text-sm font-medium ml-2">Processing Logs</span>
        </div>
        <div className="flex items-center gap-2">
          {(eventStatus === 'analyzing' || eventStatus === 'generating') && (
            <span className="flex items-center gap-1.5 text-xs text-[#4078F2]">
              <span className="w-2 h-2 bg-[#4078F2] rounded-full animate-pulse"></span>
              Live
            </span>
          )}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              autoScroll
                ? 'bg-[#4078F2]/20 text-[#4078F2]'
                : 'bg-[#333] text-[#A1A1A1] hover:text-white'
            }`}
          >
            Auto-scroll {autoScroll ? 'ON' : 'OFF'}
          </button>
        </div>
      </div>

      <div
        className="h-64 overflow-y-auto p-4 font-mono text-sm"
        onScroll={handleScroll}
      >
        {logs.map((log, index) => (
          <div
            key={log.id}
            className={`flex items-start gap-3 py-1.5 ${
              index !== logs.length - 1 ? 'border-b border-[#333]/50' : ''
            }`}
          >
            {/* Status indicator */}
            <div className="flex-shrink-0 mt-0.5">
              {log.status === 'completed' && (
                <svg className="w-4 h-4 text-[#50A14F]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
              {log.status === 'in_progress' && (
                <div className="w-4 h-4 border-2 border-[#4078F2] border-t-transparent rounded-full animate-spin"></div>
              )}
              {log.status === 'error' && (
                <svg className="w-4 h-4 text-[#CA1243]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              )}
            </div>

            {/* Type badge */}
            <span className={`flex-shrink-0 px-2 py-0.5 rounded text-xs font-medium ${
              log.type === 'analysis'
                ? 'bg-[#E5A00D]/20 text-[#E5A00D]'
                : log.type === 'generation'
                  ? 'bg-[#4078F2]/20 text-[#4078F2]'
                  : 'bg-[#A1A1A1]/20 text-[#A1A1A1]'
            }`}>
              {log.type === 'analysis' ? 'ANALYZE' : log.type === 'generation' ? 'GENERATE' : 'INFO'}
            </span>

            {/* Stage */}
            <span className="flex-shrink-0 text-[#A1A1A1] min-w-[80px]">
              [{log.stage}]
            </span>

            {/* Message */}
            <span className={`flex-1 ${
              log.status === 'completed'
                ? 'text-[#50A14F]'
                : log.status === 'in_progress'
                  ? 'text-white'
                  : log.status === 'error'
                    ? 'text-[#CA1243]'
                    : 'text-[#A1A1A1]'
            }`}>
              {log.message}
            </span>
          </div>
        ))}
        <div ref={logsEndRef} />
      </div>
    </div>
  )
}
