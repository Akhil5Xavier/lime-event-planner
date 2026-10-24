import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, events, health, ingest, users, venues
from app.config import get_settings
from app.observability import setup_logging, setup_sentry

settings = get_settings()
setup_logging(settings)
setup_sentry(settings)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.check_production()
    if settings.environment != "production" and settings.production_problems():
        log.warning("Development config in use (%s); not safe for production.",
                    "; ".join(settings.production_problems()))
    scheduler = None
    if settings.scheduler_enabled:
        from app.scheduler import start_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Lime Stuttgart Event Planner", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (health, auth, users, venues, events, ingest):
    app.include_router(module.router)
