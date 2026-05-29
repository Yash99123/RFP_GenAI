"""
City Portals Scraper — EITACIES RFP GenAI (Updated)
Scrapes verified working city/county portals.
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

PROJECT_DIR = Path(__file__).parent.parent.parent
EXPORT_DIR = PROJECT_DIR / "exports" / "raw"


def classify_from_title(title):
    t = title.lower()
    if any(kw in t for kw in ["staff", "workforce", "personnel", "augmentation"]):
        return "IT Staffing"
    if any(kw in t for kw in ["ai", "artificial intelligence", "machine learning", "ml", "llm"]):
        return "AI / Machine Learning"
    if any(kw in t for kw in ["software", "application", "platform", "web", "mobile"]):
        return "Software Development"
    if any(kw in t for kw in ["infrastructure", "server", "network", "hardware"]):
        return "IT Infrastructure"
    if any(kw in t for kw in ["cloud", "aws", "azure", "saas"]):
        return "Cloud Services"
    if any(kw in t for kw in ["security", "cyber", "vulnerability"]):
        return "Cybersecurity"
    if any(kw in t for kw in ["data", "analytics", "intelligence", "reporting"]):
        return "Data Analytics"
    if any(kw in t for kw in ["consulting", "advisory", "professional"]):
        return "Consulting / Advisory"
    if any(kw in t for kw in ["training", "education"]):
        return "Training & Education"
    if any(kw in t for kw in ["research", "r&d", "innovation"]):
        return "Research & Development"
    return "Other Technology"


CITY_PORTALS = [
    {
        "name": "LA County",
        "category": "City",
        "search_url": "https://camisvr.co.la.ca.us/LACoBids/BidLookUp/OpenBidList",
    },
    {
        "name": "LAFPP (Los Angeles)",
        "category": "City",
        "search_url": "https://lafpp.lacity.gov/about/request-proposals",
    },
    {
        "name": "Texas DOT",
        "category": "City",
        "search_url": "https://www.txdot.gov/business/peps/opportunities.html",
    },
]


async def scrape_city_portal(page, portal):
    """Scrape a single city portal."""
    results = []
    try:
        print(f"  {portal['name']}: loading...")
        await page.goto(portal["search_url"], timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Extract bid/RFP listings
        page_data = await page.evaluate("""() => {
            const items = [];
            const seen = new Set();

            // Get all links
            const links = document.querySelectorAll('a[href]');
            for (const link of links) {
                const href = link.getAttribute('href');
                const text = link.innerText.trim();
                if (!text || text.length < 10) continue;
                if (/^(Home|About|Contact|Login|Sign|Help|Privacy|Terms|Menu|Search|Back|Skip|Main|Nav)/i.test(text)) continue;

                const isBid = /bid|solicitation|rfp|rfq|rfi|proposal|procurement|contract|opportunity|addendum/i.test(text);
                if (isBid && !seen.has(text)) {
                    seen.add(text);
                    items.push({
                        title: text.substring(0, 200),
                        url: href.startsWith('http') ? href : (new URL(href, window.location.origin)).href
                    });
                }
            }

            // Get table rows
            const rows = document.querySelectorAll('table tbody tr');
            for (const row of rows) {
                const text = row.innerText.trim();
                if (text.length > 15) {
                    const firstLine = text.split('\\n')[0].trim();
                    if (!seen.has(firstLine) && firstLine.length > 5 && /bid|solicitation|rfp|proposal|procurement/i.test(firstLine)) {
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
            # Try to extract dates from title
            dates = {}
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', item["title"])
            if date_match:
                dates["closing_date"] = date_match.group(1)

            results.append({
                "rfp_id": f"{portal['name'].replace(' ', '-')}-{len(results)+1}",
                "title": re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}', '', item["title"]).strip(),
                "portal": portal["name"],
                "portal_category": portal["category"],
                "details_url": item["url"] or portal["search_url"],
                "summary": re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}', '', item["title"]).strip()[:200],
                "rfp_category": classify_from_title(item["title"]),
                "closing_date": dates.get("closing_date"),
                "scraped_at": datetime.utcnow().isoformat(),
            })

        print(f"  {portal['name']}: {len(results)} results")

    except Exception as e:
        print(f"  ERROR {portal['name']}: {str(e)[:80]}")

    return results


async def scrape_city_portals():
    """Scrape all city portals."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        for portal in CITY_PORTALS:
            results = await scrape_city_portal(page, portal)
            all_results.extend(results)

        await browser.close()

    output_path = EXPORT_DIR / f"city_portals_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nCity Portals: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_city_portals())
    print(f"Total scraped: {len(results)}")
