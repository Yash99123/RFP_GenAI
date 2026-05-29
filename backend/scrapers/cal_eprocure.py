"""
Cal eProcure Scraper — EITACIES RFP GenAI
Scrapes California's Cal eProcure procurement portal.
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
    """Classify RFP category from title keywords."""
    t = title.lower()
    if any(kw in t for kw in ["staff", "workforce", "personnel", "augmentation"]):
        return "IT Staffing"
    if any(kw in t for kw in ["ai", "artificial intelligence", "machine learning", "ml", "llm", "cognitive"]):
        return "AI / Machine Learning"
    if any(kw in t for kw in ["software", "application", "platform", "web", "mobile", "development"]):
        return "Software Development"
    if any(kw in t for kw in ["infrastructure", "server", "network", "hardware", "data center"]):
        return "IT Infrastructure"
    if any(kw in t for kw in ["cloud", "aws", "azure", "saas", "hosting"]):
        return "Cloud Services"
    if any(kw in t for kw in ["security", "cyber", "vulnerability", "compliance"]):
        return "Cybersecurity"
    if any(kw in t for kw in ["data", "analytics", "intelligence", "reporting", "database"]):
        return "Data Analytics"
    if any(kw in t for kw in ["consulting", "advisory", "professional", "management"]):
        return "Consulting / Advisory"
    if any(kw in t for kw in ["training", "education", "instructor"]):
        return "Training & Education"
    if any(kw in t for kw in ["research", "r&d", "innovation", "pilot"]):
        return "Research & Development"
    if any(kw in t for kw in ["healthcare", "health", "medical", "clinical", "hospital"]):
        return "Healthcare IT"
    if any(kw in t for kw in ["telecom", "communication", "network", "wireless"]):
        return "Network / Telecom"
    return "Other Technology"


async def scrape_cal_eprocure():
    """Scrape Cal eProcure for open solicitations."""
    from playwright.async_api import async_playwright

    results = []

    # Cal eProcure actual search URL (CSCR - California State Contracts Register)
    search_url = "https://caleprocure.ca.gov/pages/Events-BS3/event-search.aspx"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        try:
            print(f"  Cal eProcure: Loading {search_url}...")
            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            # Extract listings from the page
            page_data = await page.evaluate("""() => {
                const items = [];
                const seen = new Set();

                // Look for table rows with bid/solicitation info
                const rows = document.querySelectorAll('table tr, .event-item, [class*="event"], [class*="bid"], [class*="solicitation"]');
                for (const row of rows) {
                    const text = row.innerText.trim();
                    if (text.length < 10) continue;

                    // Extract title and URL
                    const link = row.querySelector('a[href]');
                    const title = link ? link.innerText.trim() : text.split('\\n')[0].trim();
                    const url = link ? (link.getAttribute('href').startsWith('http') ? link.getAttribute('href') : new URL(link.getAttribute('href'), window.location.origin).href) : '';

                    if (title && title.length > 5 && !seen.has(title)) {
                        seen.add(title);
                        items.push({
                            title: title.substring(0, 200),
                            url: url,
                            full_text: text.substring(0, 500)
                        });
                    }
                }

                // Also look for any links with bid/solicitation keywords
                const links = document.querySelectorAll('a[href]');
                for (const link of links) {
                    const href = link.getAttribute('href');
                    const text = link.innerText.trim();
                    if (!text || text.length < 10) continue;

                    const isBid = /bid|solicitation|rfp|rfq|rfi|proposal|procurement|contract|opportunity|event/i.test(text);
                    if (isBid && !seen.has(text)) {
                        seen.add(text);
                        items.push({
                            title: text.substring(0, 200),
                            url: href.startsWith('http') ? href : (new URL(href, window.location.origin)).href,
                            full_text: text.substring(0, 500)
                        });
                    }
                }

                return items;
            }""")

            for item in page_data:
                # Extract dates from title or text
                closing_date = None
                open_date = None

                # Look for closing/due dates
                date_patterns = [
                    r'(?:closing|due|deadline|response due)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
                    r'(?:closing|due|deadline|response due)[\s:]+(\w+\s+\d{1,2},?\s+\d{4})',
                    r'(\d{1,2}/\d{1,2}/\d{2,4})',
                ]

                for pattern in date_patterns:
                    match = re.search(pattern, item.get("full_text", ""), re.IGNORECASE)
                    if match:
                        closing_date = match.group(1)
                        break

                # Generate a unique ID
                rfp_id = f"Cal-eProcure-{hash(item['title']) % 100000}"

                results.append({
                    "rfp_id": rfp_id,
                    "title": item["title"],
                    "portal": "Cal eProcure",
                    "portal_category": "State",
                    "details_url": item["url"] or search_url,
                    "summary": item["title"][:200],
                    "rfp_category": classify_from_title(item["title"]),
                    "closing_date": closing_date,
                    "open_date": open_date,
                    "scraped_at": datetime.utcnow().isoformat(),
                    "description": item.get("full_text", ""),
                })

            print(f"  Cal eProcure: {len(page_data)} results")

        except Exception as e:
            print(f"  ERROR Cal eProcure: {str(e)[:100]}")

        await browser.close()

    print(f"  Cal eProcure total: {len(results)} results")
    return results


if __name__ == "__main__":
    results = asyncio.run(scrape_cal_eprocure())
    print(f"\nTotal scraped: {len(results)}")

    # Save results
    output_path = EXPORT_DIR / f"cal_eprocure_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved to: {output_path}")
