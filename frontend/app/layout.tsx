import type { Metadata } from 'next'
import './globals.css'
import LayoutClient from './layout-client'

export const metadata: Metadata = {
  title: {
    default: 'Anchor - AI-Powered Video Production',
    template: '%s - Anchor'
  },
  description: 'Multi-angle phone footage to broadcast-quality highlight reels with native ad integration',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <LayoutClient>{children}</LayoutClient>
    </html>
  )
}
