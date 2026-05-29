---
name: scrape-sap-ariba-jaggaer
description: Scrapes all JAGGAER-platform portals for EITACIES. Covers SAP Ariba, JAGGAER Supplier Network, Montana Gov JAGGAER, Montana EMACS, JAGGAER Minnesota, University of Minnesota, University of Iowa, and EMACS. All use the same Playwright login pattern since they share the JAGGAER platform.
version: 1.0.0
metadata:
  hermes:
    tags: [eitacies, rfp, jaggaer, ariba, scraping]
    category: automation
    requires_toolsets: [terminal, web, file_system]
---

# SAP Ariba + JAGGAER Group Scraper

## Output
`~/RFP_GenAI/exports/raw/jaggaer_group_YYYY-MM-DD.json`

## Portals Covered
All use JAGGAER platform — same scraping logic, different base URLs and credentials.

| Portal | Base URL | Username Env | Password Env |
|---|---|---|---|
| SAP Ariba | supplier.ariba.com | SAP_ARIBA_USERNAME | SAP_ARIBA_PASSWORD |
| JAGGAER Supplier | supplier.jaggaer.com | JAGGAER_SUPPLIER_USERNAME | JAGGAER_SUPPLIER_PASSWORD |
| Montana JAGGAER | mt.jaggaer.com | MONTANA_GOV_JAGGAER_USERNAME | MONTANA_GOV_JAGGAER_PASSWORD |
| Montana EMACS | emacs.mt.gov | MONTANA_EMACS_USERNAME | MONTANA_EMACS_PASSWORD |
| JAGGAER Minnesota | mn.jaggaer.com | JAGGAER_MINNESOTA_USERNAME | JAGGAER_MINNESOTA_PASSWORD |
| University of Minnesota | umn.jaggaer.com | UNIVERSITY_OF_MINNESOTA_USERNAME | UNIVERSITY_OF_MINNESOTA_PASSWORD |
| University of Iowa | uiowa.edu/purchasing | UNIVERSITY_OF_IOWA_USERNAME | UNIVERSITY_OF_IOWA_PASSWORD |
| EMACS | emacs.mt.gov | EMACS_USERNAME | EMACS_PASSWORD |

---

## JAGGAER Platform Scraper (reusable for all portals)

