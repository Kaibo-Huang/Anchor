'use client'

import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { uploadVideo } from '@/lib/api'
import type { Video } from '@/lib/supabase'

interface VideoUploadProps {
  eventId: string
  existingVideos: Video[]
}

const ANGLE_TYPES = [
  { value: 'wide', label: 'Wide Shot' },
  { value: 'closeup', label: 'Close-up' },
  { value: 'crowd', label: 'Crowd' },
  { value: 'goal_angle', label: 'Goal/Stage Angle' },
  { value: 'other', label: 'Other' },
]

export default function VideoUpload({ eventId, existingVideos }: VideoUploadProps) {
  const queryClient = useQueryClient()
  const [dragActive, setDragActive] = useState(false)
  const [uploads, setUploads] = useState<Array<{
    file: File
    angleType: string
    progress: number
    status: 'pending' | 'uploading' | 'done' | 'error'
    error?: string
  }>>([])

  const uploadMutation = useMutation({
    mutationFn: async ({ file, angleType, index }: { file: File; angleType: string; index: number }) => {
      setUploads(prev => prev.map((u, i) =>
        i === index ? { ...u, status: 'uploading' as const, progress: 50 } : u
      ))

      await uploadVideo(eventId, file, angleType)

      setUploads(prev => prev.map((u, i) =>
        i === index ? { ...u, status: 'done' as const, progress: 100 } : u
      ))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['videos', eventId] })
    },
    onError: (error, { index }) => {
      setUploads(prev => prev.map((u, i) =>
        i === index ? { ...u, status: 'error' as const, error: error.message } : u
      ))
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

    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('video/'))
    addFiles(files)
  }, [])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files)
      addFiles(files)
    }
  }

  const addFiles = (files: File[]) => {
    const newUploads = files.map(file => ({
      file,
      angleType: 'wide',
      progress: 0,
      status: 'pending' as const,
    }))
    setUploads(prev => [...prev, ...newUploads])
  }

  const updateAngleType = (index: number, angleType: string) => {
    setUploads(prev => prev.map((u, i) =>
      i === index ? { ...u, angleType } : u
    ))
  }

  const removeUpload = (index: number) => {
    setUploads(prev => prev.filter((_, i) => i !== index))
  }

  const startUpload = (index: number) => {
    const upload = uploads[index]
    if (upload.status === 'pending') {
      uploadMutation.mutate({ file: upload.file, angleType: upload.angleType, index })
    }
  }

  const uploadAll = () => {
    uploads.forEach((upload, index) => {
      if (upload.status === 'pending') {
        uploadMutation.mutate({ file: upload.file, angleType: upload.angleType, index })
      }
    })
  }

  const pendingUploads = uploads.filter(u => u.status === 'pending')

  return (
    <div className="space-y-6">
      {/* Drop Zone */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragActive ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <div className="text-4xl mb-4">📹</div>
        <p className="text-gray-600 mb-2">Drag and drop video files here, or</p>
        <label className="cursor-pointer">
          <span className="text-indigo-600 hover:text-indigo-700 font-medium">browse files</span>
          <input
            type="file"
            multiple
            accept="video/*"
            onChange={handleFileSelect}
            className="hidden"
          />
        </label>
        <p className="text-sm text-gray-400 mt-2">Supports MP4, MOV, AVI (max 12 videos)</p>
      </div>

      {/* Existing Videos */}
      {existingVideos.length > 0 && (
        <div>
          <h3 className="font-medium mb-3">Uploaded Videos ({existingVideos.length})</h3>
          <div className="space-y-2">
            {existingVideos.map((video) => (
              <div key={video.id} className="flex items-center justify-between p-3 bg-green-50 rounded-lg">
                <div className="flex items-center gap-3">
                  <span className="text-green-500">✓</span>
                  <span className="text-sm">{video.angle_type}</span>
                </div>
                <span className="text-xs text-gray-500">{video.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pending Uploads */}
      {uploads.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium">New Videos ({uploads.length})</h3>
            {pendingUploads.length > 0 && (
              <button
                onClick={uploadAll}
                className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700"
              >
                Upload All ({pendingUploads.length})
              </button>
            )}
          </div>
          <div className="space-y-3">
            {uploads.map((upload, index) => (
              <div key={index} className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm truncate max-w-[200px]">
                    {upload.file.name}
                  </span>
                  <div className="flex items-center gap-2">
                    {upload.status === 'pending' && (
                      <>
                        <select
                          value={upload.angleType}
                          onChange={(e) => updateAngleType(index, e.target.value)}
                          className="text-sm border rounded px-2 py-1"
                        >
                          {ANGLE_TYPES.map(type => (
                            <option key={type.value} value={type.value}>{type.label}</option>
                          ))}
                        </select>
                        <button
                          onClick={() => startUpload(index)}
                          className="px-3 py-1 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700"
                        >
                          Upload
                        </button>
                        <button
                          onClick={() => removeUpload(index)}
                          className="text-gray-400 hover:text-red-500"
                        >
                          ✕
                        </button>
                      </>
                    )}
                    {upload.status === 'uploading' && (
                      <span className="text-sm text-indigo-600">Uploading...</span>
                    )}
                    {upload.status === 'done' && (
                      <span className="text-sm text-green-600">✓ Done</span>
                    )}
                    {upload.status === 'error' && (
                      <span className="text-sm text-red-600">Error: {upload.error}</span>
                    )}
                  </div>
                </div>
                {upload.status === 'uploading' && (
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-indigo-600 h-2 rounded-full transition-all"
                      style={{ width: `${upload.progress}%` }}
                    />
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
