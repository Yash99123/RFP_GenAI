"""
Tracking routes for RFP status management and notes.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import query, get_db
import json

router = APIRouter()

# Status workflow: new -> identified -> active/in_progress -> completed/rejected
VALID_STATUSES = ["new", "identified", "active", "in_progress", "rejected", "completed"]
VALID_TRANSITIONS = {
    "new": ["identified", "rejected"],
    "identified": ["active", "in_progress", "rejected", "new"],
    "active": ["in_progress", "completed", "rejected"],
    "in_progress": ["active", "completed", "rejected"],
    "rejected": ["new", "identified"],
    "completed": ["active", "in_progress"],
}


class StatusUpdate(BaseModel):
    status: str
    note: Optional[str] = None


class NoteCreate(BaseModel):
    note: str
    author: Optional[str] = "User"


class NoteResponse(BaseModel):
    id: int
    note: str
    author: str
    created_at: str


@router.get("/tracking/summary")
def get_tracking_summary():
    """Get counts of tenders by status for the tracking dashboard."""
    rows = query("""
        SELECT 
            COALESCE(status, 'new') as status,
            COUNT(*) as count
        FROM tenders
        GROUP BY status
        ORDER BY 
            CASE status
                WHEN 'new' THEN 1
                WHEN 'identified' THEN 2
                WHEN 'active' THEN 3
                WHEN 'in_progress' THEN 4
                WHEN 'completed' THEN 5
                WHEN 'rejected' THEN 6
                ELSE 7
            END
    """)
    
    summary = {r["status"]: r["count"] for r in rows}
    
    # Get total
    total = sum(summary.values())
    
    return {
        "total": total,
        "by_status": summary,
        "new": summary.get("new", 0),
        "identified": summary.get("identified", 0),
        "active": summary.get("active", 0),
        "in_progress": summary.get("in_progress", 0),
        "completed": summary.get("completed", 0),
        "rejected": summary.get("rejected", 0),
    }


@router.get("/tracking/{status}")
def get_tenders_by_status(status: str, limit: int = 50, offset: int = 0):
    """Get tenders filtered by tracking status."""
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    rows = query("""
        SELECT id, solicitation_id, name, source_portal, end_client, 
               closing_date, closing_date_note, office, summary, rfp_category,
               contact_name, contact_email, budget_text, first_seen, status, 
               is_open, notes, identified_at, last_modified_at
        FROM tenders
        WHERE COALESCE(status, 'new') = %s
        ORDER BY 
            COALESCE(identified_at, first_seen) DESC
        LIMIT %s OFFSET %s
    """, [status, limit, offset])
    
    total = query(
        "SELECT COUNT(*) as n FROM tenders WHERE COALESCE(status, 'new') = %s",
        [status]
    )[0]["n"]
    
    return {"data": rows, "total": total, "status": status}


@router.patch("/{tender_id}/status")
def update_tender_status(tender_id: int, update: StatusUpdate):
    """Update the tracking status of a tender."""
    if update.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")
    
    # Get current status
    current = query("SELECT status FROM tenders WHERE id = %s", [tender_id])
    if not current:
        raise HTTPException(status_code=404, detail="Tender not found")
    
    current_status = current[0]["status"] or "new"
    
    # Check if transition is valid
    if update.status not in VALID_TRANSITIONS.get(current_status, []):
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot transition from '{current_status}' to '{update.status}'"
        )
    
    now = datetime.utcnow()
    now_iso = now.isoformat()
    
    with get_db() as conn:
        cur = conn.cursor()
        
        # Get current status_history
        cur.execute("SELECT status_history FROM tenders WHERE id = %s", [tender_id])
        row = cur.fetchone()
        history = row[0] if row[0] else []
        
        # Append new status change
        history.append({
            "from": current_status,
            "to": update.status,
            "at": now_iso,
            "note": update.note
        })
        
        # Update status and history
        identified_at = None
        if update.status == "identified":
            identified_at = now_iso
        
        cur.execute("""
            UPDATE tenders 
            SET status = %s, 
                status_history = %s,
                identified_at = COALESCE(%s, identified_at),
                last_modified_at = %s
            WHERE id = %s
        """, [update.status, json.dumps(history), identified_at, now, tender_id])
        
        # If there's a note, add it to notes_history too
        if update.note:
            cur.execute("SELECT notes_history FROM tenders WHERE id = %s", [tender_id])
            notes_row = cur.fetchone()
            notes_history = notes_row[0] if notes_row[0] else []
            
            notes_history.append({
                "note": f"Status changed to {update.status}: {update.note}",
                "author": "System",
                "created_at": now_iso,
                "type": "status_change"
            })
            
            cur.execute("""
                UPDATE tenders 
                SET notes_history = %s
                WHERE id = %s
            """, [json.dumps(notes_history), tender_id])
    
    return {
        "success": True,
        "tender_id": tender_id,
        "previous_status": current_status,
        "new_status": update.status
    }


@router.post("/{tender_id}/notes")
def add_note(tender_id: int, note: NoteCreate):
    """Add a note to a tender."""
    # Check tender exists
    current = query("SELECT id FROM tenders WHERE id = %s", [tender_id])
    if not current:
        raise HTTPException(status_code=404, detail="Tender not found")
    
    now = datetime.utcnow()
    now_iso = now.isoformat()
    
    with get_db() as conn:
        cur = conn.cursor()
        
        # Get current notes_history
        cur.execute("SELECT notes_history FROM tenders WHERE id = %s", [tender_id])
        row = cur.fetchone()
        history = row[0] if row[0] else []
        
        # Add new note
        history.append({
            "note": note.note,
            "author": note.author,
            "created_at": now_iso,
            "type": "user_note"
        })
        
        # Update notes_history, notes (for backward compat), and last_modified_at
        cur.execute("""
            UPDATE tenders 
            SET notes_history = %s,
                notes = COALESCE(notes, '') || E'\n---\n' || %s,
                last_modified_at = %s
            WHERE id = %s
        """, [json.dumps(history), f"[{now_iso}] {note.note}", now, tender_id])
    
    return {
        "success": True,
        "tender_id": tender_id,
        "note_added": note.note
    }


@router.get("/{tender_id}/notes")
def get_notes(tender_id: int):
    """Get all notes for a tender."""
    rows = query("""
        SELECT notes_history FROM tenders WHERE id = %s
    """, [tender_id])
    
    if not rows:
        raise HTTPException(status_code=404, detail="Tender not found")
    
    notes = rows[0]["notes_history"] or []
    
    # Sort by created_at descending (newest first)
    notes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {"tender_id": tender_id, "notes": notes}


@router.delete("/{tender_id}/notes/{note_index}")
def delete_note(tender_id: int, note_index: int):
    """Delete a note by index."""
    with get_db() as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT notes_history FROM tenders WHERE id = %s", [tender_id])
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tender not found")
        
        history = row[0] if row[0] else []
        
        if note_index < 0 or note_index >= len(history):
            raise HTTPException(status_code=400, detail="Invalid note index")
        
        # Remove the note
        history.pop(note_index)
        
        cur.execute("""
            UPDATE tenders SET notes_history = %s WHERE id = %s
        """, [json.dumps(history), tender_id])
    
    return {"success": True, "tender_id": tender_id}
