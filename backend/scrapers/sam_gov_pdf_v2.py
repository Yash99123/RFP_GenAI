"""
SAM.gov PDF Reader v2 — EITACIES RFP GenAI
Improved version with better SPA handling and NLP summarization.
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


def nlp_summarize(title, text, api_key):
    """Use NLP to generate a 2-3 sentence summary from RFP text."""
    if not api_key or len(text) < 50:
        return title[:250]

    # Clean text
    clean = re.sub(r'\s+', ' ', text).strip()
    clean = clean[:3000]  # Limit for NLP context

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
                    {'role': 'system', 'content': 'You are a government RFP analyst. Provide a 2-3 sentence factual summary of this RFP. Include: 1) What the agency is seeking, 2) Key requirements or scope, 3) Any important dates or budget info if present. Only use facts from the text. Do not add information not present.'},
                    {'role': 'user', 'content': f'Title: {title}\n\nRFP Content:\n{clean}\n\nProvide a 2-3 sentence summary:'}
                ],
                'max_tokens': 200,
            },
            timeout=25,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data['choices'][0]['message']['content'].strip().strip('"\'')[:400]
        return title[:250]
    except Exception:
        return title[:250]


def nlp_classify(title, text, api_key):
    """Use NLP to classify the RFP category from full content."""
    if not api_key or len(text) < 50:
        return classify_from_title(title)

    clean = re.sub(r'\s+', ' ', text).strip()[:2000]

    categories = [
        "AI / Machine Learning", "Software Development", "IT Infrastructure",
        "Cloud Services", "Cybersecurity", "Data Analytics", "IT Staffing",
        "Consulting / Advisory", "Training & Education", "Research & Development",
        "Professional Services", "Healthcare IT", "Digital Transformation",
        "Network / Telecom", "Other Technology",
    ]

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
                    {'role': 'system', 'content': f'Classify this RFP into exactly one category from this list: {", ".join(categories)}. Respond with ONLY the category name, nothing else.'},
                    {'role': 'user', 'content': f'Title: {title}\n\nContent:\n{clean}\n\nCategory:'}
                ],
                'max_tokens': 30,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            cat = resp.json()['choices'][0]['message']['content'].strip().strip('"\'')
            if cat in categories:
                return cat
        return classify_from_title(title)
    except Exception:
        return classify_from_title(title)


def classify_from_title(title):
    """Fallback classification from title only."""
    t = title.lower()
    if any(kw in t for kw in ["staff augmentation", "staffing", "workforce", "personnel"]):
        return "IT Staffing"
    if any(kw in t for kw in ["artificial intelligence", "machine learning", "ai ", "ml ", "llm", "cognitive"]):
        return "AI / Machine Learning"
    if any(kw in t for kw in ["software", "application", "platform", "web development"]):
        return "Software Development"
    if any(kw in t for kw in ["infrastructure", "server", "network", "hardware"]):
        return "IT Infrastructure"
    if any(kw in t for kw in ["cloud", "aws", "azure", "saas", "hosting"]):
        return "Cloud Services"
    if any(kw in t for kw in ["cybersecurity", "security", "cyber", "vulnerability"]):
        return "Cybersecurity"
    if any(kw in t for kw in ["data", "analytics", "intelligence", "reporting"]):
        return "Data Analytics"
    if any(kw in t for kw in ["research", "r&d", "innovation", "pilot"]):
        return "Research & Development"
    if any(kw in t for kw in ["training", "education", "instructor"]):
        return "Training & Education"
    if any(kw in t for kw in ["healthcare", "health", "medical", "clinical"]):
        return "Healthcare IT"
    if any(kw in t for kw in ["consulting", "advisory", "professional"]):
        return "Consulting / Advisory"
    return "Other Technology"


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using pdfplumber."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages[:15]):  # First 15 pages
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
                except Exception:
                    continue
        return text[:8000]  # Limit to 8000 chars for NLP
    except Exception as e:
        return f"PDF extraction error: {str(e)[:200]}"


def download_pdf(url, timeout=20):
    """Download a PDF from URL and return temp path."""
    try:
        resp = requests.get(url, timeout=timeout, stream=True, allow_redirects=True,
                           headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "").lower()
            if "pdf" in content_type or url.lower().endswith(".pdf"):
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                for chunk in resp.iter_content(8192):
                    tmp.write(chunk)
                tmp.close()
                return tmp.name
    except Exception:
        pass
    return None


def extract_dates_from_text(text):
    """Extract closing and open dates from text."""
    closing_date = None
    open_date = None
    
    # Closing date patterns
    closing_patterns = [
        r'(?:response date|closing date|due date|deadline|submission due)[\s:]+(\w+\s+\d{1,2},?\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*[AP]M\s*\w+)?)',
        r'(?:response date|closing date|due date|deadline|submission due)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(?:response date|closing date|due date|deadline|submission due)[\s:]+(\d{4}-\d{2}-\d{2})',
    ]
    
    for pattern in closing_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            closing_date = match.group(1).strip()
            break
    
    # Open/published date patterns - more comprehensive
    open_patterns = [
        r'(?:published date|open date|posted date|release date|issue date|posted on|published on|solicitation open|bid open|rfp open)[\s:]+(\w+\s+\d{1,2},?\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*[AP]M\s*\w+)?)',
        r'(?:published date|open date|posted date|release date|issue date|posted on|published on)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(?:published date|open date|posted date|release date|issue date|posted on|published on)[\s:]+(\d{4}-\d{2}-\d{2})',
        r'(?:effective date|start date|begin date)[\s:]+(\w+\s+\d{1,2},?\s+\d{4})',
        r'(?:effective date|start date|begin date)[\s:]+(\d{1,2}/\d{1,2}/\d{2,4})',
    ]
    
    for pattern in open_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            open_date = match.group(1).strip()
            break
    
    return closing_date, open_date


def extract_contact_email(text):
    """Extract contact email from text."""
    # Look for email patterns
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    return email_match.group(0) if email_match else ""


def extract_budget(text):
    """Extract budget information from text."""
    budget_patterns = [
        r'(?:budget|estimated|value|contract|amount|ceiling|total)[\s:]*\$[\d,]+(?:\.\d{2})?',
        r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:total|overall|aggregate))',
    ]
    
    for pattern in budget_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return ""


async def process_sam_gov_page(record, page, api_key):
    """Visit SAM.gov page, extract content, use NLP to summarize and classify."""
    url = record.get("details_url", "")
    if not url or not url.startswith("http"):
        return record

    try:
        # Navigate to page with longer timeout for SPA
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        
        # Wait for SPA content to load (SAM.gov is Angular-based)
        await page.wait_for_timeout(6000)
        
        # Try to wait for specific content indicators
        try:
            await page.wait_for_selector('app-root', timeout=10000)
        except:
            pass
        
        # Get full page text
        page_text = await page.evaluate("() => document.body.innerText")
        
        if not page_text or len(page_text) < 100:
            print(f"    Warning: Page text too short ({len(page_text)} chars)")
            return record
        
        # Find PDF links on the page
        pdf_links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.getAttribute('href');
                const text = a.innerText.trim().toLowerCase();
                if (href && (
                    href.includes('.pdf') ||
                    text.includes('pdf') ||
                    text.includes('attachment') ||
                    text.includes('document') ||
                    text.includes('solicitation')
                )) {
                    // Skip javascript: links
                    if (!href.startsWith('javascript:')) {
                        links.push(href.startsWith('http') ? href : new URL(href, window.location.origin).href);
                    }
                }
            });
            return [...new Set(links)].slice(0, 3);
        }""")

        # Try to download and read PDFs
        pdf_text = ""
        for pdf_url in pdf_links[:2]:
            try:
                tmp_path = download_pdf(pdf_url)
                if tmp_path:
                    text = extract_text_from_pdf(tmp_path)
                    if text and len(text) > 100 and "error" not in text.lower():
                        pdf_text += text[:4000] + "\n\n"
                    os.unlink(tmp_path)
            except Exception:
                pass

        # Use PDF text if available, otherwise use page text
        content_for_nlp = pdf_text if pdf_text else page_text
        has_pdf = bool(pdf_text)
        
        # Extract structured data from page text
        closing_date, open_date = extract_dates_from_text(page_text)
        contact_email = extract_contact_email(page_text)
        budget_text = extract_budget(page_text)
        
        # Extract description section if present
        description = ""
        desc_match = re.search(r'Description\s*\n(.*?)(?=\n(?:What|Contact|Attachment|$))', page_text, re.DOTALL | re.IGNORECASE)
        if desc_match:
            description = desc_match.group(1).strip()[:2000]
        
        # NLP summarization
        record["summary"] = nlp_summarize(record.get("title", ""), content_for_nlp, api_key)
        
        # NLP classification
        record["rfp_category"] = nlp_classify(record.get("title", ""), content_for_nlp, api_key)
        
        # Store full description
        record["description"] = description[:2000] if description else content_for_nlp[:2000]
        
        # Store PDF text
        record["pdf_text"] = pdf_text[:5000] if pdf_text else ""
        
        # Store extracted dates
        if closing_date:
            record["closing_date"] = closing_date
        if open_date:
            record["open_date"] = open_date
        
        # Store contact email
        record["contact_email"] = contact_email
        
        # Store budget
        record["budget_text"] = budget_text
        
        print(f"    PDF: {'YES' if has_pdf else 'NO'} | Summary: {record['summary'][:60]}...")

    except Exception as e:
        print(f"    Error: {str(e)[:80]}")

    return record


