'use client'

import { useState } from 'react'
import type { ShopifyProduct } from '@/lib/api'

interface ProductSelectorProps {
  products: ShopifyProduct[]
  onSelect: (productIds: string[]) => void
  maxSelections?: number
}

export default function ProductSelector({
  products,
  onSelect,
  maxSelections = 5,
}: ProductSelectorProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const toggleProduct = (productId: string) => {
    const newSelected = new Set(selectedIds)
    if (newSelected.has(productId)) {
      newSelected.delete(productId)
    } else if (newSelected.size < maxSelections) {
      newSelected.add(productId)
    }
    setSelectedIds(newSelected)
  }

  const handleConfirm = () => {
    onSelect(Array.from(selectedIds))
  }

  if (products.length === 0) {
    return (
      <div className="text-center py-8 text-gray-700">
        No products available in this store.
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-600">
          Select up to {maxSelections} products ({selectedIds.size} selected)
        </p>
        {selectedIds.size > 0 && (
          <button
            onClick={() => setSelectedIds(new Set())}
            className="text-sm text-gray-600 hover:text-gray-800"
          >
            Clear all
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4 mb-6">
        {products.map((product) => {
          const isSelected = selectedIds.has(product.id)
          const isDisabled = !isSelected && selectedIds.size >= maxSelections

          return (
            <button
              key={product.id}
              onClick={() => toggleProduct(product.id)}
              disabled={isDisabled}
              className={`relative p-3 border-2 rounded-lg text-left transition-all ${
                isSelected
                  ? 'border-indigo-500 bg-indigo-50'
                  : isDisabled
                  ? 'border-gray-200 bg-gray-100 opacity-60 cursor-not-allowed'
                  : 'border-gray-200 hover:border-indigo-300'
              }`}
            >
              {isSelected && (
                <div className="absolute top-2 right-2 w-6 h-6 bg-indigo-500 rounded-full flex items-center justify-center">
                  <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
              )}

              {product.image_url ? (
                <img
                  src={product.image_url}
                  alt={product.title}
                  className="w-full h-24 object-cover rounded mb-2"
                />
              ) : (
                <div className="w-full h-24 bg-gray-100 rounded mb-2 flex items-center justify-center">
                  <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
              )}

              <h4 className="text-sm font-medium text-gray-900 truncate">
                {product.title}
              </h4>
              <p className="text-sm text-gray-700">
                ${typeof product.price === 'number' ? product.price.toFixed(2) : product.price}
              </p>
            </button>
          )
        })}
      </div>

      {selectedIds.size > 0 && (
        <div className="sticky bottom-0 bg-white border-t pt-4">
          <button
            onClick={handleConfirm}
            className="w-full py-3 px-4 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition-colors"
          >
            Add {selectedIds.size} Product{selectedIds.size > 1 ? 's' : ''} to Event
          </button>
        </div>
      )}
    </div>
  )
}
