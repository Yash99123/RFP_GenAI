---
name: rfp-report
description: Generates EITACIES weekly RFP Excel report. Aggregates all RFPs found during the week, formats them into a styled 3-sheet Excel file, and delivers to team channel. Runs every Sunday at 5PM ET.
version: 1.0.0
metadata:
  hermes:
    tags: [eitacies, rfp, report, excel, weekly]
    category: automation
    requires_toolsets: [terminal, file_system]
---

# RFP GenAI Weekly Report — EITACIES

## Output
`~/RFP_GenAI/exports/weekly/EITACIES_RFPs_Week_YYYY-WXX.xlsx`

## Step 1 — Pull This Week's Records from PostgreSQL

```python
import psycopg2, os, pandas as pd
from datetime import datetime

conn = psycopg2.connect(os.environ["DATABASE_URL"])
df = pd.read_sql("""
    SELECT
        rfp_id, title, agency, portal, portal_category,
        due_date, posted_date, state, country,
        naics_code, set_aside, contract_type,
        contract_value, contract_value_text,
        category, details_url, description,
        contact_name, contact_email,
        score, tier, flags, red_flags, first_seen
    FROM tenders
    WHERE first_seen >= NOW() - INTERVAL '7 days'
    ORDER BY score DESC, due_date ASC
""", conn)
conn.close()
print(f"Loaded {len(df)} RFPs for weekly report")
```

## Step 2 — Generate Excel

```python
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import os

def generate_excel(df):
    wb = Workbook()

    # ── Sheet 1: All New RFPs ───────────────────────────────
    ws1 = wb.active
    ws1.title = "New RFPs This Week"

    header_fill = PatternFill("solid", fgColor="1A1A18")
    header_font = Font(color="FFFFFF", bold=True, size=10, name="Calibri")

    COLS = [
        ("Tier",          "tier",               12),
        ("Score",         "score",               8),
        ("Title",         "title",              48),
        ("Agency",        "agency",             28),
        ("Portal",        "portal",             18),
        ("State",         "state",               8),
        ("Category",      "category",           22),
        ("NAICS",         "naics_code",         10),
        ("Set-Aside",     "set_aside",          16),
        ("Due Date",      "due_date",           14),
        ("Contract Value","contract_value_text", 16),
        ("Contact Email", "contact_email",      26),
        ("URL",           "details_url",        40),
        ("Description",   "description",        55),
        ("Red Flags",     "red_flags",          30),
    ]

    TIER_COLORS = {
        "Tier 1 - Pursue":   "FF6600",
        "Tier 2 - Prospect": "FFCC00",
        "Tier 3 - Monitor":  "92D050",
        "Tier 4 - Skip":     "CCCCCC",
    }

    for ci, (header, _, width) in enumerate(COLS, 1):
        cell = ws1.cell(1, ci, header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws1.column_dimensions[get_column_letter(ci)].width = width
    ws1.row_dimensions[1].height = 28

    for ri, (_, row) in enumerate(df.iterrows(), 2):
        for ci, (_, field, _) in enumerate(COLS, 1):
            val = row.get(field, "")
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            cell = ws1.cell(ri, ci, val)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.font = Font(size=9, name="Calibri")

            if field == "tier" and val in TIER_COLORS:
                cell.fill = PatternFill("solid", fgColor=TIER_COLORS[val])
                cell.font = Font(bold=True, size=9, name="Calibri")
            if field == "details_url" and val:
                cell.hyperlink = str(val)
                cell.font = Font(color="0563C1", underline="single", size=9, name="Calibri")
            if field == "red_flags" and val:
                cell.fill = PatternFill("solid", fgColor="FFE6E6")
        ws1.row_dimensions[ri].height = 56

    ws1.freeze_panes = "A2"
    ws1.auto_filter.ref = ws1.dimensions

    # ── Sheet 2: Summary by Tier ──────────────────────────
    ws2 = wb.create_sheet("Summary")
    ws2["A1"] = f"EITACIES RFP Report — Week of {datetime.utcnow().strftime('%B %d, %Y')}"
    ws2["A1"].font = Font(bold=True, size=14, name="Calibri")

    summary = df.groupby("tier").agg(
        count=("rfp_id", "count"),
        avg_score=("score", "mean"),
        earliest_due=("due_date", "min")
    ).reset_index()

    for ci, hdr in enumerate(["Tier", "Count", "Avg Score", "Earliest Due"], 1):
        ws2.cell(3, ci, hdr).font = Font(bold=True, name="Calibri")
    for ri, (_, row) in enumerate(summary.iterrows(), 4):
        ws2.cell(ri, 1, row["tier"])
        ws2.cell(ri, 2, int(row["count"]))
        ws2.cell(ri, 3, round(float(row["avg_score"]), 1))
        ws2.cell(ri, 4, str(row["earliest_due"]))

    by_portal = df.groupby("portal")["rfp_id"].count().sort_values(ascending=False)
    ws2["A" + str(len(summary) + 6)] = "RFPs by Portal:"
    for i, (portal, count) in enumerate(by_portal.items()):
        r = len(summary) + 7 + i
        ws2.cell(r, 1, portal)
        ws2.cell(r, 2, int(count))

    # ── Sheet 3: Urgent (closing < 14 days) ──────────────
    ws3 = wb.create_sheet("Closing Soon")
    ws3["A1"] = "Closing Within 14 Days"
    ws3["A1"].font = Font(bold=True, size=12, color="CC0000", name="Calibri")

    urgent = df[pd.to_datetime(df["due_date"], errors="coerce") <=
                pd.Timestamp("today") + pd.Timedelta(days=14)].sort_values("due_date")

    urgent_cols = ["tier", "title", "agency", "portal", "due_date", "details_url"]
    for ci, col in enumerate(urgent_cols, 1):
        ws3.cell(2, ci, col.replace("_", " ").title()).font = Font(bold=True, name="Calibri")
    for ri, (_, row) in enumerate(urgent.iterrows(), 3):
        for ci, col in enumerate(urgent_cols, 1):
            ws3.cell(ri, ci, str(row.get(col, "")))

    # Save
    week_num = datetime.utcnow().strftime("%Y-W%V")
    path = f"/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/exports/weekly/EITACIES_RFPs_Week_{week_num}.xlsx"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    print(f"Report saved: {path}")
    return path
```

## Cron Schedule
```bash
hermes cron create "0 17 * * 0" \
  "Generate weekly EITACIES RFP Excel report, save to exports/weekly/, and send to team Slack" \
  --skill rfp-report \
  --name "rfp-weekly-report"
```
