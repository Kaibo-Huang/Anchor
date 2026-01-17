from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import events, videos, shopify, reels


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    print(f"Starting Anchor Backend...")
    print(f"Base URL: {settings.base_url}")
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title="Anchor API",
    description="AI-powered video production platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(videos.router, prefix="/api/events", tags=["videos"])
app.include_router(shopify.router, tags=["shopify"])
app.include_router(reels.router, prefix="/api/events", tags=["reels"])


@app.get("/")
async def root():
    return {"message": "Anchor API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
