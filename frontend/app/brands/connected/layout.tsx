import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Brand Connected',
}

export default function ConnectedLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}
