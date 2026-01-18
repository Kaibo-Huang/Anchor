"use client"

import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import { createEvent } from '@/lib/api'
import PrimaryCreate from '@/components/PrimaryCreate'
import TopNav from "@/components/TopNav";

export default function CreatePage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [eventType, setEventType] = useState<'sports' | 'ceremony' | 'performance'>('sports')

  const createEventMutation = useMutation({
    mutationFn: () => createEvent({ name, event_type: eventType }),
    onSuccess: (event) => router.push(`/events/${event.id}`),
  })

  return (
    <div>
      <PrimaryCreate />
      <TopNav/>
    </div>
  )
}
