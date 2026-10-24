import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingest import runner
from app.models import IngestRun
from app.schemas import IngestRunOut, SourceStatus
from app.security import require_admin

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"], dependencies=[Depends(require_admin)])


@router.get("/sources", response_model=list[SourceStatus])
def sources():
    return [SourceStatus(name=c.name, enabled=c.is_enabled()) for c in runner.all_connectors()]


@router.get("/runs", response_model=list[IngestRunOut])
def runs(limit: int = 50, db: Session = Depends(get_db)):
    return db.scalars(select(IngestRun).order_by(IngestRun.started_at.desc()).limit(min(limit, 200))).all()


def _run_manual():
    try:
        runner.run_ingestion(trigger="manual")
    except runner.IngestAlreadyRunning:
        log.info("Manual ingestion skipped: a run is already in progress")


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
def run_now(background: BackgroundTasks, db: Session = Depends(get_db)):
    if runner.is_running(db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An ingestion run is already in progress")
    if not any(c.is_enabled() for c in runner.all_connectors()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No data source is configured. Set TICKETMASTER_API_KEY.")
    background.add_task(_run_manual)
    return {"status": "started"}
