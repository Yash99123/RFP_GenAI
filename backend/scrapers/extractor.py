"""
RFP Detail Extractor — EITACIES RFP GenAI
Extracts full details from SAM.gov and other portal pages.
"""
import asyncio
import json
import os
import re
import sys
import tempfile
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

PROJECT_DIR = Path(__file__).parent.parent.parent

CATEGORIES = [
    "AI / Machine Learning",
    "Software Development",
    "IT Infrastructure",
    "Cloud Services",
    "Cybersecurity",
    "Data Analytics",
    "IT Staffing",
    "Consulting / Advisory",
    "Training & Education",
    "Research & Development",
    "Professional Services",
    "Healthcare IT",
    "Digital Transformation",
    "Network / Telecom",
    "Other Technology",
]


def classify_rfp(title, description="", pdf_text=""):
    """Classify an RFP into a category based on its content."""
    text = f"{title} {description} {pdf_text}".lower()

    if any(kw in text for kw in ["artificial intelligence", "machine learning", "ai ", "deep learning", "nlp", "natural language", "llm", "generative ai", "neural", "cognitive"]):
        return "AI / Machine Learning"
    if any(kw in text for kw in ["software development", "software engineering", "application development", "custom software", "web development", "mobile app"]):
        return "Software Development"
    if any(kw in text for kw in ["infrastructure", "server", "network hardware", "data center", "storage", "vpn", "firewall"]):
        return "IT Infrastructure"
    if any(kw in text for kw in ["cloud", "aws", "azure", "saas", "iaas", "paas", "hosting", "migration"]):
        return "Cloud Services"
    if any(kw in text for kw in ["cybersecurity", "security", "penetration", "vulnerability", "compliance", "audit", "siem", "soc"]):
        return "Cybersecurity"
    if any(kw in text for kw in ["data analytics", "business intelligence", "data science", "predictive", "reporting", "database", "data engineer"]):
        return "Data Analytics"
    if any(kw in text for kw in ["staffing", "staff augmentation", "temporary personnel", "contract personnel", "workforce", "manpower", "resource augmentation"]):
        return "IT Staffing"
    if any(kw in text for kw in ["consulting", "advisory", "professional services", "management consulting", "strategic planning"]):
        return "Consulting / Advisory"
    if any(kw in text for kw in ["training", "education", "e-learning", "lms", "instructor", "courseware"]):
        return "Training & Education"
    if any(kw in text for kw in ["research", "r&d", "innovation", "pilot", "proof of concept", "study"]):
        return "Research & Development"
    if any(kw in text for kw in ["healthcare", "health", "medical", "clinical", "hipaa", "ehr"]):
        return "Healthcare IT"
    if any(kw in text for kw in ["digital transformation", "modernization", "modernisation", "digitization"]):
        return "Digital Transformation"
    if any(kw in text for kw in ["telecom", "telecommunications", "fiber", "broadband", "wireless", "bandwidth"]):
        return "Network / Telecom"
    return "Other Technology"


def generate_summary(title, description="", pdf_text=""):
    """Generate a meaningful one-line summary from available text."""
    # Clean title
    title = re.sub(r'\s+', ' ', title).strip()

    # If we have description, use first meaningful sentence
    if description:
        desc = re.sub(r'\s+', ' ', description).strip()
        sentences = re.split(r'(?<=[.!?])\s+', desc)
        for sent in sentences:
            sent = sent.strip()
            if len(sent) > 20 and len(sent) < 250 and not sent.startswith(('http', 'www', 'click')):
                return sent

    # If we have PDF text, use first meaningful sentence
    if pdf_text:
        pdf = re.sub(r'\s+', ' ', pdf_text).strip()
        sentences = re.split(r'(?<=[.!?])\s+', pdf)
        for sent in sentences:
            sent = sent.strip()
            if len(sent) > 20 and len(sent) < 250:
                return sent

    # Fallback: clean up the title to be a summary
    if len(title) > 100:
        # Try to find a meaningful portion
        parts = re.split(r'[\-–|]', title)
        for part in parts:
            part = part.strip()
            if len(part) > 15:
                return part

    return title if title else "RFP opportunity"


