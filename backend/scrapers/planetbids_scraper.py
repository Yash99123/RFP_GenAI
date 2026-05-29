"""
PlanetBids Scraper — EITACIES RFP GenAI
Scrapes PlanetBids-based portals (City of Burbank, Fresno, San Diego, etc.)
PlanetBids is an Ember.js SPA that requires JavaScript rendering.
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

# PlanetBids portals: portal ID in URL maps to the organization
PLANETBIDS_PORTALS = [
    {
        "name": "City of Burbank",
        "category": "City",
        "portal_id": "14210",
        "base_url": "https://vendors.planetbids.com",
        "list_url": "https://vendors.planetbids.com/portal/14210/bo/bo-search",
    },
    {
        "name": "City of Fresno",
        "category": "City",
        "portal_id": "14769",
        "base_url": "https://vendors.planetbids.com",
        "list_url": "https://vendors.planetbids.com/portal/14769/vp/vp-home",
    },
    {
        "name": "City of Santa Rosa",
        "category": "City",
        "portal_id": "20314",
        "base_url": "https://vendors.planetbids.com",
        "list_url": "https://vendors.planetbids.com/portal/20314/vp/vp-home",
    },
    {
        "name": "Metropolitan Water District",
        "category": "City",
        "portal_id": "16151",
        "base_url": "https://vendors.planetbids.com",
        "list_url": "https://vendors.planetbids.com/portal/16151/bo/bo-search",
    },
    {
        "name": "County of Stanislaus",
        "category": "City",
        "portal_id": "14599",
        "base_url": "https://vendors.planetbids.com",
        "list_url": "https://vendors.planetbids.com/portal/14599/portal-home",
    },
]


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


async def scrape_planetbids_portal(page, portal):
    """Scrape a single PlanetBids portal."""
    results = []
    try:
        print(f"  {portal['name']}: loading {portal['list_url']}...")
        await page.goto(portal["list_url"], timeout=30000, wait_until="networkidle")
        await page.wait_for_timeout(8000)  # PlanetBids SPA needs extra time

        # PlanetBids is an Ember.js SPA - wait for content to render
        # Try multiple times
        for attempt in range(3):
            page_data = await page.evaluate("""() => {
                const items = [];
                const seen = new Set();

                // PlanetBids renders tables with bid data
                const rows = document.querySelectorAll('table tbody tr, .ember-table-row, tr');
                for (const row of rows) {
                    const text = row.innerText.trim();
                    if (text.length < 10) continue;

                    const link = row.querySelector('a[href*="bo-detail"], a[href*="vp-detail"]');
                    if (!link) continue;

                    const href = link.getAttribute('href') || '';
                    const title = link.innerText.trim();
                    if (!title || title.length < 3 || seen.has(title)) continue;
                    seen.add(title);

                    // Extract date from row
                    const dateMatch = text.match(/(\d{1,2}\/\d{1,2}\/\d{2,4})/);

                    items.push({
                        title: title.substring(0, 300),
                        detail_url: href.startsWith('http') ? href : (new URL(href, window.location.origin)).href,
                        close_date: dateMatch ? dateMatch[1] : '',
                        full_text: text.substring(0, 500)
                    });
                }

                // Also try links directly
                if (items.length === 0) {
                    const links = document.querySelectorAll('a[href*="bo-detail"], a[href*="vp-detail"], a[href*="bid"]');
                    for (const link of links) {
                        const text = link.innerText.trim();
                        const href = link.getAttribute('href') || '';
                        if (text.length > 5 && !seen.has(text) && /bid|rfp|solicitation|project/i.test(text + href)) {
                            seen.add(text);
                            items.push({
                                title: text.substring(0, 300),
                                detail_url: href.startsWith('http') ? href : (new URL(href, window.location.origin)).href,
                                close_date: '',
                                full_text: text
                            });
                        }
                    }
                }

                return items;
            }""")

            if len(page_data) > 0:
                break
            print(f"  {portal['name']}: attempt {attempt+1} found 0 listings, retrying...")
            await page.wait_for_timeout(5000)

        print(f"  {portal['name']}: found {len(page_data)} listings")

        for item in page_data:
            detail_url = item["detail_url"]
            result = {
                "rfp_id": f"{portal['name'].replace(' ', '-')}-{len(results)+1}",
                "title": item["title"],
                "portal": portal["name"],
                "portal_category": portal["category"],
                "details_url": detail_url,
                "summary": item.get("full_text", item["title"])[:200],
                "rfp_category": classify_from_title(item["title"]),
                "closing_date": item.get("close_date", ""),
                "office": portal["name"],
                "scraped_at": datetime.utcnow().isoformat(),
            }
            results.append(result)

        # Enrich with detail pages
        for i, result in enumerate(results[:20]):
            try:
                detail_url = result["details_url"]
                if not detail_url or "detail" not in detail_url:
                    continue
                print(f"    Detail: {result['title'][:50]}...")
                await page.goto(detail_url, timeout=20000, wait_until="networkidle")
                await page.wait_for_timeout(5000)

                detail = await page.evaluate("""() => {
                    const data = {};
                    const allText = document.body.innerText;

                    // PlanetBids detail pages have structured fields
                    const labels = document.querySelectorAll('dt, .label, strong, b, th');
                    for (const label of labels) {
                        const key = label.innerText.trim().toLowerCase().replace(/[:\\s]+$/, '');
                        const valueEl = label.nextElementSibling || label.parentElement;
                        if (valueEl) {
                            const value = valueEl.innerText.trim();
                            if (value && value !== key && value.length < 500) {
                                data[key] = value;
                            }
                        }
                    }

                    // Get description
                    const descEl = document.querySelector('.description, [class*="desc"], .prose');
                    if (descEl) {
                        data.description = descEl.innerText.trim().substring(0, 3000);
                    }

                    data.page_text = allText.substring(0, 5000);
                    return data;
                }""")

                if detail.get("description"):
                    result["summary"] = detail["description"][:500]
                    result["description"] = detail["description"]

                # Extract structured fields
                for key, value in detail.items():
                    if key.startswith("_") or key in ("page_text", "description"):
                        continue
                    kl = key.lower()
                    if "close" in kl or "deadline" in kl:
                        result["closing_date"] = value
                    elif "open" in kl or "posted" in kl:
                        result["open_date"] = value
                    elif "contact" in kl and "email" in kl:
                        result["contact_email"] = value
                    elif "contact" in kl:
                        result["contact_name"] = value
                    elif "budget" in kl or "estimat" in kl:
                        result["budget_text"] = value

                await page.wait_for_timeout(1000)

            except Exception as e:
                print(f"    Detail error: {str(e)[:60]}")

    except Exception as e:
        print(f"  ERROR {portal['name']}: {str(e)[:100]}")

    return results


async def scrape_all_planetbids():
    """Scrape all configured PlanetBids portals."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        for portal in PLANETBIDS_PORTALS:
            results = await scrape_planetbids_portal(page, portal)
            all_results.extend(results)

        await browser.close()

    output_path = EXPORT_DIR / f"planetbids_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\nPlanetBids Portals: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_all_planetbids())
    print(f"Total scraped: {len(results)}")
