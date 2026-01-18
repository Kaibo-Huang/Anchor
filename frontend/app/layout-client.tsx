'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import Link from 'next/link'
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
    h6: {
      fontSize: 'clamp(1.25rem, 2.6vw, 2rem)',
      fontWeight: 600,
      color: '#FAFAFA',
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
        main: '#CA1243', // grey
    },
    grey: {
      100: '#FAFAFA',
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

export default function LayoutClient({
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
  const isHomePage = pathname === '/'

  const bodyClass = isHomePage ? 'min-h-screen bg-white text-gray-900' : 'min-h-screen bg-[#FAFAFA] text-[#383A42]'

  return (
    <body className={`${bodyClass} overflow-x-hidden`}>
      <QueryClientProvider client={queryClient}>
        {!isHomePage && (
          <nav className="bg-white border-b border-[#E5E5E5]">
            <div className="max-w-5xl mx-auto px-6 lg:px-8">
              <div className="flex justify-between h-20 items-center">
                <Link href="/" className="flex items-center gap-3 group">
                  <img src="/Anchor FInal.svg" alt="Anchor" className="h-8 w-auto" />
                </Link>
                <div className="text-sm font-medium text-[#A1A1A1]">AI-Powered Video Production</div>
              </div>
            </div>
          </nav>
        )}
        <ThemeProvider theme={customTheme}>
          {isHomePage ? (
            <main className="w-full">
              {children}
            </main>
          ) : (
            <main className="px-6 lg:px-8 py-10">{children}</main>
          )}
        </ThemeProvider>
      </QueryClientProvider>
    </body>
  )
}
