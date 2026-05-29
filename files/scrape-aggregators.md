---
name: scrape-aggregators
description: Scrapes all aggregator and marketplace procurement portals for EITACIES. Covers BidNet Direct, BidPrime, Bonfire, OpenGov, Planet Bids, Central Bidding, Public Purchase, Unison Marketplace, RFP Delivery, RFP Mart, Covendis, Ingram, Bids and Tenders, Kawartha Lakes, City of Waterloo, Vendor Registry, Vendor Registry Okaloosa, and EI Cooperative Services.
version: 1.0.0
metadata:
  hermes:
    tags: [eitacies, rfp, aggregators, marketplace, scraping]
    category: automation
    requires_toolsets: [terminal, web, file_system]
---

# Aggregators & Marketplace Portals Scraper

## Output
`~/RFP_GenAI/exports/raw/aggregators_YYYY-MM-DD.json`

## Portals Covered

| Portal | Type | Geography |
|---|---|---|
| BidNet Direct | Aggregator | US + Canada |
| BidPrime | Aggregator | US Federal/State |
| Bonfire | Platform | US + Canada |
| OpenGov | Platform | US |
| Planet Bids | Platform | US |
| Central Bidding | Aggregator | US |
| Public Purchase | Aggregator | US |
| Unison Marketplace | Marketplace | US Federal |
| RFP Delivery | Aggregator | US |
| RFP Mart | Aggregator | US |
| Covendis | Platform | US |
| Ingram | Marketplace | US |
| Bids and Tenders | Aggregator | Canada |
| Kawartha Lakes | Municipal | Canada (ON) |
| City of Waterloo | Municipal | Canada (ON) |
| Vendor Registry | Registry | US |
| Vendor Registry Okaloosa | Registry | US (FL) |
| EI Cooperative Services | Cooperative | US |

---

## BidNet Direct (Priority — covers 100s of agencies)

```python
from playwright.async_api import async_playwright
import asyncio, os, json, re
from datetime import datetime

async def scrape_bidnet_direct():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://www.bidnetdirect.com/login")
        await page.wait_for_load_state("networkidle")
        await page.fill('#email, input[name="email"]', os.environ["BIDNET_DIRECT_USERNAME"])
        await page.fill('input[type="password"]',      os.environ["BIDNET_DIRECT_PASSWORD"])
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")

        keywords = [
            "artificial intelligence", "machine learning", "software development",
            "cloud services", "IT services", "cybersecurity", "data analytics",
            "digital transformation", "technology consulting"
        ]
        results = []
        seen = set()

        for kw in keywords:
            await page.goto(f"https://www.bidnetdirect.com/public/solicitations/search?keyword={kw.replace(' ', '+')}")
            await page.wait_for_load_state("networkidle")

            items = await page.query_selector_all(".solicitation-list-item, .bid-list-item")
            for item in items:
                try:
                    sol_id = await item.get_attribute("data-solicitation-id") or ""
                    if sol_id in seen:
                        continue
                    seen.add(sol_id)

                    title_el  = await item.query_selector(".title, .solicitation-title")
                    agency_el = await item.query_selector(".agency, .organization")
                    close_el  = await item.query_selector(".closing-date, .due-date")
                    link_el   = await item.query_selector("a")

                    title = (await title_el.inner_text()).strip() if title_el else ""
                    if not title:
                        continue

                    results.append({
                        "rfp_id":      sol_id or f"BIDNET-{datetime.utcnow().strftime('%Y%m%d')}-{re.sub(r'[^a-z0-9]','-',title.lower())[:15]}",
                        "title":       title,
                        "agency":      (await agency_el.inner_text()).strip() if agency_el else "",
                        "portal":      "BidNet Direct",
                        "due_date":    (await close_el.inner_text()).strip() if close_el else "",
                        "details_url": await link_el.get_attribute("href") if link_el else "",
                        "keyword_matched": kw,
                        "country": "US",
                    })
                except Exception:
                    continue

        await browser.close()
        print(f"  BidNet Direct: {len(results)} RFPs")
        return results
```

---

## Bonfire + OpenGov (Platform-based portals)

