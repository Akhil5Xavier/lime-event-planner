"""Admin commands.

  python -m app.cli init-db                      apply migrations and seed Stuttgart venues
  python -m app.cli create-user EMAIL [--role admin|manager] [--name NAME]
  python -m app.cli ingest                       run ingestion once, now
  python -m app.cli scheduler                    run the nightly sync scheduler (worker service)
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import User
from app.security import hash_password
from app.seed.venues import seed_venues

BACKEND_DIR = Path(__file__).resolve().parent.parent


def init_db() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        added = seed_venues(db)
        admin = bootstrap_admin(db)
    print(f"Database ready. Seeded {added} new venue(s).")
    if admin:
        print(f"Created first admin {admin} from ADMIN_EMAIL / ADMIN_PASSWORD.")


def bootstrap_admin(db) -> str | None:
    """Create the first admin from settings, but only while there are no users at all.

    Once any user exists this does nothing, so changing ADMIN_PASSWORD later never resets a
    password, and deleting the variables after the first start is safe.
    """
    from app.config import get_settings

    s = get_settings()
    if not s.admin_email or not s.admin_password:
        return None
    if db.scalar(select(func.count()).select_from(User)):
        return None
    if len(s.admin_password) < 8:
        print("ADMIN_PASSWORD must be at least 8 characters; no admin created.", file=sys.stderr)
        return None
    email = s.admin_email.strip().lower()
    db.add(User(email=email, name="Admin", role="admin", password_hash=hash_password(s.admin_password)))
    db.commit()
    return email


def create_user(email: str, role: str, name: str | None) -> None:
    # Allow non-interactive use (e.g. container setup) via env var.
    password = os.environ.get("LIME_USER_PASSWORD") or getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(func.lower(User.email) == email.lower())):
            sys.exit(f"User {email} already exists.")
        db.add(User(email=email.lower(), name=name, role=role, password_hash=hash_password(password)))
        db.commit()
    print(f"Created {role} {email}.")


def ingest() -> None:
    from app.ingest.runner import IngestAlreadyRunning, run_ingestion

    try:
        runs = run_ingestion(trigger="cli")
    except IngestAlreadyRunning:
        sys.exit("A sync is already running. Try again when it has finished.")
    if not runs:
        print("No data source configured (set TICKETMASTER_API_KEY and/or PREDICTHQ_TOKEN).")
    for r in runs:
        print(f"{r.source}: {r.status} fetched={r.fetched} created={r.created} "
              f"updated={r.updated} duplicates={r.duplicates} {r.error or ''}")


def scheduler() -> None:
    from app.config import get_settings
    from app.observability import setup_logging, setup_sentry
    from app.scheduler import run_worker

    settings = get_settings()
    settings.check_production()
    setup_logging(settings)
    setup_sentry(settings)
    run_worker()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    cu = sub.add_parser("create-user")
    cu.add_argument("email")
    cu.add_argument("--role", choices=["admin", "manager"], default="manager")
    cu.add_argument("--name")
    sub.add_parser("ingest")
    sub.add_parser("scheduler")
    args = parser.parse_args()

    if args.cmd == "init-db":
        init_db()
    elif args.cmd == "create-user":
        create_user(args.email, args.role, args.name)
    elif args.cmd == "ingest":
        ingest()
    elif args.cmd == "scheduler":
        scheduler()


if __name__ == "__main__":
    main()
