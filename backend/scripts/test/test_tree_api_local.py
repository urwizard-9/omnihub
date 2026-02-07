
import requests
import json

def get_tree(path="/"):
    url = "http://localhost:8000/api/tree?folder=" + path
    headers = {
        "X-User-Id": "test-user",
        "X-Tenant-Id": "my-tenant",
        "X-Engagement-Id": "eng-001",
        "X-Roles": "admin"
    }
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json()
        else:
            print(f"❌ API Failed: {res.status_code} {res.text}")
            return None
    except Exception as e:
        print(f"❌ Request Error: {e}")
        return None

def explore_tree(path="/", depth=0):
    if depth > 3: return # 너무 깊이 안 들어가도록
    
    print(f"📂 Checking {path}...")
    data = get_tree(path)
    if not data: return

    files = data.get("files", [])
    if files:
        print(f"✅ Found {len(files)} files in {path}!")
        first = files[0]
        print(f"Sample File: {json.dumps(first, indent=2, ensure_ascii=False)}")
        return # 찾았으면 종료
        
    folders = data.get("folders", [])
    for f in folders:
        explore_tree(f['path'], depth + 1)

if __name__ == "__main__":
    explore_tree()
