import Link from 'next/link'

export default function Landing() {
  return (
    <div>
      <div className="max-w-7xl mx-auto px-6 py-12 text-center">
        <p className="text-lg text-gray-600 mb-6">Ready to create your first video?</p>
        <div className="flex items-center justify-center gap-4">
          <Link href="/create" className="inline-block bg-[#4078f2] text-white px-6 py-3 rounded-lg font-medium">Go to Create Page</Link>
          <Link href="/" className="inline-block border border-gray-200 px-6 py-3 rounded-lg">Explore</Link>
        </div>
      </div>
    </div>
  )
}
