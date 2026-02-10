
import os
import sys
# Ensure backend in path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

from app.core.config import settings

print(f"GOOGLE_CLIENT_ID: '{settings.GOOGLE_CLIENT_ID}'")
print(f"GOOGLE_CLIENT_SECRET: '{settings.GOOGLE_CLIENT_SECRET}'")
print(f"LEN ID: {len(settings.GOOGLE_CLIENT_ID)}")
print(f"LEN SECRET: {len(settings.GOOGLE_CLIENT_SECRET)}")

if ' ' in settings.GOOGLE_CLIENT_ID:
    print("WARNING: Space in Client ID")
if ' ' in settings.GOOGLE_CLIENT_SECRET:
    print("WARNING: Space in Client Secret")
