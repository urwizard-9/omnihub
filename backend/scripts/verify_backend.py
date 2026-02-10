import sys
import os
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

print(f"Checking backend at: {project_root}")

try:
    from app.main import app
    print("✅ [Success] 'app.main' imported successfully.")
except ImportError as e:
    print(f"❌ [Fatal] Import Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ [Fatal] Startup Error: {e}")
    sys.exit(1)

# Check Routes
print("\n[Registered Routes]")
ai_routes_found = False
webhook_found = False

for route in app.routes:
    if hasattr(route, "path"):
        print(f" - {route.path} [{','.join(route.methods)}]")
        if "/api/search/rag" in route.path:
            ai_routes_found = True
        if "/webhook/drive" in route.path:
            webhook_found = True

print("-" * 30)

if ai_routes_found:
    print("✅ AI (RAG) Routes detected.")
else:
    print("⚠️  Warning: AI Routes NOT found.")

if webhook_found:
    print("✅ Webhook Routes detected.")
else:
    print("⚠️  Warning: Webhook Routes NOT found.")

print("\nBackend Verification Completed.")
