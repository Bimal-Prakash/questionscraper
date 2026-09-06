"""FastAPI application - the public read API and the extractor's control panel.

Every read endpoint serves from the database (Neon Postgres in production,
SQLite locally), so they are fast and safe to call on every keystroke. The
mutating endpoints only start or stop background work, and require
`X-Admin-Token` whenever ADMIN_TOKEN is set.

Handlers are declared `def`, not `async def`: the storage layer and the scraper
are synchronous, so FastAPI runs each one in its threadpool instead of blocking
the event loop on a database round-trip.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

# pyrefly: ignore [missing-import]
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field

from config import settings
from db import describe_database, dispose_db, healthcheck, init_db
from scraper import ContinuousExtractor, DbProblemStore, fetch_problem

logger = logging.getLogger(__name__)

VERSION = "3.0.0"

# Built in the lifespan handler: importing this module must not open a database
# connection, or `--reload` and the test collector both pay for one.
store: Optional[DbProblemStore] = None
extractor: Optional[ContinuousExtractor] = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global store, extractor

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    init_db()

    store = DbProblemStore()
    extractor = ContinuousExtractor(store=store, delay_seconds=settings.extract_delay_seconds)
    logger.info(
        "Serving %s question(s) from %s", store.count(), describe_database()
    )

    if settings.extract_on_startup:
        extractor.start()

    yield

    if extractor is not None:
        extractor.stop()
    dispose_db()


app = FastAPI(
    title=settings.app_name,
    description=(
        "Coding question dataset for LeetCode & HackerRank. Questions are "
        "harvested on a schedule into Postgres; every read endpoint serves "
        "from that store, with zero duplicates guaranteed by the database."
    ),
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    # For frontends on rotating hostnames (preview deploys). Ignored when empty.
    allow_origin_regex=settings.cors_origin_regex or None,
    # Credentials cannot be combined with a wildcard origin per the CORS spec;
    # browsers reject that pairing outright.
    allow_credentials=bool(settings.cors_origins),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)


# --------------------------------------------------------------- plumbing
def get_store() -> DbProblemStore:
    if store is None:  # pragma: no cover - only before lifespan has run
        raise HTTPException(status_code=503, detail="Service still starting up.")
    return store


def get_extractor() -> ContinuousExtractor:
    if extractor is None:  # pragma: no cover - only before lifespan has run
        raise HTTPException(status_code=503, detail="Service still starting up.")
    return extractor


def require_admin(x_admin_token: str = Header(default="")) -> None:
    """Gate the mutating endpoints.

    No token configured means no check, which is what local development wants.
    Every deployed environment sets one - the extractor makes outbound requests
    to LeetCode and HackerRank from your host, so an open Start button is
    someone else's rate limit to burn.
    """
    if not settings.admin_token:
        return
    if x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Admin-Token header.",
        )


class StartRequest(BaseModel):
    delay: Optional[float] = Field(None, description="Delay between requests in seconds")


class FetchRequest(BaseModel):
    query: str = Field(..., description="Problem URL or slug (e.g., 'two-sum')")
    platform: Optional[str] = Field("auto", description="'auto', 'leetcode', or 'hackerrank'")


# ------------------------------------------------------------------ meta
@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness plus the two facts worth alerting on."""
    db_ok = healthcheck()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": VERSION,
        "database": db_ok,
        "database_target": describe_database(),
        "environment": settings.environment,
        # The dashboard shows its admin-token field only when this is true.
        "admin_token_required": bool(settings.admin_token),
        "extractor_running": bool(extractor and extractor.is_running),
        "total_questions": store.count() if (store and db_ok) else 0,
    }


@app.get("/api/stats")
def get_stats(db: DbProblemStore = Depends(get_store)) -> dict[str, Any]:
    return db.get_stats()


# ------------------------------------------------------------- extractor
@app.post("/api/extractor/start", dependencies=[Depends(require_admin)])
def start_extractor(
    req: Optional[StartRequest] = None,
    ext: ContinuousExtractor = Depends(get_extractor),
) -> dict[str, Any]:
    """Start continuously pulling questions into the database."""
    if req and req.delay:
        ext.delay_seconds = max(0.2, req.delay)

    started = ext.start()
    return {"success": True, "already_running": not started, "state": ext.get_state()}


