---
name: scrape-state-portals
description: Scrapes US state government procurement portals for EITACIES. Covers CAL eProcure, MyFlorida, PRISM, Florida ProRFX, Louisiana LaGov, CommBuys (Massachusetts), Vermont Procurement, and SupplierClearinghouse.
version: 1.0.0
metadata:
  hermes:
    tags: [eitacies, rfp, state, government, scraping]
    category: automation
    requires_toolsets: [terminal, web, file_system]
---

# State Procurement Portals Scraper

## Output
`~/RFP_GenAI/exports/raw/state_portals_YYYY-MM-DD.json`

## Portals Covered

| Portal | URL | Login Env | State |
|---|---|---|---|
| CAL eProcure | caleprocure.ca.gov | CAL_E_PROCURE_USERNAME | CA |
| MyFlorida | myfloridamarketplace.myflorida.com | MYFLORIDA_USERNAME | FL |
| PRISM | prism.florida.com | PRISM_USERNAME | FL |
| Florida ProRFX | prorfx.com | FLORIDA_PRORFX_USERNAME | FL |
| Louisiana LaGov | wwwcfprd.doa.louisiana.gov | STATE_OF_LOUISIANA_LAGOV_USERNAME | LA |
| CommBuys | commbuys.com | COMMBUYS_USERNAME | MA |
| Vermont Procurement | bgs.vermont.gov/purchasing | VERMONT_DEPARTMENT_USERNAME | VT |
| SupplierClearinghouse | clearinghouse.cdfa.ca.gov | SUPPLIERCLEARINGHOUSE_USERNAME | CA |

---

## Scraper Template (Playwright — works for all state portals)