async def run_pdf_pipeline():
    """Run the full SAM.gov PDF reading pipeline."""
    import psycopg2
    from playwright.async_api import async_playwright

    api_key = os.environ.get('OPENROUTER_API_KEY', '')

    # Load SAM.gov records that don't have PDF text yet
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    cur.execute("""
        SELECT id, solicitation_id, name, source_portal, details_url, summary, rfp_category
        FROM tenders
        WHERE source_portal = 'SAM.gov'
        AND (pdf_text IS NULL OR pdf_text = '')
        ORDER BY first_seen DESC
    """)
    rows = cur.fetchall()
    conn.close()

    records = []
    for row in rows:
        records.append({
            '_db_id': row[0],
            'rfp_id': row[1],
            'title': row[2],
            'portal': row[3],
            'details_url': row[4],
            'summary': row[5] or '',
            'rfp_category': row[6] or '',
        })

    print(f"Processing {len(records)} SAM.gov RFPs with PDF reading...")
    print(f"NLP API: {'Connected' if api_key else 'NO API KEY'}")

    processed = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        for i, record in enumerate(records[:100]):  # Process first 100
            try:
                print(f"\n[{i+1}/{min(len(records),100)}] {record['title'][:60]}...")
                enriched = await process_sam_gov_page(record, page, api_key)

                # Update database
                conn = psycopg2.connect(os.environ['DATABASE_URL'])
                conn.autocommit = True
                cur = conn.cursor()
                cur.execute("""
                    UPDATE tenders SET
                        summary = %s,
                        rfp_category = %s,
                        full_description = COALESCE(NULLIF(%s, ''), full_description),
                        pdf_text = COALESCE(NULLIF(%s, ''), pdf_text),
                        contact_email = COALESCE(NULLIF(%s, ''), contact_email),
                        budget_text = COALESCE(NULLIF(%s, ''), budget_text),
                        open_date = COALESCE(%s, open_date),
                        closing_date = COALESCE(%s, closing_date)
                    WHERE id = %s
                """, [
                    enriched.get('summary', ''),
                    enriched.get('rfp_category', ''),
                    enriched.get('description', ''),
                    enriched.get('pdf_text', ''),
                    enriched.get('contact_email', ''),
                    enriched.get('budget_text', ''),
                    enriched.get('open_date') or None,
                    enriched.get('closing_date') or None,
                    record['_db_id'],
                ])
                conn.close()
                processed += 1

                if (i + 1) % 10 == 0:
                    print(f"\n  --- Processed {i+1} records ---")

            except Exception as e:
                print(f"    Error: {str(e)[:50]}")

        await browser.close()

    print(f"\nDone! Processed {processed} records with PDF reading and NLP summaries.")


if __name__ == "__main__":
    asyncio.run(run_pdf_pipeline())
