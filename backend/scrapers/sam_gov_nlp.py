"""
SAM.gov Scraper with NLP Summarization — EITACIES RFP GenAI
Uses Playwright to search SAM.gov, extracts details, and uses LLM for summaries.
"""
import asyncio
import json
import os
import re
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

PROJECT_DIR = Path(__file__).parent.parent.parent
EXPORT_DIR = PROJECT_DIR / "exports" / "raw"

# IT staffing focused keywords + general AI/tech keywords
KEYWORDS = [
    # IT Staffing keywords
    "staff augmentation",
    "staffing services",
    "contract personnel",
    "workforce solutions",
    "resource augmentation",
    "temporary IT staff",
    "IT staffing",
    "technology staffing",
    # AI/ML keywords
    "artificial intelligence",
    "machine learning",
    "data analytics",
    "cloud services",
    "cybersecurity",
    "software development",
    "digital transformation",
    "IT modernization",
]

# EITACIES categories
CATEGORIES = [
    "AI / Machine Learning", "Software Development", "IT Infrastructure",
    "Cloud Services", "Cybersecurity", "Data Analytics", "IT Staffing",
    "Consulting / Advisory", "Training & Education", "Research & Development",
    "Professional Services", "Healthcare IT", "Digital Transformation",
    "Network / Telecom", "Other Technology",
]


def classify_from_text(title, description=""):
    """Classify RFP from title and description."""
    text = f"{title} {description}".lower()

    if any(kw in text for kw in ["staff augmentation", "staffing", "workforce", "contract personnel", "resource augmentation", "manpower"]):
        return "IT Staffing"
    if any(kw in text for kw in ["artificial intelligence", "machine learning", "ai ", "ml ", "deep learning", "nlp", "llm", "cognitive", "neural"]):
        return "AI / Machine Learning"
    if any(kw in text for kw in ["software development", "software engineering", "application development", "web development", "mobile app"]):
        return "Software Development"
    if any(kw in text for kw in ["infrastructure", "server", "network", "hardware", "data center", "storage"]):
        return "IT Infrastructure"
    if any(kw in text for kw in ["cloud", "aws", "azure", "saas", "hosting", "migration"]):
        return "Cloud Services"
    if any(kw in text for kw in ["cybersecurity", "security", "cyber", "penetration", "vulnerability", "siem"]):
        return "Cybersecurity"
    if any(kw in text for kw in ["data", "analytics", "intelligence", "reporting", "database", "data engineer"]):
        return "Data Analytics"
    if any(kw in text for kw in ["consulting", "advisory", "professional services", "management consulting"]):
        return "Consulting / Advisory"
    if any(kw in text for kw in ["training", "education", "instructor", "courseware"]):
        return "Training & Education"
    if any(kw in text for kw in ["research", "r&d", "innovation", "pilot", "experiment"]):
        return "Research & Development"
    if any(kw in text for kw in ["healthcare", "health", "medical", "clinical", "hospital"]):
        return "Healthcare IT"
    if any(kw in text for kw in ["digital", "modernization", "transformation"]):
        return "Digital Transformation"
    if any(kw in text for kw in ["telecom", "fiber", "broadband", "wireless"]):
        return "Network / Telecom"
    return "Other Technology"


def extract_dates(text):
    """Extract all dates from text with multiple formats."""
    dates = {"open_date": None, "closing_date": None, "questions_deadline": None}

    # Closing date patterns
    closing_patterns = [
        r'(?:closing|due|deadline|response due|submission due|bid due|expires?|close date)[\s:]+(\w+\s+\d{1,2},?\s+\d{4})',
        r'(?:closing|due|deadline|response due|submission due|bid due|expires?|close date)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(?:closing|due|deadline|response due|submission due|bid due|expires?|close date)[\s:]+(\d{4}-\d{2}-\d{2})',
        r'(?:close|end)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:\(.*?close|deadline)',
    ]

    # Open date patterns
    open_patterns = [
        r'(?:posted|open|release|issue|published|synopsis)[\s:]+(\w+\s+\d{1,2},?\s+\d{4})',
        r'(?:posted|open|release|issue|published|synopsis)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(?:posted|open|release|issue|published|synopsis)[\s:]+(\d{4}-\d{2}-\d{2})',
    ]

    # Questions deadline patterns
    questions_patterns = [
        r'(?:questions|inquiries|clarifications)\s+(?:due|deadline)[\s:]+(\w+\s+\d{1,2},?\s+\d{4})',
        r'(?:questions|inquiries|clarifications)\s+(?:due|deadline)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
    ]

    for pattern in closing_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            dates["closing_date"] = match.group(1).strip()
            break

    for pattern in open_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            dates["open_date"] = match.group(1).strip()
            break

    for pattern in questions_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            dates["questions_deadline"] = match.group(1).strip()
            break

    return dates


