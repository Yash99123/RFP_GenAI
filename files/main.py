from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime
from routes import tenders, pipeline, queue, stats

app = FastAPI(title="Entro Tender Automation", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tenders.router, prefix="/api/tenders",  tags=["Tenders"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["Pipeline"])
app.include_router(queue.router,    prefix="/api/queue",    tags=["Queue"])
app.include_router(stats.router,    prefix="/api/stats",    tags=["Stats"])

frontend_dir = Path("/Users/yasha/Downloads/RFP_Automation_System/RFP GenAI/frontend")
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
