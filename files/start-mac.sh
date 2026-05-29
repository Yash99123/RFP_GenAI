#!/bin/bash
# EITACIES RFP GenAI Dashboard — Local Start Script (Mac)
set -e

PROJECT_DIR="/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI"
cd "$PROJECT_DIR"

echo ""
echo "  EITACIES RFP GenAI Dashboard"
echo "  ─────────────────────────────────"
echo ""

if ! command -v python3 &>/dev/null; then
  echo "  ERROR: Python 3 is not installed."
  echo "  Download from https://python.org and re-run."
  exit 1
fi

echo "  Installing dependencies..."
pip3 install --quiet fastapi "uvicorn[standard]" psycopg2-binary python-dotenv python-multipart

echo "  Testing database connection..."
cd "$PROJECT_DIR/backend"
python3 -c "
from database import query
try:
    r = query('SELECT COUNT(*) as n FROM tenders')
    print('  DB connected -- ' + str(r[0]['n']) + ' RFPs in database')
except Exception as e:
    print('  DB note: ' + str(e))
    print('  Run db-init.sql in Supabase if tables are missing')
"

echo ""
echo "  Starting server..."
echo ""
echo "  Open in browser: http://localhost:8000"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