def extract_dates_from_text(text):
    """Extract open and closing dates from text."""
    dates = {"open_date": None, "closing_date": None}

    # Common date patterns
    closing_patterns = [
        r'(?:closing|due|deadline|response due|submission due|bid due|expires?)[\s:]+(\w+\s+\d{1,2},?\s+\d{4})',
        r'(?:closing|due|deadline|response due|submission due|bid due|expires?)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(?:closing|due|deadline|response due|submission due|bid due|expires?)[\s:]+(\d{4}-\d{2}-\d{2})',
        r'(?:close|end)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
    ]

    open_patterns = [
        r'(?:posted|open|release|issue|published)[\s:]+(\w+\s+\d{1,2},?\s+\d{4})',
        r'(?:posted|open|release|issue|published)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(?:posted|open|release|issue|published)[\s:]+(\d{4}-\d{2}-\d{2})',
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

    return dates


async def extract_sam_gov_details(page, url):
    """Extract details from a SAM.gov opportunity page."""
    details = {
        "description": "",
        "open_date": None,
        "closing_date": None,
        "contact_name": "",
        "contact_email": "",
        "office": "",
        "budget_text": "",
    }

    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # Extract full page text
        page_text = await page.evaluate("() => document.body.innerText")

        # Extract dates
        date_info = extract_dates_from_text(page_text)
        details["open_date"] = date_info["open_date"]
        details["closing_date"] = date_info["closing_date"]

        # Extract contact email
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', page_text)
        if email_match:
            details["contact_email"] = email_match.group(0)

        # Extract description from specific SAM.gov elements
        desc_selectors = [
            ".description-text", ".opp-description", "[class*='description']",
            ".usa-accordion__content", ".sds-page-level-content"
        ]
        for sel in desc_selectors:
            el = await page.query_selector(sel)
            if el:
                desc = await el.inner_text()
                if len(desc) > 30:
                    details["description"] = desc[:1000]
                    break

        # If no description found, use page text
        if not details["description"]:
            paragraphs = [p.strip() for p in page_text.split("\n") if len(p.strip()) > 40]
            # Skip navigation paragraphs
            meaningful = [p for p in paragraphs if not any(skip in p.lower() for skip in
                ['skip to', 'sign in', 'search', 'menu', 'home', 'help', 'contact us',
                 'cookie', 'privacy', 'accessibility', 'sitemap', 'federal'])]
            if meaningful:
                details["description"] = " ".join(meaningful[:3])[:800]

        # Extract budget
        budget_match = re.search(r'(?:budget|estimated|value|contract|amount|ceiling)[\s:]*\$[\d,]+', page_text, re.IGNORECASE)
        if budget_match:
            details["budget_text"] = budget_match.group(0).strip()

        # Extract office/agency
        office_match = re.search(r'(?:office|agency|department|bureau)[\s:]+([^\n]{10,60})', page_text, re.IGNORECASE)
        if office_match:
            details["office"] = office_match.group(1).strip()

    except Exception as e:
        details["description"] = f"Extraction error: {str(e)[:200]}"

    return details


async def enrich_record(page, record):
    """Enrich a single record by visiting its page."""
    url = record.get("details_url", "")
    if not url or not url.startswith("http"):
        return record

    portal = record.get("portal", "")
    title = record.get("title", "")

    print(f"    Extracting: {title[:50]}...")

    if portal == "SAM.gov":
        details = await extract_sam_gov_details(page, url)
    else:
        # Generic extraction for other portals
        try:
            await page.goto(url, timeout=20000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            page_text = await page.evaluate("() => document.body.innerText")
            details = extract_dates_from_text(page_text)
            details["description"] = " ".join([p.strip() for p in page_text.split("\n") if len(p.strip()) > 40][:3])[:800]
            details["contact_email"] = ""
            details["contact_name"] = ""
            details["office"] = ""
            details["budget_text"] = ""
        except Exception as e:
            details = {"description": str(e)[:200], "open_date": None, "closing_date": None,
                       "contact_email": "", "contact_name": "", "office": "", "budget_text": ""}

    # Update record
    record["description"] = details.get("description", "") or record.get("description", "")
    record["summary"] = generate_summary(title, details.get("description", ""))
    record["rfp_category"] = classify_rfp(title, details.get("description", ""))
    record["open_date"] = details.get("open_date")
    record["closing_date"] = details.get("closing_date") or record.get("closing_date")
    record["contact_email"] = details.get("contact_email", "")
    record["contact_name"] = details.get("contact_name", "")
    record["office"] = details.get("office", "") or record.get("office", "")
    record["budget_text"] = details.get("budget_text", "")

    return record


async def enrich_all_records(records, max_records=100):
    """Enrich records by visiting pages."""
    from playwright.async_api import async_playwright

    enriched = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        for i, record in enumerate(records[:max_records]):
            try:
                enriched_record = await enrich_record(page, record)
                enriched.append(enriched_record)
                if (i + 1) % 10 == 0:
                    print(f"  Processed {i+1}/{min(len(records), max_records)} records")
            except Exception as e:
                print(f"  Error: {str(e)[:50]}")
                enriched.append(record)

        await browser.close()

    return enriched