```python
async def scrape_bonfire():
    """Bonfire serves many municipalities — single login, search across all"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://gobonfire.com/login")
        await page.wait_for_load_state("networkidle")
        await page.fill('input[name="email"]', os.environ["BONFIRE_USERNAME"])
        await page.fill('input[type="password"]', os.environ["BONFIRE_PASSWORD"])
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")

        results = []
        keywords = ["AI", "software", "IT services", "cloud", "technology"]
        for kw in keywords:
            await page.goto(f"https://gobonfire.com/portal/public?q={kw}")
            await page.wait_for_load_state("networkidle")

            items = await page.query_selector_all(".opportunity-card, .bid-card, .rfp-card")
            for item in items:
                try:
                    title_el = await item.query_selector("h2, h3, .title")
                    link_el  = await item.query_selector("a")
                    due_el   = await item.query_selector(".date, .closing")

                    title = (await title_el.inner_text()).strip() if title_el else ""
                    href  = await link_el.get_attribute("href") if link_el else ""

                    results.append({
                        "rfp_id":      f"BONFIRE-{datetime.utcnow().strftime('%Y%m%d')}-{re.sub(r'[^a-z0-9]','-',title.lower())[:15]}",
                        "title":       title,
                        "portal":      "Bonfire",
                        "due_date":    (await due_el.inner_text()).strip() if due_el else "",
                        "details_url": f"https://gobonfire.com{href}" if href and not href.startswith("http") else href,
                        "keyword_matched": kw,
                        "country": "US",
                    })
                except Exception:
                    continue

        await browser.close()
        print(f"  Bonfire: {len(results)} RFPs")
        return results


async def scrape_opengov():
    """OpenGov serves many US municipalities"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://procurement.opengov.com/login")
        await page.fill('input[name="email"]', os.environ["OPENGOV_USERNAME"])
        await page.fill('input[type="password"]', os.environ["OPENGOV_PASSWORD"])
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")

        results = []
        keywords = ["artificial intelligence", "software", "IT services", "cloud"]
        for kw in keywords:
            await page.goto(f"https://procurement.opengov.com/portal?search={kw.replace(' ', '+')}")
            await page.wait_for_load_state("networkidle")

            items = await page.query_selector_all(".opportunity-item, .solicitation-card")
            for item in items:
                try:
                    title_el = await item.query_selector(".title, h3")
                    link_el  = await item.query_selector("a")
                    due_el   = await item.query_selector(".due-date")

                    title = (await title_el.inner_text()).strip() if title_el else ""
                    href  = await link_el.get_attribute("href") if link_el else ""

                    results.append({
                        "rfp_id":      f"OPENGOV-{datetime.utcnow().strftime('%Y%m%d')}-{re.sub(r'[^a-z0-9]','-',title.lower())[:15]}",
                        "title":       title,
                        "portal":      "OpenGov",
                        "due_date":    (await due_el.inner_text()).strip() if due_el else "",
                        "details_url": href,
                        "keyword_matched": kw,
                        "country": "US",
                    })
                except Exception:
                    continue

        await browser.close()
        print(f"  OpenGov: {len(results)} RFPs")
        return results
```

---

## Remaining Aggregators (Central Bidding, Planet Bids, Public Purchase, etc.)

