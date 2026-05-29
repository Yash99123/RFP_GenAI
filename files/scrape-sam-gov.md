---
name: scrape-sam-gov
description: Scrapes SAM.gov (System for Award Management) — the primary US federal procurement portal. Uses authenticated login for full access, then searches EITACIES-relevant keywords. Falls back to SAM.gov public API for bulk queries.
version: 1.0.0
metadata:
  hermes:
    tags: [eitacies, rfp, sam.gov, federal, scraping]
    category: automation
    requires_toolsets: [terminal, web, file_system]
---

# SAM.gov Scraper

## Output
`~/RFP_GenAI/exports/raw/sam_gov_YYYY-MM-DD.json`

## Credentials
```
SAM_GOV_USERNAME=bdm@eitacies.com
SAM_GOV_PASSWORD=Eita567890$%
```

---

## Path A — SAM.gov Public API (Preferred, no login needed)

SAM.gov provides a free public API for opportunity search.

```python
import requests, json, os
from datetime import datetime, timedelta

API_KEY = os.environ.get("SAM_GOV_API_KEY", "")  # optional — public endpoint works without key
BASE = "https://api.sam.gov/opportunities/v2/search"

KEYWORDS = [
    "artificial intelligence", "machine learning", "AI services",
    "natural language processing", "generative AI", "LLM",
    "robotic process automation", "data science", "predictive analytics",
    "digital transformation", "software development", "cloud services",
    "cybersecurity", "IT modernization", "business intelligence"
]

date_from = (datetime.utcnow() - timedelta(days=7)).strftime("%m/%d/%Y")
all_results = []
seen = set()

for kw in KEYWORDS:
    params = {
        "limit": 100,
        "offset": 0,
        "postedFrom": date_from,
        "ptype": "o,k,r,s",   # o=solicitation, k=combined, r=sources sought, s=special notice
        "q": kw,
        "status": "active",
    }
    if API_KEY:
        params["api_key"] = API_KEY

    resp = requests.get(BASE, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"SAM.gov API error {resp.status_code} for '{kw}'")
        continue

    data = resp.json()
    opps = data.get("opportunitiesData", [])

    for opp in opps:
        uid = opp.get("noticeId", "")
        if uid in seen:
            continue
        seen.add(uid)

        all_results.append({
            "rfp_id":     uid,
            "title":      opp.get("title", ""),
            "agency":     opp.get("fullParentPathName", opp.get("departmentName", "")),
            "portal":     "SAM.gov",
            "due_date":   opp.get("responseDeadLine", ""),
            "posted_date": opp.get("postedDate", ""),
            "naics_code": opp.get("naicsCode", ""),
            "set_aside":  opp.get("typeOfSetAside", ""),
            "state":      opp.get("placeOfPerformance", {}).get("state", {}).get("code", ""),
            "city":       opp.get("placeOfPerformance", {}).get("city", {}).get("name", ""),
            "details_url": f"https://sam.gov/opp/{uid}/view",
            "contract_value_text": opp.get("award", {}).get("amount", ""),
            "description": opp.get("description", "")[:500],
            "contact_email": opp.get("pointOfContact", [{}])[0].get("email", ""),
            "contact_name":  opp.get("pointOfContact", [{}])[0].get("fullName", ""),
            "keyword_matched": kw,
            "raw_type": opp.get("type", ""),
        })

    print(f"SAM.gov '{kw}': {len(all_results)} total so far")

output_path = f"/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/exports/raw/sam_gov_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    json.dump(all_results, f, indent=2)

print(f"SAM.gov: Saved {len(all_results)} records")
```

---

## Path B — Playwright Authenticated Login (Fallback)

```python
from playwright.async_api import async_playwright
import asyncio, os

async def scrape_sam_gov_browser():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://sam.gov/login")
        await page.wait_for_load_state("networkidle")

        await page.fill('input[name="email"], #email', os.environ["SAM_GOV_USERNAME"])
        await page.fill('input[type="password"]', os.environ["SAM_GOV_PASSWORD"])
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")

        # Navigate to opportunities search
        await page.goto("https://sam.gov/search/?index=opp&q=artificial+intelligence&sort=-relevance&dateRange=custom&startDate=&endDate=&status=Open")
        await page.wait_for_selector(".opportunity-result", timeout=15000)

        results = []
        # Extract search results
        cards = await page.query_selector_all(".opportunity-result, .sam-result-card")
        for card in cards:
            title_el = await card.query_selector("h3, .result-title, .opp-title")
            agency_el = await card.query_selector(".agency-name, .department")
            due_el = await card.query_selector(".response-date, .due-date")
            link_el = await card.query_selector("a")

            title = await title_el.inner_text() if title_el else ""
            href = await link_el.get_attribute("href") if link_el else ""
            results.append({
                "title":      title,
                "agency":     await agency_el.inner_text() if agency_el else "",
                "due_date":   await due_el.inner_text() if due_el else "",
                "details_url": f"https://sam.gov{href}" if href else "",
                "portal":     "SAM.gov",
            })

        await browser.close()
        return results
```

## Pitfalls
- SAM.gov API is free and reliable — always try it first
- The public API `responseDeadLine` field uses ISO 8601 format — no conversion needed
- For NAICS filtering, EITACIES relevant codes: 541511, 541512, 541519, 541715, 518210
- API may return up to 1,000 results per keyword — always paginate with `offset` if count > 100
- SAM.gov login uses OKTA SSO — Playwright may hit a Captcha on repeated attempts
