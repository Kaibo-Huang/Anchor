'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listShopifyStores, getShopifyStoreProducts } from '@/lib/api'
import type { ShopifyStore, ShopifyProduct } from '@/lib/api'
import ProductSelector from './ProductSelector'

interface BrandStoreBrowserProps {
  eventId: string
  onProductsSelected: (storeId: string, productIds: string[]) => void
}

export default function BrandStoreBrowser({ eventId, onProductsSelected }: BrandStoreBrowserProps) {
  const [selectedStore, setSelectedStore] = useState<ShopifyStore | null>(null)

  const { data: storesData, isLoading: storesLoading } = useQuery({
    queryKey: ['shopify-stores'],
    queryFn: () => listShopifyStores('active', 50, 0),
  })

  const { data: productsData, isLoading: productsLoading } = useQuery({
    queryKey: ['store-products', selectedStore?.id],
    queryFn: () => getShopifyStoreProducts(selectedStore!.id, 100, 0),
    enabled: !!selectedStore,
  })

  const stores = storesData?.stores || []
  const products = productsData?.products || []

  if (storesLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
      </div>
    )
  }

  if (stores.length === 0) {
    return (
      <div className="text-center py-12 px-4">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-gray-100 rounded-full mb-4">
          <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">No Brand Stores Available</h3>
        <p className="text-gray-600 mb-4">
          Brand partners need to install the Anchor app first.
        </p>
        <a
          href="/brands/install"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center text-indigo-600 hover:text-indigo-700 font-medium"
        >
          Share install link with brands
          <svg className="w-4 h-4 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
      </div>
    )
  }

  if (selectedStore) {
    return (
      <div>
        <button
          onClick={() => setSelectedStore(null)}
          className="flex items-center text-indigo-600 hover:text-indigo-700 mb-4"
        >
          <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to stores
        </button>

        <div className="flex items-center mb-6 p-4 bg-indigo-50 rounded-lg">
          <div className="flex-shrink-0 w-12 h-12 bg-indigo-100 rounded-full flex items-center justify-center">
            <span className="text-lg font-bold text-indigo-600">
              {(selectedStore.shop_name || selectedStore.shop_domain)[0].toUpperCase()}
            </span>
          </div>
          <div className="ml-4">
            <h3 className="font-medium text-gray-900">
              {selectedStore.shop_name || selectedStore.shop_domain}
            </h3>
            <p className="text-sm text-gray-500">{selectedStore.product_count} products</p>
          </div>
        </div>

        {productsLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
          </div>
        ) : (
          <ProductSelector
            products={products}
            onSelect={(productIds) => onProductsSelected(selectedStore.id, productIds)}
          />
        )}
      </div>
    )
  }

  return (
    <div>
      <h3 className="font-medium text-gray-900 mb-4">Select a Brand Store</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {stores.map((store) => (
          <button
            key={store.id}
            onClick={() => setSelectedStore(store)}
            className="flex items-center p-4 border border-gray-200 rounded-lg hover:border-indigo-300 hover:bg-indigo-50 transition-colors text-left"
          >
            <div className="flex-shrink-0 w-12 h-12 bg-indigo-100 rounded-full flex items-center justify-center">
              <span className="text-lg font-bold text-indigo-600">
                {(store.shop_name || store.shop_domain)[0].toUpperCase()}
              </span>
            </div>
            <div className="ml-4 flex-1 min-w-0">
              <h4 className="font-medium text-gray-900 truncate">
                {store.shop_name || store.shop_domain}
              </h4>
              <p className="text-sm text-gray-500">
                {store.product_count} products
              </p>
            </div>
            <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        ))}
      </div>
    </div>
  )
}
