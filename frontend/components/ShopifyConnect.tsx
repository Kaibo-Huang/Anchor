'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getShopifyAuthUrl, getShopifyProducts, disconnectShopify } from '@/lib/api'
import type { ShopifyProduct } from '@/lib/api'

interface ShopifyConnectProps {
  eventId: string
  connectedUrl: string | null
}

export default function ShopifyConnect({ eventId, connectedUrl }: ShopifyConnectProps) {
  const queryClient = useQueryClient()
  const [shopDomain, setShopDomain] = useState('')

  const { data: productsData, isLoading: productsLoading } = useQuery({
    queryKey: ['shopify-products', eventId],
    queryFn: () => getShopifyProducts(eventId),
    enabled: !!connectedUrl,
  })

  const connectMutation = useMutation({
    mutationFn: async () => {
      const { auth_url } = await getShopifyAuthUrl(eventId, shopDomain)
      window.location.href = auth_url
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: () => disconnectShopify(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', eventId] })
      queryClient.invalidateQueries({ queryKey: ['shopify-products', eventId] })
    },
  })

  if (connectedUrl) {
    const products = productsData?.products || []

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between p-4 bg-green-50 rounded-lg">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🛍️</span>
            <div>
              <p className="font-medium text-green-800">Shopify Connected</p>
              <p className="text-sm text-green-600">{connectedUrl}</p>
            </div>
          </div>
          <button
            onClick={() => disconnectMutation.mutate()}
            disabled={disconnectMutation.isPending}
            className="text-sm text-red-600 hover:text-red-700"
          >
            Disconnect
          </button>
        </div>

        {productsLoading ? (
          <div className="text-center py-4">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
          </div>
        ) : products.length > 0 ? (
          <div>
            <h3 className="font-medium mb-3">Available Products ({products.length})</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {products.slice(0, 8).map((product: ShopifyProduct) => (
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

  return (
    <div className="space-y-4">
      <p className="text-gray-600 text-sm">
        Connect your Shopify store to automatically insert product ads into natural video breaks.
      </p>

      <div className="flex gap-2">
        <input
          type="text"
          value={shopDomain}
          onChange={(e) => setShopDomain(e.target.value)}
          placeholder="your-store.myshopify.com"
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        />
        <button
          onClick={() => connectMutation.mutate()}
          disabled={!shopDomain || connectMutation.isPending}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {connectMutation.isPending ? 'Connecting...' : 'Connect'}
        </button>
      </div>

      {connectMutation.isError && (
        <p className="text-red-600 text-sm">
          Error: {connectMutation.error.message}
        </p>
      )}

      <p className="text-xs text-gray-400">
        Don&apos;t have a Shopify store? You can skip this step - your video will still be generated without ads.
      </p>
    </div>
  )
}
