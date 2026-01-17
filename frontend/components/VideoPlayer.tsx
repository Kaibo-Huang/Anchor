'use client'

import { useEffect, useRef } from 'react'
import videojs from 'video.js'
import 'video.js/dist/video-js.css'

interface VideoPlayerProps {
  url: string
  poster?: string
}

export default function VideoPlayer({ url, poster }: VideoPlayerProps) {
  const videoRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<ReturnType<typeof videojs> | null>(null)

  useEffect(() => {
    // Make sure Video.js player is only initialized once
    if (!playerRef.current && videoRef.current) {
      const videoElement = document.createElement('video-js')
      videoElement.classList.add('vjs-big-play-centered')
      videoRef.current.appendChild(videoElement)

      playerRef.current = videojs(videoElement, {
        autoplay: false,
        controls: true,
        responsive: true,
        fluid: true,
        sources: [{
          src: url,
          type: getVideoType(url),
        }],
        poster: poster,
      })
    } else if (playerRef.current) {
      // Update source if URL changes
      playerRef.current.src({
        src: url,
        type: getVideoType(url),
      })
    }
  }, [url, poster])

  // Dispose the Video.js player when the component unmounts
  useEffect(() => {
    const player = playerRef.current

    return () => {
      if (player && !player.isDisposed()) {
        player.dispose()
        playerRef.current = null
      }
    }
  }, [])

  return (
    <div data-vjs-player>
      <div ref={videoRef} className="rounded-lg overflow-hidden" />
    </div>
  )
}

function getVideoType(url: string): string {
  if (url.includes('.mp4') || url.includes('mp4')) {
    return 'video/mp4'
  }
  if (url.includes('.webm')) {
    return 'video/webm'
  }
  if (url.includes('.m3u8')) {
    return 'application/x-mpegURL'
  }
  // Default to mp4
  return 'video/mp4'
}
