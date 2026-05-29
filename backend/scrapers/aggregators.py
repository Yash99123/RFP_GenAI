"""
Aggregators Scraper — EITACIES RFP GenAI
Covers: BidNet Direct, BidPrime, Bonfire, OpenGov, Planet Bids, etc.
"""
import asyncio
import json
import os
import sys
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

PROJECT_DIR = Path(__file__).parent.parent.parent
EXPORT_DIR = PROJECT_DIR / "exports" / "raw"

KEYWORDS = [
    "artificial intelligence", "machine learning", "software development",
    "cloud services", "IT services", "cybersecurity", "data analytics",
    "digital transformation", "technology consulting"
]


async def scrape_bidnet_direct(page):
    """Scrape BidNet Direct with login."""
    results = []
    try:
        print("  BidNet Direct: logging in...")
        await page.goto("https://www.bidnetdirect.com/login", timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        try:
            await page.fill('#email, input[name="email"]', os.environ.get("BIDNET_DIRECT_USERNAME", ""))
            await page.fill('input[type="password"]', os.environ.get("BIDNET_DIRECT_PASSWORD", ""))
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  BidNet Direct: login failed ({str(e)[:50]}), trying public search...")

        for kw in KEYWORDS[:3]:
            try:
                url = f"https://www.bidnetdirect.com/public/solicitations/search?keyword={kw.replace(' ', '+')}"
                await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                page_data = await page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    const rows = document.querySelectorAll('.solicitation-list-item, .bid-list-item, table tbody tr, .list-item');
                    for (const row of rows) {
                        const text = row.innerText.trim();
                        if (text.length > 10) {
                            const firstLine = text.split('\\n')[0].trim();
                            if (!seen.has(firstLine) && firstLine.length > 5) {
                                seen.add(firstLine);
                                const link = row.querySelector('a[href]');
                                items.push({
                                    title: firstLine.substring(0, 200),
                                    url: link ? link.getAttribute('href') : ''
                                });
                            }
                        }
                    }
                    // Also try links
                    const links = document.querySelectorAll('a[href*="solicitation"], a[href*="bid"]');
                    for (const link of links) {
                        const text = link.innerText.trim();
                        if (text.length > 10 && !seen.has(text)) {
                            seen.add(text);
                            items.push({
                                title: text.substring(0, 200),
                                url: link.getAttribute('href')
                            });
                        }
                    }
                    return items;
                }""")

                for item in page_data:
                    full_url = item["url"]
                    if full_url and not full_url.startswith("http"):
                        full_url = "https://www.bidnetdirect.com" + full_url
                    results.append({
                        "rfp_id": f"BIDNET-{len(results)+1}",
                        "title": item["title"],
                        "agency": "",
                        "portal": "BidNet Direct",
                        "portal_category": "Aggregator",
                        "due_date": "",
                        "posted_date": "",
                        "details_url": full_url,
                        "description": "",
                        "keyword_matched": kw,
                        "scraped_at": datetime.utcnow().isoformat(),
                    })
            except Exception as e:
                print(f"    BidNet keyword '{kw}' failed: {str(e)[:50]}")

        print(f"  BidNet Direct: {len(results)} RFPs")

    except Exception as e:
        print(f"  ERROR BidNet Direct: {str(e)[:80]}")

    return results


async def scrape_bonfire(page):
    """Scrape Bonfire (public procurement platform)."""
    results = []
    try:
        print("  Bonfire: loading...")
        await page.goto("https://www.bonfirehub.com/opportunities", timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        page_data = await page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            const links = document.querySelectorAll('a[href]');
            for (const link of links) {
                const text = link.innerText.trim();
                const href = link.getAttribute('href');
                if (text.length > 10 && /bid|rfp|solicitation|opportunity|procurement/i.test(text) && !seen.has(text)) {
                    seen.add(text);
                    items.push({
                        title: text.substring(0, 200),
                        url: href.startsWith('http') ? href : new URL(href, window.location.origin).href
                    });
                }
            }
            return items;
        }""")

        for item in page_data:
            results.append({
                "rfp_id": f"BONFIRE-{len(results)+1}",
                "title": item["title"],
                "agency": "",
                "portal": "Bonfire",
                "portal_category": "Aggregator",
                "due_date": "",
                "posted_date": "",
                "details_url": item["url"],
                "description": "",
                "keyword_matched": "",
                "scraped_at": datetime.utcnow().isoformat(),
            })

        print(f"  Bonfire: {len(results)} RFPs")

    except Exception as e:
        print(f"  ERROR Bonfire: {str(e)[:80]}")

    return results


