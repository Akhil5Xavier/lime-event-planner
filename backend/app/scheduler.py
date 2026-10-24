import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.db import SessionLocal
from app.ingest import runner
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


def run_worker() -> None:
    """Blocking scheduler for the dedicated worker service; returns only on shutdown."""
    scheduler = BlockingScheduler(timezone=get_settings().timezone)
    _configure(scheduler)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler worker stopped")