def nlp_summarize(title, page_text, api_key):
    """Use NLP to generate a meaningful one-line summary from page content."""
    if not api_key:
        return title[:200]

    # Clean page text - remove navigation, headers, footers
    clean_text = re.sub(r'(?:Skip to|Sign in|Search|Menu|Home|Help|Contact|Cookie|Privacy|Accessibility|Sitemap|\.gov means|Official website|How you know).*?\n', '', page_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    # Take first 1500 chars of meaningful content
    if len(clean_text) > 1500:
        clean_text = clean_text[:1500]

    if len(clean_text) < 30:
        return title[:200]

    try:
        resp = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'meta-llama/llama-3.1-8b-instruct',
                'messages': [
                    {'role': 'system', 'content': 'You are a government RFP analyst. Generate a one-sentence summary of the RFP based ONLY on the provided text. Be factual and specific. Mention the agency name, what they are seeking, and any key details. Do not add information not present in the text.'},
                    {'role': 'user', 'content': f'Title: {title}\n\nPage content:\n{clean_text}\n\nProvide a one-sentence factual summary:'}
                ],
                'max_tokens': 150,
            },
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            summary = data['choices'][0]['message']['content'].strip()
            # Remove quotes if present
            summary = summary.strip('"\'')
            return summary[:250]
        else:
            return title[:200]
    except Exception:
        return title[:200]


async def scrape_sam_gov_with_nlp():
    """Scrape SAM.gov with NLP summarization and date extraction."""
    from playwright.async_api import async_playwright

    api_key = os.environ.get('OPENROUTER_API_KEY', '')
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
                print(f"  Searching SAM.gov: '{kw}'...")

                await page.goto("https://sam.gov/search/?index=opp", timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                search_input = await page.query_selector("input#newSimpleSearch, input[type='search']")
                if not search_input:
                    continue

                await search_input.fill(kw)
                await search_input.press("Enter")
                await page.wait_for_timeout(5000)

                # Extract results
                page_results = await page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    const links = document.querySelectorAll('a[href*="/opp/"], a[href*="/workspace/contract/opp/"]');
                    
                    for (const link of links) {
                        const href = link.getAttribute('href');
                        let title = link.innerText.trim();
                        if (!title || title.length < 5 || /^\\(\\d+\\)$/.test(title)) continue;
                        
                        const fullUrl = href.startsWith('/') ? 'https://sam.gov' + href : href;
                        const urlKey = fullUrl.split('?')[0];
                        if (seen.has(urlKey)) continue;
                        seen.add(urlKey);
                        
                        const match = href.match(/\\/opp\\/([a-f0-9]+)/);
                        const noticeId = match ? match[1] : '';
                        
                        items.push({
                            title: title,
                            url: fullUrl,
                            noticeId: noticeId,
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
                            "portal": "SAM.gov",
                            "portal_category": "Federal",
                            "details_url": item["url"],
                            "keyword_matched": kw,
                            "scraped_at": datetime.utcnow().isoformat(),
                        })

                print(f"    {len(page_results)} results, {len(results)} total unique")

            except Exception as e:
                print(f"    Error: {str(e)[:80]}")
                continue

        # Now visit each page to extract details, dates, and NLP summaries
        print(f"\n  Extracting details from {len(results)} pages...")
        for i, record in enumerate(results[:150]):  # Limit to 150
            try:
                print(f"    [{i+1}/{min(len(results),150)}] {record['title'][:50]}...")
                await page.goto(record["details_url"], timeout=25000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                page_text = await page.evaluate("() => document.body.innerText")

                # Extract dates
                dates = extract_dates(page_text)
                record["open_date"] = dates["open_date"]
                record["closing_date"] = dates["closing_date"]

                # Extract contact email
                email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', page_text)
                record["contact_email"] = email_match.group(0) if email_match else ""

                # NLP summary
                record["summary"] = nlp_summarize(record["title"], page_text, api_key)

                # Classify
                record["rfp_category"] = classify_from_text(record["title"], page_text)

                # Extract agency from page
                agency_match = re.search(r'(?:agency|department|bureau|office)[\s:]+([^\n]{5,60})', page_text, re.IGNORECASE)
                record["agency"] = agency_match.group(1).strip() if agency_match else ""

                if (i + 1) % 10 == 0:
                    print(f"  Processed {i+1} pages")

            except Exception as e:
                print(f"    Error: {str(e)[:50]}")
                record["summary"] = record["title"]
                record["rfp_category"] = classify_from_text(record["title"])

        await browser.close()

    # Save results
    output_path = EXPORT_DIR / f"sam_gov_nlp_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nSAM.gov: Saved {len(results)} records with NLP summaries")
    return results


if __name__ == "__main__":
    results = asyncio.run(scrape_sam_gov_with_nlp())
    print(f"Total scraped: {len(results)}")
