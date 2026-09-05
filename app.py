import json
import shutil
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException, BackgroundTasks
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse, JSONResponse
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field

from scraper import (
    fetch_problem,
    Platform,
    Problem,
    JsonProblemStore,
    ContinuousExtractor
)

app = FastAPI(
    title="Coding Question Extractor API",
    description="Continuous JSON question extraction for LeetCode & HackerRank with zero duplicates",
    version="2.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to the single unified questions.json dataset
DATASET_PATH = Path("questions.json").resolve()

# Shared JSON Problem Store and Continuous Extractor
store = JsonProblemStore(file_path=DATASET_PATH)
extractor = ContinuousExtractor(store=store, delay_seconds=0.8)

class StartRequest(BaseModel):
    delay: Optional[float] = Field(0.8, description="Delay between requests in seconds")

class FetchRequest(BaseModel):
    query: str = Field(..., description="Problem URL or slug (e.g., 'two-sum')")
    platform: Optional[str] = Field("auto", description="'auto', 'leetcode', or 'hackerrank'")

@app.post("/api/extractor/start")
async def start_extractor(req: Optional[StartRequest] = None):
    """
    Start continuous pulling of questions into questions.json.
    """
    if req and req.delay:
        extractor.delay_seconds = max(0.2, req.delay)

    started = extractor.start()
    return {
        "success": True,
        "already_running": not started,
        "state": extractor.get_state()
    }

@app.post("/api/extractor/stop")
async def stop_extractor():
    """
    Stop continuous pulling of questions.
    """
    stopped = extractor.stop()
    return {
        "success": True,
        "already_stopped": not stopped,
        "state": extractor.get_state()
    }

@app.get("/api/extractor/status")
async def get_extractor_status():
    """
    Get real-time status, counters, current action, and recently pulled questions.
    """
    return extractor.get_state()

@app.get("/api/questions")
async def get_all_questions(offset: int = 0, limit: int = 50, summary_only: bool = False):
    """
    Returns questions stored in questions.json.
    """
    all_probs = store.get_all()
    total = len(all_probs)
    sliced = all_probs[offset: offset + limit]

    if summary_only:
        items = [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "slug": p.get("slug"),
                "platform": p.get("platform"),
                "difficulty": p.get("difficulty"),
                "url": p.get("url"),
                "tags": p.get("tags", []),
            }
            for p in sliced
        ]
    else:
        items = sliced

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "questions": items,
        "stats": store.get_stats()
    }

@app.get("/api/questions/download")
async def download_questions_json():
    """
    Download the single unified questions.json dataset file.
    """
    store.save()
    return FileResponse(
        path=str(store.file_path),
        filename="questions.json",
        media_type="application/json",
        headers={
            "X-Total-Questions": str(len(store.problems)),
            "X-Dataset-File": str(store.file_path)
        }
    )

@app.post("/api/questions/save")
@app.post("/api/questions/save-to-problems")
async def save_dataset_file():
    """
    Saves and flushes questions into the single questions.json file.
    """
    store.save()
    return {
        "success": True,
        "file": str(store.file_path),
        "total_questions": len(store.problems)
    }

@app.delete("/api/questions")
async def clear_questions():
    """
    Reset questions.json and deduplication index.
    """
    if extractor.is_running:
        extractor.stop()
    store.clear()
    return {"success": True, "message": "questions.json has been reset", "stats": store.get_stats()}

@app.post("/api/fetch")
async def api_fetch_single_problem(req: FetchRequest):
    """
    Optionally fetch and save an individual problem by URL or slug into questions.json.
    """
    cleaned = req.query.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
        prob = fetch_problem(cleaned, platform=req.platform)
        added = store.add_problem(prob)
        return {
            "problem": prob.model_dump(),
            "added_to_json": added,
            "was_duplicate": not added,
            "stats": store.get_stats()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
async def serve_index():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"message": "Coding Question Extractor API running."})

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
