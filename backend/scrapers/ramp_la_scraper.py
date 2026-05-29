"""
RAMP LA Scraper — EITACIES RFP GenAI
Scrapes RAMP LA (Regional Alliance Marketplace for Procurement) for City of LA bids.
LAFPP opportunities are primarily posted through RAMP LA.
URL: https://www.rampla.org/s/
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


async def scrape_rampla():
    """Scrape RAMP LA for City of LA procurement opportunities."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        print("  RAMP LA: loading...")
        await page.goto(
            "https://www.rampla.org/s/",
            timeout=30000,
            wait_until="domcontentloaded"
        )
        await page.wait_for_timeout(5000)

        # RAMP LA has tables with opportunities
        page_data = await page.evaluate("""() => {
            const items = [];
            const seen = new Set();

            // Get all tables on the page
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                for (const row of rows) {
                    const cells = row.querySelectorAll('td');
                    if (cells.length < 2) continue;

                    const link = row.querySelector('a[href]');
                    if (!link) continue;

                    const text = row.innerText.trim();
                    const title = link.innerText.trim();
                    const href = link.getAttribute('href') || '';

                    if (title.length > 5 && !seen.has(title)) {
                        seen.add(title);

                        // Extract dates from row
                        const dateMatches = text.match(/\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}/g) || [];
                        let postDate = dateMatches.length > 0 ? dateMatches[0] : '';
                        let dueDate = dateMatches.length > 1 ? dateMatches[1] : '';

                        // Get org/type from cells
                        let org = '';
                        let type = '';
                        for (const cell of cells) {
                            const cellText = cell.innerText.trim();
                            if (/rfp|rfq|rfi|ifb|solicitation|bid/i.test(cellText) && cellText.length < 30) {
                                type = cellText;
                            }
                            if (/lafpp|lapd|lafd|city|dept|agency/i.test(cellText) && cellText.length < 50) {
                                org = cellText;
                            }
                        }

                        items.push({
                            title: title.substring(0, 300),
                            detail_url: href.startsWith('http') ? href : new URL(href, window.location.origin).href,
                            organization: org,
                            type: type,
                            post_date: postDate,
                            due_date: dueDate,
                            full_text: text.substring(0, 500)
                        });
                    }
                }
            }

            // Also try links directly if tables didn't work
            if (items.length === 0) {
                const links = document.querySelectorAll('a[href]');
                for (const link of links) {
                    const text = link.innerText.trim();
                    const href = link.getAttribute('href') || '';
                    if (text.length > 10 && !seen.has(text) && /rfp|rfq|bid|solicitation|opportunity|project/i.test(text)) {
                        seen.add(text);
                        items.push({
                            title: text.substring(0, 300),
                            detail_url: href.startsWith('http') ? href : new URL(href, window.location.origin).href,
                            organization: '',
                            type: '',
                            post_date: '',
                            due_date: '',
                            full_text: text
                        });
                    }
                }
            }

            return items;
        }""")

        print(f"  RAMP LA: found {len(page_data)} listings")

        for item in page_data:
            result = {
                "rfp_id": f"RAMP-LA-{len(all_results)+1}",
                "title": item["title"],
                "portal": "RAMP LA",
                "portal_category": "City",
                "details_url": item["detail_url"],
                "summary": item.get("full_text", item["title"])[:200],
                "rfp_category": classify_from_title(item["title"]),
                "closing_date": item.get("due_date", ""),
                "open_date": item.get("post_date", ""),
                "office": item.get("organization", "City of Los Angeles"),
                "scraped_at": datetime.utcnow().isoformat(),
            }

            # Try to get detail page
            try:
                detail_url = item["detail_url"]
                if detail_url and "rampla.org" in detail_url:
                    print(f"    Detail: {item['title'][:50]}...")
                    await page.goto(detail_url, timeout=20000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)

                    detail = await page.evaluate("""() => {
                        const data = {};
                        const allText = document.body.innerText;

                        // Extract structured fields
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
                        const descEl = document.querySelector('.description, [class*="desc"], .prose, .content');
                        if (descEl) {
                            data.description = descEl.innerText.trim().substring(0, 3000);
                        }

                        data.page_text = allText.substring(0, 5000);
                        return data;
                    }""")

                    if detail.get("description"):
                        result["summary"] = detail["description"][:500]
                        result["description"] = detail["description"]

                    for key, value in detail.items():
                        if key.startswith("_") or key in ("page_text", "description"):
                            continue
                        kl = key.lower()
                        if "close" in kl or "deadline" in kl or "due" in kl:
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

            all_results.append(result)

        await browser.close()

    output_path = EXPORT_DIR / f"rampla_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\nRAMP LA: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_rampla())
    print(f"Total scraped: {len(results)}")
