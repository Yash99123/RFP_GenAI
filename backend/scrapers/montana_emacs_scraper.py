"""
Montana EMACS (SciQuest/Jaggaer) Scraper — EITACIES RFP GenAI
Scrapes Montana state procurement bids from SciQuest public listing.
URL: https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=StateOfMontana
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


EXTRACT_BIDS_JS = """() => {
    const items = [];
    const rows = document.querySelectorAll('table[aria-label="Search Results"] tbody tr');
    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 2) continue;

        // Cell 0: Status badge
        const statusEl = cells[0].querySelector('.status-badge');
        const status = statusEl ? statusEl.innerText.trim() : '';

        // Cell 1: Details
        const titleLink = cells[1].querySelector('a.btn-link-header, a.btn-link');
        const title = titleLink ? titleLink.innerText.trim() : '';
        const detailUrl = titleLink ? titleLink.getAttribute('href') : '';

        if (!title || title.length < 3) continue;

        // Get all .data-row-content values (dates, type, number, contact)
        const allValues = cells[1].querySelectorAll('.data-row-content');
        const openDate = allValues[0] ? allValues[0].innerText.trim() : '';
        const closeDate = allValues[1] ? allValues[1].innerText.trim() : '';
        const bidType = allValues[2] ? allValues[2].innerText.trim() : '';
        const bidNumber = allValues[3] ? allValues[3].innerText.trim() : '';
        const contact = allValues[4] ? allValues[4].innerText.trim() : '';

        // Get description
        const descEl = cells[1].querySelector('.phx.display-block, .label-mini');
        const description = descEl ? descEl.innerText.trim() : '';

        // Get PDF link
        const pdfLink = allValues[5] ? allValues[5].querySelector('a') : null;
        const pdfUrl = pdfLink ? pdfLink.getAttribute('href') : '';

        // Parse contact name and email
        let contactName = '';
        let contactEmail = '';
        if (contact) {
            const emailMatch = contact.match(/[\\w.-]+@[\\w.-]+\\.\\w+/);
            if (emailMatch) {
                contactEmail = emailMatch[0];
                contactName = contact.replace(contactEmail, '').trim();
            } else {
                contactName = contact;
            }
        }

        items.push({
            title,
            detail_url: detailUrl || '',
            description,
            open_date: openDate,
            close_date: closeDate,
            type: bidType,
            number: bidNumber,
            contact_name: contactName,
            contact_email: contactEmail,
            pdf_url: pdfUrl
        });
    }
    return items;
}"""


async def scrape_montana_emacs():
    """Scrape Montana EMACS public bid listing."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        print("  Montana EMACS: loading public bid listing...")
        await page.goto(
            "https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=StateOfMontana",
            timeout=30000,
            wait_until="domcontentloaded"
        )
        await page.wait_for_timeout(5000)

        # Extract bids from current page
        page_data = await page.evaluate(EXTRACT_BIDS_JS)
        print(f"  Montana EMACS: found {len(page_data)} listings on page 1")

        # Try to get more pages (pagination)
        total_pages = 3  # Known from analysis: 59 results, 20 per page = 3 pages
        for pg in range(2, total_pages + 1):
            try:
                # Click next page or navigate
                await page.evaluate(f"submitPageChange('{pg}','ActiveForm',PhoenixTable.handlePageLimits,'','',{{}});")
                await page.wait_for_timeout(3000)
                more = await page.evaluate(EXTRACT_BIDS_JS)
                print(f"  Montana EMACS: page {pg} found {len(more)} listings")
                page_data.extend(more)
            except Exception as e:
                print(f"  Montana EMACS: page {pg} error: {str(e)[:50]}")
                break

        # Process results
        for item in page_data:
            detail_url = item.get("detail_url", "")

            result = {
                "rfp_id": f"Montana-EMACS-{item.get('number', '') or len(all_results)+1}",
                "title": item["title"],
                "portal": "Montana EMACS",
                "portal_category": "State",
                "details_url": detail_url or "https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=StateOfMontana",
                "summary": item.get("description", item["title"])[:500],
                "description": item.get("description", ""),
                "rfp_category": classify_from_title(item["title"]),
                "closing_date": item.get("close_date", ""),
                "open_date": item.get("open_date", ""),
                "contact_name": item.get("contact_name", ""),
                "contact_email": item.get("contact_email", ""),
                "office": "Montana State",
                "scraped_at": datetime.utcnow().isoformat(),
            }
            all_results.append(result)

        await browser.close()

    output_path = EXPORT_DIR / f"montana_emacs_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\nMontana EMACS: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_montana_emacs())
    print(f"Total scraped: {len(results)}")
