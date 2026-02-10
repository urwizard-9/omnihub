import sys
import os
import logging
import itertools
from collections import defaultdict
from google.cloud import firestore

# [통합] Backend Imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

# Logger 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugCooc")

from app.rag.steps.build_graph_serving_index import GraphServingIndexBuilder
from app.core.config import settings

def debug_cooc_logic():
    print(f"\n🔎 Debugging Concept Co-occurrence Logic")
    print(f"   Settings: TopK={settings.COOC_DOC_TOPK}, Shared={settings.COOC_MIN_SHARED_DOCS}, MinW={settings.COOC_MIN_WEIGHT}")
    
    # 1. Initialize Builder
    builder = GraphServingIndexBuilder()
    
    # 2. Simulate Data Loading (Fast)
    # Let's fetch Top 5 Docs and their Top Concepts (Assuming they have common ones for testing)
    # If not, we might not see edges.
    
    db = firestore.Client(project=settings.PROJECT_ID)
    docs_ref = (db.collection("documents")
                .where(filter=firestore.FieldFilter("aiStatus", "==", "completed")) # or active=True
                .limit(10)
                .stream())
    
    doc_neighbors = defaultdict(list)
    valid_ids = []
    
    print("\n[Step 1] Loading Sample Data...")
    for d in docs_ref:
        data = d.to_dict()
        top_concepts = data.get("top_concepts", [])
        if not top_concepts:
            # Try fetching from edges if top_concepts missing
            pass
        else:
            # Reconstruct doc_neighbors format
            # top_concepts has {concept_id, score, ...}
            valid_ids.append(d.id)
            for c in top_concepts:
                 doc_neighbors[d.id].append({
                     "concept_id": c["concept_id"],
                     "score": c["score"]
                 })
                 
    print(f"   Loaded {len(valid_ids)} docs. Concepts per doc avg: {sum(len(v) for v in doc_neighbors.values()) / max(len(valid_ids), 1):.1f}")

    # 3. Running Implementation Logic (Copy-Paste Logic for Dry Run Verification)
    print("\n[Step 2] Calculating Co-occurrence (Simulation)...")
    
    pair_stats = defaultdict(lambda: {"weight": 0.0, "shared": 0})
    
    for doc_id, concepts in doc_neighbors.items():
        # Filter Top-K
        active_concepts = sorted(concepts, key=lambda x: x["score"], reverse=True)[:builder.cooc_doc_topk]
        
        if len(active_concepts) < 2: continue
        
        ids_scores = [(c["concept_id"], c["score"]) for c in active_concepts]
        
        for (c1, s1), (c2, s2) in itertools.combinations(ids_scores, 2):
            if c1 > c2: c1, c2 = c2, c1
            w = min(s1, s2)
            k = (c1, c2)
            pair_stats[k]["weight"] += w
            pair_stats[k]["shared"] += 1
            
    print(f"   Generated {len(pair_stats)} raw pairs.")
    
    # 4. Filter & Check
    print("\n[Step 3] Verification...")
    
    valid_pairs = []
    for k, stats in pair_stats.items():
        if stats["shared"] >= builder.cooc_min_shared and stats["weight"] >= builder.cooc_min_weight:
            valid_pairs.append({
                "pair": k,
                "stats": stats
            })
            
    valid_pairs.sort(key=lambda x: x["stats"]["weight"], reverse=True)
    
    print(f"   Passed Filter: {len(valid_pairs)} pairs")
    
    if valid_pairs:
        print("   ✅ Top 3 Strongest Connections:")
        for p in valid_pairs[:3]:
            # Fetch names for clarity
            c1_name = "Unknown"
            c2_name = "Unknown"
            try:
                c1_d = db.collection("concepts").document(p["pair"][0]).get()
                c2_d = db.collection("concepts").document(p["pair"][1]).get()
                if c1_d.exists: c1_name = c1_d.get("canonical_name")
                if c2_d.exists: c2_name = c2_d.get("canonical_name")
            except: pass
            
            print(f"     🔗 {c1_name} <-> {c2_name} | W: {p['stats']['weight']:.2f}, Shared: {p['stats']['shared']}")
    else:
        print("   ⚠️ No pairs passed the filter. (Maybe sample too small or threshold too high?)")
        print("   -> Try lowering COOC_MIN_SHARED_DOCS or checking if docs share concepts.")

if __name__ == "__main__":
    debug_cooc_logic()
