from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import Event


def purge_old_events(db: Session, retention_days: int) -> int:
    """Delete events that ended more than `retention_days` ago. Returns how many were deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    old_ids = list(db.scalars(
        select(Event.id).where(
            or_(Event.end_at < cutoff, Event.end_at.is_(None) & (Event.start_at < cutoff))
        )
    ))
    if not old_ids:
        return 0
    # Newer duplicates may still point at an old primary; remove them first so the FK holds.
    dup_count = db.execute(
        delete(Event).where(Event.duplicate_of_id.in_(old_ids), Event.id.not_in(old_ids))
    ).rowcount
    count = db.execute(delete(Event).where(Event.id.in_(old_ids))).rowcount
    db.commit()
    return count + dup_count
