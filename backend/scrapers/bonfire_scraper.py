"""
Bonfire Platform Scraper — EITACIES RFP GenAI
Reusable scraper for any Bonfire procurement portal.
Covers: Texas DOT, Chicago Public Schools, City of Roswell, EUNA PennBID
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

# Bonfire portals config: each has a base URL and portal name
BONFIRE_PORTALS = [
    {
        "name": "Texas DOT",
        "category": "State",
        "base_url": "https://txdot.bonfirehub.com",
        "list_url": "https://txdot.bonfirehub.com/portal/?tab=openOpportunities",
    },
    {
        "name": "Chicago Public Schools",
        "category": "Education",
        "base_url": "https://cps.bonfirehub.com",
        "list_url": "https://cps.bonfirehub.com/portal/?tab=openOpportunities",
    },
    {
        "name": "City of Roswell",
        "category": "City",
        "base_url": "https://roswellgov.bonfirehub.com",
        "list_url": "https://roswellgov.bonfirehub.com/portal/?tab=openOpportunities",
    },
    {
        "name": "EUNA PennBID",
        "category": "Aggregator",
        "base_url": "https://pennbid.bonfirehub.com",
        "list_url": "https://pennbid.bonfirehub.com/portal/?tab=openOpportunities",
    },
]


def classify_from_title(title):
    """Classify RFP category from title keywords."""
    t = title.lower()
    if any(kw in t for kw in ["staff", "workforce", "personnel", "augmentation"]):
        return "IT Staffing"
    if any(kw in t for kw in ["ai", "artificial intelligence", "machine learning", "ml", "llm"]):
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
    if any(kw in t for kw in ["research", "r&d", "innovation"]):
        return "Research & Development"
    return "Other Technology"


async def scrape_bonfire_listing(page, portal):
    """Scrape the listing page of a Bonfire portal."""
    results = []
    try:
        print(f"  {portal['name']}: loading listing page...")
        await page.goto(portal["list_url"], timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Extract all bid rows from the table using JavaScript
        page_data = await page.evaluate("""() => {
            const items = [];
            // Bonfire uses a table with rows containing bid info
            const rows = document.querySelectorAll('table tbody tr, .opportunity-row, tr[data-id]');
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length < 4) continue;

                // Extract text from cells
                const cellTexts = Array.from(cells).map(c => c.innerText.trim());

                // Find the link to the opportunity detail
                const link = row.querySelector('a[href*="opportunities"]');
                const detailUrl = link ? link.getAttribute('href') : '';

                // Get the project/title - usually in a prominent cell
                let title = '';
                let refNum = '';
                let closeDate = '';
                let department = '';
                let status = '';

                for (let i = 0; i < cells.length; i++) {
                    const text = cellTexts[i];
                    if (/open|closed|upcoming/i.test(text) && text.length < 20) {
                        status = text;
                    }
                    if (/ref|number|#|\d{2}-\d{4}/.test(text) || /^\d{8,}/.test(text)) {
                        refNum = text;
                    }
                    if (/\d{1,2}\/\d{1,2}\/\d{2,4}|\w+\s+\d{1,2},?\s+\d{4}/.test(text) && text.length < 40) {
                        closeDate = text;
                    }
                    if (text.length > 15 && !title) {
                        title = text;
                    }
                    if (/^(PRO_|SSD_|CSD|PEPS|Dept|div)/i.test(text)) {
                        department = text;
                    }
                }

                // Fallback: try to get title from the link text
                if (!title && link) {
                    title = link.innerText.trim();
                }

                if (title && title.length > 5) {
                    items.push({
                        title: title.substring(0, 300),
                        ref_num: refNum,
                        close_date: closeDate,
                        department: department,
                        status: status,
                        detail_url: detailUrl
                    });
                }
            }

            // Also try alternate selectors for newer Bonfire layouts
            if (items.length === 0) {
                const cards = document.querySelectorAll('.opportunity-card, .bid-card, [class*="opportunity"]');
                for (const card of cards) {
                    const heading = card.querySelector('h2, h3, h4, a[href*="opportunities"]');
                    const link = card.querySelector('a[href*="opportunities"]');
                    if (heading || link) {
                        const title = (heading || link).innerText.trim();
                        const detailUrl = link ? link.getAttribute('href') : '';
                        items.push({
                            title: title.substring(0, 300),
                            ref_num: '',
                            close_date: '',
                            department: '',
                            status: '',
                            detail_url: detailUrl
                        });
                    }
                }
            }

            return items;
        }""")

        print(f"  {portal['name']}: found {len(page_data)} listings on page")

        for item in page_data:
            detail_url = item["detail_url"]
            if detail_url and not detail_url.startswith("http"):
                detail_url = portal["base_url"] + detail_url

            results.append({
                "rfp_id": f"{portal['name'].replace(' ', '-')}-{item.get('ref_num', '') or len(results)+1}",
                "title": item["title"],
                "portal": portal["name"],
                "portal_category": portal["category"],
                "details_url": detail_url or portal["list_url"],
                "summary": item["title"][:200],
                "rfp_category": classify_from_title(item["title"]),
                "closing_date": item.get("close_date", ""),
                "office": item.get("department", ""),
                "scraped_at": datetime.utcnow().isoformat(),
            })

    except Exception as e:
        print(f"  ERROR {portal['name']}: {str(e)[:100]}")

    return results


async def scrape_bonfire_detail(page, portal, result):
    """Scrape individual bid detail page from Bonfire."""
    url = result.get("details_url", "")
    if not url or "opportunities" not in url:
        return result

    try:
        print(f"    Detail: {result['title'][:50]}...")
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        detail = await page.evaluate("""() => {
            const data = {};

            // Get all label-value pairs
            const labels = document.querySelectorAll('dt, .label, .field-label, strong, b');
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

            // Get the main description
            const descEl = document.querySelector('.description, .opportunity-description, [class*="description"], .prose');
            if (descEl) {
                data['full_description'] = descEl.innerText.trim().substring(0, 5000);
            }

            // Get all text content as fallback
            const mainContent = document.querySelector('main, .content, #content, .opportunity-details');
            if (mainContent) {
                data['page_text'] = mainContent.innerText.trim().substring(0, 5000);
            }

            // Extract dates
            const allText = document.body.innerText;
            const dateMatches = allText.match(/\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}/g);
            if (dateMatches) {
                data['_all_dates'] = dateMatches;
            }

            return data;
        }""")

        # Parse detail fields
        if detail.get("full_description"):
            result["summary"] = detail["full_description"][:500]
            result["description"] = detail.get("full_description", "")
        elif detail.get("page_text"):
            result["summary"] = detail["page_text"][:500]
            result["description"] = detail.get("page_text", "")

        # Try to extract structured fields
        for key, value in detail.items():
            if key.startswith("_"):
                continue
            kl = key.lower()
            if "close" in kl or "deadline" in kl or "due" in kl:
                result["closing_date"] = value
            elif "open" in kl or "posted" in kl or "start" in kl:
                result["open_date"] = value
            elif "contact" in kl and "email" in kl:
                result["contact_email"] = value
            elif "contact" in kl:
                result["contact_name"] = value
            elif "budget" in kl or "estimat" in kl:
                result["budget_text"] = value
            elif "category" in kl or "type" in kl:
                cat = classify_from_title(value + " " + result.get("title", ""))
                if cat != "Other Technology":
                    result["rfp_category"] = cat

    except Exception as e:
        print(f"    Detail error: {str(e)[:60]}")

    return result


async def scrape_bonfire(portal):
    """Scrape a complete Bonfire portal: listing + details."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        # Step 1: Get listing
        listings = await scrape_bonfire_listing(page, portal)

        # Step 2: Get details for each bid (limit to avoid timeout)
        for i, listing in enumerate(listings[:30]):  # Cap at 30 detail pages
            enriched = await scrape_bonfire_detail(page, portal, listing)
            all_results.append(enriched)
            await page.wait_for_timeout(1000)  # Rate limit

        # Add remaining listings without detail enrichment
        for listing in listings[30:]:
            all_results.append(listing)

        await browser.close()

    return all_results


async def scrape_all_bonfire_portals():
    """Scrape all configured Bonfire portals."""
    all_results = []
    for portal in BONFIRE_PORTALS:
        print(f"\n  Scraping {portal['name']}...")
        try:
            results = await scrape_bonfire(portal)
            all_results.extend(results)
            print(f"  {portal['name']}: {len(results)} total records")
        except Exception as e:
            print(f"  ERROR {portal['name']}: {str(e)[:100]}")

    output_path = EXPORT_DIR / f"bonfire_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\nBonfire Portals: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_all_bonfire_portals())
    print(f"Total scraped: {len(results)}")
