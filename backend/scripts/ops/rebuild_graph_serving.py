
import sys
import os
import argparse
from dotenv import load_dotenv

# .env 로드
base_path = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.dirname(os.path.dirname(base_path)) # backend/
load_dotenv(os.path.join(backend_path, '.env'))
sys.path.append(backend_path)

from app.rag.steps.build_graph_serving_index import GraphServingIndexBuilder

def rebuild_graph():
    print("🚀 Starting Graph Serving Index Rebuild...")
    builder = GraphServingIndexBuilder()
    builder.run()
    print("✅ Graph Serving Index Rebuilt!")

if __name__ == "__main__":
    rebuild_graph()
