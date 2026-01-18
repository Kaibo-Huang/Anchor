import React from 'react'

const IMG_VECTOR = 'https://www.figma.com/api/mcp/asset/d2a84f94-cd28-42ff-99f1-0bd4d56eb2d8'
const IMG_ARROW = 'https://www.figma.com/api/mcp/asset/884863fd-a2c3-488d-81e6-e163102a5bbe'
const IMG_ANCHOR = 'https://www.figma.com/api/mcp/asset/0ff6fc2f-9068-496c-bacb-3809d32426ef'

export default function Hero() {
  return (
    <section className="relative overflow-hidden bg-[#fafafa]">
      <div className="absolute inset-0 pointer-events-none">
        <img src={IMG_VECTOR} alt="background vector" className="w-[140%] -left-40 -top-24 absolute" />
      </div>

      <div className="relative max-w-7xl mx-auto px-6 py-24 lg:py-32">
        <div className="flex flex-col lg:flex-row items-start gap-8">
          <div className="w-full lg:w-1/2">
            <div className="h-36 mb-8">
              <img src={IMG_ANCHOR} alt="Anchor logo" className="h-full object-contain" />
            </div>

            <h2 className="text-4xl lg:text-5xl font-bold text-white mb-8 drop-shadow-[0_2px_0_rgba(0,0,0,0.08)]">
              What are we up to?
            </h2>

            <div className="mb-8">
              <button className="inline-flex items-center gap-3 bg-white text-[#4078f2] px-6 py-3 rounded-lg shadow-md">
                <span className="inline-flex items-center justify-center w-6 h-6 bg-[#eef2ff] rounded-full">⭐</span>
                <span className="font-medium">Upload Videos</span>
              </button>
            </div>
          </div>

          <div className="w-full lg:w-1/2 flex items-center justify-center">
            {/* Right side intentionally left minimal for landing hero; primary create UI moved to PrimaryCreate component */}
            <div className="opacity-0 w-full h-40" />
          </div>
        </div>
      </div>
    </section>
  )
}
