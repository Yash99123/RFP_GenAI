from fastapi import APIRouter
from database import query

router = APIRouter()

@router.get("/summary")
def get_summary():
    total        = query("SELECT COUNT(*) as n FROM tenders")[0]["n"]
    today        = query("SELECT COUNT(*) as n FROM tenders WHERE first_seen::date = CURRENT_DATE")[0]["n"]
    this_week    = query("SELECT COUNT(*) as n FROM tenders WHERE first_seen >= NOW() - INTERVAL '7 days'")[0]["n"]

    by_portal = query("""
        SELECT source_portal, COUNT(*) as count
        FROM tenders
        WHERE first_seen >= NOW() - INTERVAL '7 days'
        GROUP BY source_portal ORDER BY count DESC
    """)

    by_category = query("""
        SELECT rfp_category, COUNT(*) as count
        FROM tenders
        WHERE first_seen >= NOW() - INTERVAL '7 days' AND rfp_category IS NOT NULL
        GROUP BY rfp_category ORDER BY count DESC
    """)

    categories = query("SELECT COUNT(DISTINCT rfp_category) as n FROM tenders WHERE rfp_category IS NOT NULL")[0]["n"]

    last_run = query("SELECT run_at, total_scraped, new_after_dedup FROM pipeline_runs ORDER BY run_at DESC LIMIT 1")
    if last_run:
        lr = last_run[0]
        if lr.get("run_at"):
            lr["run_at"] = lr["run_at"].isoformat()

    return {
        "total_all_time":  total,
        "new_today":       today,
        "new_this_week":   this_week,
        "categories":      categories,
        "by_portal":       by_portal,
        "by_category":     by_category,
        "last_run":        last_run[0] if last_run else None,
    }
