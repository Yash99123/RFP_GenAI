---
name: rfp-schema
description: Defines the canonical RFP data schema for EITACIES RFP GenAI pipeline. Normalises all scraped data from 50+ portals into a consistent format. Load this skill before parsing any raw scraper output.
version: 1.0.0
metadata:
  hermes:
    tags: [eitacies, rfp, schema]
    category: automation
---

# RFP Schema — EITACIES RFP GenAI

## When to Use
Load before parsing any scraped data. This is the single source of truth for all field names.

## Canonical Schema

Every parsed RFP record MUST be a JSON object with these exact fields:

```json
{
  "rfp_id":              "<string> — unique ID from source portal. PRIMARY DEDUP KEY",
  "title":               "<string> — full RFP/solicitation title",
  "agency":              "<string> — issuing organisation / government body",
  "portal":              "<string> — source portal name (see allowed values below)",
  "portal_category":     "<string> — Federal | State | City | Aggregator | Education | Niche",
  "due_date":            "<ISO 8601 YYYY-MM-DD> — submission deadline",
  "posted_date":         "<ISO 8601 YYYY-MM-DD or null>",
  "questions_deadline":  "<ISO 8601 YYYY-MM-DD or null>",

  "state":               "<US state abbreviation e.g. CA, TX, FL or null>",
  "city":                "<city name or null>",
  "country":             "<US | Canada | Other>",
  "location_text":       "<raw location string from portal>",

  "naics_code":          "<string NAICS code or null>",
  "set_aside":           "<Small Business | 8(a) | WOSB | HUBZone | SDVOSB | None | null>",
  "contract_type":       "<Firm Fixed Price | T&M | Cost Plus | IDIQ | BPA | Other | null>",
  "contract_value":      "<number in USD or null>",
  "contract_value_text": "<raw budget string from portal>",
  "period_of_performance": "<string e.g. 12 months or null>",

  "category":            "<one of allowed values below>",
  "keywords_matched":    "<array of matched keywords from scoring>",

  "details_url":         "<string URL — direct link to RFP on portal>",
  "pdf_urls":            "<array of Cloudflare R2 URLs for downloaded attachments>",

  "description":         "<string — 2-3 sentence plain-English summary>",
  "evaluation_criteria": "<string — how bids will be scored, if found>",
  "contact_name":        "<string or null>",
  "contact_email":       "<string or null>",

  "_score":              "<integer 0-100 — internal relevance score, not synced to CRM>",
  "_tier":               "<Tier 1 - Pursue | Tier 2 - Prospect | Tier 3 - Monitor | Tier 4 - Skip>",
  "_flags":              "<array of flag strings>",
  "_red_flags":          "<array of red flag strings>",
  "_exclude":            "<true | false — if true, do not sync to CRM>"
}
```

## Allowed Portal Names
SAM.gov, SAP Ariba, JAGGAER, BidNet Direct, BidPrime, Bonfire, OpenGov,
CAL eProcure, MyFlorida, PRISM, Florida ProRFX, Louisiana LaGov, CommBuys,
Vermont Procurement, Planet Bids, Central Bidding, Public Purchase,
Unison Marketplace, RFP Delivery, RFP Mart, Covendis, Ingram,
University of Iowa, University of Minnesota, Chicago Public Schools,
City of Los Angeles, LA Unified School District, City of Burbank,
City of Sunnyvale, Angeleno RAMP, City of Cincinnati, Broward County,
Texas DOT, TIPS, Delano, Falmouth, City of Ashland Oregon,
CivicPlus, Bids and Tenders, Kawartha Lakes, City of Waterloo,
Vendor Registry, Vendor Registry Okaloosa, EI Cooperative Services,
Pacific Northwest, Montana EMACS, SupplierClearinghouse, USDA, Other

## Allowed Category Values
AI / Machine Learning, Software Development, IT Infrastructure,
Cloud Services, Cybersecurity, Data Analytics, Consulting / Advisory,
Training & Education, Research & Development, Professional Services,
Healthcare IT, Financial Technology, Digital Transformation,
Network / Telecom, Other Technology

## EITACIES Core Keywords (must match at least one to score above 0)
Primary (high score): artificial intelligence, machine learning, AI, deep learning,
  natural language processing, NLP, computer vision, generative AI, LLM,
  predictive analytics, data science, automation, robotic process automation, RPA

Secondary (medium score): software development, cloud computing, SaaS, platform,
  digital transformation, data analytics, business intelligence, cybersecurity,
  IT modernisation, IT modernization, enterprise software, API, integration

Tertiary (low score): consulting, advisory, professional services, training,
  IT services, managed services, technical support, helpdesk

## Date Normalisation Rules
- All dates MUST be ISO 8601: YYYY-MM-DD
- If time is included: extract date only
- Common formats: "Jan 15, 2026" → "2026-01-15" | "01/15/2026" → "2026-01-15"
- If year is missing, assume current year

## Extraction Rules
1. Output ONLY valid JSON array — no prose, no markdown fences
2. Required minimum fields: rfp_id, title, agency, portal, due_date, details_url
3. If rfp_id not found: construct as [PORTAL_SLUG]-[YYYYMMDD]-[TITLE_SLUG_15CHARS]
4. description: write your own 2-3 sentence summary — do not copy verbatim
5. Parse PDF attachments via pdfplumber to fill missing fields (especially NAICS, value, eval criteria)
6. country defaults to "US" unless clearly Canadian

## Verification Before Downstream
- All records valid JSON
- No record missing rfp_id, title, or portal
- All dates ISO 8601
- country field populated on every record
