"""In-process daily job scheduler.

Runs the market-data daily update (D09 §6 — price fetch + indicator
snapshots + D06 alert engine) automatically once a day, instead of relying
on someone to trigger POST /market-data/daily-update by hand. There is no
Celery beat / worker in this deployment (BackgroundTasks replaced Celery for
the AI-analysis job; see D07), so this uses APScheduler's AsyncIOScheduler
inside the FastAPI process itself — started/stopped from main.py's lifespan.

Fire time is a fixed wall-clock hour in Europe/Madrid (not a UTC offset), so
it doesn't drift across the March/October DST changes.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

DAILY_UPDATE_HOUR_MADRID = 16  # 4pm Europe/Madrid

_scheduler: AsyncIOScheduler | None = None


async def _run_daily_update_job() -> None:
    from app.services.market_data.service import get_market_data_service

    logger.info("Scheduled daily market-data update starting.")
    try:
        async with AsyncSessionLocal() as db:
            summary = await get_market_data_service().run_daily_update(db)
        logger.info("Scheduled daily market-data update finished: %s", summary)
    except Exception:
        logger.exception("Scheduled daily market-data update failed.")


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="Europe/Madrid")
    _scheduler.add_job(
        _run_daily_update_job,
        trigger=CronTrigger(hour=DAILY_UPDATE_HOUR_MADRID, minute=0, timezone="Europe/Madrid"),
        id="daily_market_data_update",
        misfire_grace_time=3600,  # still run if the process was down at 16:00 (e.g. machine asleep), up to 1h late
        coalesce=True,            # if multiple fire times were missed, only run once on catch-up
    )
    _scheduler.start()
    logger.info("Scheduler started — daily market-data update at %02d:00 Europe/Madrid.", DAILY_UPDATE_HOUR_MADRID)
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
