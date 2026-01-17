'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getEventBrands,
  addEventBrands,
  removeEventBrand,
  getShopifyAuthUrl,
  getShopifyProducts,
  disconnectShopify,
} from '@/lib/api'
import type { BrandProduct, ShopifyProduct } from '@/lib/api'
import BrandStoreBrowser from './BrandStoreBrowser'

interface ShopifyConnectProps {
  eventId: string
  connectedUrl: string | null  // Legacy: per-event connection
}

export default function ShopifyConnect({ eventId, connectedUrl }: ShopifyConnectProps) {
  const queryClient = useQueryClient()
  const [showBrowser, setShowBrowser] = useState(false)
  const [legacyShopDomain, setLegacyShopDomain] = useState('')

  // New model: get brand products associated with this event
  const { data: brandsData, isLoading: brandsLoading } = useQuery({
    queryKey: ['event-brands', eventId],
    queryFn: () => getEventBrands(eventId),
  })

  // Legacy model: get products from per-event connection
  const { data: legacyProductsData, isLoading: legacyProductsLoading } = useQuery({
    queryKey: ['shopify-products', eventId],
    queryFn: () => getShopifyProducts(eventId),
    enabled: !!connectedUrl,
  })

  const addBrandsMutation = useMutation({
    mutationFn: ({ storeId, productIds }: { storeId: string; productIds: string[] }) =>
      addEventBrands(eventId, storeId, productIds, true),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event-brands', eventId] })
      setShowBrowser(false)
    },
  })

  const removeBrandMutation = useMutation({
    mutationFn: (associationId: string) => removeEventBrand(eventId, associationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event-brands', eventId] })
    },
  })

  // Legacy mutations
  const legacyConnectMutation = useMutation({
    mutationFn: async () => {
      const { auth_url } = await getShopifyAuthUrl(eventId, legacyShopDomain)
      window.location.href = auth_url
    },
  })

  const legacyDisconnectMutation = useMutation({
    mutationFn: () => disconnectShopify(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] })
      queryClient.invalidateQueries({ queryKey: ['shopify-products', eventId] })
    },
  })

  const brandProducts = brandsData?.brand_products || []
  const legacyProducts = legacyProductsData?.products || []
  const hasNewModelProducts = brandProducts.length > 0
  const hasLegacyConnection = !!connectedUrl

  // Show brand store browser
  if (showBrowser) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-medium text-gray-900">Select Brand Products</h3>
          <button
            onClick={() => setShowBrowser(false)}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Cancel
          </button>
        </div>
        <BrandStoreBrowser
          eventId={eventId}
          onProductsSelected={(storeId, productIds) => {
            addBrandsMutation.mutate({ storeId, productIds })
          }}
        />
        {addBrandsMutation.isPending && (
          <div className="flex items-center justify-center py-4">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600"></div>
            <span className="ml-2 text-gray-600">Adding products...</span>
          </div>
        )}
      </div>
    )
  }

  // New model: Show selected brand products
  if (hasNewModelProducts) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-medium text-gray-900">Brand Products ({brandProducts.length})</h3>
          <button
            onClick={() => setShowBrowser(true)}
            className="text-sm text-indigo-600 hover:text-indigo-700"
          >
            Add more
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {brandProducts.map((bp: BrandProduct) => (
            <div key={bp.id} className="relative border rounded-lg p-3 group">
              <button
                onClick={() => removeBrandMutation.mutate(bp.id)}
                disabled={removeBrandMutation.isPending}
                className="absolute top-2 right-2 w-6 h-6 bg-red-100 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <svg className="w-4 h-4 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>

              {bp.product?.image_url ? (
                <img
                  src={bp.product.image_url}
                  alt={bp.product.title}
                  className="w-full h-20 object-cover rounded mb-2"
                />
              ) : (
                <div className="w-full h-20 bg-gray-100 rounded mb-2" />
              )}
              <p className="text-sm font-medium truncate">{bp.product?.title}</p>
              <p className="text-xs text-gray-500">{bp.store?.shop_name || bp.store?.shop_domain}</p>
            </div>
          ))}
        </div>

        <p className="text-sm text-gray-500">
          These products will be featured in AI-generated video ad breaks.
        </p>
      </div>
    )
  }

  // Legacy model: Show connected store and products
  if (hasLegacyConnection) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between p-4 bg-green-50 rounded-lg">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🛍️</span>
            <div>
              <p className="font-medium text-green-800">Shopify Connected (Legacy)</p>
              <p className="text-sm text-green-600">{connectedUrl}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowBrowser(true)}
              className="text-sm text-indigo-600 hover:text-indigo-700"
            >
              Switch to new model
            </button>
            <button
              onClick={() => legacyDisconnectMutation.mutate()}
              disabled={legacyDisconnectMutation.isPending}
              className="text-sm text-red-600 hover:text-red-700"
            >
              Disconnect
            </button>
          </div>
        </div>

        {legacyProductsLoading ? (
          <div className="text-center py-4">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
          </div>
        ) : legacyProducts.length > 0 ? (
          <div>
            <h3 className="font-medium mb-3">Available Products ({legacyProducts.length})</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {legacyProducts.slice(0, 8).map((product: ShopifyProduct) => (
                <div key={product.id} className="border rounded-lg p-3">
                  {product.image_url && (
                    <img
                      src={product.image_url}
                      alt={product.title}
                      className="w-full h-24 object-cover rounded mb-2"
                    />
                  )}
                  <p className="text-sm font-medium truncate">{product.title}</p>
                  <p className="text-sm text-gray-500">${product.price}</p>
                </div>
              ))}
            </div>
            <p className="text-sm text-gray-500 mt-3">
              Products will be automatically featured in video ad breaks.
            </p>
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No active products found in your store.</p>
        )}
      </div>
    )
  }

  // No connection: Show options to connect
  return (
    <div className="space-y-6">
      {/* New model: Browse brand stores */}
      <div className="p-4 border-2 border-indigo-200 rounded-lg bg-indigo-50">
        <h3 className="font-medium text-indigo-900 mb-2">Browse Brand Partners</h3>
        <p className="text-sm text-indigo-700 mb-4">
          Select products from brands that have installed Anchor to feature in your video.
        </p>
        <button
          onClick={() => setShowBrowser(true)}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
        >
          Browse Brands
        </button>
      </div>

      {/* Divider */}
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-gray-300" />
        </div>
        <div className="relative flex justify-center text-sm">
          <span className="px-2 bg-white text-gray-500">or connect your own store</span>
        </div>
      </div>

      {/* Legacy model: Connect own store */}
      <div className="p-4 border border-gray-200 rounded-lg">
        <h3 className="font-medium text-gray-900 mb-2">Connect Your Shopify Store</h3>
        <p className="text-gray-600 text-sm mb-4">
          Connect your own Shopify store to insert your product ads.
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            value={legacyShopDomain}
            onChange={(e) => setLegacyShopDomain(e.target.value)}
            placeholder="your-store.myshopify.com"
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
          <button
            onClick={() => legacyConnectMutation.mutate()}
            disabled={!legacyShopDomain || legacyConnectMutation.isPending}
            className="px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-900 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {legacyConnectMutation.isPending ? 'Connecting...' : 'Connect'}
          </button>
        </div>

        {legacyConnectMutation.isError && (
          <p className="text-red-600 text-sm mt-2">
            Error: {legacyConnectMutation.error.message}
          </p>
        )}
      </div>

      <p className="text-xs text-gray-400 text-center">
        Your video will still be generated without ads if you skip this step.
      </p>
    </div>
  )
}
