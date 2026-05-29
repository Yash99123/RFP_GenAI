"""
SAM.gov Scraper — EITACIES RFP GenAI
Uses Playwright to search SAM.gov for AI/technology RFPs.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

PROJECT_DIR = Path(__file__).parent.parent.parent
EXPORT_DIR = PROJECT_DIR / "exports" / "raw"

KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "AI services",
    "natural language processing",
    "generative AI",
    "data science",
    "predictive analytics",
    "digital transformation",
    "software development",
    "cloud services",
    "cybersecurity",
    "IT modernization",
    "business intelligence",
]


async def scrape_sam_gov():
    """Scrape SAM.gov for AI/tech RFPs using Playwright."""
    from playwright.async_api import async_playwright

    results = []
    seen = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for kw in KEYWORDS:
            try:
                print(f"  SAM.gov: Searching '{kw}'...")

                # Navigate to search page
                await page.goto("https://sam.gov/search/?index=opp", timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # Fill search input (type=search, id=newSimpleSearch)
                search_input = await page.query_selector("input#newSimpleSearch, input[type='search']")
                if not search_input:
                    print(f"    No search input found, skipping")
                    continue

                await search_input.fill(kw)
                await search_input.press("Enter")
                await page.wait_for_timeout(5000)

                # Extract results using JavaScript for reliability
                page_results = await page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    
                    // Find all links to opportunities
                    const links = document.querySelectorAll('a[href*="/opp/"], a[href*="/workspace/contract/opp/"]');
                    
                    for (const link of links) {
                        const href = link.getAttribute('href');
                        let title = link.innerText.trim();
                        
                        // Skip empty titles, counts like "(6)", or very short entries
                        if (!title || title.length < 5 || /^\\(\\d+\\)$/.test(title)) continue;
                        
                        // Deduplicate by URL
                        const fullUrl = href.startsWith('/') ? 'https://sam.gov' + href : href;
                        const urlKey = fullUrl.split('?')[0];
                        if (seen.has(urlKey)) continue;
                        seen.add(urlKey);
                        
                        // Extract notice ID from URL
                        const match = href.match(/\\/opp\\/([a-f0-9]+)/);
                        const noticeId = match ? match[1] : '';
                        
                        // Get surrounding text for agency/date info
                        let container = link.closest('li, div[class*="result"], div[class*="card"]');
                        let agency = '';
                        let dates = [];
                        
                        if (container) {
                            const allText = container.innerText;
                            const lines = allText.split('\\n').map(l => l.trim()).filter(l => l && l.length > 3);
                            // Agency is usually the second meaningful line
                            for (let i = 1; i < Math.min(lines.length, 5); i++) {
                                const line = lines[i];
                                if (/\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}/.test(line) || /\\d{4}-\\d{2}-\\d{2}/.test(line)) {
                                    dates.push(line);
                                } else if (!agency && line.length > 5 && !/^\\(\\d+\\)$/.test(line)) {
                                    agency = line;
                                }
                            }
                        }
                        
                        items.push({
                            title: title,
                            url: fullUrl,
                            noticeId: noticeId,
                            agency: agency,
                            dates: dates.join(' | ')
                        });
                    }
                    return items;
                }""")

                for item in page_results:
                    uid = item.get("noticeId", "") or item["url"]
                    if uid not in seen:
                        seen.add(uid)
                        results.append({
                            "rfp_id": f"SAM-{item['noticeId']}" if item["noticeId"] else f"SAM-{len(results)+1}",
                            "title": item["title"],
                            "agency": item["agency"],
                            "portal": "SAM.gov",
                            "portal_category": "Federal",
                            "due_date": "",
                            "posted_date": item.get("dates", ""),
                            "details_url": item["url"],
                            "description": "",
                            "keyword_matched": kw,
                            "scraped_at": datetime.utcnow().isoformat(),
                        })

                print(f"    {len(page_results)} results, {len(results)} total unique")

            except Exception as e:
                print(f"    Error: {str(e)[:80]}")
                continue

        await browser.close()

    # Save results
    output_path = EXPORT_DIR / f"sam_gov_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nSAM.gov: Saved {len(results)} records to {output_path}")
    return results


if __name__ == "__main__":
    results = asyncio.run(scrape_sam_gov())
    print(f"Total scraped: {len(results)}")
