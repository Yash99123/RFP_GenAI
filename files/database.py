import psycopg2, psycopg2.extras, os
from contextlib import contextmanager
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
load_dotenv(Path("/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/.env"))

DATABASE_URL = os.environ.get("DATABASE_URL", "")

@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()

def query(sql: str, params=None) -> list[dict]:
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or [])
        return [dict(r) for r in cur.fetchall()]

def execute(sql: str, params=None):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or [])
