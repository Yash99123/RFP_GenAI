from fastapi import APIRouter
from database import query
import json, os

router = APIRouter()

@router.get("/")
def get_queue():
    queue_path = "/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/exports/queue/attio_pending.json"
    if not os.path.exists(queue_path):
        return {"total": 0, "pending": 0, "synced": 0, "records": []}
    with open(queue_path) as f:
        data = json.load(f)
    pending = [r for r in data if not r.get("_attio_synced")]
    synced  = [r for r in data if r.get("_attio_synced")]
    preview = [{
        "solicitation_id": r.get("solicitation_id"),
        "name":            r.get("name"),
        "priority":        r.get("priority"),
        "score":           r.get("_score"),
        "source_portal":   r.get("source_portal"),
        "closing_date":    r.get("closing_date"),
        "queued_at":       r.get("_queued_at"),
    } for r in pending[:50]]
    return {
        "total":   len(data),
        "pending": len(pending),
        "synced":  len(synced),
        "records": preview,
    }
