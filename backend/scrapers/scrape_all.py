"""
Master Scraper with Detail Extraction — EITACIES RFP GenAI
Scrapes all portals, enriches with PDF reading, stores in PostgreSQL.
"""
import asyncio
import json
import os
import sys
import psycopg2
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

PROJECT_DIR = Path(__file__).parent.parent.parent
EXPORT_DIR = PROJECT_DIR / "exports" / "raw"


def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def store_tenders(records):
    """Store enriched records in the tenders table with dedup."""
    if not records:
        return 0, 0

    conn = get_db()
    conn.autocommit = True
    cur = conn.cursor()

    new_count = 0
    dupe_count = 0

    for rec in records:
        solicitation_id = rec.get("rfp_id", "")
        if not solicitation_id:
            continue

        cur.execute("SELECT id FROM tenders WHERE solicitation_id = %s", [solicitation_id])
        if cur.fetchone():
            # Update existing record with new info
            try:
                cur.execute("""
                    UPDATE tenders SET
                        summary = COALESCE(NULLIF(%s, ''), summary),
                        rfp_category = COALESCE(NULLIF(%s, ''), rfp_category),
                        full_description = COALESCE(NULLIF(%s, ''), full_description),
                        pdf_text = COALESCE(NULLIF(%s, ''), pdf_text),
                        contact_name = COALESCE(NULLIF(%s, ''), contact_name),
                        contact_email = COALESCE(NULLIF(%s, ''), contact_email),
                        budget_text = COALESCE(NULLIF(%s, ''), budget_text),
                        open_date = COALESCE(%s, open_date)
                    WHERE solicitation_id = %s
                """, [
                    rec.get("summary", ""),
                    rec.get("rfp_category", ""),
                    rec.get("description", ""),
                    rec.get("pdf_text", ""),
                    rec.get("contact_name", ""),
                    rec.get("contact_email", ""),
                    rec.get("budget_text", ""),
                    rec.get("open_date") or None,
                    solicitation_id,
                ])
            except Exception as e:
                print(f"  DB update error for {solicitation_id}: {e}")
            dupe_count += 1
            continue

        try:
            cur.execute("""
                INSERT INTO tenders (
                    solicitation_id, name, source_portal, end_client, sector,
                    closing_date, office, country, details_url, description,
                    summary, rfp_category, full_description, pdf_text,
                    contact_name, contact_email, budget_text, open_date,
                    first_seen, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [
                solicitation_id,
                rec.get("title", ""),
                rec.get("portal", ""),
                rec.get("agency", ""),
                rec.get("sector", ""),
                rec.get("closing_date") or None,
                rec.get("office", ""),
                rec.get("country", "US"),
                rec.get("details_url", ""),
                rec.get("description", ""),
                rec.get("summary", ""),
                rec.get("rfp_category", "Other Technology"),
                rec.get("description", ""),
                rec.get("pdf_text", ""),
                rec.get("contact_name", ""),
                rec.get("contact_email", ""),
                rec.get("budget_text", ""),
                rec.get("open_date") or None,
                datetime.utcnow(),
                "new",
            ])
            new_count += 1
        except Exception as e:
            print(f"  DB insert error for {solicitation_id}: {e}")

    conn.close()
    return new_count, dupe_count


def record_pipeline_run(scraped, new, errors=None, duration=0):
    """Record a pipeline run."""
    conn = get_db()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pipeline_runs (run_at, total_scraped, new_after_dedup, errors, duration_seconds)
        VALUES (%s, %s, %s, %s, %s)
    """, [datetime.utcnow(), scraped, new, errors, duration])
    conn.close()


def load_existing_records():
    """Load existing records from DB that need enrichment."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT solicitation_id, name, source_portal, end_client, details_url, description
        FROM tenders
        WHERE (summary IS NULL OR summary = '') AND details_url IS NOT NULL AND details_url != ''
        LIMIT 100
    """)
    rows = cur.fetchall()
    conn.close()

    records = []
    for row in rows:
        records.append({
            "rfp_id": row[0],
            "title": row[1],
            "portal": row[2],
            "agency": row[3],
            "details_url": row[4],
            "description": row[5] or "",
        })
    return records


