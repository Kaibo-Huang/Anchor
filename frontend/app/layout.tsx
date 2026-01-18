'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import './globals.css'
import { createTheme, ThemeProvider } from '@mui/material/styles';

const customTheme = createTheme({
  typography: {
    h1: {
      fontSize: 'clamp(2rem, 5.5vw, 4rem)',
      fontWeight: 700,
    },
    h2: {
      fontSize: 'clamp(1.75rem, 5vw, 3rem)',
      fontWeight: 700,
      color: '#383A42'
    },
    h4: {
        fontSize: 'clamp(1.25rem, 2.6vw, 2rem)',
        fontWeight: 500,
        color: '#A1A1A1',
    },
    h5: {
      fontSize: 'clamp(1.25rem, 2.6vw, 2rem)',
      fontWeight: 600,
      color: '#4078F2',
    },
    button: {
      textTransform: 'none'
    },
    body1: {
      fontSize: 'clamp(1rem, 2vw, 1.5rem)',
      color: '#FAFAFA'
    }
  },
  palette: {
    primary: {
      main: '#383A42', // A custom primary color
    },
    secondary: {
      main: '#4078F2', // Blue
    },
    success: {
      main: '#50A14F', // Green
    },
    error: {
      main: '#FAFAFA', // Red
    },
    warning: {
        main: '#A1A1A1', // grey
    },
    info: {
        main: '#FAFAFA', // A custom background color
    },
    background: {
      default: '#FAFAFA', // A custom background color
    }
    // You can add other standard colors here (secondary, error, etc.)
  },
});

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

  const pathname = usePathname?.() ?? ''
  const isCreate = pathname.startsWith('/create')

  const bodyClass = isCreate ? 'min-h-screen bg-white text-gray-900' : 'min-h-screen bg-gray-50 text-black'

  return (
    <html lang="en">
      <body className={`${bodyClass} overflow-x-hidden`}>
        <QueryClientProvider client={queryClient}>
          {!isCreate && (
            <nav className="bg-white shadow-sm border-b">
              <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex justify-between h-16 items-center">
                  <a href="/" className="text-xl font-bold text-indigo-600">
                    Anchor
                  </a>
                  <div className="text-sm text-gray-500">AI-Powered Video Production</div>
                </div>
              </div>
            </nav>
          )}
          <ThemeProvider theme={customTheme}>
            {isCreate ? (
              <main className="w-full">
                {children}
              </main>
            ) : (
              <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</main>
            )}
          </ThemeProvider>
        </QueryClientProvider>
      </body>
    </html>
  )
}
