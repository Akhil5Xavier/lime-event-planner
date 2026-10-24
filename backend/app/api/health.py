"""Unauthenticated health endpoints for container healthchecks and uptime monitors."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.ingest import runner
from app.models import IngestRun

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def health(db: Session = Depends(get_db)):
    """The API is up and can reach the database."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB failure means unhealthy
        return JSONResponse(status_code=503, content={"status": "error", "database": "unreachable"})
    return {"status": "ok", "database": "ok"}


@router.get("/ingest")
def ingest_health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Unhealthy (503) when no data source is configured or the last successful sync is too old."""
    if not any(c.is_enabled() for c in runner.all_connectors()):
        return JSONResponse(status_code=503, content={"status": "error", "reason": "no data source configured"})
    last = db.scalar(
        select(IngestRun.finished_at)
        .where(IngestRun.status == "success")
        .order_by(IngestRun.finished_at.desc())
        .limit(1)
    )
    max_age = timedelta(hours=settings.ingest_max_age_hours)
    body = {"last_success": last.isoformat() if last else None, "max_age_hours": settings.ingest_max_age_hours}
    if last is None or datetime.now(timezone.utc) - last > max_age:
        return JSONResponse(status_code=503, content={"status": "stale", **body})
    return {"status": "ok", **body}
