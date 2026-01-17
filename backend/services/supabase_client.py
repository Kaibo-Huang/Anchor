"""Supabase client singleton for database operations."""

from functools import lru_cache

from supabase import create_client, Client

from config import get_settings


@lru_cache
def get_supabase() -> Client:
    """Get Supabase client singleton."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)
