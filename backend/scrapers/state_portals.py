"""
State Portals Scraper — EITACIES RFP GenAI
Covers: CAL eProcure, MyFlorida, Louisiana LaGov, CommBuys, Vermont, SupplierClearinghouse
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

PROJECT_DIR = Path(__file__).parent.parent.parent
EXPORT_DIR = PROJECT_DIR / "exports" / "raw"

KEYWORDS = [
    "artificial intelligence", "machine learning", "software development",
    "IT services", "cloud computing", "cybersecurity", "data analytics",
    "digital transformation", "consulting", "technology services"
]

STATE_PORTALS = [
    {
        "name": "CAL eProcure",
        "state": "CA",
        "search_url": "https://caleprocure.ca.gov/pages/Events/event-search.aspx",
        "public": True,
    },
    {
        "name": "MyFlorida",
        "state": "FL",
        "search_url": "https://www.myfloridamarketplace.com/mfmp/main/publish/searchAds.do",
        "public": True,
    },
    {
        "name": "CommBuys",
        "state": "MA",
        "search_url": "https://www.commbuys.com/bso/external/publicBids.sdo",
        "public": True,
    },
    {
        "name": "Vermont Procurement",
        "state": "VT",
        "search_url": "https://bgs.vermont.gov/purchasing/bids",
        "public": True,
    },
    {
        "name": "Louisiana LaGov",
        "state": "LA",
        "search_url": "https://wwwcfprd.doa.louisiana.gov/osp/lapac/vendor.cfm",
        "public": False,
        "login_url": "https://wwwcfprd.doa.louisiana.gov/osp/lapac/dspVendorLogin.cfm",
        "username": os.environ.get("STATE_OF_LOUISIANA_LAGOV_USERNAME", ""),
        "password": os.environ.get("STATE_OF_LOUISIANA_LAGOV_PASSWORD", ""),
    },
    {
        "name": "SupplierClearinghouse",
        "state": "CA",
        "search_url": "https://clearinghouse.cdfa.ca.gov/bids",
        "public": False,
        "login_url": "https://clearinghouse.cdfa.ca.gov/login",
        "username": os.environ.get("SUPPLIERCLEARINGHOUSE_USERNAME", ""),
        "password": os.environ.get("SUPPLIERCLEARINGHOUSE_PASSWORD", ""),
    },
]


async def scrape_state_portal(page, portal):
    """Scrape a single state portal."""
    results = []
    try:
        # Login if required
        if not portal.get("public", True):
            try:
                print(f"  {portal['name']}: logging in...")
                await page.goto(portal["login_url"], timeout=20000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                await page.fill(
                    'input[type="text"], input[name="username"], input[name="userId"], #username',
                    portal.get("username", "")
                )
                await page.fill('input[type="password"]', portal.get("password", ""))
                await page.click('button[type="submit"], input[type="submit"], input[value="Login"]')
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"  {portal['name']}: login failed ({str(e)[:50]}), trying public...")

        # Navigate to search page
        print(f"  {portal['name']}: searching...")
        await page.goto(portal["search_url"], timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Extract all visible links and text that look like bids/RFPs
        page_data = await page.evaluate("""() => {
            const items = [];
            const seen = new Set();

            // Get all links
            const links = document.querySelectorAll('a[href]');
            for (const link of links) {
                const href = link.getAttribute('href');
                const text = link.innerText.trim();

                if (!text || text.length < 10) continue;
                if (/^(Home|About|Contact|Login|Sign|Help|Privacy|Terms|Menu|Search)/i.test(text)) continue;

                const isBid = /bid|solicitation|rfp|rfq|rfi|proposal|procurement|contract|opportunity|award/i.test(text) ||
                              /bid|solicitation|rfp|rfq|rfi/i.test(href);

                if (isBid && !seen.has(text)) {
                    seen.add(text);
                    items.push({
                        title: text.substring(0, 200),
                        url: href.startsWith('http') ? href : (new URL(href, window.location.origin)).href
                    });
                }
            }

            // Also get table rows
            const rows = document.querySelectorAll('table tbody tr');
            for (const row of rows) {
                const text = row.innerText.trim();
                if (text.length > 15) {
                    const firstLine = text.split('\\n')[0].trim();
                    if (!seen.has(firstLine) && firstLine.length > 5) {
                        seen.add(firstLine);
                        const link = row.querySelector('a[href]');
                        items.push({
                            title: firstLine.substring(0, 200),
                            url: link ? (link.getAttribute('href').startsWith('http') ? link.getAttribute('href') : new URL(link.getAttribute('href'), window.location.origin).href) : ''
                        });
                    }
                }
            }

            return items;
        }""")

        for item in page_data:
            results.append({
                "rfp_id": f"{portal['name'].replace(' ', '-')}-{len(results)+1}",
                "title": item["title"],
                "agency": portal["name"],
                "portal": portal["name"],
                "portal_category": "State",
                "due_date": "",
                "posted_date": "",
                "details_url": item["url"] or portal["search_url"],
                "description": "",
                "keyword_matched": "",
                "scraped_at": datetime.utcnow().isoformat(),
            })

        print(f"  {portal['name']}: {len(results)} results")

    except Exception as e:
        print(f"  ERROR {portal['name']}: {str(e)[:80]}")

    return results


async def scrape_state_portals():
    """Scrape all state portals."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for portal in STATE_PORTALS:
            results = await scrape_state_portal(page, portal)
            all_results.extend(results)

        await browser.close()

    output_path = EXPORT_DIR / f"state_portals_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nState Portals: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_state_portals())
    print(f"Total scraped: {len(results)}")
