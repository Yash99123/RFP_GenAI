from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from database import query, get_db
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

router = APIRouter()


class TenderCreate(BaseModel):
    name: str
    source_portal: Optional[str] = None
    end_client: Optional[str] = None
    sector: Optional[str] = None
    rfp_category: Optional[str] = None
    closing_date: Optional[str] = None
    closing_date_note: Optional[str] = None
    open_date: Optional[str] = None
    office: Optional[str] = None
    country: Optional[str] = None
    details_url: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    budget_text: Optional[str] = None
    solicitation_id: Optional[str] = None
    is_open: Optional[bool] = True
    status: Optional[str] = "new"

# Allowed sort columns
SORT_COLUMNS = {
    "closing_date": "closing_date",
    "open_date": "open_date",
    "name": "name",
    "source_portal": "source_portal",
    "rfp_category": "rfp_category",
    "first_seen": "first_seen",
}

@router.get("/")
def get_tenders(
    source:   Optional[str] = None,
    office:   Optional[str] = None,
    sector:   Optional[str] = None,
    status:   Optional[str] = None,
    search:   Optional[str] = None,
    category: Optional[str] = None,
    is_open:  Optional[str] = None,
    new_today: Optional[str] = None,
    sort:     Optional[str] = "closing_date",
    order:    Optional[str] = "asc",
    limit:    int = 50,
    offset:   int = 0,
):
    filters, params = [], []

    if source:
        filters.append("source_portal = %s")
        params.append(source)
    if office:
        filters.append("office = %s")
        params.append(office)
    if sector:
        filters.append("sector = %s")
        params.append(sector)
    if category:
        filters.append("rfp_category = %s")
        params.append(category)
    if is_open == "open":
        filters.append("(is_open = TRUE OR is_open IS NULL)")
    elif is_open == "closed":
        filters.append("is_open = FALSE")
    if new_today == "true":
        filters.append("first_seen::date = CURRENT_DATE")
        filters.append("(is_open = TRUE OR is_open IS NULL)")
    if search:
        filters.append("(name ILIKE %s OR end_client ILIKE %s OR summary ILIKE %s OR description ILIKE %s)")
        params += [f"%{search}%"] * 4

    where = "WHERE " + " AND ".join(filters) if filters else ""

    # Build ORDER BY
    sort_col = SORT_COLUMNS.get(sort, "closing_date")
    if order == "desc":
        order_sql = "DESC"
    else:
        order_sql = "ASC"

    # Nulls handling: NULLS LAST for ascending, NULLS FIRST for descending
    nulls = "NULLS LAST" if order_sql == "ASC" else "NULLS FIRST"

    order_clause = f"{sort_col} {order_sql} {nulls}"

    # Always add secondary sort by first_seen for consistency
    if sort_col != "first_seen":
        order_clause += ", first_seen DESC"

    params += [limit, offset]

    rows = query(f"""
        SELECT id, solicitation_id, name, source_portal, end_client, sector,
               closing_date, closing_date_note, office, country, details_url,
               summary, rfp_category, contact_name, contact_email, budget_text,
               first_seen, status, is_open, open_date
        FROM tenders
        {where}
        ORDER BY {order_clause}
        LIMIT %s OFFSET %s
    """, params)

    total_params = params[:-2]
    total = query(f"SELECT COUNT(*) as n FROM tenders {where}", total_params)[0]["n"]

    return {"data": rows, "total": total, "limit": limit, "offset": offset}


@router.post("/")
def create_tender(tender: TenderCreate):
    """Create a new tender manually from the tracker."""
    now = datetime.utcnow().isoformat()
    # Generate a unique solicitation_id if not provided
    solicitation_id = tender.solicitation_id or f"MANUAL-{int(datetime.utcnow().timestamp())}"

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tenders (
                solicitation_id, name, source_portal, end_client, sector,
                rfp_category, closing_date, closing_date_note, open_date,
                office, country, details_url, summary, description,
                contact_name, contact_email, budget_text, is_open, status,
                first_seen, last_modified_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s
            ) RETURNING id
        """, [
            solicitation_id, tender.name, tender.source_portal, tender.end_client, tender.sector,
            tender.rfp_category, tender.closing_date, tender.closing_date_note, tender.open_date,
            tender.office, tender.country, tender.details_url, tender.summary, tender.description,
            tender.contact_name, tender.contact_email, tender.budget_text, tender.is_open, tender.status,
            now, now
        ])
        row = cur.fetchone()
        new_id = row[0] if row else None

    return {"success": True, "id": new_id, "solicitation_id": solicitation_id}


@router.get("/search")
def search_tenders(q: str = "", limit: int = 20):
    """Search tenders by name/ID for the tracker dropdown."""
    if not q or len(q) < 2:
        return {"data": []}
    rows = query("""
        SELECT id, solicitation_id, name, source_portal, end_client,
               rfp_category, closing_date, status
        FROM tenders
        WHERE name ILIKE %s OR solicitation_id ILIKE %s OR end_client ILIKE %s
        ORDER BY first_seen DESC
        LIMIT %s
    """, [f"%{q}%", f"%{q}%", f"%{q}%", limit])
    return {"data": rows}


@router.get("/options/filters")
def filter_options():
    portals   = query("SELECT DISTINCT source_portal FROM tenders WHERE source_portal IS NOT NULL ORDER BY 1")
    offices   = query("SELECT DISTINCT office FROM tenders WHERE office IS NOT NULL AND office != '' ORDER BY 1")
    sectors   = query("SELECT DISTINCT sector FROM tenders WHERE sector IS NOT NULL AND sector != '' ORDER BY 1")
    categories = query("SELECT DISTINCT rfp_category FROM tenders WHERE rfp_category IS NOT NULL ORDER BY 1")
    return {
        "portals":    [r["source_portal"] for r in portals],
        "offices":    [r["office"] for r in offices],
        "sectors":    [r["sector"] for r in sectors],
        "categories": [r["rfp_category"] for r in categories],
    }


@router.get("/{tender_id}")
def get_tender(tender_id: int):
    rows = query("SELECT * FROM tenders WHERE id = %s", [tender_id])
    if not rows:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Tender not found")
    row = rows[0]
    for key in ["closing_date", "first_seen", "questions_deadline"]:
        if row.get(key):
            row[key] = row[key].isoformat()
    return row