```python
REMAINING_AGGREGATORS = [
    { "name": "Central Bidding",     "url": "https://www.centralbidding.com/",           "u_env": "CENTRAL_BIDDING_USERNAME",    "p_env": "CENTRAL_BIDDING_PASSWORD"    },
    { "name": "Planet Bids",         "url": "https://www.planetbids.com/portal/",        "u_env": "PLANET_BIDS_USERNAME",        "p_env": "PLANET_BIDS_PASSWORD"        },
    { "name": "Public Purchase",     "url": "https://www.publicpurchase.com/gems/",      "u_env": "PUBLIC_PURCHASE_USERNAME",    "p_env": "PUBLIC_PURCHASE_PASSWORD"    },
    { "name": "Unison Marketplace",  "url": "https://unisonmarketplace.com/",            "u_env": "UNISON_MARKETPLACE_USERNAME", "p_env": "UNISON_MARKETPLACE_PASSWORD" },
    { "name": "RFP Delivery",        "url": "https://www.rfpdelivery.com/",              "u_env": "RFP_DELIVERY_USERNAME",       "p_env": "RFP_DELIVERY_PASSWORD"       },
    { "name": "RFP Mart",            "url": "https://www.rfpmart.com/",                  "u_env": "RFP_MART_USERNAME",           "p_env": "RFP_MART_PASSWORD"           },
    { "name": "Covendis",            "url": "https://www.covendis.com/",                 "u_env": "COVENDIS_USERNAME",           "p_env": "COVENDIS_PASSWORD"           },
    { "name": "Vendor Registry",     "url": "https://www.vendorregistry.com/",           "u_env": "VENDOR_REGISTRY_USERNAME",    "p_env": "VENDOR_REGISTRY_PASSWORD"    },
    { "name": "EI Cooperative",      "url": "https://ei.org/",                           "u_env": "EI_COOPERATIVE_USERNAME",     "p_env": "EI_COOPERATIVE_PASSWORD"     },
    { "name": "Bids and Tenders",    "url": "https://bidsandtenders.ca/",                "u_env": "BIDS_AND_TENDERS_USERNAME",   "p_env": "BIDS_AND_TENDERS_PASSWORD",  "country": "Canada" },
    { "name": "Kawartha Lakes",      "url": "https://www.kawarthalakes.ca/en/doing-business/bids-tenders.aspx", "u_env": "KAWARTHA_LAKES_USERNAME", "p_env": "KAWARTHA_LAKES_PASSWORD", "country": "Canada" },
    { "name": "City of Waterloo",    "url": "https://www.waterloo.ca/en/business/bids-and-tenders.aspx",        "u_env": "CITY_OF_WATERLOO_USERNAME","p_env": "CITY_OF_WATERLOO_PASSWORD","country": "Canada"},
]

# Use generic Firecrawl scraping for these — most have public listing pages
async def scrape_aggregator_firecrawl(portal):
    import requests
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        print(f"  No Firecrawl key — skipping {portal['name']}")
        return []

    resp = requests.post(
        "https://api.firecrawl.dev/v0/scrape",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"url": portal["url"], "pageOptions": {"includeHtml": False}},
        timeout=30
    )
    if resp.status_code != 200:
        print(f"  Firecrawl failed for {portal['name']}: {resp.status_code}")
        return []

    data = resp.json()
    content = data.get("data", {}).get("content", "")

    # Extract any lines that look like RFP titles near keywords
    results = []
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    kw_set = {"artificial intelligence", "machine learning", "software", "IT", "cloud", "technology", "digital"}
    for i, line in enumerate(lines):
        if any(kw.lower() in line.lower() for kw in kw_set) and len(line) > 20:
            results.append({
                "rfp_id":      f"{portal['name'][:8].replace(' ','-')}-{datetime.utcnow().strftime('%Y%m%d')}-{re.sub(r'[^a-z0-9]','-',line.lower())[:15]}",
                "title":       line[:200],
                "portal":      portal["name"],
                "country":     portal.get("country", "US"),
                "details_url": portal["url"],
            })
    print(f"  {portal['name']}: {len(results)} potential RFPs (Firecrawl)")
    return results
```

---

## Master Aggregator Runner

```python
async def run_all_aggregators():
    all_results = []

    print("BidNet Direct...")
    all_results.extend(await scrape_bidnet_direct())
    await asyncio.sleep(3)

    print("Bonfire...")
    all_results.extend(await scrape_bonfire())
    await asyncio.sleep(3)

    print("OpenGov...")
    all_results.extend(await scrape_opengov())
    await asyncio.sleep(3)

    for portal in REMAINING_AGGREGATORS:
        print(f"{portal['name']}...")
        all_results.extend(await scrape_aggregator_firecrawl(portal))
        await asyncio.sleep(2)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    output_path = f"/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/exports/raw/aggregators_{today}.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nAggregators: Saved {len(all_results)} total records")

asyncio.run(run_all_aggregators())
```

## Pitfalls
- BidNet Direct is the highest-yield aggregator — prioritise debugging here first
- Bonfire and OpenGov require valid subscriptions — if login fails, contact portal support
- Firecrawl fallback works well for public listing pages but may miss detail fields
- Canadian portals (Bids and Tenders, Kawartha Lakes, Waterloo) return fewer AI/tech RFPs — low priority
