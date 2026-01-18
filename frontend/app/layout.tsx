'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import Link from 'next/link'
import './globals.css'

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000, // 1 minute
        retry: 1,
      },
    },
  }))

  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <QueryClientProvider client={queryClient}>
          <nav className="bg-white shadow-sm border-b">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex justify-between h-16 items-center">
                <div className="flex items-center gap-8">
                  <Link href="/" className="text-xl font-bold text-indigo-600">
                    Anchor
                  </Link>
                  <div className="flex items-center gap-4">
                    <Link href="/events" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">
                      All Events
                    </Link>
                    <Link href="/" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">
                      + New Event
                    </Link>
                  </div>
                </div>
                <div className="text-sm text-gray-500">
                  AI-Powered Video Production
                </div>
              </div>
            </div>
          </nav>
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>
        </QueryClientProvider>
      </body>
    </html>
  )
}
