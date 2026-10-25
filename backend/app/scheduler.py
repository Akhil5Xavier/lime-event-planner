import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.ingest import runner
from app.models import IngestRun
from app.services.cleanup import purge_old_events

log = logging.getLogger(__name__)


def nightly_job():
    try:
        runner.run_ingestion(trigger="schedule")
    except runner.IngestAlreadyRunning:
        log.info("Scheduled ingestion skipped: a run is already in progress")
    with SessionLocal() as db:
        deleted = purge_old_events(db, get_settings().event_retention_days)
    if deleted:
        log.info("Deleted %s events past the retention period", deleted)


def _configure(scheduler: BaseScheduler) -> None:
    settings = get_settings()
    scheduler.add_job(
        nightly_job,
        CronTrigger.from_crontab(settings.ingest_cron, timezone=settings.timezone),
        id="ingest",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    log.info("Ingestion scheduled with cron '%s' (%s)", settings.ingest_cron, settings.timezone)


def start_scheduler() -> BackgroundScheduler:
    """In-process scheduler for development (SCHEDULER_ENABLED=true)."""
    scheduler = BackgroundScheduler(timezone=get_settings().timezone)
    _configure(scheduler)
    scheduler.start()
    return scheduler


def needs_catch_up(session_factory=SessionLocal) -> bool:
    """True when a data source is configured but no sync succeeded within INGEST_MAX_AGE_HOURS,
    e.g. a brand-new install or a worker that was down overnight."""
    if not any(c.is_enabled() for c in runner.all_connectors()):
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=get_settings().ingest_max_age_hours)
    with session_factory() as db:
        recent = db.scalar(
            select(IngestRun.id).where(IngestRun.status == "success", IngestRun.finished_at > cutoff).limit(1)
        )
    return recent is None


def run_worker() -> None:
    """Blocking scheduler for the dedicated worker service; returns only on shutdown."""
    scheduler = BlockingScheduler(timezone=get_settings().timezone)
    _configure(scheduler)
    if needs_catch_up():
        # Don't leave a fresh install with an empty calendar until 03:00.
        log.info("No recent successful sync; running one now")
        scheduler.add_job(nightly_job, id="catch-up")  # no trigger = run once, right away
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler worker stopped")
