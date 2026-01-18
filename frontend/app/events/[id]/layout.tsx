import type { Metadata } from 'next'
import { getEvent } from '@/lib/api'

type Props = {
  params: Promise<{ id: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  try {
    const { id } = await params
    const event = await getEvent(id)
    return {
      title: event.name,
    }
  } catch (error) {
    return {
      title: 'Event',
    }
  }
}

export default function EventLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}