```python
from playwright.async_api import async_playwright
import asyncio, os, json
from datetime import datetime

JAGGAER_PORTALS = [
    {
        "name": "SAP Ariba",
        "login_url": "https://supplier.ariba.com",
        "search_url": "https://supplier.ariba.com/ad/ng/ariba-sourcing/rfx/list",
        "username": os.environ.get("SAP_ARIBA_USERNAME"),
        "password": os.environ.get("SAP_ARIBA_PASSWORD"),
    },
    {
        "name": "JAGGAER Supplier",
        "login_url": "https://supplier.jaggaer.com/web/login",
        "search_url": "https://supplier.jaggaer.com/web/rfp/public",
        "username": os.environ.get("JAGGAER_SUPPLIER_USERNAME"),
        "password": os.environ.get("JAGGAER_SUPPLIER_PASSWORD"),
    },
    {
        "name": "Montana JAGGAER",
        "login_url": "https://mt.jaggaer.com/web/login",
        "search_url": "https://mt.jaggaer.com/web/rfp/public",
        "username": os.environ.get("MONTANA_GOV_JAGGAER_USERNAME"),
        "password": os.environ.get("MONTANA_GOV_JAGGAER_PASSWORD"),
    },
    {
        "name": "JAGGAER Minnesota",
        "login_url": "https://mn.jaggaer.com/web/login",
        "search_url": "https://mn.jaggaer.com/web/rfp/public",
        "username": os.environ.get("JAGGAER_MINNESOTA_USERNAME"),
        "password": os.environ.get("JAGGAER_MINNESOTA_PASSWORD"),
    },
    {
        "name": "University of Minnesota",
        "login_url": "https://umn.jaggaer.com/web/login",
        "search_url": "https://umn.jaggaer.com/web/rfp/public",
        "username": os.environ.get("UNIVERSITY_OF_MINNESOTA_USERNAME"),
        "password": os.environ.get("UNIVERSITY_OF_MINNESOTA_PASSWORD"),
    },
]

EITACIES_KEYWORDS = [
    "artificial intelligence", "machine learning", "software",
    "IT services", "cloud", "data analytics", "cybersecurity",
    "digital transformation", "consulting", "technology"
]

async def scrape_jaggaer_portal(page, portal):
    results = []
    try:
        # Login
        await page.goto(portal["login_url"], timeout=30000)
        await page.wait_for_load_state("networkidle")

        await page.fill(
            'input[type="email"], input[name="username"], #username, input[name="email"]',
            portal["username"]
        )
        await page.fill('input[type="password"]', portal["password"])
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=15000)

        if "login" in page.url.lower() or "error" in page.url.lower():
            print(f"  WARNING: {portal['name']} login may have failed — {page.url}")

        # Search each keyword
        for kw in EITACIES_KEYWORDS:
            try:
                await page.goto(portal["search_url"] + f"?q={kw.replace(' ', '+')}")
                await page.wait_for_load_state("networkidle", timeout=10000)

                # Generic JAGGAER result extraction
                rows = await page.query_selector_all(
                    ".rfx-row, .sourcing-row, tr.rfp-item, .event-row, [data-rfx-id]"
                )
                for row in rows:
                    try:
                        title_el = await row.query_selector(".title, .rfx-title, td:first-child a")
                        due_el   = await row.query_selector(".due-date, .close-date, td.date")
                        link_el  = await row.query_selector("a")

                        title = (await title_el.inner_text()).strip() if title_el else ""
                        if not title:
                            continue

                        href = await link_el.get_attribute("href") if link_el else ""
                        full_url = (portal["login_url"] + href) if href and not href.startswith("http") else href

                        rfp_id = await row.get_attribute("data-rfx-id") or \
                                 await row.get_attribute("data-id") or \
                                 f"{portal['name'].replace(' ','-')}-{datetime.utcnow().strftime('%Y%m%d')}-{title[:15].replace(' ','-')}"

                        results.append({
                            "rfp_id":     rfp_id,
                            "title":      title,
                            "agency":     portal["name"],
                            "portal":     portal["name"],
                            "due_date":   (await due_el.inner_text()).strip() if due_el else "",
                            "details_url": full_url,
                            "keyword_matched": kw,
                        })
                    except Exception:
                        continue

            except Exception as e:
                print(f"  {portal['name']} keyword '{kw}' failed: {e}")
                continue

    except Exception as e:
        print(f"  ERROR scraping {portal['name']}: {e}")

    print(f"  {portal['name']}: {len(results)} RFPs found")
    return results


async def run_all_jaggaer():
    all_results = []
    async with async_playwright() as p:
        for portal in JAGGAER_PORTALS:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
            print(f"Scraping {portal['name']}...")
            results = await scrape_jaggaer_portal(page, portal)
            all_results.extend(results)
            await browser.close()

    today = datetime.utcnow().strftime("%Y-%m-%d")
    output_path = f"/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/exports/raw/jaggaer_group_{today}.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nJAGGAER group: Saved {len(all_results)} total records")

asyncio.run(run_all_jaggaer())
```

---

## University of Iowa (different platform)
```python
# University of Iowa uses its own purchasing portal, not standard JAGGAER
# URL: https://pur.uiowa.edu/rfp-bid-notices
# No login required for public listings

async def scrape_university_iowa():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://pur.uiowa.edu/rfp-bid-notices")
        await page.wait_for_load_state("networkidle")

        rows = await page.query_selector_all("table tbody tr, .view-content .views-row")
        results = []
        for row in rows:
            try:
                title_el = await row.query_selector("a, .title")
                date_el  = await row.query_selector(".date, td:nth-child(2)")
                link_el  = await row.query_selector("a")

                title = (await title_el.inner_text()).strip() if title_el else ""
                href  = await link_el.get_attribute("href") if link_el else ""

                results.append({
                    "rfp_id":      f"UIOWA-{datetime.utcnow().strftime('%Y%m%d')}-{title[:15].replace(' ','-')}",
                    "title":       title,
                    "agency":      "University of Iowa",
                    "portal":      "University of Iowa",
                    "due_date":    (await date_el.inner_text()).strip() if date_el else "",
                    "details_url": f"https://pur.uiowa.edu{href}" if href and not href.startswith("http") else href,
                })
            except Exception:
                continue

        await browser.close()
        return results
```

## Pitfalls
- SAP Ariba may require SSO/SAML — if login fails, use the Ariba Discovery public search instead
- JAGGAER portals share a UI pattern but URLs differ per state — always use the correct login_url
- Rate-limit between portals: wait 3 seconds between each portal to avoid IP blocks
- Session cookies expire after ~30 min — run scrapers sequentially, not parallel
