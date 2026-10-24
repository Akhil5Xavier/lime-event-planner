import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import send_alert
from app.config import get_settings
from app.db import SessionLocal
from app.ingest.base import Connector
from app.ingest.predicthq import PredictHQConnector
from app.ingest.ticketmaster import TicketmasterConnector
from app.ingest.store import upsert_events
from app.models import IngestRun

log = logging.getLogger(__name__)

# Guards against overlapping runs inside one process. Across processes (API workers and
# the scheduler worker) the "running" rows in ingest_runs are checked as well.
_lock = threading.Lock()
# A "running" row older than this is assumed to be left over from a crashed process.
STALE_RUN_AFTER = timedelta(hours=2)


class IngestAlreadyRunning(Exception):
    pass


def _scrub(message: str) -> str:
    """Remove API credentials from error text (httpx errors include the request URL)."""
    s = get_settings()
    for secret in (s.ticketmaster_api_key, s.predicthq_token, s.llm_api_key):
        if secret:
            message = message.replace(secret, "***")
    return message


def all_connectors() -> list[Connector]:
    return [TicketmasterConnector(), PredictHQConnector()]


def _running_in_db(db: Session) -> bool:
    cutoff = datetime.now(timezone.utc) - STALE_RUN_AFTER
    return db.scalar(
        select(IngestRun.id).where(IngestRun.status == "running", IngestRun.started_at > cutoff).limit(1)
    ) is not None


def is_running(db: Session) -> bool:
    return _lock.locked() or _running_in_db(db)


def _alert_if_needed(run: IngestRun) -> None:
    if run.status == "failed":
        send_alert(f":warning: Lime event sync from *{run.source}* failed: {run.error}")
    elif run.fetched == 0:
        send_alert(f":warning: Lime event sync from *{run.source}* succeeded but found 0 events. "
                   "Check the API key and the source's status.")


def run_ingestion(
    trigger: str = "schedule",
    connectors: list[Connector] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> list[IngestRun]:
    """Fetch the next N days from every enabled connector. One IngestRun row per source.

    A failing connector is recorded as failed and does not stop the others.
    """
    if not _lock.acquire(blocking=False):
        raise IngestAlreadyRunning()
    try:
        settings = get_settings()
        start = datetime.now(timezone.utc) - timedelta(days=1)
        end = start + timedelta(days=settings.ingest_days_ahead + 1)
        enabled = [c for c in (connectors if connectors is not None else all_connectors()) if c.is_enabled()]

        # Create every run row up front so other processes see this sync as running throughout.
        with session_factory() as db:
            if _running_in_db(db):
                raise IngestAlreadyRunning()
            runs = [IngestRun(source=c.name, trigger=trigger) for c in enabled]
            db.add_all(runs)
            db.commit()

        finished: list[IngestRun] = []
        for connector, pending in zip(enabled, runs):
            with session_factory() as db:
                run = db.merge(pending)
                run.started_at = datetime.now(timezone.utc)
                db.commit()
                try:
                    events = connector.fetch(start, end)
                    run.fetched = len(events)
                    res = upsert_events(db, events)
                    run.created, run.updated, run.duplicates = res.created, res.updated, res.duplicates
                    run.status = "success"
                except Exception as exc:  # noqa: BLE001 - recorded on the run row
                    db.rollback()
                    log.exception("Ingestion from %s failed", connector.name)
                    run.status = "failed"
                    run.error = _scrub(f"{type(exc).__name__}: {exc}")[:2000]
                run.finished_at = datetime.now(timezone.utc)
                db.add(run)
                db.commit()
            log.info("Ingestion from %s: %s fetched=%s created=%s updated=%s duplicates=%s",
                     run.source, run.status, run.fetched, run.created, run.updated, run.duplicates)
            _alert_if_needed(run)
            finished.append(run)
        return finished
    finally:
        _lock.release()
