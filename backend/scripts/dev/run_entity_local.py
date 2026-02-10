import sys
import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Add backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.rag.steps.extract_entities_relations import EntityExtractor
from app.core.gcp_clients import get_firestore_client
from app.core.config import settings

# Logger Config
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("EntityTest")

def main():
    db = get_firestore_client()
    extractor = EntityExtractor()

    # 1. Fetch all documents from 'chunks' collection (processed docs)
    #    because Entity Extraction depends on chunks being ready.
    docs = db.collection("chunks").stream()
    doc_ids = [d.id for d in docs]

    if not doc_ids:
        logger.warning("No documents found in 'chunks' collection. Run pipeline first.")
        return

    logger.info(f"🔍 Found {len(doc_ids)} documents to process.")

    # 2. Process each document
    #    Using process_single_document logic which handles loading chunks, filtering, LLM calling, and saving.
    success_count = 0
    fail_count = 0

    for doc_id in doc_ids:
        logger.info(f"🚀 Processing Entities for: {doc_id}")
        try:
             # Run in thread pool to mimic production environment if needed, 
             # but sequential call is fine for debugging.
             extractor.process_single_document(doc_id)
             
             # Verify result
             ent_ref = db.collection("entities").document(doc_id).get()
             if ent_ref.exists:
                 data = ent_ref.to_dict()
                 count = data.get("entity_count", 0)
                 logger.info(f"✅ Success: {doc_id} -> {count} entities extracted.")
                 success_count += 1
             else:
                 logger.error(f"❌ Failed: {doc_id} - Entity document not created.")
                 fail_count += 1
                 
        except Exception as e:
            logger.error(f"❌ Error processing {doc_id}: {e}", exc_info=True)
            fail_count += 1

    logger.info("="*50)
    logger.info(f"📝 Summary: Success={success_count}, Failed={fail_count}")
    logger.info("="*50)

if __name__ == "__main__":
    main()
