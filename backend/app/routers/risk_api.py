from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.gcp_clients import get_firestore_client
from app.models.risk import RiskData
from typing import List, Optional
from app.routers.auth import get_current_user
from google.cloud.firestore import Query as direction

router = APIRouter(
    prefix="/api/risk",
    tags=["risk"],
    responses={404: {"description": "Not found"}},
)

import traceback
from fastapi.responses import JSONResponse

@router.get("/history")
async def get_risk_history(
    limit: int = Query(50, description="Number of users to fetch"),
    current_user: dict = Depends(get_current_user) # Require Auth
):
    """
    Fetch risk history/events from Firestore 'risk_users_latest' collection.
    Since parent documents may be empty, we fetch the latest entry from each user's 'history' subcollection.
    """
    try:
        db = get_firestore_client()
        print(f"[DEBUG] Firestore client created successfully")
        
        collection_ref = db.collection('risk_users_latest')
        print(f"[DEBUG] Accessing collection: risk_users_latest")
        
        # Fetch all user documents (up to limit)
        user_docs = list(collection_ref.limit(limit).stream())
        print(f"[DEBUG] Found {len(user_docs)} user documents in risk_users_latest")
        
        if len(user_docs) == 0:
            print(f"[ERROR] No documents found in risk_users_latest collection!")
            print(f"[ERROR] This means the collection is empty or doesn't exist")
            return JSONResponse(content=[])
        
        results = []
        for idx, user_doc in enumerate(user_docs, 1):
            user_id = user_doc.id
            print(f"[DEBUG] [{idx}/{len(user_docs)}] Processing user: {user_id}")
            
            # For each user, get the latest document from their 'history' subcollection
            history_ref = user_doc.reference.collection('history')
            
            try:
                # Try to fetch latest document (ordered by lastEventAt descending)
                print(f"[DEBUG] Querying history for {user_id}...")
                latest_query = history_ref.order_by('lastEventAt', direction=direction.DESCENDING).limit(1)
                latest_docs = list(latest_query.stream())
                print(f"[DEBUG] User {user_id}: found {len(latest_docs)} history documents")
                
                if latest_docs:
                    data = latest_docs[0].to_dict()
                    if 'userId' not in data:
                        data['userId'] = user_id
                    results.append(data)
                    print(f"[DEBUG] ✓ Successfully added {user_id} to results")
                else:
                    print(f"[WARNING] User {user_id} has NO history documents in subcollection")
                    
            except Exception as query_err:
                # Fallback: If Firestore index missing, fetch all and sort in memory
                print(f"[WARNING] Firestore sort failed for {user_id}: {query_err}")
                print(f"[DEBUG] Attempting memory sort fallback for {user_id}...")
                try:
                    all_history = list(history_ref.limit(20).stream())
                    print(f"[DEBUG] Fallback: fetched {len(all_history)} history docs for {user_id}")
                    
                    if all_history:
                        # Sort by lastEventAt in memory
                        all_history.sort(
                            key=lambda d: d.to_dict().get('lastEventAt', ''), 
                            reverse=True
                        )
                        data = all_history[0].to_dict()
                        if 'userId' not in data:
                            data['userId'] = user_id
                        results.append(data)
                        print(f"[DEBUG] ✓ Fallback successful for {user_id}")
                    else:
                        print(f"[WARNING] Fallback: User {user_id} has NO history documents")
                except Exception as fallback_err:
                    print(f"[ERROR] Fallback also failed for {user_id}: {fallback_err}")

        # Sort all results by lastEventAt (most recent first)
        results.sort(key=lambda x: x.get('lastEventAt', ''), reverse=True)

        print(f"[API] Returning {len(results)} user risk records")
        return JSONResponse(content=results)
        
    except Exception as e:
        print(f"[ERROR] Fatal error in get_risk_history: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()}, status_code=500)

from fastapi import Request
from app.services.risk_monitor_service import handle_risk_event

@router.post("/event")
async def receive_risk_event(request: Request):
    """
    Eventarc Trigger Endpoint.
    Receives CloudEvents from Google Cloud Eventarc.
    """
    try:
        # Eventarc for Firestore sends data in Protobuf format (binary).
        # Parsing Protobuf in Python requires complex setup (proto definitions).
        # Fortunately, the CloudEvent HEADER "ce-subject" contains the resource name!
        # Example ce-subject: "projects/.../databases/(default)/documents/risk_users_latest/{userId}"
        
        ce_subject = request.headers.get("ce-subject")
        print(f"[Eventarc] Received event. Subject: {ce_subject}") # Debug log
        
        if not ce_subject:
            # Fallback or error. If it's a test?
            print("[Eventarc] Warning: No 'ce-subject' header found.")
            # We might try to read body if JSON (for local test), but for Prod it's binary.
            try:
                body = await request.json()
                if isinstance(body, dict) and 'value' in body:
                     # Simulate extracting name for local test
                     ce_subject = body.get('value', {}).get('name')
            except:
                pass

        if ce_subject:
            await handle_risk_event(ce_subject)
        else:
            print("[Eventarc] Could not extract document name. Skipping.")
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Error processing risk event: {e}")
        # Return 200 to acknowledge receipt to Eventarc
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{user_id}")
async def get_user_risk_history(
    user_id: str,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch specific user's risk history for charting.
    Expected to return list of RiskData from 'history' subcollection.
    """
    try:
        db = get_firestore_client()
        # Path: risk_users_latest/{userId}/history
        history_ref = db.collection('risk_users_latest').document(user_id).collection('history')
        
        # Order by lastEventAt descending
        query = history_ref.order_by('lastEventAt', direction=direction.DESCENDING).limit(limit)
        
        # NOTE: If "Missing Index" error occurs here, we will fallback to memory sort again.
        # But for subcollections, sometimes indexes are needed.
        # Let's try native sort first.
        try:
            docs = query.stream()
            results = [doc.to_dict() for doc in docs]
        except Exception as query_err:
             print(f"[Warning] Firestore Sort Failed (Index?): {query_err}. Fallback to memory sort.")
             docs = history_ref.limit(limit).stream()
             results = [doc.to_dict() for doc in docs]
             # Memory Sort
             results.sort(key=lambda x: x.get('lastEventAt', ''), reverse=True)

        return JSONResponse(content=results)
    except Exception as e:
         return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()}, status_code=500)
