"""Test script to debug reel generation."""
import sys
from services.supabase_client import get_supabase
from services.twelvelabs_service import search_videos, get_vibe_embedding

def test_reel_generation():
    """Test the reel generation process step by step."""
    # Use the completed event
    event_id = "a16ad8c2-3e65-41a6-81cd-766a025a26ce"
    query = "highlights"

    print("========== TESTING REEL GENERATION ==========")
    print(f"Event ID: {event_id}")
    print(f"Query: {query}")
    print()

    # Step 1: Get event
    print("STEP 1: Fetching event...")
    supabase = get_supabase()
    event = supabase.table("events").select("*").eq("id", event_id).single().execute()
    event_data = event.data

    print(f"Event name: {event_data['name']}")
    print(f"Event status: {event_data['status']}")
    print(f"TwelveLabs index ID: {event_data.get('twelvelabs_index_id')}")
    print()

    if not event_data.get("twelvelabs_index_id"):
        print("ERROR: No TwelveLabs index ID found!")
        return

    # Step 2: Search for moments
    print("STEP 2: Searching for moments...")
    try:
        moments = search_videos(
            index_id=event_data["twelvelabs_index_id"],
            query=query,
            limit=20,
        )
        print(f"Found {len(moments)} moments")

        if moments:
            print("\nTop 5 moments:")
            for i, moment in enumerate(moments[:5]):
                print(f"  {i+1}. Video {moment['video_id']}: {moment['start']:.1f}s-{moment['end']:.1f}s (confidence: {moment['confidence']:.2f})")
        else:
            print("No moments found!")
            return
    except Exception as e:
        print(f"ERROR searching: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    print()

    # Step 3: Get vibe embedding
    print("STEP 3: Getting vibe embedding...")
    try:
        vibe = "high_energy"
        vibe_embedding = get_vibe_embedding(vibe)
        print(f"Vibe embedding dimension: {len(vibe_embedding) if vibe_embedding else 0}")
    except Exception as e:
        print(f"ERROR getting vibe embedding: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    print()

    # Step 4: Get videos
    print("STEP 4: Fetching video metadata...")
    try:
        videos = supabase.table("videos").select("*").eq("event_id", event_id).execute()
        print(f"Found {len(videos.data)} videos")

        for i, video in enumerate(videos.data):
            print(f"  {i+1}. ID: {video['id']}")
            print(f"     TwelveLabs ID: {video.get('twelvelabs_video_id')}")
            print(f"     Original URL: {video.get('original_url')}")
            print(f"     Has embeddings: {bool(video.get('analysis_data', {}).get('embeddings'))}")
    except Exception as e:
        print(f"ERROR fetching videos: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    print()
    print("========== TEST COMPLETE ==========")

if __name__ == "__main__":
    test_reel_generation()