@app.post("/api/extractor/stop", dependencies=[Depends(require_admin)])
def stop_extractor(ext: ContinuousExtractor = Depends(get_extractor)) -> dict[str, Any]:
    """Stop the continuous pull."""
    stopped = ext.stop()
    return {"success": True, "already_stopped": not stopped, "state": ext.get_state()}


@app.get("/api/extractor/status")
def get_extractor_status(ext: ContinuousExtractor = Depends(get_extractor)) -> dict[str, Any]:
    """Live status, counters, current action, and recently pulled questions."""
    return ext.get_state()


# -------------------------------------------------------------- questions
@app.get("/api/questions")
def get_all_questions(
    offset: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1),
    platform: Optional[str] = Query(None, description="leetcode | hackerrank"),
    difficulty: Optional[str] = Query(None, description="Easy | Medium | Hard"),
    tag: Optional[str] = Query(None, description="Exact topic tag, e.g. 'Array'"),
    q: Optional[str] = Query(None, description="Substring match on title or slug"),
    summary_only: bool = False,
    db: DbProblemStore = Depends(get_store),
) -> dict[str, Any]:
    """One page of stored questions, filtered."""
    page_size = min(limit or settings.default_page_size, settings.max_page_size)
    total, items = db.query(
        offset=offset,
        limit=page_size,
        platform=platform,
        difficulty=difficulty,
        tag=tag,
        search=q,
        summary_only=summary_only,
    )
    return {
        "total": total,
        "offset": offset,
        "limit": page_size,
        "questions": items,
        "stats": db.get_stats(),
    }


@app.get("/api/questions/download")
def download_questions_json(db: DbProblemStore = Depends(get_store)) -> StreamingResponse:
    """The whole dataset as one questions.json download.

    Streamed row by row rather than serialised in one go: the full export is
    tens of megabytes of problem statements, and the free instance has 512MB.
    """

    def rows() -> Iterator[str]:
        yield "[\n"
        first = True
        for item in db.iter_all():
            prefix = "" if first else ",\n"
            first = False
            yield prefix + json.dumps(item, ensure_ascii=False, indent=2)
        yield "\n]\n"

    return StreamingResponse(
        rows(),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="questions.json"',
            "X-Total-Questions": str(db.count()),
        },
    )


@app.post("/api/questions/save")
@app.post("/api/questions/save-to-problems")
def save_dataset_file(db: DbProblemStore = Depends(get_store)) -> dict[str, Any]:
    """No-op kept for the dashboard: every question is committed as it arrives."""
    return {"success": True, "storage": describe_database(), "total_questions": db.count()}


@app.delete("/api/questions", dependencies=[Depends(require_admin)])
def clear_questions(
    db: DbProblemStore = Depends(get_store),
    ext: ContinuousExtractor = Depends(get_extractor),
) -> dict[str, Any]:
    """Delete every stored question and reset the catalogue cursor."""
    if ext.is_running:
        ext.stop()
    db.clear()
    ext.lc_skip = 0
    ext.hr_offset = 0
    ext.hr_track_index = 0
    return {"success": True, "message": "All questions deleted", "stats": db.get_stats()}


@app.get("/api/questions/{platform}/{slug}")
def get_question(
    platform: str, slug: str, db: DbProblemStore = Depends(get_store)
) -> dict[str, Any]:
    """A single stored question, in full."""
    found = db.get_by_slug(platform, slug)
    if not found:
        raise HTTPException(status_code=404, detail=f"No stored question {platform}/{slug}")
    return found


@app.post("/api/fetch", dependencies=[Depends(require_admin)])
def api_fetch_single_problem(
    req: FetchRequest, db: DbProblemStore = Depends(get_store)
) -> dict[str, Any]:
    """Fetch one problem by URL or slug and store it."""
    cleaned = req.query.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
        prob = fetch_problem(cleaned, platform=req.platform)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    added = db.add_problem(prob)
    return {
        "problem": prob.model_dump(mode="json"),
        "added": added,
        "was_duplicate": not added,
        "stats": db.get_stats(),
    }


# ----------------------------------------------------------------- static
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def serve_index():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"message": "Coding Question Extractor API running.", "docs": "/docs"})


if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn

    uvicorn.run("app:app", host=settings.api_host, port=settings.api_port, reload=True)
