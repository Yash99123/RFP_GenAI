---
name: rfp-score-filter
description: Scores, flags, and filters normalised RFP records for EITACIES. Applies AI/technology relevance scoring (0-100), hard exclusions, red flag detection, and tier assignment. Tuned for EITACIES's core competencies in AI, machine learning, software development, and IT consulting.
version: 1.0.0
metadata:
  hermes:
    tags: [eitacies, rfp, scoring, filtering]
    category: automation
---

# RFP Score + Filter — EITACIES

## When to Use
Called by `rfp-pipeline` at Step 4, after `rfp-schema` normalisation.

---

## Step 1 — Hard Exclusions (Remove Immediately)

```python
HARD_EXCLUDE = [
    # Physical / construction
    "construction", "infrastructure", "road", "bridge", "building",
    "maintenance", "landscaping", "janitorial", "cleaning", "facilities",
    "plumbing", "electrical contractor", "hvac", "civil engineering",
    # Supplies / commodities
    "food service", "catering", "furniture", "uniforms", "printing",
    "office supplies", "medical supplies", "pharmaceutical",
    # Highly specialised non-tech
    "legal services", "audit", "actuarial", "insurance brokerage",
    "architecture", "engineering design", "surveying",
    # Low-value services
    "pest control", "security guard", "waste management", "recycling",
    "moving services", "towing", "taxi",
]

def is_hard_excluded(record):
    text = f"{record.get('title','')} {record.get('description','')}".lower()
    for kw in HARD_EXCLUDE:
        if kw in text:
            record["_exclude"] = True
            record["_flags"] = record.get("_flags", []) + [f"HARD_EXCLUDED: {kw}"]
            return True
    return False
```

---

## Step 2 — Relevance Scoring (0–100)

```python
# Primary AI/ML keywords — highest value for EITACIES
AI_PRIMARY = {
    "artificial intelligence": 20, "machine learning": 20, "deep learning": 18,
    "generative ai": 18, "large language model": 17, "llm": 16, "nlp": 15,
    "natural language processing": 15, "computer vision": 14,
    "predictive analytics": 13, "ai": 12, "neural network": 12,
    "robotic process automation": 12, "rpa": 11,
}

# Secondary tech keywords
TECH_SECONDARY = {
    "software development": 10, "cloud computing": 9, "saas": 9,
    "digital transformation": 9, "data science": 9, "data analytics": 8,
    "cybersecurity": 8, "api integration": 8, "automation": 7,
    "business intelligence": 7, "cloud services": 7, "it modernization": 7,
    "it modernisation": 7, "platform": 6, "enterprise software": 6,
}

# Tertiary — general IT services
IT_TERTIARY = {
    "it services": 5, "technology consulting": 5, "consulting": 4,
    "managed services": 4, "professional services": 4, "helpdesk": 3,
    "technical support": 3, "training": 3, "software": 3,
}

# NAICS codes EITACIES is qualified for
RELEVANT_NAICS = {
    "541511": 15,  # Custom Computer Programming
    "541512": 15,  # Computer Systems Design
    "541519": 12,  # Other Computer Services
    "541715": 12,  # R&D in Physical/Engineering Sciences
    "518210": 10,  # Data Processing and Hosting
    "541613": 8,   # Marketing Consulting
    "611420": 5,   # Computer Training
}

def calculate_score(record):
    score = 0
    text = f"{record.get('title','')} {record.get('description','')}".lower()

    # Primary AI/ML keywords (cap at 40)
    ai_score = sum(v for k, v in AI_PRIMARY.items() if k in text)
    score += min(ai_score, 40)

    # Secondary tech keywords (cap at 20)
    tech_score = sum(v for k, v in TECH_SECONDARY.items() if k in text)
    score += min(tech_score, 20)

    # Tertiary IT keywords (cap at 10)
    it_score = sum(v for k, v in IT_TERTIARY.items() if k in text)
    score += min(it_score, 10)

    # NAICS code bonus
    naics = record.get("naics_code", "") or ""
    for code, points in RELEVANT_NAICS.items():
        if naics.startswith(code[:4]):
            score += points
            record["_flags"] = record.get("_flags", []) + [f"NAICS_MATCH: {naics}"]
            break

    # Set-aside bonus (small business preference = easier win)
    set_aside = record.get("set_aside", "") or ""
    if "small business" in set_aside.lower():
        score += 8
    elif "8(a)" in set_aside:
        score += 5

    # Federal/SAM.gov bonus (higher contract values)
    if record.get("portal") == "SAM.gov":
        score += 5

    # Red flag penalties
    score -= len(record.get("_red_flags", [])) * 8

    record["_score"] = max(0, min(100, score))
    record["keywords_matched"] = [k for k in {**AI_PRIMARY, **TECH_SECONDARY, **IT_TERTIARY} if k in text]
    return record["_score"]
```