async def run_all_scrapers():
    """Run ALL scrapers and return combined results."""
    from sam_gov import scrape_sam_gov
    from enterprise import scrape_enterprise
    from city_portals import scrape_city_portals
    from aggregators import scrape_aggregators
    from cal_eprocure import scrape_cal_eprocure
    from bonfire_scraper import scrape_all_bonfire_portals
    from la_county_scraper import scrape_la_county
    from montana_emacs_scraper import scrape_montana_emacs
    from tips_usa_scraper import scrape_tips_usa
    from planetbids_scraper import scrape_all_planetbids
    from ramp_la_scraper import scrape_rampla

    all_results = []

    scrapers = [
        ("SAM.gov (Federal)", scrape_sam_gov),
        ("Enterprise (Montana EMACS, Iowa, ProRFX)", scrape_enterprise),
        ("City Portals", scrape_city_portals),
        ("Aggregators (BidNet, Bonfire)", scrape_aggregators),
        ("Cal eProcure (California)", scrape_cal_eprocure),
        ("Bonfire (Texas DOT, CPS, Roswell, PennBID)", scrape_all_bonfire_portals),
        ("LA County", scrape_la_county),
        ("Montana EMACS (SciQuest)", scrape_montana_emacs),
        ("TIPS USA", scrape_tips_usa),
        ("PlanetBids (Burbank, Fresno, etc)", scrape_all_planetbids),
        ("RAMP LA (LAFPP / City of LA)", scrape_rampla),
    ]

    for name, scraper_fn in scrapers:
        print(f"\n{'='*60}")
        print(f"SCRAPER: {name}")
        print(f"{'='*60}")
        try:
            results = await scraper_fn()
            all_results.extend(results)
            print(f"  ✓ {name}: {len(results)} records")
        except Exception as e:
            print(f"  ✗ {name} FAILED: {str(e)[:100]}")

    return all_results


def main():
    """Main entry point."""
    start_time = datetime.utcnow()
    print("\n" + "=" * 60)
    print("EITACIES RFP GenAI — FULL PIPELINE WITH DETAIL EXTRACTION")
    print(f"Started: {start_time.isoformat()}")
    print("=" * 60)

    # Step 1: Run scrapers to get basic records
    print("\n--- STEP 1: Scraping portals ---")
    all_results = asyncio.run(run_all_scrapers())

    # Step 2: Store basic records
    print("\n--- STEP 2: Storing basic records ---")
    new_count, dupe_count = store_tenders(all_results)
    print(f"  New: {new_count}, Updated: {dupe_count}")

    # Step 3: Enrich records with detail extraction
    print("\n--- STEP 3: Extracting details from RFP pages ---")
    existing = load_existing_records()
    if existing:
        print(f"  Found {len(existing)} records needing enrichment")
        from extractor import enrich_all_records
        enriched = asyncio.run(enrich_all_records(existing, max_records=50))

        # Store enriched data
        print("\n--- STEP 4: Storing enriched data ---")
        enriched_new, enriched_updated = store_tenders(enriched)
        print(f"  Enriched: {enriched_updated} records updated")

    # Record pipeline run
    duration = (datetime.utcnow() - start_time).total_seconds()
    record_pipeline_run(len(all_results), new_count, duration=duration)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Total scraped:  {len(all_results)}")
    print(f"  New records:    {new_count}")
    print(f"  Duration:       {duration:.1f}s")

    portal_counts = {}
    for rec in all_results:
        portal = rec.get("portal", "Unknown")
        portal_counts[portal] = portal_counts.get(portal, 0) + 1
    print(f"\n  By portal:")
    for portal, count in sorted(portal_counts.items(), key=lambda x: -x[1]):
        print(f"    {portal}: {count}")

    print(f"\n  Dashboard: http://localhost:8000")


if __name__ == "__main__":
    main()
