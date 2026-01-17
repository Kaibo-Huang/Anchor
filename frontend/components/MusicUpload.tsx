'use client'

import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { uploadMusic, analyzeMusic } from '@/lib/api'

interface MusicUploadProps {
  eventId: string
  currentMusicUrl: string | null
}

export default function MusicUpload({ eventId, currentMusicUrl }: MusicUploadProps) {
  const queryClient = useQueryClient()
  const [dragActive, setDragActive] = useState(false)
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'analyzing' | 'done'>('idle')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      setUploadState('uploading')
      await uploadMusic(eventId, file)
      setUploadState('analyzing')
      await analyzeMusic(eventId)
      setUploadState('done')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] })
    },
    onError: () => {
      setUploadState('idle')
    },
  })

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith('audio/')) {
      setSelectedFile(file)
    }
  }, [])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      setSelectedFile(e.target.files[0])
    }
  }

  const handleUpload = () => {
    if (selectedFile) {
      uploadMutation.mutate(selectedFile)
    }
  }

  if (currentMusicUrl) {
    return (
      <div className="flex items-center justify-between p-4 bg-green-50 rounded-lg">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🎵</span>
          <div>
            <p className="font-medium text-green-800">Music track uploaded</p>
            <p className="text-sm text-green-600">Beat detection complete</p>
          </div>
        </div>
        <button
          onClick={() => {
            setSelectedFile(null)
            setUploadState('idle')
          }}
          className="text-sm text-green-700 hover:text-green-800"
        >
          Change
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-gray-600 text-sm">
        Upload your team anthem, graduation song, or favorite track. We&apos;ll sync cuts to the beat
        and mix it with the event audio.
      </p>

      {!selectedFile ? (
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
            dragActive ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-gray-400'
          }`}
        >
          <div className="text-3xl mb-2">🎵</div>
          <p className="text-gray-600 text-sm mb-1">Drop audio file here, or</p>
          <label className="cursor-pointer">
            <span className="text-indigo-600 hover:text-indigo-700 font-medium text-sm">browse files</span>
            <input
              type="file"
              accept="audio/*"
              onChange={handleFileSelect}
              className="hidden"
            />
          </label>
          <p className="text-xs text-gray-400 mt-2">MP3, WAV, M4A supported</p>
        </div>
      ) : (
        <div className="border rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-2xl">🎵</span>
              <div>
                <p className="font-medium truncate max-w-[200px]">{selectedFile.name}</p>
                <p className="text-sm text-gray-500">
                  {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {uploadState === 'idle' && (
                <>
                  <button
                    onClick={handleUpload}
                    className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700"
                  >
                    Upload
                  </button>
                  <button
                    onClick={() => setSelectedFile(null)}
                    className="text-gray-400 hover:text-red-500"
                  >
                    ✕
                  </button>
                </>
              )}
              {uploadState === 'uploading' && (
                <span className="text-sm text-indigo-600">Uploading...</span>
              )}
              {uploadState === 'analyzing' && (
                <span className="text-sm text-yellow-600">Analyzing beats...</span>
              )}
              {uploadState === 'done' && (
                <span className="text-sm text-green-600">✓ Ready</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