```python
from playwright.async_api import async_playwright
import asyncio, os, json, re
from datetime import datetime, timedelta

EITACIES_KEYWORDS = [
    "artificial intelligence", "machine learning", "software development",
    "IT services", "cloud computing", "cybersecurity", "data analytics",
    "digital transformation", "consulting", "technology services"
]

STATE_PORTALS = [
    {
        "name": "CAL eProcure",
        "state": "CA",
        "login_url": "https://caleprocure.ca.gov/pages/LandingPage/landing-page.aspx",
        "search_url": "https://caleprocure.ca.gov/pages/Events/event-search.aspx",
        "username": os.environ.get("CAL_E_PROCURE_USERNAME"),
        "password": os.environ.get("CAL_E_PROCURE_PASSWORD"),
        "public": True,  # CAL eProcure has public search — login not always required
    },
    {
        "name": "MyFlorida",
        "state": "FL",
        "login_url": "https://www.myfloridamarketplace.com/mfmp/",
        "search_url": "https://www.myfloridamarketplace.com/mfmp/main/publish/searchAds.do",
        "username": os.environ.get("MYFLORIDA_USERNAME"),
        "password": os.environ.get("MYFLORIDA_PASSWORD"),
        "public": True,
    },
    {
        "name": "Louisiana LaGov",
        "state": "LA",
        "login_url": "https://wwwcfprd.doa.louisiana.gov/osp/lapac/dspVendorLogin.cfm",
        "search_url": "https://wwwcfprd.doa.louisiana.gov/osp/lapac/vendor.cfm",
        "username": os.environ.get("STATE_OF_LOUISIANA_LAGOV_USERNAME"),  # V31027852201
        "password": os.environ.get("STATE_OF_LOUISIANA_LAGOV_PASSWORD"),
        "public": False,
    },
    {
        "name": "CommBuys",
        "state": "MA",
        "login_url": "https://www.commbuys.com/bso/",
        "search_url": "https://www.commbuys.com/bso/external/publicBids.sdo",
        "username": os.environ.get("COMMBUYS_USERNAME"),
        "password": os.environ.get("COMMBUYS_PASSWORD"),
        "public": True,
    },
    {
        "name": "Vermont Procurement",
        "state": "VT",
        "login_url": "https://bgs.vermont.gov/purchasing/vendors",
        "search_url": "https://bgs.vermont.gov/purchasing/bids",
        "username": os.environ.get("VERMONT_DEPARTMENT_USERNAME"),
        "password": os.environ.get("VERMONT_DEPARTMENT_PASSWORD"),
        "public": True,
    },
    {
        "name": "SupplierClearinghouse",
        "state": "CA",
        "login_url": "https://clearinghouse.cdfa.ca.gov/login",
        "search_url": "https://clearinghouse.cdfa.ca.gov/bids",
        "username": os.environ.get("SUPPLIERCLEARINGHOUSE_USERNAME"),
        "password": os.environ.get("SUPPLIERCLEARINGHOUSE_PASSWORD"),
        "public": False,
    },
]


async def scrape_state_portal(portal):
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        try:
            # Login if required
            if not portal.get("public", True):
                await page.goto(portal["login_url"], timeout=20000)
                await page.wait_for_load_state("networkidle")
                await page.fill(
                    'input[type="text"], input[name="username"], input[name="userId"], #username',
                    portal["username"]
                )
                await page.fill('input[type="password"]', portal["password"])
                await page.click('button[type="submit"], input[type="submit"], input[value="Login"]')
                await page.wait_for_load_state("networkidle", timeout=10000)
                print(f"  {portal['name']}: logged in")

            # Search each keyword
            for kw in EITACIES_KEYWORDS:
                try:
                    await page.goto(portal["search_url"], timeout=15000)
                    await page.wait_for_load_state("networkidle")

                    # Try to find search input
                    search_input = await page.query_selector(
                        'input[type="search"], input[name="keyword"], input[name="description"], #keyword, .search-input'
                    )
                    if search_input:
                        await search_input.fill(kw)
                        await page.keyboard.press("Enter")
                        await page.wait_for_load_state("networkidle", timeout=8000)

                    # Extract results
                    result_rows = await page.query_selector_all(
                        "table tbody tr, .bid-row, .rfp-item, .solicitation-row, .result-item"
                    )
                    for row in result_rows:
                        try:
                            title_el = await row.query_selector("a, .title, td:first-child")
                            date_el  = await row.query_selector(".date, .due-date, td:nth-child(3)")
                            link_el  = await row.query_selector("a")

                            title = (await title_el.inner_text()).strip() if title_el else ""
                            if not title or len(title) < 5:
                                continue

                            href  = await link_el.get_attribute("href") if link_el else ""
                            base  = "/".join(portal["search_url"].split("/")[:3])
                            full_url = (base + href) if href and not href.startswith("http") else href

                            results.append({
                                "rfp_id":     f"{portal['state']}-{portal['name'].replace(' ','-')[:10]}-{datetime.utcnow().strftime('%Y%m%d')}-{re.sub(r'[^a-z0-9]', '-', title.lower())[:15]}",
                                "title":      title,
                                "agency":     portal["name"],
                                "portal":     portal["name"],
                                "state":      portal["state"],
                                "country":    "US",
                                "due_date":   (await date_el.inner_text()).strip() if date_el else "",
                                "details_url": full_url,
                                "keyword_matched": kw,
                            })
                        except Exception:
                            continue

                except Exception as e:
                    print(f"  {portal['name']} / '{kw}': {e}")
                    continue

        except Exception as e:
            print(f"  FAILED {portal['name']}: {e}")

        await browser.close()
    print(f"  {portal['name']}: {len(results)} RFPs")
    return results


async def run_all_state_portals():
    all_results = []
    for portal in STATE_PORTALS:
        print(f"Scraping {portal['name']}...")
        results = await scrape_state_portal(portal)
        all_results.extend(results)
        await asyncio.sleep(3)  # Rate limit between portals

    today = datetime.utcnow().strftime("%Y-%m-%d")
    output_path = f"/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/exports/raw/state_portals_{today}.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nState portals: Saved {len(all_results)} total records")

asyncio.run(run_all_state_portals())
```

## Pitfalls
- Louisiana LaGov uses "User ID" not email — the username is `V31027852201` (stored in env as-is)
- CAL eProcure and CommBuys have robust public search — login is optional for basic scraping
- Florida has 3 separate portals (MyFlorida, PRISM, ProRFX) — run all 3 independently
- Some state portals use CAPTCHA — if triggered, switch to Firecrawl for that portal
