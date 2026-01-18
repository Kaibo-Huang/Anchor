'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React, { useState } from 'react'
import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { createTheme, ThemeProvider } from '@mui/material/styles';
import BotNav from "@/components/BotNav";

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
    },
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
  transitions:{

  }
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
  const isEventsPage = pathname.startsWith('/events')

  const bodyClass = (isHomePage || isEventsPage)
    ? 'min-h-screen bg-white text-gray-900'
    : 'min-h-screen bg-[#FAFAFA] text-[#383A42]'

  return (
    <body
      className={`${bodyClass} overflow-x-hidden`}
      style={{ backgroundColor: (isHomePage || isEventsPage) ? '#ffffff' : '#FAFAFA' }}
    >
      <QueryClientProvider client={queryClient}>
        {!isHomePage && (
            <div className="absolute z-20" style={{left: '3vw', top: '5vh', width: '32vw'}}>
              <img src="/Anchor%20FInal.svg" alt="Anchor logo" className="w-full h-auto object-contain"/>
            </div>
        )}
        <ThemeProvider theme={customTheme}>
          {isHomePage ? (
            <main className="w-full">
              {children}
            </main>
          ) : (
            <main className="px-6 lg:px-8 py-10">{children}</main>
          )}
          <BotNav/>
        </ThemeProvider>
      </QueryClientProvider>
    </body>
  )
}
