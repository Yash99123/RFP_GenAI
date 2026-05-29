"""
JAGGAER Group Scraper — EITACIES RFP GenAI
Covers: SAP Ariba, JAGGAER, Montana JAGGAER, JAGGAER Minnesota, U of Minnesota
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
    "artificial intelligence", "machine learning", "software",
    "IT services", "cloud", "data analytics", "cybersecurity",
    "digital transformation", "consulting", "technology"
]

JAGGAER_PORTALS = [
    {
        "name": "SAP Ariba",
        "login_url": "https://supplier.ariba.com",
        "search_url": "https://supplier.ariba.com/ad/ng/ariba-sourcing/rfx/list",
        "username": os.environ.get("SAP_ARIBA_USERNAME", ""),
        "password": os.environ.get("SAP_ARIBA_PASSWORD", ""),
    },
    {
        "name": "JAGGAER Supplier",
        "login_url": "https://supplier.jaggaer.com/web/login",
        "search_url": "https://supplier.jaggaer.com/web/rfp/public",
        "username": os.environ.get("JAGGAER_SUPPLIER_USERNAME", ""),
        "password": os.environ.get("JAGGAER_SUPPLIER_PASSWORD", ""),
    },
    {
        "name": "Montana JAGGAER",
        "login_url": "https://mt.jaggaer.com/web/login",
        "search_url": "https://mt.jaggaer.com/web/rfp/public",
        "username": os.environ.get("MONTANA_GOV_JAGGAER_USERNAME", ""),
        "password": os.environ.get("MONTANA_GOV_JAGGAER_PASSWORD", ""),
    },
    {
        "name": "JAGGAER Minnesota",
        "login_url": "https://mn.jaggaer.com/web/login",
        "search_url": "https://mn.jaggaer.com/web/rfp/public",
        "username": os.environ.get("JAGGAER_MINNESOTA_USERNAME", ""),
        "password": os.environ.get("JAGGAER_MINNESOTA_PASSWORD", ""),
    },
    {
        "name": "University of Minnesota",
        "login_url": "https://umn.jaggaer.com/web/login",
        "search_url": "https://umn.jaggaer.com/web/rfp/public",
        "username": os.environ.get("UNIVERSITY_OF_MINNESOTA_USERNAME", ""),
        "password": os.environ.get("UNIVERSITY_OF_MINNESOTA_PASSWORD", ""),
    },
]


async def scrape_jaggaer_portal(page, portal):
    """Scrape a single JAGGAER-based portal."""
    results = []
    try:
        print(f"  {portal['name']}: logging in...")
        await page.goto(portal["login_url"], timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Fill login
        try:
            await page.fill(
                'input[type="email"], input[name="username"], #username, input[name="email"]',
                portal["username"]
            )
            await page.fill('input[type="password"]', portal["password"])
            await page.click('button[type="submit"], input[type="submit"]')
            await page.wait_for_timeout(5000)
            print(f"  {portal['name']}: logged in")
        except Exception as e:
            print(f"  {portal['name']}: login failed ({str(e)[:50]}), trying public search...")

        # Search each keyword
        for kw in KEYWORDS[:3]:  # Limit to 3 keywords per portal for speed
            try:
                search_url = portal["search_url"] + f"?q={kw.replace(' ', '+')}"
                await page.goto(search_url, timeout=20000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                # Generic JAGGAER result extraction
                rows = await page.query_selector_all(
                    ".rfx-row, .sourcing-row, tr.rfp-item, .event-row, [data-rfx-id], "
                    "table tbody tr, .list-item, .result-item"
                )
                for row in rows[:10]:
                    try:
                        text = await row.inner_text()
                        lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 5]
                        if not lines:
                            continue

                        title = lines[0][:200]
                        agency = lines[1] if len(lines) > 1 else portal["name"]

                        link_el = await row.query_selector("a[href]")
                        href = await link_el.get_attribute("href") if link_el else ""
                        full_url = (portal["login_url"] + href) if href and not href.startswith("http") else href

                        results.append({
                            "rfp_id": f"{portal['name'].replace(' ', '-')}-{len(results)+1}",
                            "title": title,
                            "agency": agency,
                            "portal": portal["name"],
                            "portal_category": "Enterprise",
                            "due_date": "",
                            "posted_date": "",
                            "details_url": full_url or portal["login_url"],
                            "description": "",
                            "keyword_matched": kw,
                            "scraped_at": datetime.utcnow().isoformat(),
                        })
                    except Exception:
                        continue

            except Exception as e:
                print(f"    {portal['name']} keyword '{kw}' failed: {str(e)[:50]}")
                continue

    except Exception as e:
        print(f"  ERROR {portal['name']}: {str(e)[:80]}")

    print(f"  {portal['name']}: {len(results)} RFPs found")
    return results


async def scrape_jaggaer_group():
    """Scrape all JAGGAER-based portals."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for portal in JAGGAER_PORTALS:
            results = await scrape_jaggaer_portal(page, portal)
            all_results.extend(results)

        await browser.close()

    output_path = EXPORT_DIR / f"jaggaer_group_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nJAGGAER Group: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_jaggaer_group())
    print(f"Total scraped: {len(results)}")
