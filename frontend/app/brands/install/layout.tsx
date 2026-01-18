import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Connect Your Brand',
}

export default function InstallLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}
