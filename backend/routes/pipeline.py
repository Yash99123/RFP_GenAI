from fastapi import APIRouter, BackgroundTasks
from database import query
import json, os, subprocess, time, psycopg2
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

router = APIRouter()

PROJECT_DIR = str(Path(__file__).parent.parent.parent)
SCRAPERS_DIR = os.path.join(PROJECT_DIR, "backend", "scrapers")
PYTHON = os.path.join(PROJECT_DIR, "venv", "bin", "python3")

# EITACIES scraper scripts
SCRAPER_SCRIPTS = {
    "scrape-sam-gov":            "sam_gov.py",
    "scrape-sap-ariba-jaggaer":  None,  # Not yet implemented
    "scrape-state-portals":      None,  # Not yet implemented
    "scrape-city-portals":       None,  # Not yet implemented
    "scrape-aggregators":        "aggregators.py",
}


def _get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _record_run(start_time, scraped=0, new_count=0, errors=None):
    elapsed = time.time() - start_time
    conn = _get_db()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pipeline_runs
            (run_at, total_scraped, new_after_dedup, errors, duration_seconds)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        datetime.utcnow(),
        scraped,
        new_count,
        errors,
        round(elapsed, 1),
    ))
    conn.close()


def _run_scraper(script_name=None):
    """Run a scraper script and return results."""
    start = time.time()

    if script_name:
        # Run single scraper
        scripts = [script_name]
    else:
        # Run all available scrapers
        scripts = [s for s in SCRAPER_SCRIPTS.values() if s]

    total_scraped = 0
    total_new = 0
    all_errors = []

    for script in scripts:
        script_path = os.path.join(SCRAPERS_DIR, script)
        if not os.path.exists(script_path):
            all_errors.append(f"Script not found: {script}")
            continue

        try:
            print(f"Running {script}...")
            result = subprocess.run(
                [PYTHON, script_path],
                capture_output=True, text=True, timeout=600,
                cwd=SCRAPERS_DIR,
                env={**os.environ, "PYTHONPATH": SCRAPERS_DIR},
            )

            output = result.stdout + result.stderr

            # Parse output for counts
            for line in output.split("\n"):
                if "Total scraped:" in line:
                    try:
                        count = int(line.split(":")[-1].strip())
                        total_scraped += count
                    except ValueError:
                        pass
                elif "New records:" in line:
                    try:
                        count = int(line.split(":")[-1].strip())
                        total_new += count
                    except ValueError:
                        pass

            if result.returncode != 0:
                err = output[-500:] if len(output) > 500 else output
                all_errors.append(f"{script}: {err}")

        except subprocess.TimeoutExpired:
            all_errors.append(f"{script}: timed out after 600s")
        except Exception as e:
            all_errors.append(f"{script}: {str(e)}")

    errors_str = "\n".join(all_errors) if all_errors else None
    _record_run(start, total_scraped, total_new, errors_str)

    return {
        "total_scraped": total_scraped,
        "new_after_dedup": total_new,
        "errors": all_errors,
    }


def run_full_pipeline():
    """Run all EITACIES portal scrapers."""
    return _run_scraper()


def run_skill(skill_name):
    """Run a single scraper skill."""
    script = SCRAPER_SCRIPTS.get(skill_name)
    if script:
        return _run_scraper(script)
    return {"error": f"No script for {skill_name}"}


@router.get("/runs")
def get_runs():
    rows = query("""
        SELECT id, run_at, total_scraped, new_after_dedup, excluded_count,
               crm_synced, errors, duration_seconds
        FROM pipeline_runs
        ORDER BY run_at DESC
        LIMIT 20
    """)
    for r in rows:
        if r.get("run_at"):
            r["run_at"] = r["run_at"].isoformat()
        if r.get("duration_seconds") is not None:
            r["duration_seconds"] = float(r["duration_seconds"])
    return rows


@router.get("/cron")
def get_cron_jobs():
    return {"jobs": []}


@router.post("/trigger")
def trigger_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_full_pipeline)
    return {
        "status": "triggered",
        "message": "Full pipeline started — scraping SAM.gov and Aggregators."
    }


@router.post("/trigger/{skill_name}")
def trigger_skill(skill_name: str, background_tasks: BackgroundTasks):
    allowed = list(SCRAPER_SCRIPTS.keys()) + ["rfp-report"]
    if skill_name not in allowed:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{skill_name}' not recognized. Use: {allowed}"
        )
    background_tasks.add_task(run_skill, skill_name)
    return {
        "status": "triggered",
        "skill": skill_name,
        "message": f"Running {skill_name}..."
    }


@router.post("/cron/{name}/pause")
def pause_cron(name: str):
    return {"status": "paused", "message": f"Paused {name}"}


@router.post("/cron/{name}/resume")
def resume_cron(name: str):
    return {"status": "resumed", "message": f"Resumed {name}"}
