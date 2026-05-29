"""
TIPS USA Scraper — EITACIES RFP GenAI
Scrapes TIPS (The Interlocal Purchasing System) bid schedule.
URL: https://www.tips-usa.com/vendors/bid-schedule
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


async def scrape_tips_usa():
    """Scrape TIPS USA bid schedule."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        print("  TIPS USA: loading bid schedule...")
        await page.goto(
            "https://www.tips-usa.com/vendors/bid-schedule",
            timeout=30000,
            wait_until="domcontentloaded"
        )
        await page.wait_for_timeout(5000)

        # TIPS page has no tables - data is just text lines
        # Format: Category, Contract#, Exp Date, Posting Date, Closing Date
        body_text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in body_text.split('\n') if l.strip()]

        # Find the section with bid data (after headers)
        # Headers are: Category, Contract, Exp. Date, Posting Date, Closing Date
        header_idx = -1
        for i, line in enumerate(lines):
            if line == "Category" and i + 4 < len(lines):
                if lines[i + 1] == "Contract":
                    header_idx = i
                    break

        if header_idx >= 0:
            # Skip header row
            data_lines = lines[header_idx + 5:]

            # Parse in groups of 5: Category, Contract, Exp Date, Posting Date, Closing Date
            i = 0
            while i + 4 < len(data_lines):
                category = data_lines[i]
                contract = data_lines[i + 1]
                exp_date = data_lines[i + 2]
                posting_date = data_lines[i + 3]
                closing_date = data_lines[i + 4]

                # Validate: contract should be numeric, dates should have slashes
                if re.match(r'^\d{6,8}$', contract) and '/' in closing_date:
                    all_results.append({
                        "rfp_id": f"TIPS-{contract}",
                        "title": category[:300],
                        "portal": "TIPS USA",
                        "portal_category": "Aggregator",
                        "details_url": "https://www.tips-usa.com/vendors/bid-schedule",
                        "summary": category[:200],
                        "rfp_category": classify_from_title(category),
                        "closing_date": closing_date,
                        "open_date": posting_date,
                        "office": "TIPS Cooperative",
                        "scraped_at": datetime.utcnow().isoformat(),
                    })
                    i += 5
                else:
                    i += 1
        else:
            # Fallback: try regex on full text
            # Pattern: category text followed by 6-8 digit contract number
            entries = re.findall(
                r'([A-Z][^\n]{15,})\n(\d{6,8})\n(\d{1,2}/\d{1,2}/\d{2,4})\n(\d{1,2}/\d{1,2}/\d{2,4})\n(\d{1,2}/\d{1,2}/\d{2,4})',
                body_text
            )
            for cat, contract, exp, post, close in entries:
                all_results.append({
                    "rfp_id": f"TIPS-{contract}",
                    "title": cat.strip()[:300],
                    "portal": "TIPS USA",
                    "portal_category": "Aggregator",
                    "details_url": "https://www.tips-usa.com/vendors/bid-schedule",
                    "summary": cat.strip()[:200],
                    "rfp_category": classify_from_title(cat),
                    "closing_date": close,
                    "open_date": post,
                    "office": "TIPS Cooperative",
                    "scraped_at": datetime.utcnow().isoformat(),
                })

        print(f"  TIPS USA: found {len(all_results)} listings")

        await browser.close()

    output_path = EXPORT_DIR / f"tips_usa_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\nTIPS USA: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_tips_usa())
    print(f"Total scraped: {len(results)}")
