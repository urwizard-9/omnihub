
import requests
import json
import sys

API_URL = "http://localhost:8000/api/graph/init?limit=50"

def test_graph_api():
    print(f"📡 Requesting Graph Init API: {API_URL}")
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        
        data = response.json()
        nodes = data.get("nodes", [])
        edges = data.get("edges", []) # API might return 'edges' or 'links' depending on implementation
        links = data.get("links", [])
        
        final_links = edges if edges else links
        
        print("\n📊 Response Summary:")
        print(f" - Nodes Count: {len(nodes)}")
        print(f" - Edges/Links Count: {len(final_links)}")
        
        if len(final_links) == 0:
            print("\n❌ CRITICAL: No edges returned from API!")
            print("   Possible reasons: Data missing, Logic error, Permission filtering.")
        else:
            print("\n✅ API returned edges successfully.")
            print(f"   First Edge: {final_links[0]}")
            
    except Exception as e:
        print(f"\n❌ API Request Failed: {e}")
        # Print raw response if available
        try:
            print(f"   Response Text: {response.text[:500]}")
        except:
            pass

if __name__ == "__main__":
    test_graph_api()
