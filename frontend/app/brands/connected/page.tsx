'use client'

import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Suspense } from 'react'

function ConnectedContent() {
  const searchParams = useSearchParams()
  const shop = searchParams.get('shop')

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-xl p-8 text-center">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-green-100 rounded-full mb-6">
          <svg className="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>

        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          Successfully Connected!
        </h1>

        {shop && (
          <p className="text-lg text-gray-600 mb-6">
            <span className="font-medium text-gray-900">{shop}</span> is now connected to Anchor
          </p>
        )}

        <div className="bg-gray-50 rounded-lg p-4 mb-6 text-left">
          <h3 className="font-medium text-gray-900 mb-3">What happens now?</h3>
          <ul className="space-y-3 text-sm text-gray-600">
            <li className="flex items-start">
              <div className="flex-shrink-0 w-6 h-6 bg-indigo-100 rounded-full flex items-center justify-center mr-3">
                <span className="text-xs font-medium text-indigo-600">1</span>
              </div>
              <span>Your products are being synced in the background</span>
            </li>
            <li className="flex items-start">
              <div className="flex-shrink-0 w-6 h-6 bg-indigo-100 rounded-full flex items-center justify-center mr-3">
                <span className="text-xs font-medium text-indigo-600">2</span>
              </div>
              <span>Event organizers can now browse and select your products</span>
            </li>
            <li className="flex items-start">
              <div className="flex-shrink-0 w-6 h-6 bg-indigo-100 rounded-full flex items-center justify-center mr-3">
                <span className="text-xs font-medium text-indigo-600">3</span>
              </div>
              <span>Your products will be featured in AI-generated video ads</span>
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          <Link
            href="/"
            className="block w-full py-3 px-4 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition-colors"
          >
            Create an Event
          </Link>
          <Link
            href="/brands/install"
            className="block w-full py-3 px-4 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200 transition-colors"
          >
            Connect Another Store
          </Link>
        </div>

        <p className="mt-6 text-xs text-gray-500">
          You can manage your connection from your Shopify admin panel at any time.
        </p>
      </div>
    </div>
  )
}

export default function BrandConnectedPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600"></div>
      </div>
    }>
      <ConnectedContent />
    </Suspense>
  )
}
