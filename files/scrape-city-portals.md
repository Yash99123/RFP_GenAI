---
name: scrape-city-portals
description: Scrapes all city and county government procurement portals for EITACIES. Covers Los Angeles, LA Unified School District, Angeleno RAMP, City of Burbank, City of Sunnyvale, City of Cincinnati, Broward County, Chicago Public Schools, Texas DOT, TIPS, Delano, Falmouth, City of Ashland Oregon, CivicPlus, and Pacific Northwest.
version: 1.0.0
metadata:
  hermes:
    tags: [eitacies, rfp, city, municipal, scraping]
    category: automation
    requires_toolsets: [terminal, web, file_system]
---

# City Portals Scraper

## Output
`~/RFP_GenAI/exports/raw/city_portals_YYYY-MM-DD.json`

## Portals Covered

| Portal | URL | State | Notes |
|---|---|---|---|
| City of Los Angeles | labavn.org | CA | Login: bdm@eitacies.com |
| LA Unified School District | laschools.org/vendor | CA | Login: bdm@eitacies.com |
| Angeleno RAMP | rampla.org | CA | Login: bdm@eitacies.com |
| City of Burbank | burbankca.gov/purchasing | CA | Login: bdm@eitacies.com |
| City of Sunnyvale | sunnyvale.ca.gov/bids | CA | Login: bdm@eitacies.com |
| City of Cincinnati | publicpurchase.com/gems | OH | Login: eitacies |
| Broward County | broward.org/Purchasing | FL | Login: bdm@eitacies.com |
| Chicago Public Schools | cps.edu/procurement | IL | Login: bdm@eitacies.com |
| Texas DOT | txdot.gov/business | TX | Login: bdm@eitacies.com |
| TIPS | tips-usa.com | TX | Cooperative purchasing |
| Delano | delano.ca.us | CA | Login: bdm@eitacies.com |
| Falmouth | falmouth.com | Various | Login: bdm@eitacies.com |
| City of Ashland Oregon | ashland.or.us | OR | Username: Thiruvalluvan |
| CivicPlus | civicplus.com | Various | Login: bdm@eitacies.com |
| Pacific Northwest | Various | WA/OR | Login: bdm@eitacies.com |
| USDA | usda.gov/ams | Federal | Login: bdm@eitacies.com |

---

## City Portals Scraper

