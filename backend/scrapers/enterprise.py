"""
JAGGAER / Enterprise Portals Scraper — EITACIES RFP GenAI
Covers: SAP Ariba, Montana EMACS (SciQuest), U of Iowa eBid, Florida ProRFX
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

ENTERPRISE_PORTALS = [
    {
        "name": "Montana EMACS",
        "category": "State",
        "search_url": "https://solutions.sciquest.com/apps/Router/SupplierLogin?CustOrg=StateOfMontana",
        "public": True,
    },
    {
        "name": "University of Iowa",
        "category": "Education",
        "search_url": "https://ap-purchasing.fo.uiowa.edu/purchasing/ebid",
        "public": True,
    },
    {
        "name": "Florida ProRFX",
        "category": "State",
        "search_url": "https://prorfx.com",
        "public": True,
    },
    {
        "name": "Montana EMACS Resources",
        "category": "State",
        "search_url": "https://spb.mt.gov/emacs-resources",
        "public": True,
    },
]


async def scrape_enterprise_portal(page, portal):
    """Scrape a single enterprise portal."""
    results = []
    try:
        print(f"  {portal['name']}: loading...")
        await page.goto(portal["search_url"], timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Extract all bid/RFP related links and content
        page_data = await page.evaluate("""() => {
            const items = [];
            const seen = new Set();

            // Get all links
            const links = document.querySelectorAll('a[href]');
            for (const link of links) {
                const href = link.getAttribute('href');
                const text = link.innerText.trim();

                if (!text || text.length < 8) continue;
                if (/^(Home|About|Contact|Login|Sign|Help|Privacy|Terms|Menu|Search|Back|Skip|Main|Nav)/i.test(text)) continue;

                const isBid = /bid|solicitation|rfp|rfq|rfi|proposal|procurement|contract|opportunity|award|register|vendor/i.test(text) ||
                              /bid|solicitation|rfp|rfq|rfi|ebid|procurement/i.test(href);

                if (isBid && !seen.has(text)) {
                    seen.add(text);
                    items.push({
                        title: text.substring(0, 200),
                        url: href.startsWith('http') ? href : (new URL(href, window.location.origin)).href
                    });
                }
            }

            // Get table rows
            const rows = document.querySelectorAll('table tbody tr, .list-item, .bid-item, .result-item');
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

            // Get any card/panel content
            const cards = document.querySelectorAll('.card, .panel, .item, article');
            for (const card of cards) {
                const heading = card.querySelector('h2, h3, h4, .title, .heading');
                if (heading) {
                    const text = heading.innerText.trim();
                    if (text.length > 10 && !seen.has(text)) {
                        seen.add(text);
                        const link = card.querySelector('a[href]');
                        items.push({
                            title: text.substring(0, 200),
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
                "portal_category": portal["category"],
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


async def scrape_enterprise():
    """Scrape all enterprise portals."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for portal in ENTERPRISE_PORTALS:
            results = await scrape_enterprise_portal(page, portal)
            all_results.extend(results)

        await browser.close()

    output_path = EXPORT_DIR / f"enterprise_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nEnterprise: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_enterprise())
    print(f"Total scraped: {len(results)}")