---

## Step 3 — Red Flag Detection

```python
import re

def detect_red_flags(record):
    red_flags = []
    text = f"{record.get('title','')} {record.get('description','')} {record.get('evaluation_criteria','')}".lower()

    # Red Flag 1: Incumbent language (existing vendor preferred)
    if any(x in text for x in ["incumbent", "existing vendor", "current contractor", "sole source"]):
        red_flags.append("INCUMBENT_LIKELY: existing vendor mentioned")

    # Red Flag 2: Very short notice (< 5 business days)
    if record.get("due_date") and record.get("posted_date"):
        try:
            import numpy as np
            from datetime import datetime
            posted = datetime.strptime(record["posted_date"][:10], "%Y-%m-%d")
            due    = datetime.strptime(record["due_date"][:10], "%Y-%m-%d")
            bdays  = int(np.busday_count(posted.date(), due.date()))
            if bdays < 5:
                red_flags.append(f"SHORT_NOTICE: only {bdays} business days")
        except Exception:
            pass

    # Red Flag 3: Requires physical presence / on-site only
    if any(x in text for x in ["on-site only", "on-premises only", "no remote", "in-person only"]):
        red_flags.append("ONSITE_ONLY: remote work not permitted")

    # Red Flag 4: Requires specific certifications EITACIES may not have
    certs_required = ["cmmi level", "iso 9001", "fedramp authorized", "top secret clearance"]
    for cert in certs_required:
        if cert in text:
            red_flags.append(f"CERT_REQUIRED: {cert}")

    # Red Flag 5: Price-based evaluation only (no technical scoring)
    if re.search(r'price.*100%|lowest.*bid.*only|low bid.*award', text):
        red_flags.append("PRICE_ONLY: awarded on lowest price only")

    record["_red_flags"] = red_flags
    return red_flags
```

---

## Step 4 — Tier Assignment

```python
def assign_tier(record):
    score = record.get("_score", 0)
    if score >= 65:
        record["_tier"] = "Tier 1 - Pursue"
    elif score >= 45:
        record["_tier"] = "Tier 2 - Prospect"
    elif score >= 25:
        record["_tier"] = "Tier 3 - Monitor"
    else:
        record["_tier"] = "Tier 4 - Skip"
```

---

## Step 5 — Dedup Against PostgreSQL

```python
import psycopg2, os

def dedup(records):
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur  = conn.cursor()
    new  = []
    for r in records:
        cur.execute("SELECT 1 FROM seen_ids WHERE solicitation_id = %s", (r["rfp_id"],))
        if cur.fetchone():
            continue
        new.append(r)
        cur.execute(
            "INSERT INTO seen_ids (solicitation_id, source, first_seen) VALUES (%s,%s,NOW())",
            (r["rfp_id"], r.get("portal",""))
        )
    conn.commit(); cur.close(); conn.close()
    print(f"After dedup: {len(new)} new (skipped {len(records)-len(new)} duplicates)")
    return new
```

---

## Full Pipeline Runner

```python
import json, os
from datetime import datetime

today = datetime.utcnow().strftime("%Y-%m-%d")
BASE  = "/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI"
input_path  = f"{BASE}/exports/parsed/rfps_normalised_{today}.json"
output_path = f"{BASE}/exports/parsed/rfps_new_{today}.json"

with open(input_path) as f:
    records = json.load(f)

processed = []
for r in records:
    if is_hard_excluded(r):
        continue
    detect_red_flags(r)
    calculate_score(r)
    assign_tier(r)
    processed.append(r)

new_records = dedup(processed)
new_records.sort(key=lambda x: x["_score"], reverse=True)

os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    json.dump(new_records, f, indent=2)

print(f"Scored {len(new_records)} new RFPs. Top score: {new_records[0]['_score'] if new_records else 0}")
```
