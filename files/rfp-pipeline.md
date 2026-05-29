---
name: rfp-pipeline
description: Master orchestration skill for EITACIES RFP GenAI pipeline. Coordinates all scrapers across 50+ portals, parses, scores, deduplicates, queues for CRM sync, and delivers the weekly Excel report.
version: 1.0.0
metadata:
  hermes:
    tags: [eitacies, rfp, genai, automation, orchestration]
    category: automation
    requires_toolsets: [terminal, web, file_system]
---

# RFP GenAI Pipeline — Master Orchestration (EITACIES)

## When to Use
- Running the full weekly pipeline (cron-triggered or manually)
- User says "run pipeline", "scrape RFPs", or "run rfp-pipeline"

## Pipeline Overview
```
[SAM.gov]  [SAP Ariba / JAGGAER]  [Bonfire / OpenGov]  [State Portals]  [Aggregators]
                            ↓
              [rfp-schema: parse + normalise all records]
                            ↓
              [rfp-score-filter: score, flag, exclude]
                            ↓
               [dedup against PostgreSQL seen_ids]
                            ↓
                [crm-sync-queue: queue for CRM]
                            ↓
                  [rfp-report: weekly Excel]
```

## Portal Groups (run in parallel)
### Group A — Federal (highest priority)
- /scrape-sam-gov
- /scrape-sap-ariba-jaggaer

### Group B — State procurement
- /scrape-state-portals

### Group C — City portals
- /scrape-city-portals

### Group D — Aggregators
- /scrape-aggregators

### Group E — Education / Niche
- /scrape-education-niche

## Execution Order

### Step 1 — Pre-flight checks
```bash
[ -z "$OPENROUTER_API_KEY" ] && echo "MISSING: OPENROUTER_API_KEY" && exit 1
[ -z "$DATABASE_URL" ]       && echo "MISSING: DATABASE_URL"       && exit 1
[ -z "$FIRECRAWL_API_KEY" ]  && echo "MISSING: FIRECRAWL_API_KEY"  && exit 1
echo "All required env vars present."
```

### Step 2 — Run all 5 scraper groups in parallel
Each saves to: `~/RFP_GenAI/exports/raw/[group]_YYYY-MM-DD.json`
Wait for all 5 to complete before proceeding.

### Step 3 — Parse and normalise
Load `/rfp-schema`.
Combine all raw JSON files into a single normalised array.
Save to: `~/RFP_GenAI/exports/parsed/rfps_normalised_YYYY-MM-DD.json`

### Step 4 — Score, filter, deduplicate
Load `/rfp-score-filter`.
Apply scoring, exclusions, red flags.
Dedup against PostgreSQL `seen_ids`.
Save to: `~/RFP_GenAI/exports/parsed/rfps_new_YYYY-MM-DD.json`

### Step 5 — Queue for CRM
No CRM key yet — queue all records to:
`~/RFP_GenAI/exports/queue/crm_pending.json`

```python
import json, os
from datetime import datetime

queue_path = os.path.expanduser(
    "/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/exports/queue/crm_pending.json"
)
os.makedirs(os.path.dirname(queue_path), exist_ok=True)

existing = []
if os.path.exists(queue_path):
    with open(queue_path) as f:
        existing = json.load(f)

today = datetime.utcnow().strftime("%Y-%m-%d")
new_path = f"/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/exports/parsed/rfps_new_{today}.json"
with open(new_path) as f:
    new_records = json.load(f)

for r in new_records:
    r["_queued_at"] = datetime.utcnow().isoformat()
    r["_crm_synced"] = False

combined = existing + new_records
with open(queue_path, "w") as f:
    json.dump(combined, f, indent=2)

print(f"Queued {len(new_records)} records. Total pending: {len(combined)}")
```

### Step 6 — Weekly report (Sundays only)
Load `/rfp-report`.

### Step 7 — Pipeline summary to Slack/Telegram
```
✅ RFP GenAI Pipeline Complete — [DATE]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Federal (SAM.gov / Ariba):  XX
State portals:               XX
City portals:                XX
Aggregators:                 XX
Education / Niche:           XX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total new:                   XX
Hard excluded:               XX
Flagged:                     XX
CRM queue total:             XX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Next run: Monday [DATE] 6:00 AM ET
```

## Error Handling
- If a portal group fails: log and continue with remaining groups
- Never abort pipeline for a single portal failure
- Always log error details to ~/RFP_GenAI/exports/logs/

## Cron Schedules
- Main pipeline:  Monday 6:00 AM ET  → cron: 0 6 * * 1
- Weekly report:  Sunday 5:00 PM ET  → cron: 0 17 * * 0
- Hot alerts:     Daily 8:00 AM ET   → cron: 0 8 * * *