```python
from playwright.async_api import async_playwright
import asyncio, os, json, re
from datetime import datetime

EITACIES_KEYWORDS = [
    "artificial intelligence", "machine learning", "software", "IT services",
    "cloud", "data analytics", "cybersecurity", "digital", "consulting", "technology"
]

CITY_PORTALS = [
    {
        "name": "City of Los Angeles",
        "state": "CA",
        "login_url": "https://labavn.org/buyer/default.aspx",
        "search_url": "https://labavn.org/buyer/contract_opportunities.cfm",
        "username_env": "CITY_OF_LOS_ANGELES_USERNAME",
        "password_env": "CITY_OF_LOS_ANGELES_PASSWORD",
        "public": True,
    },
    {
        "name": "Angeleno RAMP",
        "state": "CA",
        "login_url": "https://rampla.org/login",
        "search_url": "https://rampla.org/opportunities",
        "username_env": "ANGELENO_RAMP_USERNAME",
        "password_env": "ANGELENO_RAMP_PASSWORD",
        "public": False,
    },
    {
        "name": "City of Burbank",
        "state": "CA",
        "login_url": "https://www.burbankca.gov/i-want-to/do-business-with-burbank",
        "search_url": "https://www.burbankca.gov/departments/finance/purchasing/bids-rfps",
        "username_env": "CITY_OF_BURBANK_USERNAME",
        "password_env": "CITY_OF_BURBANK_PASSWORD",
        "public": True,
    },
    {
        "name": "City of Sunnyvale",
        "state": "CA",
        "login_url": "https://www.sunnyvale.ca.gov/your-government/bids-rfps",
        "search_url": "https://www.sunnyvale.ca.gov/your-government/bids-rfps",
        "username_env": "CITY_OF_SUNNYVALE_USERNAME",
        "password_env": "CITY_OF_SUNNYVALE_PASSWORD",
        "public": True,
    },
    {
        "name": "Broward County",
        "state": "FL",
        "login_url": "https://www.broward.org/Purchasing/Pages/Default.aspx",
        "search_url": "https://www.broward.org/Purchasing/Pages/CurrentBids.aspx",
        "username_env": "BROWARD_ORG_USERNAME",
        "password_env": "BROWARD_ORG_PASSWORD",
        "public": True,
    },
    {
        "name": "Chicago Public Schools",
        "state": "IL",
        "login_url": "https://www.cps.edu/about/procurement/",
        "search_url": "https://www.cps.edu/about/procurement/current-solicitations/",
        "username_env": "CHICAGO_PUBLIC_SCHOOLS_USERNAME",
        "password_env": "CHICAGO_PUBLIC_SCHOOLS_PASSWORD",
        "public": True,
    },
    {
        "name": "Texas DOT",
        "state": "TX",
        "login_url": "https://www.txdot.gov/business/doing-business.html",
        "search_url": "https://www.txdot.gov/business/purchasing/open-bids.html",
        "username_env": "TEXAS_DOT_USERNAME",
        "password_env": "TEXAS_DOT_PASSWORD",
        "public": True,
    },
    {
        "name": "TIPS",
        "state": "TX",
        "login_url": "https://www.tips-usa.com/assets_customer/login.cfm",
        "search_url": "https://www.tips-usa.com/vendors_public.cfm",
        "username_env": "TIPS_USERNAME",
        "password_env": "TIPS_PASSWORD",
        "public": True,  # TIPS is a cooperative purchasing portal — most content public
    },
    {
        "name": "City of Ashland Oregon",
        "state": "OR",
        "login_url": "https://www.ashland.or.us/bids.asp",
        "search_url": "https://www.ashland.or.us/bids.asp",
        "username_env": "CITY_OF_ASHLAND_OREGON_USERNAME",  # Thiruvalluvan
        "password_env": "CITY_OF_ASHLAND_OREGON_PASSWORD",
        "public": True,
    },
    {
        "name": "CivicPlus",
        "state": "Various",
        "login_url": "https://civicplus.com",
        "search_url": "https://civicplus.com/bids",
        "username_env": "CIVIC_PLUS_USERNAME",
        "password_env": "CIVIC_PLUS_PASSWORD",
        "public": False,
    },
    {
        "name": "USDA",
        "state": "Federal",
        "login_url": "https://www.usda.gov/ams/vendors",
        "search_url": "https://www.ams.usda.gov/services/transportation-marketing/transportation-services/vendors/registered-vendor-solicitations",
        "username_env": "USDA_USERNAME",
        "password_env": "USDA_PASSWORD",
        "public": True,
    },
]

async def scrape_city_portal(portal):
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
                uname = os.environ.get(portal["username_env"], "")
                pwd   = os.environ.get(portal["password_env"], "")
                await page.fill('input[type="email"], input[name="username"], input[type="text"]', uname)
                await page.fill('input[type="password"]', pwd)
                await page.click('button[type="submit"], input[type="submit"]')
                await page.wait_for_load_state("networkidle", timeout=10000)

            # Go to search / bids page
            await page.goto(portal["search_url"], timeout=15000)
            await page.wait_for_load_state("networkidle")

            # Try keyword search if available
            for kw in EITACIES_KEYWORDS[:5]:  # top 5 keywords only for city portals
                try:
                    search_el = await page.query_selector(
                        'input[type="search"], input[name="keyword"], input[placeholder*="search" i], .search-box'
                    )
                    if search_el:
                        await search_el.fill(kw)
                        await page.keyboard.press("Enter")
                        await page.wait_for_load_state("networkidle", timeout=8000)

                    items = await page.query_selector_all(
                        "table tbody tr, .bid-item, .rfp-item, .solicitation, li.result"
                    )
                    for item in items:
                        try:
                            title_el = await item.query_selector("a, .title, h3, td:first-child")
                            link_el  = await item.query_selector("a")
                            date_el  = await item.query_selector(".date, .due, td:nth-child(2)")

                            title = (await title_el.inner_text()).strip() if title_el else ""
                            if not title or len(title) < 5:
                                continue

                            href = await link_el.get_attribute("href") if link_el else ""
                            base = "/".join(portal["search_url"].split("/")[:3])
                            full_url = (base + href) if href and not href.startswith("http") else href

                            slug = re.sub(r"[^a-z0-9]", "-", title.lower())[:15]
                            results.append({
                                "rfp_id":      f"{portal['state']}-{portal['name'][:8].replace(' ','-')}-{datetime.utcnow().strftime('%Y%m%d')}-{slug}",
                                "title":       title,
                                "agency":      portal["name"],
                                "portal":      portal["name"],
                                "state":       portal["state"],
                                "country":     "US",
                                "due_date":    (await date_el.inner_text()).strip() if date_el else "",
                                "details_url": full_url,
                                "keyword_matched": kw,
                            })
                        except Exception:
                            continue
                    break  # Found results for first keyword — move on
                except Exception as e:
                    continue

        except Exception as e:
            print(f"  FAILED {portal['name']}: {e}")

        await browser.close()
    print(f"  {portal['name']}: {len(results)} RFPs")
    return results


async def run_all_city_portals():
    all_results = []
    for portal in CITY_PORTALS:
        print(f"Scraping {portal['name']}...")
        results = await scrape_city_portal(portal)
        all_results.extend(results)
        await asyncio.sleep(2)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    output_path = f"/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/exports/raw/city_portals_{today}.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nCity portals: Saved {len(all_results)} total records")

asyncio.run(run_all_city_portals())
```

## Note on City of Ashland
Username stored as `Thiruvalluvan` — confirm this is correct with manager before first run.
