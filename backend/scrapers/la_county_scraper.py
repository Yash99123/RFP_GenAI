"""
LA County Bids Scraper — EITACIES RFP GenAI
Scrapes LA County solicitation portal (custom ASP.NET form-based system).
URL: https://camisvr.co.la.ca.us/LACoBids/BidLookUp/OpenBidList
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
    if any(kw in t for kw in ["ai", "artificial intelligence", "machine learning"]):
        return "AI / Machine Learning"
    if any(kw in t for kw in ["software", "application", "platform", "web", "mobile", "system"]):
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
    return "Other Technology"


EXTRACT_LA_COUNTY_BIDS_JS = """() => {
    const items = [];
    const seen = new Set();

    // LA County uses a table with bid rows
    // Each row has: Solicitation Number (link), Title, Type, Department, Close Date
    const rows = document.querySelectorAll('table tr');
    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 3) continue;

        // Find the solicitation number link
        const link = row.querySelector('a[href], a[onclick]');
        if (!link) continue;

        const bidRef = link.innerText.trim();
        if (!bidRef || bidRef.length < 3) continue;
        if (seen.has(bidRef)) continue;

        // Skip UI elements
        if (/^(Items per page|Page|Next|Previous|Show|Search|Filter)/i.test(bidRef)) continue;
        if (/^\\d+$/.test(bidRef)) continue;

        seen.add(bidRef);

        // Parse all cell text
        const cellTexts = Array.from(cells).map(c => c.innerText.trim());

        let title = '';
        let type = '';
        let department = '';
        let closeDate = '';

        for (let i = 0; i < cells.length; i++) {
            const text = cellTexts[i];
            if (!text || text === bidRef) continue;

            // Title is usually the longest text
            if (text.length > 15 && text.length > title.length) {
                title = text;
            }
            // Type
            if (/commodity|service|professional/i.test(text) && text.length < 30) {
                type = text;
            }
            // Department
            if (/internal|public works|health|parks|sheriff|probation|mental|county/i.test(text) && text.length < 50) {
                department = text;
            }
            // Close date
            if (/\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}/.test(text) || /continuous/i.test(text)) {
                closeDate = text;
            }
        }

        if (title && title.length > 5) {
            items.push({
                solicitation_num: bidRef,
                title: title.substring(0, 300),
                type: type,
                department: department,
                close_date: closeDate
            });
        }
    }
    return items;
}"""


async def scrape_la_county():
    """Scrape LA County open bids."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        print("  LA County: loading bid list...")
        await page.goto(
            "https://camisvr.co.la.ca.us/LACoBids/BidLookUp/OpenBidList",
            timeout=30000,
            wait_until="domcontentloaded"
        )
        await page.wait_for_timeout(5000)

        # Extract all bids from the table
        page_data = await page.evaluate(EXTRACT_LA_COUNTY_BIDS_JS)
        print(f"  LA County: found {len(page_data)} listings")

        # Also try the CSV download which has all data
        try:
            csv_url = "https://camisvr.co.la.ca.us/LACoBids/Download/Rpt_Listing/OpenBidList.csv"
            print("  LA County: trying CSV download...")
            response = await page.goto(csv_url, timeout=20000)
            if response and response.ok:
                csv_content = await response.text()
                lines = csv_content.strip().split('\n')
                if len(lines) > 1:
                    print(f"  LA County: CSV has {len(lines)-1} rows")
                    # Parse CSV
                    for line in lines[1:]:
                        parts = line.split(',')
                        if len(parts) >= 4:
                            solicitation = parts[0].strip('"').strip()
                            title = parts[1].strip('"').strip() if len(parts) > 1 else ''
                            close_date = parts[-1].strip('"').strip() if len(parts) > 3 else ''

                            if title and len(title) > 5 and solicitation not in [r.get('solicitation_num', '') for r in all_results]:
                                page_data.append({
                                    "solicitation_num": solicitation,
                                    "title": title[:300],
                                    "type": parts[2].strip('"').strip() if len(parts) > 2 else '',
                                    "department": parts[3].strip('"').strip() if len(parts) > 3 else '',
                                    "close_date": close_date
                                })
        except Exception as e:
            print(f"  LA County: CSV download failed: {str(e)[:50]}")

        # Process results
        for item in page_data:
            result = {
                "rfp_id": f"LA-County-{item.get('solicitation_num', '') or len(all_results)+1}",
                "title": item["title"],
                "portal": "LA County",
                "portal_category": "City",
                "details_url": "https://camisvr.co.la.ca.us/LACoBids/BidLookUp/OpenBidList",
                "summary": item["title"][:200],
                "rfp_category": classify_from_title(item["title"]),
                "closing_date": item.get("close_date", ""),
                "office": item.get("department", "LA County"),
                "scraped_at": datetime.utcnow().isoformat(),
            }
            all_results.append(result)

        await browser.close()

    output_path = EXPORT_DIR / f"la_county_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\nLA County: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_la_county())
    print(f"Total scraped: {len(results)}")
