"""Test full reel generation locally (not via Celery)."""
from worker import generate_highlight_reel_task

# Use the test reel we just created
event_id = "a16ad8c2-3e65-41a6-81cd-766a025a26ce"
reel_id = "dc62156e-bfaf-4565-8c72-d702e9ad94fb"
query = "test highlights"
vibe = "high_energy"
duration = 15

print("Running reel generation task directly...")
print(f"Event: {event_id}")
print(f"Reel: {reel_id}")
print(f"Query: {query}")
print()

try:
    # Call the task function directly (not via Celery)
    result = generate_highlight_reel_task(event_id, reel_id, query, vibe, duration)
    print("\n========== RESULT ==========")
    print(result)
except Exception as e:
    print("\n========== ERROR ==========")
    print(f"{type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