async def scrape_opengov(page):
    """Scrape OpenGov Procurement."""
    results = []
    try:
        print("  OpenGov: loading...")
        await page.goto("https://procurement.opengov.com/bids", timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        page_data = await page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            const links = document.querySelectorAll('a[href]');
            for (const link of links) {
                const text = link.innerText.trim();
                const href = link.getAttribute('href');
                if (text.length > 10 && /bid|rfp|solicitation|opportunity|procurement/i.test(text) && !seen.has(text)) {
                    seen.add(text);
                    items.push({
                        title: text.substring(0, 200),
                        url: href.startsWith('http') ? href : new URL(href, window.location.origin).href
                    });
                }
            }
            return items;
        }""")

        for item in page_data:
            results.append({
                "rfp_id": f"OPENGOV-{len(results)+1}",
                "title": item["title"],
                "agency": "",
                "portal": "OpenGov",
                "portal_category": "Aggregator",
                "due_date": "",
                "posted_date": "",
                "details_url": item["url"],
                "description": "",
                "keyword_matched": "",
                "scraped_at": datetime.utcnow().isoformat(),
            })

        print(f"  OpenGov: {len(results)} RFPs")

    except Exception as e:
        print(f"  ERROR OpenGov: {str(e)[:80]}")

    return results


async def scrape_planetbids(page):
    """Scrape Planet Bids."""
    results = []
    try:
        print("  Planet Bids: loading...")
        await page.goto("https://www.planetbids.com/portal/portal.cfm?CompanyID=AB1480", timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        page_data = await page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            const links = document.querySelectorAll('a[href]');
            for (const link of links) {
                const text = link.innerText.trim();
                const href = link.getAttribute('href');
                if (text.length > 10 && /bid|rfp|solicitation|opportunity|procurement/i.test(text) && !seen.has(text)) {
                    seen.add(text);
                    items.push({
                        title: text.substring(0, 200),
                        url: href.startsWith('http') ? href : new URL(href, window.location.origin).href
                    });
                }
            }
            return items;
        }""")

        for item in page_data:
            results.append({
                "rfp_id": f"PLANETBIDS-{len(results)+1}",
                "title": item["title"],
                "agency": "",
                "portal": "Planet Bids",
                "portal_category": "Aggregator",
                "due_date": "",
                "posted_date": "",
                "details_url": item["url"],
                "description": "",
                "keyword_matched": "",
                "scraped_at": datetime.utcnow().isoformat(),
            })

        print(f"  Planet Bids: {len(results)} RFPs")

    except Exception as e:
        print(f"  ERROR Planet Bids: {str(e)[:80]}")

    return results


async def scrape_aggregators():
    """Scrape all aggregator portals."""
    from playwright.async_api import async_playwright

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # BidNet Direct (priority — largest aggregator)
        results = await scrape_bidnet_direct(page)
        all_results.extend(results)

        # Bonfire
        results = await scrape_bonfire(page)
        all_results.extend(results)

        # OpenGov
        results = await scrape_opengov(page)
        all_results.extend(results)

        # Planet Bids
        results = await scrape_planetbids(page)
        all_results.extend(results)

        await browser.close()

    output_path = EXPORT_DIR / f"aggregators_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nAggregators: Saved {len(all_results)} records")
    return all_results


if __name__ == "__main__":
    results = asyncio.run(scrape_aggregators())
    print(f"Total scraped: {len(results)}")
