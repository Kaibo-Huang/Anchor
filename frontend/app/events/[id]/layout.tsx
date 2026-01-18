import type { Metadata } from 'next'
import { getEvent } from '@/lib/api'

type Props = {
  params: { id: string }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  try {
    const event = await getEvent(params.id)
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
